from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from .config import Config
from .limits import Limits, RateGate

# A urllib-only client. It builds URLs by joining the gateway base with the
# caller-supplied path and nothing else: it never talks to a target directly and
# never sees policy. If it guesses a path the gateway forbids, it gets a 4xx and
# that is the correct outcome.


@dataclass
class Result:
    ok: bool
    status: int | None
    body: str
    headers: dict[str, str] = field(default_factory=dict)
    error: str | None = None
    route: str | None = None

    def summary(self) -> str:
        if not self.ok and self.status is None:
            return f"ERROR: {self.error}"
        snippet = self.body[:200].replace("\n", " ")
        route = f" [{self.route}]" if self.route else ""
        return f"{self.status}{route} {snippet}"


class Client:
    def __init__(self, config: Config | None = None, limits: Limits | None = None) -> None:
        self.config = config or Config.from_env()
        self.limits = limits or Limits.from_env()
        self._gate = RateGate(self.limits.rate_per_minute)

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> Result:
        self._gate.wait()
        url = self.config.gateway_url + (path if path.startswith("/") else "/" + path)

        req_headers = {"X-API-Key": self.config.api_key}
        if headers:
            req_headers.update(headers)
        if body is not None:
            req_headers.setdefault("Content-Type", "application/json")

        req = urllib.request.Request(url, data=body, method=method, headers=req_headers)

        try:
            with urllib.request.urlopen(req, timeout=self.limits.timeout_seconds) as resp:
                return self._read(resp)
        except urllib.error.HTTPError as exc:
            # A response WITH a status (401/403/404/405/413/429/504/...). Not a
            # tool failure; it is exactly the signal we probe for.
            return self._read(exc, ok=True)
        except TimeoutError:
            return Result(ok=False, status=None, body="", error="timeout")
        except urllib.error.URLError as exc:
            return Result(ok=False, status=None, body="", error=f"connection error: {exc.reason}")
        except (OSError, ValueError) as exc:
            return Result(ok=False, status=None, body="", error=f"request error: {exc}")

    def _read(self, resp: Any, ok: bool = True) -> Result:
        raw = resp.read(self.limits.max_response_bytes + 1)
        truncated = len(raw) > self.limits.max_response_bytes
        raw = raw[: self.limits.max_response_bytes]
        text = raw.decode("utf-8", errors="replace")
        if truncated:
            text += "\u2026[truncated]"
        headers = {k: v for k, v in resp.headers.items()}
        status = getattr(resp, "status", None) or getattr(resp, "code", None)
        # resp.headers is a case-insensitive message; look the route up there
        # rather than in the plain dict (header names arrive lowercased).
        return Result(
            ok=ok,
            status=status,
            body=text,
            headers=headers,
            route=resp.headers.get("X-Gateway-Route"),
        )

    def get(self, path: str, headers: dict[str, str] | None = None) -> Result:
        return self._request("GET", path, headers=headers)

    def post(
        self,
        path: str,
        payload: Any = None,
        headers: dict[str, str] | None = None,
    ) -> Result:
        body = json.dumps(payload).encode("utf-8") if payload is not None else b"{}"
        return self._request("POST", path, body=body, headers=headers)

    def routes(self) -> Result:
        # Discovery: ask the gateway what it publishes. The tool does not decide.
        return self.get("/_gateway/routes")
