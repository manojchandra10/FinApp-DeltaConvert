"""M-01, M-03 and L-04: unit tests for core/security.py."""
from types import SimpleNamespace

from cortex.app.core import security


def _request(peer, headers=None):
    return SimpleNamespace(client=SimpleNamespace(host=peer), headers=headers or {})


def test_limiter_accepts_thirty_per_window_then_refuses():
    limiter = security.RateLimiter(max_requests=30, window_seconds=60)
    results = [limiter.is_allowed("198.51.100.1") for _ in range(40)]
    assert results.count(True) == 30 and results[30:] == [False] * 10


def test_limiter_window_expires(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(security.time, "monotonic", lambda: clock[0])
    limiter = security.RateLimiter(max_requests=2, window_seconds=60)
    assert limiter.is_allowed("a") and limiter.is_allowed("a") and not limiter.is_allowed("a")
    clock[0] += 61
    assert limiter.is_allowed("a")


def test_limiter_memory_is_bounded(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(security.time, "monotonic", lambda: clock[0])
    limiter = security.RateLimiter(max_clients=20000)
    for i in range(50000):
        limiter.is_allowed(f"id-{i}")
    assert len(limiter) == 20000
    clock[0] += 121
    limiter.is_allowed("late")
    assert len(limiter) == 1


def test_x_real_ip_is_ignored_from_an_untrusted_peer():
    request = _request("203.0.113.9", {"x-real-ip": "198.51.100.77"})
    assert security.client_address(request) == "203.0.113.9"


def test_x_real_ip_is_used_from_nginx_on_a_private_network():
    request = _request("172.18.0.4", {"x-real-ip": "198.51.100.77"})
    assert security.client_address(request) == "198.51.100.77"


def test_x_real_ip_must_be_a_literal_address():
    request = _request("172.18.0.4", {"x-real-ip": "deltaconvert.com?x"})
    assert security.client_address(request) == "172.18.0.4"


def test_ipv6_clients_are_grouped_per_64():
    first = security.rate_limit_key("2001:db8:1:2:aaaa::1")
    second = security.rate_limit_key("2001:db8:1:2:bbbb::9")
    assert first == second == "2001:db8:1:2::/64"
    assert security.rate_limit_key("::ffff:198.51.100.5") == "198.51.100.5"


def test_token_comparison_never_raises():
    assert security.tokens_match("abc", "abc")
    assert not security.tokens_match("abd", "abc")
    # Starlette hands header bytes over as latin-1 text; non-ASCII used to
    # make hmac.compare_digest raise TypeError (a 500).
    assert not security.tokens_match("\xe9t\xe9", "a" * 64)


def test_admin_secret_strength():
    assert security.admin_secret_problem("") is not None
    assert security.admin_secret_problem("short") is not None
    assert security.admin_secret_problem("local_dev_admin_token_change_me_please_1234") is not None
    assert security.admin_secret_problem("0123456789abcdef" * 4) is None


def test_admin_requires_loopback_peer(monkeypatch):
    secret = "f" * 64
    monkeypatch.setenv("ADMIN_SECRET", secret)
    assert security.admin_request_permitted(_request("127.0.0.1"), secret)
    assert not security.admin_request_permitted(_request("172.18.0.4"), secret)
    assert not security.admin_request_permitted(_request("127.0.0.1"), "wrong")


def test_cors_origins_accept_exact_origins_only():
    origins = security.parse_cors_origins(
        "https://deltaconvert.com, *, https://*.example.com, https://user:pw@evil.example,"
        "https://evil.example/path, ftp://x.example, http://localhost:5173"
    )
    assert origins == ["https://deltaconvert.com", "http://localhost:5173"]
