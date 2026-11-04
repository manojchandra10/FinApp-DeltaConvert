import io
import logging
import re
import threading
import time
from datetime import date
from urllib.parse import urljoin, urlsplit

import pandas as pd
import requests

logger = logging.getLogger("cortex.fetcher")

session = requests.Session()
session.headers.update({
    "User-Agent": "Cortex/1.2",
    "Accept": "text/csv",
})

ECB_BASE = "https://data-api.ecb.europa.eu/service/data/EXR"

# Limits on what one upstream response may cost. The largest real response
# (a full series since 2000 with every attribute column) is a few MB.
MAX_RESPONSE_BYTES = 32 * 1024 * 1024
MAX_REDIRECTS = 3
CONNECT_TIMEOUT = 10
READ_TIMEOUT = 30

_CODE_PATTERN = re.compile(r"[A-Z]{3}")
_DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")

# Calendar-day fetch windows shared by every history request. Each request
# is served from the smallest window that covers it and then trimmed, so all
# horizons share four upstream URLs per currency. Before, each distinct
# `days` value had a URL of its own. 400 matches the forecast's own window.
HISTORY_WINDOWS = (60, 400, 1000, 3200)

# Small in-process response cache, keyed on the full request.
#
# This replaces requests-cache, which pulled in attrs and cattrs and broke
# on some version combinations with "name 'RequestsCookieJar' is not
# defined" while serialising a response. The ECB publishes once per
# business day, so a plain time-based cache of the response text is all
# this needs, and it removes three dependencies. The limit holds every
# history window for every currency plus the latest-rates response.
_CACHE: dict[tuple, tuple[float, str]] = {}
_CACHE_LOCK = threading.Lock()
_CACHE_LIMIT = 160


def history_window_days(days: int) -> int:
    """The shared fetch window, in calendar days, for a history of `days` points."""
    needed = int(days * 1.7) + 10
    for window in HISTORY_WINDOWS:
        if needed <= window:
            return window
    return needed


def _valid_code(code: str) -> bool:
    return isinstance(code, str) and _CODE_PATTERN.fullmatch(code) is not None


def _valid_date(text: str) -> bool:
    if not isinstance(text, str) or _DATE_PATTERN.fullmatch(text) is None:
        return False
    try:
        date.fromisoformat(text)
    except ValueError:
        return False
    return True


def _cache_key(url: str, params: dict) -> tuple:
    return (url, tuple(sorted((str(k), str(v)) for k, v in params.items())))


def _redirect_permitted(target: str) -> bool:
    """Redirects may only stay on the ECB host, over the same scheme."""
    base = urlsplit(ECB_BASE)
    parts = urlsplit(target)
    return parts.scheme == base.scheme and parts.netloc == base.netloc and not parts.username


def _download(url: str, params: dict, timeout: int) -> str | None:
    """GET url and follow at most MAX_REDIRECTS redirects, all on the ECB host.

    `timeout` is a deadline for the whole exchange; each socket read also has
    its own READ_TIMEOUT. The body may not exceed MAX_RESPONSE_BYTES.
    """
    deadline = time.monotonic() + timeout
    current_url, current_params = url, params
    for _ in range(MAX_REDIRECTS + 1):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            logger.warning(f"ECB request timed out for {url}")
            return None
        response = session.get(
            current_url,
            params=current_params,
            timeout=(min(CONNECT_TIMEOUT, remaining), min(READ_TIMEOUT, remaining)),
            allow_redirects=False,
            stream=True,
        )
        try:
            if response.is_redirect:
                target = urljoin(response.url, response.headers.get("Location", ""))
                if not _redirect_permitted(target):
                    logger.warning(f"Refusing ECB redirect from {url} to another host")
                    return None
                current_url, current_params = target, None
                continue

            if response.status_code != 200:
                logger.warning(f"ECB returned {response.status_code} for {url}")
                return None

            declared = response.headers.get("Content-Length", "")
            if declared.isdigit() and int(declared) > MAX_RESPONSE_BYTES:
                logger.warning(f"ECB response for {url} declares {declared} bytes; refusing")
                return None

            # read1() returns after a single socket read, so the deadline is
            # checked between reads even when a server drips bytes slowly.
            # iter_content() would block until a whole chunk had arrived.
            raw = response.raw
            chunks, size = [], 0
            while True:
                if time.monotonic() > deadline:
                    logger.warning(f"ECB response for {url} exceeded the {timeout}s deadline")
                    return None
                chunk = raw.read1(65536, decode_content=True)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_RESPONSE_BYTES:
                    logger.warning(f"ECB response for {url} exceeds {MAX_RESPONSE_BYTES} bytes; refusing")
                    return None
                chunks.append(chunk)
            # Hand the bytes back to requests so the text is decoded exactly
            # as response.text decoded it before streaming was introduced.
            response._content = b"".join(chunks)
            return response.text
        finally:
            response.close()

    logger.warning(f"Too many ECB redirects for {url}")
    return None


def _get_text(url: str, params: dict, timeout: int, ttl_seconds: int) -> str | None:
    """GET with a time-based cache. Returns the body text, or None on failure."""
    key = _cache_key(url, params)
    now = time.time()

    with _CACHE_LOCK:
        hit = _CACHE.get(key)
        if hit and now - hit[0] < ttl_seconds:
            return hit[1]

    text = _download(url, params, timeout)
    if text is None:
        return None

    with _CACHE_LOCK:
        if len(_CACHE) >= _CACHE_LIMIT and key not in _CACHE:
            oldest = min(_CACHE, key=lambda k: _CACHE[k][0])
            _CACHE.pop(oldest, None)
        _CACHE[key] = (now, text)

    return text


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

    # Both values end up in the upstream URL. Callers pass validated codes,
    # but the audit job reads them back from the database, so they are
    # checked here as well: three capital letters and an ISO date, or no
    # request at all.
    if not _valid_date(start_date):
        logger.error(f"Refusing ECB fetch with malformed start date {start_date!r}")
        return None

    if target_currency in ("", "EUR"):
        dates = pd.date_range(start=start_date, end=pd.Timestamp.now())
        return pd.DataFrame({"Close": 1.0}, index=dates)

    if not _valid_code(target_currency):
        logger.error(f"Refusing ECB fetch for malformed currency code {target_currency!r}")
        return None

    logger.info(f"Fetching ECB data: EUR -> {target_currency} from {start_date}")

    url = f"{ECB_BASE}/D.{target_currency}.EUR.SP00.A"
    params = {"startPeriod": start_date, "format": "csvdata"}

    try:
        text = _get_text(url, params, timeout=60, ttl_seconds=3600)
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
        code = str(row["CURRENCY"]).upper()
        period = str(row["TIME_PERIOD"])
        # Codes and dates are passed on to browsers; keep only well-formed rows.
        if not _valid_code(code) or not _valid_date(period):
            continue
        out[code] = (period, float(row["OBS_VALUE"]))

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
