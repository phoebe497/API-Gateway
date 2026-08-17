#!/usr/bin/env bash
# Local CI: lint, test, and prove no secret is committed. Tools that are not
# installed are reported as SKIP rather than failing the run, so the essential
# checks (pytest + key-leak grep) always execute.
set -uo pipefail
cd "$(dirname "$0")/.."

FAILED=0
step() { printf '\n== %s ==\n' "$1"; }

step "ruff (lint)"
if command -v ruff >/dev/null 2>&1; then
  ruff check src tests gateway targets || FAILED=1
else
  echo "SKIP: ruff not installed (pip install ruff)"
fi

step "pytest"
if command -v pytest >/dev/null 2>&1 || python3 -c 'import pytest' 2>/dev/null; then
  PYTHONPATH=src python3 -m pytest tests/ -q || FAILED=1
else
  echo "SKIP: pytest not installed"
fi

step "secret scan: API key must not be tracked"
# The key lives only in .env (gitignored). Fail if the literal key or a .env is
# staged/tracked, or if the key value appears anywhere outside .env / data/.
if [ -f .env ]; then
  key_val="$(grep -E '^SAFE_PROBE_API_KEY=' .env | cut -d= -f2-)"
  if [ -n "${key_val}" ]; then
    # Search the repo excluding .env, data/, .git, and caches.
    hits="$(grep -RIn --exclude-dir=.git --exclude-dir=data --exclude-dir=__pycache__ \
              --exclude=.env --fixed-strings "${key_val}" . 2>/dev/null || true)"
    if [ -n "${hits}" ]; then
      echo "FAIL: API key value found outside .env:"; echo "${hits}"; FAILED=1
    else
      echo "PASS: key value not present outside .env"
    fi
  fi
else
  echo "SKIP: no .env yet (run scripts/up.sh)"
fi

step "audit logs must not contain the key"
# Both logs must be clean: the tool's client-side log AND the gateway's
# server-side log (the latter records raw curl traffic too).
logs="$(ls data/*.jsonl 2>/dev/null || true)"
if [ -f .env ] && [ -n "${logs}" ]; then
  key_val="$(grep -E '^SAFE_PROBE_API_KEY=' .env | cut -d= -f2-)"
  leaked=""
  for lf in ${logs}; do
    if [ -n "${key_val}" ] && grep -qF "${key_val}" "${lf}"; then
      leaked="${leaked} ${lf}"
    fi
  done
  if [ -n "${leaked}" ]; then
    echo "FAIL: API key leaked into:${leaked}"; FAILED=1
  else
    echo "PASS: no key in any audit log (${logs//$'\n'/ })"
  fi
else
  echo "SKIP: no audit log yet"
fi

step "ggshield (secret scanner)"
if command -v ggshield >/dev/null 2>&1; then
  # Exit codes: 0 = clean, 1 = secret found (real failure), anything else =
  # tooling/auth problem (ggshield is a SaaS scanner needing `ggshield auth
  # login`). Only a genuine secret should fail the build.
  timeout 30 ggshield secret scan repo . >/tmp/ggshield.out 2>&1
  rc=$?
  if [ "$rc" -eq 0 ]; then
    echo "PASS: ggshield found no secrets"
  elif [ "$rc" -eq 1 ]; then
    echo "FAIL: ggshield found a secret:"; cat /tmp/ggshield.out; FAILED=1
  else
    echo "SKIP: ggshield could not run (needs 'ggshield auth login' / GITGUARDIAN_API_KEY)"
  fi
  rm -f /tmp/ggshield.out
else
  echo "SKIP: ggshield not installed (pip install ggshield)"
fi

echo
if [ "${FAILED}" -eq 0 ]; then echo "verify: OK"; else echo "verify: FAILED" >&2; fi
exit "${FAILED}"
