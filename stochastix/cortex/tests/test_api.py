"""H-02, M-01, M-03, L-04, L-05, L-08 and I-01 through the real app."""
import os

import pytest

from cortex.app.api.v1 import endpoints


def _count_predict_calls(monkeypatch):
    """Counts model.predict calls on every cached model."""
    calls = {"n": 0}
    for pair_code in ("EUR_GBP", "EUR_CHF"):
        model, _ = endpoints._load_model(pair_code)
        original = model.predict

        def counting(*args, _original=original, **kwargs):
            calls["n"] += 1
            return _original(*args, **kwargs)

        monkeypatch.setattr(model, "predict", counting)
    return calls


def test_crafted_host_header_is_still_rate_limited(client, upstream):
    # Starlette rebuilds request.url from the Host header; this value empties
    # request.url.path, which used to skip the limiter entirely.
    statuses = [
        client.get("/api/v1/currencies", headers={"Host": "deltaconvert.com?x"}).status_code
        for _ in range(40)
    ]
    assert statuses.count(429) == 10


def test_rotating_x_real_ip_from_an_untrusted_peer_is_limited(client, upstream):
    statuses = [
        client.get("/api/v1/currencies", headers={"X-Real-IP": f"198.51.100.{i}"}).status_code
        for i in range(40)
    ]
    assert statuses.count(429) == 10


def test_docs_and_schema_are_not_served_in_production(client):
    for path in ("/openapi.json", "/docs", "/redoc"):
        assert client.get(path).status_code == 404


def test_admin_endpoint_refuses_remote_callers_even_with_the_token(client, upstream):
    token = os.environ["ADMIN_SECRET"]
    response = client.post("/api/v1/audit/resolve", headers={"x-admin-token": token})
    assert response.status_code == 403


def test_admin_endpoint_accepts_loopback_with_a_strong_secret(client, upstream):
    client.peer.host = "127.0.0.1"
    token = os.environ["ADMIN_SECRET"]
    assert client.post("/api/v1/audit/resolve", headers={"x-admin-token": token}).status_code == 200
    assert client.post("/api/v1/audit/resolve", headers={"x-admin-token": "wrong"}).status_code == 403
    response = client.post("/api/v1/audit/resolve", headers=[("x-admin-token", "\xe9t\xe9".encode("latin-1"))])
    assert response.status_code == 403


def test_admin_endpoint_refuses_template_secret(client, upstream, monkeypatch):
    client.peer.host = "127.0.0.1"
    monkeypatch.setenv("ADMIN_SECRET", "local_dev_admin_token_change_me")
    response = client.post("/api/v1/audit/resolve", headers={"x-admin-token": "local_dev_admin_token_change_me"})
    assert response.status_code == 403


def test_validation_errors_do_not_echo_input(client):
    payload = {"from_currency": "<script>alert(1)</script>", "to_currency": "EUR", "days": 5}
    response = client.post("/api/v1/predict", json=payload)
    assert response.status_code == 422
    assert "<script>" not in response.text and "input" not in response.json()["detail"][0]


def test_cors_is_strict(client):
    preflight = {
        "Origin": "https://deltaconvert.com",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "x-admin-token",
    }
    assert client.options("/api/v1/predict", headers=preflight).status_code == 400
    other = client.get("/api/v1/currencies", headers={"Origin": "http://localhost"})
    assert "access-control-allow-origin" not in other.headers
    accepted = client.get("/api/v1/currencies", headers={"Origin": "https://deltaconvert.com"})
    assert accepted.headers.get("access-control-allow-origin") == "https://deltaconvert.com"
    assert "access-control-allow-credentials" not in accepted.headers


def test_forecast_legs_are_computed_once_per_snapshot(client, upstream, monkeypatch):
    endpoints._LEG_CACHE.clear()
    endpoints.FORECAST_CACHE.clear()
    calls = _count_predict_calls(monkeypatch)
    bodies = {}
    for i, days in enumerate([30, 45, 60, 75, 90, 89, 88, 87]):
        client.peer.host = f"203.0.113.{100 + i}"
        response = client.post("/api/v1/predict", json={"from_currency": "GBP", "to_currency": "CHF", "days": days})
        assert response.status_code == 200
        bodies[days] = response.json()["forecast"]
    # 90 steps per currency, for both currencies; 1,128 before the fix.
    assert calls["n"] == 180

    # Same values as a from-scratch computation of the shorter horizon.
    endpoints._LEG_CACHE.clear()
    endpoints.FORECAST_CACHE.clear()
    client.peer.host = "203.0.113.200"
    fresh = client.post("/api/v1/predict", json={"from_currency": "GBP", "to_currency": "CHF", "days": 45}).json()["forecast"]
    assert fresh == bodies[45]


def test_busy_compute_slots_answer_503_and_cached_requests_still_work(client, upstream):
    endpoints._LEG_CACHE.clear()
    endpoints.FORECAST_CACHE.clear()
    assert client.post("/api/v1/predict", json={"from_currency": "GBP", "to_currency": "EUR", "days": 30}).status_code == 200
    taken = 0
    while endpoints._COMPUTE_SLOTS.acquire(blocking=False):
        taken += 1
    try:
        # Needs new model steps (60 > 30): refused at once instead of queueing.
        busy = client.post("/api/v1/predict", json={"from_currency": "GBP", "to_currency": "EUR", "days": 60})
        assert busy.status_code == 503 and busy.headers.get("retry-after") == "5"
        # Within the cached leg: served without a slot.
        endpoints.FORECAST_CACHE.clear()
        cached = client.post("/api/v1/predict", json={"from_currency": "GBP", "to_currency": "EUR", "days": 20})
        assert cached.status_code == 200
    finally:
        for _ in range(taken):
            endpoints._COMPUTE_SLOTS.release()


def test_history_requests_share_upstream_windows(client, upstream):
    for i, days in enumerate(range(100, 120)):
        client.peer.host = f"203.0.113.{i}"
        assert client.get("/api/v1/rates/history", params={"base": "GBP", "quote": "USD", "days": days}).status_code == 200
    # One window per currency instead of one per distinct `days` value.
    assert len(upstream) == 2


@pytest.mark.parametrize("days", [5, 7, 29, 30, 182, 229, 230, 365, 582, 583, 1830])
def test_shared_windows_return_the_same_history(days):
    from datetime import datetime, timedelta
    from cortex.app.engine import fetcher

    def cross(start):
        base = fetcher.fetch_data("EURGBP", start_date=start)
        quote = fetcher.fetch_data("EURUSD", start_date=start)
        common = base.index.intersection(quote.index)
        return (quote.loc[common]["Close"] / base.loc[common]["Close"]).tail(days)

    from conftest import fake_ecb_csv

    fetcher.clear_cache()
    original = fetcher._download
    fetcher._download = lambda url, params, timeout: fake_ecb_csv(url, params)
    try:
        today = datetime.now().date()
        old_start = (today - timedelta(days=int(days * 1.7) + 10)).isoformat()
        new_start = (today - timedelta(days=fetcher.history_window_days(days))).isoformat()
        old, new = cross(old_start), cross(new_start)
        assert len(new) == days and old.equals(new)
    finally:
        fetcher._download = original
        fetcher.clear_cache()
