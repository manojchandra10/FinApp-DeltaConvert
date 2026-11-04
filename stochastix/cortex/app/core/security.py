"""
Request-level security helpers: client address, rate limiting, admin access
and CORS origin parsing. Kept apart from the endpoints so each rule can be
tested on its own.
"""
import hashlib
import hmac
import ipaddress
import logging
import os
import threading
import time
from collections import OrderedDict, deque
from urllib.parse import urlsplit

logger = logging.getLogger("cortex.security")


# --- Client address ----------------------------------------------------------

# Peers trusted to state the client address in X-Real-IP. nginx reaches the
# backend over a Docker bridge network, which uses private addresses. Any
# other caller (a direct request to port 8000, for example) is identified
# by its own TCP peer address, whatever headers it sends.
_DEFAULT_TRUSTED_PROXIES = "127.0.0.0/8,::1/128,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,fc00::/7"


def _parse_networks(raw: str, setting: str) -> list:
    networks = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            networks.append(ipaddress.ip_network(item, strict=False))
        except ValueError:
            logger.warning(f"Ignoring invalid network {item!r} in {setting}.")
    return networks


TRUSTED_PROXY_NETWORKS = _parse_networks(
    os.getenv("TRUSTED_PROXY_CIDRS", _DEFAULT_TRUSTED_PROXIES), "TRUSTED_PROXY_CIDRS"
)


def _as_ip(value: str):
    try:
        address = ipaddress.ip_address(value.strip())
    except ValueError:
        return None
    if address.version == 6 and address.ipv4_mapped:
        return address.ipv4_mapped
    return address


def _in_networks(address, networks) -> bool:
    return address is not None and any(address in network for network in networks)


def peer_address(request) -> str:
    """The TCP peer of the request, before any header is consulted."""
    return request.client.host if request.client else ""


def client_address(request) -> str:
    """The address the rate limiter should charge for this request."""
    peer = peer_address(request)
    if _in_networks(_as_ip(peer), TRUSTED_PROXY_NETWORKS):
        stated = _as_ip(request.headers.get("x-real-ip", ""))
        if stated is not None:
            return str(stated)
    return peer or "unknown"


def rate_limit_key(address: str) -> str:
    """IPv6 clients are grouped by /64, the block a single customer is given."""
    ip = _as_ip(address)
    if ip is not None and ip.version == 6:
        return str(ipaddress.ip_network(f"{ip}/64", strict=False))
    return str(ip) if ip is not None else address


# --- Rate limiter ------------------------------------------------------------

class RateLimiter:
    """Sliding-window limiter with a bounded client table.

    Same rule as before: at most max_requests per client within any
    window_seconds. Idle clients are swept once per window, and the table
    never holds more than max_clients entries; when it is full the client
    seen least recently is dropped.
    """

    def __init__(self, max_requests: int = 30, window_seconds: int = 60, max_clients: int = 20000):
        self.max_requests = max_requests
        self.window = window_seconds
        self.max_clients = max_clients
        self._hits: "OrderedDict[str, deque]" = OrderedDict()
        self._lock = threading.Lock()
        self._next_sweep = time.monotonic() + window_seconds

    def __len__(self) -> int:
        return len(self._hits)

    def _sweep(self, now: float) -> None:
        cutoff = now - self.window
        stale = [key for key, hits in self._hits.items() if not hits or hits[-1] <= cutoff]
        for key in stale:
            del self._hits[key]
        self._next_sweep = now + self.window

    def is_allowed(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            if now >= self._next_sweep:
                self._sweep(now)
            hits = self._hits.get(key)
            if hits is None:
                while len(self._hits) >= self.max_clients:
                    self._hits.popitem(last=False)
                hits = self._hits[key] = deque()
            else:
                self._hits.move_to_end(key)
            cutoff = now - self.window
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= self.max_requests:
                return False
            hits.append(now)
            return True


# --- Admin access ------------------------------------------------------------

MIN_ADMIN_SECRET_LENGTH = 32
_PLACEHOLDER_MARKERS = ("change_me", "changeme", "change-me", "placeholder", "example", "replace_me", "your_")

_ADMIN_NETWORKS = _parse_networks(
    os.getenv("ADMIN_CALLER_CIDRS", "127.0.0.0/8,::1/128"), "ADMIN_CALLER_CIDRS"
)


def admin_secret_problem(secret: str) -> str | None:
    """Why a configured ADMIN_SECRET is unusable, or None when it is fine."""
    if not secret:
        return "ADMIN_SECRET is not set"
    if len(secret) < MIN_ADMIN_SECRET_LENGTH:
        return f"ADMIN_SECRET is shorter than {MIN_ADMIN_SECRET_LENGTH} characters"
    lowered = secret.lower()
    if any(marker in lowered for marker in _PLACEHOLDER_MARKERS):
        return "ADMIN_SECRET is a template placeholder"
    return None


def tokens_match(supplied: str, expected: str) -> bool:
    """Constant-time comparison that accepts any input without raising.

    Starlette decodes header bytes as latin-1, so encoding back with latin-1
    restores the bytes the client sent. Hashing both sides first gives equal
    lengths, so the comparison time does not depend on the secret's length.
    """
    supplied_bytes = supplied.encode("latin-1", errors="replace")
    expected_bytes = expected.encode("utf-8")
    return hmac.compare_digest(
        hashlib.sha256(supplied_bytes).digest(),
        hashlib.sha256(expected_bytes).digest(),
    )


def admin_request_permitted(request, supplied_token: str | None) -> bool:
    """All three checks must pass: caller network, usable secret, matching token."""
    peer = peer_address(request)
    if not _in_networks(_as_ip(peer), _ADMIN_NETWORKS):
        logger.warning(f"Admin request refused: caller {peer or 'unknown'} is outside ADMIN_CALLER_CIDRS.")
        return False
    secret = os.getenv("ADMIN_SECRET", "")
    problem = admin_secret_problem(secret)
    if problem:
        logger.warning(f"Admin request refused: {problem}.")
        return False
    if not supplied_token or not tokens_match(supplied_token, secret):
        logger.warning("Admin request refused: token missing or wrong.")
        return False
    return True


# --- CORS --------------------------------------------------------------------

def parse_cors_origins(raw: str) -> list[str]:
    """Exact origins only: scheme and host, no wildcard, path or credentials."""
    origins = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        parts = urlsplit(item)
        valid = (
            "*" not in item
            and parts.scheme in ("http", "https")
            and parts.hostname
            and not parts.username
            and not parts.password
            and parts.path in ("", "/")
            and not parts.query
            and not parts.fragment
        )
        if not valid:
            logger.warning(f"Ignoring CORS origin {item!r}: only exact scheme://host[:port] origins are accepted.")
            continue
        origins.append(f"{parts.scheme}://{parts.netloc.lower()}")
    return origins
