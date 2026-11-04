import os
import re
import hashlib
import logging
import threading
import warnings
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Depends, Header, Request
from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from cortex.app.core import security
from cortex.app.core.database import get_db
from cortex.app.core.models import PredictionAudit
from cortex.app.engine.artifacts import load_inference_model, load_scaler
from cortex.app.engine.auditor import calculate_trust_label
from cortex.app.engine.fetcher import fetch_data, fetch_latest_rates, history_window_days
from cortex.app.engine.model import WINDOW_SIZE
from cortex.app.schemas.forecast import PredictionRequest, SUPPORTED_CURRENCIES

# Suppress cosmetic warnings from models trained before naming fix
warnings.filterwarnings("ignore", message="The structure of `inputs` doesn't match")
warnings.filterwarnings("ignore", category=UserWarning, module="sklearn")

router = APIRouter()
logger = logging.getLogger("cortex.api")

MODEL_CACHE = {}
MODEL_DIR = "/app/cortex/models"
_PAIR_CODE = re.compile(r"EUR_[A-Z]{3}")

# Keras models are shared objects and predict() is not documented as safe
# under concurrent calls. FastAPI runs sync endpoints in a threadpool, so
# two requests can reach inference at once; this lock serialises model
# loading and the autoregressive loop. Requests still overlap for network
# fetches and everything else.
_MODEL_LOCK = threading.Lock()

# Forecasts only change when ECB publishes a new reference rate (once per
# business day), and inference is deterministic, so identical requests within
# the same (ECB date, calendar date) window can be served from memory.
# Key: (from, to, days) -> (rate_date, today_str, response_dict)
FORECAST_CACHE: dict[tuple, tuple] = {}
FORECAST_CACHE_MAX = 512
_FORECAST_CACHE_LOCK = threading.Lock()

# Per-currency forecast legs. A leg depends only on the model and on its
# inputs (latest price, recent returns, volatility), and each step depends
# only on the step before, so the first N steps of a 90-day leg are exactly
# the N-step leg. Each currency is therefore computed once per data snapshot
# and extended to the longest horizon asked for so far: at most 90 model
# steps per currency per snapshot, whatever mix of pairs and horizons
# arrives. Previously every uncached (pair, horizon) request recomputed both
# legs from scratch, and one client could keep the model busy indefinitely.
# Key: currency -> leg dict (see _extend_leg).
_LEG_CACHE: dict[str, dict] = {}

# Requests that need model work hold one of these slots. When all are busy,
# a request is answered 503 at once and does not queue on the model lock.
# Forecast traffic can therefore never occupy the whole threadpool, and the
# cheap endpoints (/rates/latest, /currencies, /health) keep answering.
FORECAST_COMPUTE_SLOTS = 8
_COMPUTE_SLOTS = threading.BoundedSemaphore(FORECAST_COMPUTE_SLOTS)


def _load_model(pair_code: str):
    """Load model + scaler into cache. Returns (model, scaler).

    Both files are read by engine/artifacts.py: the model as weights only,
    into the architecture from model.py, and the scaler through a restricted
    unpickler. Neither file can run code when it is loaded.
    """
    if not _PAIR_CODE.fullmatch(pair_code):
        raise HTTPException(status_code=400, detail="Invalid pair.")

    with _MODEL_LOCK:
        if pair_code in MODEL_CACHE:
            return MODEL_CACHE[pair_code]

        model_path = os.path.join(MODEL_DIR, f"{pair_code}.keras")
        scaler_path = os.path.join(MODEL_DIR, f"{pair_code}_scaler.joblib")

        if not os.path.exists(model_path):
            raise HTTPException(status_code=503, detail=f"Model unavailable for {pair_code}.")

        try:
            model = load_inference_model(model_path, (WINDOW_SIZE, 1))
            scaler = load_scaler(scaler_path)
            MODEL_CACHE[pair_code] = (model, scaler)
            logger.info(f"Loaded {pair_code} into cache.")
            return model, scaler
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Model load error {pair_code}: {e}")
            raise HTTPException(status_code=500, detail="Model loading failed.")


def _snapshot_key(model, latest_price: float, daily_vol: float, recent_returns) -> str:
    """Identifies everything a leg's values depend on."""
    digest = hashlib.sha256()
    digest.update(str(id(model)).encode())
    digest.update(np.float64(latest_price).tobytes())
    digest.update(np.float64(daily_vol).tobytes())
    digest.update(np.ascontiguousarray(recent_returns, dtype=np.float64).tobytes())
    return digest.hexdigest()


def _extend_leg(target_curr: str, key: str, steps: int, model, scaler, latest_price, daily_vol, recent_returns) -> dict:
    """Returns the cached leg for this snapshot, extended to at least `steps`.

    Must be called with _MODEL_LOCK held. The loop body is the original
    autoregressive step, unchanged; it resumes from the stored state.
    """
    leg = _LEG_CACHE.get(target_curr)
    if leg is None or leg["key"] != key:
        leg = {
            "key": key,
            "batch": scaler.transform(recent_returns).reshape(1, WINDOW_SIZE, 1),
            "price": latest_price,
            "prices": [],
            "lower": [],
            "upper": [],
        }
        _LEG_CACHE[target_curr] = leg

    current_batch = leg["batch"]
    current_price = leg["price"]
    for _ in range(steps - len(leg["prices"])):
        pred_scaled = model.predict(current_batch, verbose=0)[0, 0]
        pred_return = scaler.inverse_transform([[pred_scaled]])[0, 0]
        current_price = current_price * (1 + pred_return)
        leg["prices"].append(current_price)
        next_input = np.array([[[pred_scaled]]])
        current_batch = np.concatenate([current_batch[:, 1:, :], next_input], axis=1)

        # Confidence band from historical volatility (widens with sqrt of
        # time): 80% CI ~ 1.28 standard deviations, scaled by sqrt(days).
        i = len(leg["prices"]) - 1
        band = current_price * daily_vol * 1.28 * np.sqrt(i + 1)
        leg["lower"].append(current_price - band)
        leg["upper"].append(current_price + band)
    leg["batch"] = current_batch
    leg["price"] = current_price
    return leg


def get_model_prediction(target_curr: str, steps: int):
    """
    Inference for EUR -> target_curr with volatility-based confidence bands
    from historical data. Deterministic for a given ECB data snapshot.
    """
    if target_curr == "EUR":
        return None, None, None, None

    pair_code = f"EUR_{target_curr}"
    model, scaler = _load_model(pair_code)

    start_date = (datetime.now() - timedelta(days=400)).strftime("%Y-%m-%d")
    df = fetch_data(f"EUR{target_curr}", start_date=start_date)

    if df is None or len(df) < WINDOW_SIZE:
        raise HTTPException(status_code=503, detail="Insufficient market data.")

    latest_price = float(df["Close"].iloc[-1])

    df_calc = df.copy()
    df_calc["Return"] = df_calc["Close"].pct_change()
    df_calc.dropna(inplace=True)

    if len(df_calc) < WINDOW_SIZE:
        raise HTTPException(status_code=503, detail="Insufficient data for window.")

    # Historical daily volatility for confidence bands
    daily_vol = float(df_calc["Return"].std())

    recent_returns = df_calc["Return"].values[-WINDOW_SIZE:].reshape(-1, 1)
    key = _snapshot_key(model, latest_price, daily_vol, recent_returns)

    # A leg's lists only ever grow, and a new snapshot replaces the whole
    # dict, so a hit can be read without waiting for the model lock.
    leg = _LEG_CACHE.get(target_curr)
    if leg is None or leg["key"] != key or len(leg["prices"]) < steps:
        if not _COMPUTE_SLOTS.acquire(blocking=False):
            raise HTTPException(
                status_code=503,
                detail="The forecast service is busy. Try again shortly.",
                headers={"Retry-After": "5"},
            )
        try:
            with _MODEL_LOCK:
                leg = _extend_leg(target_curr, key, steps, model, scaler, latest_price, daily_vol, recent_returns)
        finally:
            _COMPUTE_SLOTS.release()

    predicted_prices = leg["prices"][:steps]
    pred_lower = leg["lower"][:steps]
    pred_upper = leg["upper"][:steps]
    return df, predicted_prices, pred_lower, pred_upper


@router.get("/rates/history")
def rate_history(base: str, quote: str, days: int = 30):
    """
    Daily ECB reference-rate history for one pair, quoted as
    1 {base} = X {quote}, derived by EUR triangulation.
    Backs the charts on the Exchange and Forecast pages.
    """
    base = base.upper()
    quote = quote.upper()
    if base not in SUPPORTED_CURRENCIES or quote not in SUPPORTED_CURRENCIES:
        raise HTTPException(status_code=400, detail="Unsupported currency code.")
    if base == quote:
        raise HTTPException(status_code=400, detail="Base and quote must differ.")
    days = max(5, min(days, 1830))

    # Fetch a buffer of extra calendar days so weekends and holidays still
    # leave enough business-day observations, then trim to the request. The
    # buffer is rounded up to one of four shared windows, so every horizon
    # reuses the same few upstream fetches; the trimmed tail is unchanged.
    start = (datetime.now().date() - timedelta(days=history_window_days(days))).isoformat()
    df_base = fetch_data(f"EUR{base}", start_date=start)
    df_quote = fetch_data(f"EUR{quote}", start_date=start)
    if df_base is None or df_quote is None:
        raise HTTPException(status_code=503, detail="Rate source unavailable. Try again shortly.")

    common = df_base.index.intersection(df_quote.index)
    if len(common) < 2:
        raise HTTPException(status_code=503, detail="Rate source returned no usable data.")

    cross = (df_quote.loc[common]["Close"] / df_base.loc[common]["Close"]).tail(days)
    points = [
        {"date": dt.strftime("%Y-%m-%d"), "rate": round(float(rate), 6)}
        for dt, rate in cross.items()
    ]
    return {
        "pair": f"{base}/{quote}",
        "rate_date": points[-1]["date"],
        "source": "European Central Bank reference rates",
        "points": points,
    }


@router.get("/currencies")
def available_currencies():
    """
    What this deployment can actually do.

    'supported' lists currencies the converter and history charts accept.
    'forecastable' lists those with a trained model on disk, so the
    interface can offer only pairs the model can answer. EUR needs no
    model of its own because every model is already quoted against it.

    Trimming SUPPORTED_CURRENCIES or training a subset changes both lists
    without any frontend edit.
    """
    forecastable = set()
    for code in SUPPORTED_CURRENCIES:
        if code == "EUR":
            forecastable.add(code)
            continue
        model_path = os.path.join(MODEL_DIR, f"EUR_{code}.keras")
        scaler_path = os.path.join(MODEL_DIR, f"EUR_{code}_scaler.joblib")
        if os.path.exists(model_path) and os.path.exists(scaler_path):
            forecastable.add(code)

    return {
        "supported": sorted(SUPPORTED_CURRENCIES),
        "forecastable": sorted(forecastable),
    }


@router.get("/rates/latest")
def latest_rates():
    """
    Latest ECB reference rate for every supported currency, quoted against EUR.
    Published once per ECB business day (~16:00 CET); indicative only.
    Cross rates for any pair can be derived client-side as rates[to]/rates[from].
    """
    data = fetch_latest_rates()
    if data is None:
        raise HTTPException(status_code=503, detail="Rate source unavailable. Try again shortly.")

    # Only expose currencies the rest of the product supports.
    rates = {
        code: round(value, 6)
        for code, value in data["rates"].items()
        if code in SUPPORTED_CURRENCIES
    }

    if len(rates) < 2:
        raise HTTPException(status_code=503, detail="Rate source returned no usable data.")

    return {
        "base": "EUR",
        "rate_date": data["rate_date"],
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "source": "European Central Bank reference rates",
        "note": "Reference rates are published once per business day and are indicative only.",
        "rates": rates,
    }


@router.post("/predict")
def predict_forecast(request: PredictionRequest, db: Session = Depends(get_db)):
    try:
        if request.from_currency == request.to_currency:
            raise HTTPException(status_code=400, detail="Source and target currency cannot be the same.")

        today_str = datetime.now().date().isoformat()
        latest = fetch_latest_rates()
        rate_date = latest["rate_date"] if latest else None

        cache_key = (request.from_currency, request.to_currency, request.days)
        if rate_date is not None:
            with _FORECAST_CACHE_LOCK:
                cached = FORECAST_CACHE.get(cache_key)
            if cached and cached[0] == rate_date and cached[1] == today_str:
                return cached[2]

        if request.from_currency == "EUR":
            df_base = None
            pred_base_mean = [1.0] * request.days
            pred_base_lo = [1.0] * request.days
            pred_base_hi = [1.0] * request.days
        else:
            df_base, pred_base_mean, pred_base_lo, pred_base_hi = get_model_prediction(
                request.from_currency, request.days
            )

        if request.to_currency == "EUR":
            df_quote = None
            pred_quote_mean = [1.0] * request.days
            pred_quote_lo = [1.0] * request.days
            pred_quote_hi = [1.0] * request.days
        else:
            df_quote, pred_quote_mean, pred_quote_lo, pred_quote_hi = get_model_prediction(
                request.to_currency, request.days
            )

        if df_base is not None and df_quote is not None:
            common = df_base.index.intersection(df_quote.index)
            s_base = df_base.loc[common]["Close"]
            s_quote = df_quote.loc[common]["Close"]
        elif df_base is not None:
            s_base = df_base["Close"]
            s_quote = pd.Series(1.0, index=df_base.index)
        elif df_quote is not None:
            s_base = pd.Series(1.0, index=df_quote.index)
            s_quote = df_quote["Close"]
        else:
            raise HTTPException(status_code=400, detail="Invalid pair.")

        history_series = s_quote / s_base
        cross_mean = [pred_quote_mean[i] / pred_base_mean[i] for i in range(request.days)]
        cross_lower = [pred_quote_lo[i] / pred_base_hi[i] for i in range(request.days)]
        cross_upper = [pred_quote_hi[i] / pred_base_lo[i] for i in range(request.days)]

        response_data = []

        recent = history_series.tail(30)
        for dt, rate in recent.items():
            response_data.append({
                "date": dt.strftime("%Y-%m-%d"),
                "rate": round(float(rate), 4),
                "type": "history",
            })

        latest_date = recent.index[-1]
        friday_rate = float(recent.iloc[-1])
        today = datetime.now().date()
        fill_date = latest_date.date() + timedelta(days=1)

        while fill_date <= today:
            response_data.append({
                "date": fill_date.strftime("%Y-%m-%d"),
                "rate": round(friday_rate, 4),
                "type": "indicative",
            })
            fill_date += timedelta(days=1)

        forecast_start = max(today + timedelta(days=1), latest_date.date() + timedelta(days=1))
        idx = 0
        pointer = forecast_start
        first_forecast_date = None

        while idx < len(cross_mean):
            if pointer.weekday() < 5:
                if first_forecast_date is None:
                    first_forecast_date = pointer
                response_data.append({
                    "date": pointer.strftime("%Y-%m-%d"),
                    "rate": round(cross_mean[idx], 4),
                    "lower": round(cross_lower[idx], 4),
                    "upper": round(cross_upper[idx], 4),
                    "type": "forecast",
                })
                idx += 1
            pointer += timedelta(days=1)

        try:
            # The audit row carries the date of the first rendered forecast
            # point. forecast_start itself can be a Saturday, and a stored
            # date the response never showed cannot be resolved honestly.
            pair_slug = f"{request.from_currency}_{request.to_currency}"
            exists = db.query(PredictionAudit.id).filter(
                PredictionAudit.currency_pair == pair_slug,
                PredictionAudit.target_date == first_forecast_date,
            ).first()

            if not exists:
                p_rate = cross_mean[0]
                p_pct = (p_rate - friday_rate) / friday_rate if friday_rate != 0 else 0

                audit = PredictionAudit(
                    currency_pair=pair_slug,
                    target_date=first_forecast_date,
                    predicted_rate=p_rate,
                    predicted_change_pct=p_pct,
                    is_resolved=False,
                )
                db.add(audit)
                try:
                    db.commit()
                except IntegrityError:
                    # A concurrent request inserted the same (pair, date)
                    # between our existence check and this commit. The row
                    # is already there, so this request has nothing to add.
                    db.rollback()
        except Exception as e:
            db.rollback()
            logger.error(f"Audit log failed: {e}")

        result = {"pair": f"{request.from_currency}_{request.to_currency}", "forecast": response_data}

        if rate_date is not None:
            # Locked: concurrent evictions could pick the same key, and the
            # second pop then raised KeyError, which surfaced as a 500.
            with _FORECAST_CACHE_LOCK:
                if len(FORECAST_CACHE) >= FORECAST_CACHE_MAX and cache_key not in FORECAST_CACHE:
                    FORECAST_CACHE.pop(next(iter(FORECAST_CACHE)))
                FORECAST_CACHE[cache_key] = (rate_date, today_str, result)

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Prediction error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error.")


@router.get("/audit/scoreboard")
def get_scoreboard(db: Session = Depends(get_db)):
    subquery = (
        db.query(
            PredictionAudit.currency_pair,
            func.max(PredictionAudit.target_date).label("max_date"),
        )
        .filter(PredictionAudit.is_resolved == True)
        .group_by(PredictionAudit.currency_pair)
        .subquery()
    )

    latest = (
        db.query(PredictionAudit)
        .join(
            subquery,
            (PredictionAudit.currency_pair == subquery.c.currency_pair)
            & (PredictionAudit.target_date == subquery.c.max_date),
        )
        .order_by(PredictionAudit.target_date.desc())
        .limit(10)
        .all()
    )

    results = []
    for rec in latest:
        label = rec.trust_label or ""
        if label.startswith("Direction Matched"):
            status = "success"
        elif label.startswith("Flat Day") or label.startswith("No Publication"):
            status = "warning"
        else:
            status = "danger"
        actual_text = (
            f"{rec.actual_change_pct * 100:+.2f}%"
            if rec.actual_change_pct is not None
            else "—"
        )
        results.append({
            "currency": rec.currency_pair.replace("_", "/"),
            "pred": f"{rec.predicted_change_pct * 100:+.2f}%",
            "actual": actual_text,
            "label": label,
            "status": status,
        })

    return {"scoreboard": results}


@router.post("/audit/resolve", include_in_schema=False)
def resolve_audits(request: Request, x_admin_token: str = Header(None), db: Session = Depends(get_db)):
    # Three independent checks (core/security.py): the caller must be on
    # loopback (the cron job runs inside the container through docker exec),
    # ADMIN_SECRET must be at least 32 characters and not a template value,
    # and the token comparison runs in constant time for any input. nginx
    # also answers 404 for this path, so it is unreachable from outside.
    if not security.admin_request_permitted(request, x_admin_token):
        raise HTTPException(status_code=403, detail="Unauthorized.")

    pending = (
        db.query(PredictionAudit)
        .filter(
            PredictionAudit.is_resolved == False,
            PredictionAudit.target_date < datetime.now().date(),
        )
        .all()
    )

    def _rate_on(code: str, t_date) -> float | None:
        """The ECB rate for exactly t_date, or None if that day published nothing."""
        if code == "EUR":
            return 1.0
        df = fetch_data(f"EUR{code}", start_date=str(t_date))
        if df is None or df.empty:
            return None
        exact = df[df.index.date == t_date]
        if exact.empty:
            return None
        return float(exact["Close"].iloc[0])

    resolved_count = 0
    for record in pending:
        try:
            base, quote = record.currency_pair.split("_")
            v_b = _rate_on(base, record.target_date)
            v_q = _rate_on(quote, record.target_date)

            if v_b is not None and v_q is not None:
                actual_close = v_q / v_b
                implied_start = record.predicted_rate / (1 + record.predicted_change_pct)
                actual_change = (actual_close - implied_start) / implied_start

                record.actual_rate = actual_close
                record.actual_change_pct = actual_change
                record.trust_label = calculate_trust_label(record.predicted_change_pct, actual_change)
                record.is_resolved = True
                resolved_count += 1
            elif (datetime.now().date() - record.target_date).days > 5:
                # Five ECB business-day cycles with no publication for that
                # date means it was a market holiday. Close the row honestly
                # instead of leaving it pending forever.
                record.trust_label = "No Publication (Market Holiday)"
                record.is_resolved = True
                resolved_count += 1
        except Exception as e:
            logger.error(f"Audit resolution failed for {record.currency_pair}: {e}")
            continue

    db.commit()
    return {"status": "ok", "resolved": resolved_count}