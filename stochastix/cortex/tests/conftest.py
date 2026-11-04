"""
Shared fixtures for the security regression tests.

Run from the repository root, in an environment with requirements.txt,
pytest and httpx installed:

    python -m pytest stochastix/cortex/tests -q

No network access, Docker or Postgres is needed: the database is a
temporary SQLite file and the ECB is replaced by deterministic data.
"""
import datetime as dt
import os
import random
import secrets
import sys
import tempfile
from pathlib import Path

import pytest

CORTEX_DIR = Path(__file__).resolve().parents[1]
MODELS_DIR = CORTEX_DIR / "models"
sys.path.insert(0, str(CORTEX_DIR.parent))

_TMP = Path(tempfile.mkdtemp(prefix="cortex-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP / 'audit.db'}"
os.environ["ENVIRONMENT"] = "production"
os.environ["ADMIN_SECRET"] = secrets.token_hex(32)
os.environ["CORS_ORIGINS"] = "https://deltaconvert.com,https://www.deltaconvert.com"
os.environ.pop("CURRENCIES", None)
os.environ.pop("TRUSTED_PROXY_CIDRS", None)
os.environ.pop("ADMIN_CALLER_CIDRS", None)
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

BASE_RATES = {"GBP": 0.8417, "CHF": 0.94, "USD": 1.0886, "JPY": 171.38, "CAD": 1.4908}
HEADER = "KEY,FREQ,CURRENCY,CURRENCY_DENOM,EXR_TYPE,EXR_SUFFIX,TIME_PERIOD,OBS_VALUE,OBS_STATUS"


def _series(code: str):
    rng = random.Random(sum(ord(c) * (i + 7) for i, c in enumerate(code)))
    rate = BASE_RATES.get(code, 2.0)
    today = dt.date.today()
    day = today - dt.timedelta(days=4000)
    points = []
    while day <= today:
        if day.weekday() < 5:
            rate *= 1 + rng.gauss(0, 0.004)
            points.append((day.isoformat(), round(rate, 4)))
        day += dt.timedelta(days=1)
    return points


def fake_ecb_csv(url: str, params: dict) -> str | None:
    """What the ECB would send for one of the two URL shapes the fetcher uses."""
    flow = url.rsplit("/", 1)[-1]
    if flow == "D..EUR.SP00.A":
        rows = [f"EXR.D.{c}.EUR.SP00.A,D,{c},EUR,SP00,A,{d},{v},A" for c in sorted(BASE_RATES) for d, v in _series(c)[-1:]]
        return HEADER + "\n" + "\n".join(rows) + "\n"
    code = flow.split(".")[1]
    if code not in BASE_RATES:
        return None
    start = (params or {}).get("startPeriod", "1999-01-01")
    rows = [f"EXR.D.{code}.EUR.SP00.A,D,{code},EUR,SP00,A,{d},{v},A" for d, v in _series(code) if d >= start]
    return HEADER + "\n" + "\n".join(rows) + "\n"


@pytest.fixture
def upstream(monkeypatch):
    """Replaces the network download with fake data and counts the calls."""
    from cortex.app.engine import fetcher

    calls = []

    def fake_download(url, params, timeout):
        calls.append((url, tuple(sorted((params or {}).items()))))
        return fake_ecb_csv(url, params)

    fetcher.clear_cache()
    monkeypatch.setattr(fetcher, "_download", fake_download)
    yield calls
    fetcher.clear_cache()


class PeerSwitch:
    """ASGI wrapper that sets the TCP peer address the app sees."""

    def __init__(self, app):
        self.app = app
        self.host = "203.0.113.10"

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            scope = dict(scope, client=(self.host, 50000))
        await self.app(scope, receive, send)


@pytest.fixture(scope="session")
def api():
    """One running app for the whole session (model warm-up is slow)."""
    from fastapi.testclient import TestClient
    from cortex.app import main
    from cortex.app.api.v1 import endpoints

    endpoints.MODEL_DIR = str(MODELS_DIR)
    peer = PeerSwitch(main.app)
    with TestClient(peer, base_url="http://deltaconvert.com") as client:
        client.peer = peer
        yield client


@pytest.fixture
def client(api):
    """The shared app, with the peer address reset before and after a test."""
    api.peer.host = "203.0.113.10"
    yield api
    api.peer.host = "203.0.113.10"


@pytest.fixture(autouse=True)
def fresh_limits():
    """Each test starts with an empty rate-limit table and a default peer."""
    try:
        from cortex.app import main
    except Exception:  # noqa: BLE001 - artefact tests do not need the app
        yield
        return
    main.rate_limiter._hits.clear()
    yield
    main.rate_limiter._hits.clear()
