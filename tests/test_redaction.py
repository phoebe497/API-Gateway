from __future__ import annotations

import json
from pathlib import Path

from safe_probe.audit import AuditLog

SENTINEL = "SENTINEL-API-KEY-do-not-log-1234567890"


def test_key_never_written_to_log(tmp_path: Path) -> None:
    log_path = tmp_path / "audit.jsonl"
    log = AuditLog(log_path, api_key=SENTINEL)

    # The key shows up in three shapes: a header, a nested field, and buried
    # inside an otherwise-innocent echoed string. All must be redacted.
    log.write(
        {
            "headers": {"X-API-Key": SENTINEL},
            "nested": {"auth": {"token": SENTINEL}},
            "response_snippet": f"server saw key={SENTINEL} in the request",
        }
    )

    raw = log_path.read_text(encoding="utf-8")
    assert SENTINEL not in raw, "API key leaked into the audit log"
    assert "***REDACTED***" in raw


def test_secret_keys_redacted_by_name(tmp_path: Path) -> None:
    log_path = tmp_path / "audit.jsonl"
    # No live key set: redaction must still fire on secret-looking field names.
    log = AuditLog(log_path, api_key="")
    log.write({"authorization": "Bearer abc", "api_key": "xyz", "safe": "keep-me"})

    entry = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert entry["authorization"] == "***REDACTED***"
    assert entry["api_key"] == "***REDACTED***"
    assert entry["safe"] == "keep-me"


def test_timestamp_is_added(tmp_path: Path) -> None:
    log_path = tmp_path / "audit.jsonl"
    AuditLog(log_path).write({"action": "get"})
    entry = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert "ts" in entry and entry["action"] == "get"
