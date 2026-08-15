from __future__ import annotations

import re
from typing import Any

# The safe payload catalogue. Everything here probes input handling WITHOUT
# attempting to exploit it: long strings, odd unicode, empty values, wrong
# types, numeric boundaries. If a destructive pattern ever creeps in,
# tests/test_payloads.py turns red. This is an invariant, not a promise.

PAYLOADS: dict[str, Any] = {
    "empty-string": "",
    "empty-object": {},
    "empty-array": [],
    "null": None,
    "long-string": "A" * 5000,
    "special-chars": "!@#$%^&*()_+-=[]{};':\",.<>/?`~\\|",
    "unicode": "こんにちは-🌐-Ωåé-\u200b\u202e",
    "whitespace": "   \t\n\r   ",
    "wrong-type-int": 12345,
    "wrong-type-float": 3.14159,
    "wrong-type-bool": True,
    "wrong-type-list-for-object": [1, 2, 3],
    "int-max": 2**63 - 1,
    "int-min": -(2**63),
    "zero": 0,
    "negative": -1,
    "float-tiny": 1e-308,
    "nested": {"a": {"b": {"c": "A" * 100}}},
}

# Anything resembling an actual attack. These must never appear in a payload
# value. The check is intentionally broad and case-insensitive.
FORBIDDEN_PATTERNS: list[str] = [
    r"(?i)\bunion\b\s+\bselect\b",
    r"(?i)\bselect\b.+\bfrom\b",
    r"(?i)\bdrop\s+table\b",
    r"(?i)or\s+1\s*=\s*1",
    r"--\s*$",
    r"(?i)<script",
    r"(?i)javascript:",
    r"(?i)onerror\s*=",
    r"\.\./",              # path traversal
    r"(?i)\betc/passwd\b",
    r"[;&|`]\s*\w+",       # shell command chaining/injection
    r"\$\(",               # command substitution
    r"(?i)\$\{jndi:",      # log4shell
    r"(?i)\bexec\b|\beval\b",
]

_COMPILED = [re.compile(p) for p in FORBIDDEN_PATTERNS]


def _flatten(value: Any) -> list[str]:
    out: list[str] = []
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, dict):
        for k, v in value.items():
            out.append(str(k))
            out.extend(_flatten(v))
    elif isinstance(value, (list, tuple)):
        for v in value:
            out.extend(_flatten(v))
    else:
        out.append(str(value))
    return out


def is_forbidden(value: Any) -> str | None:
    """Return the offending pattern if `value` contains a forbidden token."""
    for text in _flatten(value):
        for pattern in _COMPILED:
            if pattern.search(text):
                return pattern.pattern
    return None


def get(payload_id: str) -> Any:
    if payload_id not in PAYLOADS:
        raise KeyError(f"unknown payload id: {payload_id!r}")
    value = PAYLOADS[payload_id]
    offending = is_forbidden(value)
    if offending is not None:
        # Belt-and-suspenders: refuse at use-time too, not only in tests.
        raise ValueError(f"payload {payload_id!r} matches forbidden pattern {offending!r}")
    return value


def ids() -> list[str]:
    return sorted(PAYLOADS)
