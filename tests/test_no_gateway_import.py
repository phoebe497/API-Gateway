from __future__ import annotations

from pathlib import Path

# Invariant (AGENTS.md): the tool must not share code with the gateway. If
# safe_probe could import gateway, the guardrail would be back inside the
# process under test. This test scans the source and fails on any such import.

_SRC = Path(__file__).resolve().parents[1] / "src" / "safe_probe"


def test_safe_probe_never_imports_gateway() -> None:
    offenders: list[str] = []
    for path in _SRC.rglob("*.py"):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith(("import gateway", "from gateway")):
                offenders.append(f"{path.name}:{lineno}: {stripped}")
    assert offenders == [], f"safe_probe imports gateway: {offenders}"


def test_safe_probe_is_stdlib_only() -> None:
    # No third-party runtime deps (requests/httpx/yaml/dotenv/LLM SDKs). The
    # tool is the thing under test; its surface must be fully readable.
    banned = ("import requests", "import httpx", "import yaml", "from yaml", "dotenv", "openai", "anthropic")
    offenders: list[str] = []
    for path in _SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in banned:
            if token in text:
                offenders.append(f"{path.name}: {token}")
    assert offenders == [], f"non-stdlib import found in tool: {offenders}"
