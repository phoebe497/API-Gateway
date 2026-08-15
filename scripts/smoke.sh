#!/usr/bin/env bash
# Prove, with nothing but curl, that the gateway enforces its policy. Each check
# targets exactly one refusal code. The rate-limit drain is LAST on purpose: it
# empties the token bucket, so re-running immediately will show 429 where you
# expect 403/etc. Wait ~70s between runs (bucket refills at rate_per_minute).
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo "no .env found; run scripts/up.sh first" >&2
  exit 1
fi
set -a; . ./.env; set +a
KEY="${SAFE_PROBE_API_KEY:?SAFE_PROBE_API_KEY missing}"
GW="${SMOKE_GATEWAY_URL:-http://localhost:8080}"

FAILED=0
code() { curl -s -o /dev/null -w "%{http_code}" "$@"; }
check() { # desc expected actual
  if [ "$3" = "$2" ]; then
    printf 'PASS  %-28s %s\n' "$1" "$3"
  else
    printf 'FAIL  %-28s expected %s got %s\n' "$1" "$2" "$3"
    FAILED=1
  fi
}

echo "== gateway policy smoke =="

# 401: no API key at all (auth is checked before anything else).
check "401 missing key" 401 "$(code "$GW/api/items")"

# 403: authenticated, but path is not in the allowlist -> never reaches upstream.
check "403 not in allowlist" 403 "$(code -H "X-API-Key: $KEY" "$GW/ftp")"

# 404: an allowlisted route whose upstream genuinely has no such item.
check "404 upstream passthrough" 404 "$(code -H "X-API-Key: $KEY" "$GW/api/items/999")"

# 405: allowlisted path, wrong verb (GET on a POST-only route).
check "405 wrong method" 405 "$(code -H "X-API-Key: $KEY" "$GW/echo")"

# 413: body larger than limits.max_request_bytes (default 8192).
big="$(python3 -c 'print("A"*9000)')"
check "413 payload too large" 413 \
  "$(code -H "X-API-Key: $KEY" -H "Content-Type: application/json" -X POST --data "\"$big\"" "$GW/echo")"

# 504: allowlisted route whose upstream is slower than limits.timeout_seconds.
echo "  (504 check waits for the gateway timeout ...)"
check "504 upstream timeout" 504 "$(code -H "X-API-Key: $KEY" "$GW/slow")"

# 429: drain the token bucket. The final request must be throttled.
last=""
for _ in $(seq 1 130); do last="$(code -H "X-API-Key: $KEY" "$GW/health")"; done
check "429 rate limit (drain)" 429 "$last"

echo
if [ "$FAILED" -eq 0 ]; then
  echo "all checks passed"
else
  echo "some checks FAILED" >&2
fi
exit "$FAILED"
