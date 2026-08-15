#!/usr/bin/env bash
# Live demo for the Week-4 mentor report. Loads the API key once, then runs the
# talking-point steps in order. Add --with-smoke to also prove the refusal codes
# (that step DRAINS the rate bucket, so run it last).
#
#   bash scripts/demo.sh
#   bash scripts/demo.sh --with-smoke
set -uo pipefail
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo "no .env found; run scripts/up.sh first" >&2
  exit 1
fi
set -a; . ./.env; set +a

# No client-side pacing during the demo so it feels snappy; we send far fewer
# than rate_per_minute requests, so the gateway will not 429 us.
export PYTHONPATH=src
export SAFE_PROBE_RATE_PER_MINUTE=0
CLI="python3 -m safe_probe.cli"

step() { echo; echo "════════════════════════════════════════════════════"; echo "▶ $1"; echo "  \$ $2"; echo "════════════════════════════════════════════════════"; }

step "1) Allowlist do gateway công bố (công cụ KHÔNG hard-code)" "$CLI routes"
$CLI routes

step "2) Request hợp lệ đi qua gateway -> 200" "$CLI get /api/items"
$CLI get /api/items

step "3) Endpoint ngoài allowlist bị chặn -> 403 (không tới target)" "$CLI get /ftp"
$CLI get /ftp

step "4) POST payload an toàn (sai kiểu) -> target phản chiếu" "$CLI post /echo --payload wrong-type-int"
$CLI post /echo --payload wrong-type-int

step "5) Agent ĐỀ XUẤT một loạt request an toàn và công cụ THỰC HIỆN" "$CLI plan --goal 'input validation'"
$CLI plan --goal "input validation"

if [ "${1:-}" = "--with-smoke" ]; then
  step "6) Chứng minh đủ mã từ chối 401/403/404/405/413/429/504" "bash scripts/smoke.sh"
  bash scripts/smoke.sh
fi

echo
echo "Demo xong. (Chốt: 'docker compose ps' -> demo-api không có port; curl localhost:8000 -> 000)"
