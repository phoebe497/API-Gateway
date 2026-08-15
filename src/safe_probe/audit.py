from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

# Redaction lives at the sink, not at the call sites. Callers cannot forget to
# redact because they never get the chance: every record passes through _clean
# on its way to disk. tests/test_redaction.py proves it with a sentinel key.

REDACTED = "***REDACTED***"

# Keys whose values are always secrets regardless of content.
_SECRET_KEYS = {"x-api-key", "authorization", "api_key", "apikey", "key", "secret", "token"}


class AuditLog:
    def __init__(self, path: str | os.PathLike[str], api_key: str = "") -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # The live secret value, redacted wherever it appears even inside
        # otherwise-innocent string fields (e.g. an echoed request).
        self._secret = api_key or ""

    def _clean(self, value: Any) -> Any:
        if isinstance(value, dict):
            cleaned: dict[str, Any] = {}
            for k, v in value.items():
                if str(k).lower() in _SECRET_KEYS:
                    cleaned[k] = REDACTED
                else:
                    cleaned[k] = self._clean(v)
            return cleaned
        if isinstance(value, (list, tuple)):
            return [self._clean(v) for v in value]
        if isinstance(value, str):
            if self._secret and self._secret in value:
                return value.replace(self._secret, REDACTED)
            return value
        return value

    def write(self, record: dict[str, Any]) -> None:
        entry = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **record}
        cleaned = self._clean(entry)
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(cleaned, ensure_ascii=False) + "\n")
