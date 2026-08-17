from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Server-side request/response log. This is deliberately NOT shared with the
# tool's audit module (a separate process): the gateway is the source of truth
# for what actually crossed the boundary, and it must keep working even if the
# tool is buggy or absent (e.g. requests sent with raw curl).
#
# Redaction lives at the sink: every record passes through here before touching
# disk, so no call site can forget to scrub the key. The auth header value is
# always masked, and the live key value is masked wherever else it appears.

REDACTED = "***REDACTED***"


class AuditLog:
    def __init__(self, path: str | Path, secret: str, auth_header: str) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._secret = secret or ""
        self._auth_header = auth_header.lower()
        self._lock = threading.Lock()

    def _redact_headers(self, headers: dict[str, str]) -> dict[str, str]:
        out: dict[str, str] = {}
        for k, v in headers.items():
            if k.lower() == self._auth_header:
                out[k] = REDACTED
            elif self._secret and self._secret in v:
                out[k] = v.replace(self._secret, REDACTED)
            else:
                out[k] = v
        return out

    def write(self, entry: dict[str, Any]) -> None:
        record = {"ts": datetime.now(UTC).isoformat(), **entry}
        if isinstance(record.get("headers"), dict):
            record["headers"] = self._redact_headers(record["headers"])
        line = json.dumps(record, ensure_ascii=False, default=str)
        # Belt and suspenders: scrub the raw key if it slipped into any field.
        if self._secret and self._secret in line:
            line = line.replace(self._secret, REDACTED)
        with self._lock, self._path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
