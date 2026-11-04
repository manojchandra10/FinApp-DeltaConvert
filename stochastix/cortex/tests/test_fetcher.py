"""L-08: the ECB fetcher validates its inputs and bounds what a response may cost."""
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from cortex.app.engine import fetcher

CSV = "KEY,TIME_PERIOD,OBS_VALUE\nEXR.D.GBP.EUR.SP00.A,2026-01-02,0.85\nEXR.D.GBP.EUR.SP00.A,2026-01-05,0.86\n"


class _Handler(BaseHTTPRequestHandler):
    hits = []

    def log_message(self, *args):
        pass

    def do_GET(self):
        _Handler.hits.append(self.path)
        if "/D.REDIRECTOK." in self.path:
            self.send_response(302)
            self.send_header("Location", self.path.replace("REDIRECTOK", "GBP"))
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif "/D.REDIRECTEVIL." in self.path:
            self.send_response(302)
            self.send_header("Location", "http://169.254.169.254/latest/meta-data/")
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif "/D.HUGE." in self.path:
            self.send_response(200)
            self.send_header("Content-Length", str(64 * 1024 * 1024))
            self.end_headers()
        elif "/D.STREAM." in self.path:
            self.send_response(200)
            self.end_headers()
            chunk = b"x" * 1024 * 1024
            try:
                for _ in range(40):
                    self.wfile.write(chunk)
            except OSError:
                pass
        elif "/D.SLOW." in self.path:
            self.send_response(200)
            self.send_header("Content-Length", "1000")
            self.end_headers()
            try:
                for _ in range(30):
                    self.wfile.write(b"x")
                    self.wfile.flush()
                    time.sleep(0.5)
            except OSError:
                pass
        else:
            body = CSV.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/csv")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)


@pytest.fixture
def local_ecb(monkeypatch):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(fetcher, "ECB_BASE", f"http://127.0.0.1:{server.server_port}/service/data/EXR")
    monkeypatch.setattr(fetcher.session, "trust_env", False)
    fetcher.clear_cache()
    _Handler.hits.clear()
    yield _Handler.hits
    server.shutdown()
    fetcher.clear_cache()


@pytest.mark.parametrize("ticker", ["EURG/../../x", "EURgbp", "EURGBP&x=1", "EURGBPP", "EUR123"])
def test_malformed_codes_make_no_request(local_ecb, ticker):
    assert fetcher.fetch_data(ticker, start_date="2026-01-01") is None
    assert local_ecb == []


@pytest.mark.parametrize("start", ["2026-13-01", "2026-01-01&x=1", "yesterday", "2026-1-1"])
def test_malformed_dates_make_no_request(local_ecb, start):
    assert fetcher.fetch_data("EURGBP", start_date=start) is None
    assert local_ecb == []


def test_valid_request_still_parses(local_ecb):
    frame = fetcher.fetch_data("EURGBP", start_date="2026-01-01")
    assert list(frame["Close"]) == [0.85, 0.86]


def test_redirect_on_the_same_host_is_followed(local_ecb):
    text = fetcher._download(f"{fetcher.ECB_BASE}/D.REDIRECTOK.EUR.SP00.A", {"format": "csvdata"}, timeout=10)
    assert text == CSV
    assert any("/D.GBP." in hit for hit in local_ecb)


def test_redirect_to_another_host_is_refused(local_ecb):
    started = time.monotonic()
    assert fetcher._download(f"{fetcher.ECB_BASE}/D.REDIRECTEVIL.EUR.SP00.A", {}, timeout=10) is None
    assert time.monotonic() - started < 5


def test_oversized_responses_are_dropped(local_ecb, monkeypatch):
    assert fetcher._download(f"{fetcher.ECB_BASE}/D.HUGE.EUR.SP00.A", {}, timeout=10) is None
    monkeypatch.setattr(fetcher, "MAX_RESPONSE_BYTES", 8 * 1024 * 1024)
    assert fetcher._download(f"{fetcher.ECB_BASE}/D.STREAM.EUR.SP00.A", {}, timeout=20) is None


def test_slow_drip_stops_at_the_deadline(local_ecb):
    started = time.monotonic()
    assert fetcher._download(f"{fetcher.ECB_BASE}/D.SLOW.EUR.SP00.A", {}, timeout=3) is None
    assert time.monotonic() - started < 6


def test_latest_rates_drop_malformed_rows():
    text = (
        "CURRENCY,TIME_PERIOD,OBS_VALUE\n"
        "GBP,2026-11-03,0.85\n"
        "<img src=x>,2026-11-03,1.0\n"
        "USD,2026-11-03<b>,1.1\n"
    )
    assert fetcher._parse_latest_csv(text) == {"GBP": ("2026-11-03", 0.85)}
