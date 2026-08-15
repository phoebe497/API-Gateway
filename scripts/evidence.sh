#!/usr/bin/env bash
# Regenerate ALL evidence for the Week-4 report into reports/evidence/.
# Evidence must be reproducible, not hand-pasted: anyone can re-run this and get
# the same proof. Nothing here prints the API key (smoke passes it as a header
# but only status codes are captured).
#
# Ordering matters: the rate-limit checks in smoke.sh DRAIN the token bucket, so
# smoke runs LAST. The plan/suite runs use the tool's default client-side pacing
# (== the gateway's refill rate) so they never trip 429 themselves.
set -uo pipefail
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PATH"

if [ ! -f .env ]; then
  echo "no .env; run scripts/up.sh first" >&2
  exit 1
fi
set -a; . ./.env; set +a

OUT="reports/evidence"
mkdir -p "$OUT"
STAMP="$(date -Is)"

hdr() { printf '===============================================================\n# %s\n# command : %s\n# captured: %s\n===============================================================\n\n' "$1" "$2" "$STAMP"; }

echo "[evidence] 01 topology"
{
  hdr "Topology proof: only the gateway publishes a port" "docker compose ps"
  docker compose ps --format 'table {{.Service}}\t{{.Status}}\t{{.Ports}}'
  echo
  echo "# demo-api must be UNREACHABLE directly (no published port):"
  curl -s -m 3 -o /dev/null -w "curl http://localhost:8000/health -> %{http_code} (000 == refused/unreachable)\n" \
    http://localhost:8000/health || echo "curl failed -> unreachable (expected)"
} > "$OUT/01-topology.txt" 2>&1

echo "[evidence] 02 routes (published allowlist)"
{
  hdr "Allowlist the gateway publishes (tool does not hard-code it)" "safe_probe routes"
  PYTHONPATH=src python3 -m safe_probe.cli routes
} > "$OUT/02-routes.txt" 2>&1

echo "[evidence] 03 plan (agent proposes, tool executes)"
{
  hdr "Agent proposes route_id+payload_id, tool resolves & executes" "safe_probe plan --goal 'input validation'"
  SAFE_PROBE_TIMEOUT=8 PYTHONPATH=src python3 -m safe_probe.cli plan --goal "input validation"
} > "$OUT/03-plan.txt" 2>&1

echo "[evidence] 04 suite (every safe payload x route) - this is slow (self-paced)"
{
  hdr "Suite: every safe payload against every allowlisted route" "safe_probe suite"
  SAFE_PROBE_TIMEOUT=8 PYTHONPATH=src python3 -m safe_probe.cli suite
} > "$OUT/04-suite.txt" 2>&1

echo "[evidence] 05 redaction (key must never be logged)"
{
  hdr "Audit log never stores the API key" "grep key in data/tool-audit.jsonl + pytest"
  key_val="$(grep -E '^SAFE_PROBE_API_KEY=' .env | cut -d= -f2-)"
  # grep -c prints 0 AND exits 1 on no match; keep only its stdout.
  count="$(grep -cF "${key_val}" data/tool-audit.jsonl 2>/dev/null || true)"
  echo "occurrences of the live API key in data/tool-audit.jsonl: ${count:-0}  (must be 0)"
  echo
  echo "# a sample audit record (request/response are logged, key is not):"
  tail -n 1 data/tool-audit.jsonl 2>/dev/null || echo "(no audit log yet)"
  echo
  echo "# sentinel-based unit proof:"
  PYTHONPATH=src python3 -m pytest tests/test_redaction.py -v 2>&1 | tail -8
} > "$OUT/05-redaction.txt" 2>&1

echo "[evidence] 06 verify (ruff + pytest + secret scan)"
bash scripts/verify.sh > "$OUT/06-verify.txt" 2>&1 || true

echo "[evidence] 07 smoke (refusal codes; DRAINS the bucket, runs last)"
bash scripts/smoke.sh > "$OUT/07-smoke.txt" 2>&1 || true

# A small index so a human knows what each file proves.
{
  echo "# Evidence — Tuần 4"
  echo
  echo "Sinh tự động bởi \`scripts/evidence.sh\` lúc ${STAMP}."
  echo "Tái tạo: \`bash scripts/up.sh && set -a; . ./.env; set +a && bash scripts/evidence.sh\`"
  echo
  echo "| File | Chứng minh điều gì |"
  echo "|---|---|"
  echo "| 01-topology.txt | Chỉ gateway có port; demo-api không truy cập trực tiếp được |"
  echo "| 02-routes.txt   | Allowlist do gateway công bố (công cụ không hard-code) |"
  echo "| 03-plan.txt     | Agent đề xuất request, công cụ thực hiện qua gateway |"
  echo "| 04-suite.txt    | Bảng suite: mọi payload an toàn × mọi route |"
  echo "| 05-redaction.txt| Nhật ký không lưu API key (grep = 0 + test sentinel) |"
  echo "| 06-verify.txt   | ruff + pytest (27) + quét secret |"
  echo "| 07-smoke.txt    | Đủ mã từ chối 401/403/404/405/413/429/504 |"
} > "$OUT/00-INDEX.md"

echo "[evidence] done -> ${OUT}/"
