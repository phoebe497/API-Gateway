from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import yaml
from audit import AuditLog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

# This process is the guardrail. It is intentionally generic: every decision it
# makes (who may call, how often, how big, how long, which routes) comes from
# policy.yml, never from hard-coded constants. The tool being tested runs in a
# different process and cannot edit this file or these variables.

POLICY_PATH = Path(os.environ.get("POLICY_PATH", "/app/policy.yml"))
AUDIT_PATH = Path(os.environ.get("GATEWAY_AUDIT_PATH", "/app/data/gateway-audit.jsonl"))


@dataclass(frozen=True)
class Route:
    id: str
    method: str
    segments: tuple[str, ...]  # literal segment, or "{name}" for a wildcard
    upstream: str

    def match(self, path_segments: tuple[str, ...]) -> dict[str, str] | None:
        if len(path_segments) != len(self.segments):
            return None
        params: dict[str, str] = {}
        for pat, got in zip(self.segments, path_segments):
            if pat.startswith("{") and pat.endswith("}"):
                params[pat[1:-1]] = got
            elif pat != got:
                return None
        return params

    def build_upstream(self, params: dict[str, str]) -> str:
        url = self.upstream
        for name, value in params.items():
            url = url.replace("{" + name + "}", value)
        return url


@dataclass
class Policy:
    auth_header: str
    key_env: str
    rate_per_minute: int
    timeout_seconds: float
    max_request_bytes: int
    max_response_bytes: int
    routes: list[Route]

    @classmethod
    def load(cls, path: Path) -> Policy:
        raw = yaml.safe_load(path.read_text())
        auth = raw["auth"]
        limits = raw["limits"]
        routes = [
            Route(
                id=r["id"],
                method=r["method"].upper(),
                segments=tuple(s for s in r["path"].split("/") if s != ""),
                upstream=r["upstream"],
            )
            for r in raw["routes"]
        ]
        return cls(
            auth_header=auth["header"],
            key_env=auth["key_env"],
            rate_per_minute=int(limits["rate_per_minute"]),
            timeout_seconds=float(limits["timeout_seconds"]),
            max_request_bytes=int(limits["max_request_bytes"]),
            max_response_bytes=int(limits["max_response_bytes"]),
            routes=routes,
        )


@dataclass
class _Bucket:
    tokens: float
    updated: float


@dataclass
class RateLimiter:
    # Token bucket keyed by API key. Capacity == rate_per_minute, refilled at
    # rate_per_minute/60 tokens per second, so a burst is capped and steady
    # state is exactly the configured per-minute rate.
    capacity: int
    _buckets: dict[str, _Bucket] = field(default_factory=dict)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        refill_per_sec = self.capacity / 60.0
        bucket = self._buckets.get(key)
        if bucket is None:
            self._buckets[key] = _Bucket(tokens=self.capacity - 1, updated=now)
            return True
        elapsed = now - bucket.updated
        bucket.tokens = min(self.capacity, bucket.tokens + elapsed * refill_per_sec)
        bucket.updated = now
        if bucket.tokens >= 1.0:
            bucket.tokens -= 1.0
            return True
        return False


policy = Policy.load(POLICY_PATH)
expected_key = os.environ.get(policy.key_env, "")
limiter = RateLimiter(capacity=policy.rate_per_minute)
audit = AuditLog(AUDIT_PATH, secret=expected_key, auth_header=policy.auth_header)

app = FastAPI(title="api-gateway", docs_url=None, redoc_url=None, openapi_url=None)

# Hop-by-hop and identity headers we must not forward upstream.
_STRIP_REQUEST_HEADERS = {"host", "content-length", "connection"}


def _client_key(request: Request) -> str:
    return request.headers.get(policy.auth_header, "")


def _caller(request: Request) -> str | None:
    # Identify the caller without ever logging the key: a short, stable
    # fingerprint of whatever secret was supplied. Absent key -> None.
    supplied = request.headers.get(policy.auth_header, "")
    if not supplied:
        return None
    return "key-" + hashlib.sha256(supplied.encode()).hexdigest()[:8]


def _authorized(request: Request) -> bool:
    # Constant-ish comparison; the key is a shared secret, not a password hash.
    supplied = request.headers.get(policy.auth_header, "")
    return bool(expected_key) and supplied == expected_key


@app.get("/_gateway/health")
def gateway_health() -> dict[str, str]:
    # Unauthenticated liveness probe for compose/healthchecks only.
    return {"status": "ok"}


@app.get("/_gateway/routes")
async def gateway_routes(request: Request) -> Response:
    # The published allowlist. This is how the tool discovers what it may call
    # without ever hard-coding it. Note what is absent: upstreams and the key.
    if not _authorized(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    return JSONResponse(
        {
            "routes": [
                {"id": r.id, "method": r.method, "path": "/" + "/".join(r.segments)}
                for r in policy.routes
            ]
        }
    )


@app.api_route(
    "/{full_path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
)
async def gateway(request: Request, full_path: str) -> Response:
    start = time.monotonic()

    def log(
        response: Response,
        decision: str,
        route: str | None = None,
        upstream: str | None = None,
        req_bytes: int = 0,
        resp_bytes: int = 0,
        truncated: bool = False,
    ) -> Response:
        # One record per request, whatever the outcome. Answers: when, which
        # caller/source, which method, which headers, where it was routed, and
        # what came back. The key is never written (redacted at the sink).
        audit.write(
            {
                "client_ip": request.client.host if request.client else None,
                "caller": _caller(request),
                "method": request.method,
                "path": "/" + full_path,
                "query": dict(request.query_params) or None,
                "route": route,
                "upstream": upstream,
                "decision": decision,
                "status": response.status_code,
                "req_bytes": req_bytes,
                "resp_bytes": resp_bytes,
                "truncated": truncated,
                "duration_ms": round((time.monotonic() - start) * 1000, 1),
                "headers": dict(request.headers),
            }
        )
        return response

    # Reserved control namespace: anything under /_gateway that is not an
    # explicit handler above is simply unknown -> 404 (not an allowlist matter).
    if full_path.startswith("_gateway/") or full_path == "_gateway":
        return log(JSONResponse({"error": "not found"}, status_code=404), "not_found")

    # 1) Authentication.
    if not _authorized(request):
        return log(JSONResponse({"error": "unauthorized"}, status_code=401), "unauthorized")

    # 2) Rate limit (per key).
    if not limiter.allow(_client_key(request)):
        return log(
            JSONResponse({"error": "rate limit exceeded"}, status_code=429), "rate_limited"
        )

    # 3) Allowlist match. Distinguish "path not allowed" (403) from
    #    "path allowed, wrong verb" (405) so failures are diagnosable.
    path_segments = tuple(s for s in full_path.split("/") if s != "")
    path_matched = False
    for route in policy.routes:
        params = route.match(path_segments)
        if params is None:
            continue
        path_matched = True
        if route.method != request.method:
            continue
        response, meta = await _proxy(request, route, params)
        return log(response, **meta)

    if path_matched:
        return log(
            JSONResponse({"error": "method not allowed"}, status_code=405), "method_not_allowed"
        )
    return log(
        JSONResponse({"error": "forbidden: not in allowlist"}, status_code=403), "forbidden"
    )


async def _proxy(
    request: Request, route: Route, params: dict[str, str]
) -> tuple[Response, dict[str, object]]:
    upstream_url = route.build_upstream(params)
    body = await request.body()
    req_bytes = len(body)
    if req_bytes > policy.max_request_bytes:
        return (
            JSONResponse({"error": "payload too large"}, status_code=413),
            {"decision": "payload_too_large", "route": route.id,
             "upstream": upstream_url, "req_bytes": req_bytes},
        )

    fwd_headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower() not in _STRIP_REQUEST_HEADERS
        and k.lower() != policy.auth_header.lower()  # never leak the key upstream
    }

    try:
        async with httpx.AsyncClient(timeout=policy.timeout_seconds) as client:
            upstream = await client.request(
                method=request.method,
                url=upstream_url,
                params=dict(request.query_params),
                headers=fwd_headers,
                content=body if body else None,
            )
    except httpx.TimeoutException:
        return (
            JSONResponse({"error": "upstream timeout"}, status_code=504),
            {"decision": "upstream_timeout", "route": route.id,
             "upstream": upstream_url, "req_bytes": req_bytes},
        )
    except httpx.RequestError:
        return (
            JSONResponse({"error": "upstream unavailable"}, status_code=502),
            {"decision": "upstream_unavailable", "route": route.id,
             "upstream": upstream_url, "req_bytes": req_bytes},
        )

    content = upstream.content
    truncated = len(content) > policy.max_response_bytes
    if truncated:
        content = content[: policy.max_response_bytes]

    out_headers = {"X-Gateway-Route": route.id}
    if truncated:
        out_headers["X-Truncated"] = "true"
    media_type = upstream.headers.get("content-type", "application/octet-stream")
    response = Response(
        content=content,
        status_code=upstream.status_code,
        media_type=media_type,
        headers=out_headers,
    )
    return (
        response,
        {"decision": "proxied", "route": route.id, "upstream": upstream_url,
         "req_bytes": req_bytes, "resp_bytes": len(content), "truncated": truncated},
    )
