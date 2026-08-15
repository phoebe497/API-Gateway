from __future__ import annotations

import asyncio
from typing import Any

from fastapi import Body, FastAPI, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# A deliberately boring lab target. Every endpoint is either read-only or a
# reflection: nothing here mutates persistent state, so the safe-probe suite can
# hammer it without ever changing real data. The interesting security property
# lives in the gateway, not here.
app = FastAPI(title="demo-api", docs_url=None, redoc_url=None, openapi_url=None)

_ITEMS: dict[int, dict[str, Any]] = {
    1: {"id": 1, "name": "widget", "price": 9.99},
    2: {"id": 2, "name": "gadget", "price": 19.5},
    3: {"id": 3, "name": "gizmo", "price": 4.0},
}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/items")
def list_items() -> dict[str, Any]:
    return {"items": list(_ITEMS.values())}


@app.get("/slow")
async def slow(ms: int = 6000) -> dict[str, str]:
    # Deliberately slower than the gateway's timeout so the gateway returns 504.
    # Read-only and safe: it just sleeps, touching no data.
    await asyncio.sleep(ms / 1000)
    return {"status": "eventually done"}


@app.get("/big")
async def big(kb: int = 300) -> Response:
    # Returns a body of `kb` kilobytes so the gateway's response-size cap can be
    # observed (it truncates and sets X-Truncated). Read-only, no data touched.
    kb = max(1, min(kb, 2048))
    return Response(content="X" * (kb * 1024), media_type="text/plain")


@app.get("/status/{code}")
def status_echo(code: int) -> Response:
    # Echoes back an arbitrary HTTP status so the gateway's passthrough of the
    # upstream status can be demonstrated. Invalid codes collapse to 400.
    if not 100 <= code <= 599:
        return JSONResponse({"error": "invalid status", "requested": code}, status_code=400)
    return JSONResponse({"echoed_status": code}, status_code=code)


@app.get("/api/items/{item_id}")
def get_item(item_id: int) -> Response:
    item = _ITEMS.get(item_id)
    if item is None:
        # A genuine upstream 404 the gateway passes through unchanged; this is
        # how the tool observes a 404 that is NOT an allowlist rejection.
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse(item)


@app.post("/echo")
def echo(payload: Any = Body(default=None)) -> dict[str, Any]:
    # Pure reflection. Whatever safe payload the tool sends comes straight back,
    # which lets us prove "the request reached the target" without storing it.
    return {"received": payload}


class Credentials(BaseModel):
    username: str = ""
    password: str = ""


@app.post("/login")
def login(_creds: Credentials) -> Response:
    # Always rejects: the lab has no real accounts. A safe POST that exercises an
    # auth path yet changes nothing and leaks nothing.
    return JSONResponse({"error": "invalid credentials"}, status_code=401)
