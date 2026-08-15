from __future__ import annotations

import json
import socket
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from safe_probe.client import Client
from safe_probe.config import Config
from safe_probe.limits import Limits

# A stdlib stub standing in for the gateway. We test the tool's transport
# behaviour (status handling, truncation, timeout, connection errors) without
# needing Docker or the real gateway.


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args: object) -> None:  # silence
        pass

    def _send(self, code: int, obj: object, extra: dict[str, str] | None = None) -> None:
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/slow":
            time.sleep(2)
            self._send(200, {"ok": True})
        elif self.path == "/big":
            self._send(200, {"data": "X" * 10000})
        elif self.path == "/notfound":
            self._send(404, {"error": "nope"})
        else:
            self._send(200, {"path": self.path}, {"X-Gateway-Route": "stub"})

    def do_POST(self) -> None:
        n = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(n)
        self._send(200, {"received": json.loads(raw or b"null")}, {"X-Gateway-Route": "echo"})


@pytest.fixture()
def server() -> Iterator[str]:
    httpd = HTTPServer(("127.0.0.1", 0), _Handler)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        httpd.shutdown()
        httpd.server_close()


def _client(base: str, **kw: object) -> Client:
    limits = Limits(
        timeout_seconds=float(kw.get("timeout", 5.0)),
        max_response_bytes=int(kw.get("max_bytes", 65536)),
        rate_per_minute=0,  # disable client-side spacing in tests
    )
    return Client(config=Config(gateway_url=base, api_key="k"), limits=limits)


def test_get_ok_and_route_header(server: str) -> None:
    r = _client(server).get("/api/items")
    assert r.ok and r.status == 200
    assert r.route == "stub"
    assert "/api/items" in r.body


def test_post_reflects_payload(server: str) -> None:
    r = _client(server).post("/echo", payload={"x": 1})
    assert r.status == 200
    assert json.loads(r.body)["received"] == {"x": 1}


def test_http_error_status_is_returned_not_raised(server: str) -> None:
    # A 4xx must come back as a Result with a status, NOT raise: the tool probes
    # for these codes, so they are signal, not failure.
    r = _client(server).get("/notfound")
    assert r.ok is True
    assert r.status == 404
    assert "nope" in r.body


def test_response_truncation(server: str) -> None:
    r = _client(server, max_bytes=100).get("/big")
    assert len(r.body) <= 100 + len("\u2026[truncated]")
    assert r.body.endswith("[truncated]")


def test_timeout_is_handled(server: str) -> None:
    r = _client(server, timeout=0.3).get("/slow")
    assert r.ok is False
    assert r.status is None
    assert r.error == "timeout"


def test_connection_error_is_handled() -> None:
    # Bind then close to obtain a definitely-dead port.
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    dead_port = s.getsockname()[1]
    s.close()
    r = _client(f"http://127.0.0.1:{dead_port}").get("/x")
    assert r.ok is False
    assert r.status is None
    assert r.error is not None and "connection error" in r.error
