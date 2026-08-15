from __future__ import annotations

import os
import time
from dataclasses import dataclass

# Client-side limits. These are a courtesy (and a way to observe the gateway's
# own limits without tripping them by accident) NOT a security boundary: the
# gateway enforces the real ones. The tool throttling itself does not make the
# tool trustworthy; only the out-of-process gateway does.

DEFAULT_TIMEOUT_SECONDS = 5.0
DEFAULT_MAX_RESPONSE_BYTES = 65536
DEFAULT_RATE_PER_MINUTE = 30


@dataclass(frozen=True)
class Limits:
    timeout_seconds: float
    max_response_bytes: int
    rate_per_minute: int

    @classmethod
    def from_env(cls) -> Limits:
        return cls(
            timeout_seconds=float(
                os.environ.get("SAFE_PROBE_TIMEOUT", DEFAULT_TIMEOUT_SECONDS)
            ),
            max_response_bytes=int(
                os.environ.get("SAFE_PROBE_MAX_RESPONSE_BYTES", DEFAULT_MAX_RESPONSE_BYTES)
            ),
            rate_per_minute=int(
                os.environ.get("SAFE_PROBE_RATE_PER_MINUTE", DEFAULT_RATE_PER_MINUTE)
            ),
        )


class RateGate:
    """Simple client-side spacing so we don't fire faster than N/min."""

    def __init__(self, rate_per_minute: int) -> None:
        self._min_interval = 60.0 / rate_per_minute if rate_per_minute > 0 else 0.0
        self._last = 0.0

    def wait(self) -> None:
        if self._min_interval <= 0:
            return
        now = time.monotonic()
        gap = self._last + self._min_interval - now
        if gap > 0:
            time.sleep(gap)
        self._last = time.monotonic()
