import io
import logging
import threading
import time

import pandas as pd
import requests

logger = logging.getLogger("cortex.fetcher")

session = requests.Session()
session.headers.update({
    "User-Agent": "Cortex/1.2",
    "Accept": "text/csv",
})

ECB_BASE = "https://data-api.ecb.europa.eu/service/data/EXR"

# Small in-process response cache, keyed on the full request.
#
# This replaces requests-cache, which pulled in attrs and cattrs and broke
# on some version combinations with "name 'RequestsCookieJar' is not
# defined" while serialising a response. The ECB publishes once per
# business day, so a plain time-based cache of the response text is all
# this needs, and it removes three dependencies.
_CACHE: dict[tuple, tuple[float, str]] = {}
_CACHE_LOCK = threading.Lock()
_CACHE_LIMIT = 64


def _cache_key(url: str, params: dict) -> tuple:
    return (url, tuple(sorted((str(k), str(v)) for k, v in params.items())))


def _get_text(url: str, params: dict, timeout: int, ttl_seconds: int) -> str | None:
    """GET with a time-based cache. Returns the body text, or None on failure."""
    key = _cache_key(url, params)
    now = time.time()

    with _CACHE_LOCK:
        hit = _CACHE.get(key)
        if hit and now - hit[0] < ttl_seconds:
            return hit[1]

    response = session.get(url, params=params, timeout=timeout)
    if response.status_code != 200:
        logger.warning(f"ECB returned {response.status_code} for {url}")
        return None

    with _CACHE_LOCK:
        if len(_CACHE) >= _CACHE_LIMIT:
            oldest = min(_CACHE, key=lambda k: _CACHE[k][0])
            _CACHE.pop(oldest, None)
        _CACHE[key] = (now, response.text)

    return response.text


def clear_cache() -> None:
    """Drops every cached response. Used by tests."""
    with _CACHE_LOCK:
        _CACHE.clear()


def fetch_data(ticker: str, start_date: str = "2000-01-01") -> pd.DataFrame | None:
    """
    Fetches daily reference rates from the European Central Bank.
    Input ticker format: 'EUR{CURRENCY}' e.g. 'EURUSD'.
    Returns DataFrame with 'Close' column and DateTime index.
    """
    # Strip only the leading EUR. A plain replace() would turn "EUREUR"
    # into an empty string, which then built the all-currencies URL and
    # returned every series at once instead of a constant 1.0.
    target_currency = ticker.replace("=X", "")
    if target_currency.startswith("EUR"):
        target_currency = target_currency[3:]

    if target_currency in ("", "EUR"):
        dates = pd.date_range(start=start_date, end=pd.Timestamp.now())
        return pd.DataFrame({"Close": 1.0}, index=dates)

    logger.info(f"Fetching ECB data: EUR -> {target_currency} from {start_date}")

    url = f"{ECB_BASE}/D.{target_currency}.EUR.SP00.A"
    params = {"startPeriod": start_date, "format": "csvdata"}

    try:
        text = _get_text(url, params, timeout=30, ttl_seconds=3600)
        if text is None:
            return None

        df = pd.read_csv(io.StringIO(text))

        if "TIME_PERIOD" not in df.columns or "OBS_VALUE" not in df.columns:
            logger.error(f"Unexpected ECB format for {target_currency}")
            return None

        df = df.rename(columns={"TIME_PERIOD": "Date", "OBS_VALUE": "Close"})
        df["Date"] = pd.to_datetime(df["Date"])
        df.set_index("Date", inplace=True)
        df.sort_index(inplace=True)
        df = df[["Close"]]
        df = df.apply(pd.to_numeric, errors="coerce")
        df.dropna(inplace=True)

        logger.info(f"Fetched {len(df)} rows for EUR{target_currency}")
        return df

    except Exception as e:
        logger.error(f"ECB fetch error for {target_currency}: {e}")
        return None


def _parse_latest_csv(text: str) -> dict[str, tuple[str, float]] | None:
    """
    Parses the ECB 'all currencies, last observation' CSV into
    {currency_code: (date_string, rate_vs_eur)}.

    Kept as a pure function so it can be tested without network access.
    """
    try:
        df = pd.read_csv(io.StringIO(text))
    except Exception as e:
        logger.error(f"Latest-rates CSV parse error: {e}")
        return None

    required = {"CURRENCY", "TIME_PERIOD", "OBS_VALUE"}
    if not required.issubset(df.columns):
        logger.error(f"Unexpected ECB latest-rates format. Columns: {list(df.columns)}")
        return None

    df = df[["CURRENCY", "TIME_PERIOD", "OBS_VALUE"]].copy()
    df["OBS_VALUE"] = pd.to_numeric(df["OBS_VALUE"], errors="coerce")
    df.dropna(subset=["OBS_VALUE"], inplace=True)

    # Some series can contain more than one row; keep the most recent per currency.
    df.sort_values("TIME_PERIOD", inplace=True)
    df = df.groupby("CURRENCY").tail(1)

    out: dict[str, tuple[str, float]] = {}
    for _, row in df.iterrows():
        out[str(row["CURRENCY"]).upper()] = (str(row["TIME_PERIOD"]), float(row["OBS_VALUE"]))

    return out or None


def fetch_latest_rates() -> dict | None:
    """
    Fetches the most recent ECB reference rate for every published currency
    in a single request. Returns:

        {
          "rate_date": "YYYY-MM-DD",   # most recent publication date seen
          "rates": {"USD": 1.08, "GBP": 0.85, ..., "EUR": 1.0},
          "dates": {"USD": "YYYY-MM-DD", ...},   # per-currency, for stale series
        }

    These are daily reference rates, published once per ECB business day
    at around 16:00 CET. They are indicative and differ from transactable
    market rates.
    """
    url = f"{ECB_BASE}/D..EUR.SP00.A"
    params = {"lastNObservations": 1, "format": "csvdata"}

    try:
        text = _get_text(url, params, timeout=30, ttl_seconds=1800)
        if text is None:
            return None

        parsed = _parse_latest_csv(text)
        if not parsed:
            return None

        rates = {code: value for code, (_, value) in parsed.items()}
        dates = {code: date for code, (date, _) in parsed.items()}
        rates["EUR"] = 1.0

        rate_date = max(dates.values())
        logger.info(f"Fetched latest ECB rates for {len(rates)} currencies ({rate_date})")

        return {"rate_date": rate_date, "rates": rates, "dates": dates}

    except Exception as e:
        logger.error(f"ECB latest-rates fetch error: {e}")
        return None
