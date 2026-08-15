from __future__ import annotations

import os
from dataclasses import dataclass

# The tool's whole world: one base URL and one secret, both from the
# environment. There is deliberately no way to point it at a target directly.

DEFAULT_GATEWAY_URL = "http://localhost:8080"
API_KEY_ENV = "SAFE_PROBE_API_KEY"
GATEWAY_URL_ENV = "SAFE_PROBE_GATEWAY_URL"
API_KEY_HEADER = "X-API-Key"


@dataclass(frozen=True)
class Config:
    gateway_url: str
    api_key: str

    @classmethod
    def from_env(cls) -> Config:
        return cls(
            gateway_url=os.environ.get(GATEWAY_URL_ENV, DEFAULT_GATEWAY_URL).rstrip("/"),
            api_key=os.environ.get(API_KEY_ENV, ""),
        )
