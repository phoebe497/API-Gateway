# Evidence — Tuần 4

Sinh tự động bởi `scripts/evidence.sh` lúc 2026-08-15T14:50:44+07:00.
Tái tạo: `bash scripts/up.sh && set -a; . ./.env; set +a && bash scripts/evidence.sh`

| File | Chứng minh điều gì |
|---|---|
| 01-topology.txt | Chỉ gateway có port; demo-api không truy cập trực tiếp được |
| 02-routes.txt   | Allowlist do gateway công bố (công cụ không hard-code) |
| 03-plan.txt     | Agent đề xuất request, công cụ thực hiện qua gateway |
| 04-suite.txt    | Bảng suite: mọi payload an toàn × mọi route |
| 05-redaction.txt| Nhật ký không lưu API key (grep = 0 + test sentinel) |
| 06-verify.txt   | ruff + pytest (27) + quét secret |
| 07-smoke.txt    | Đủ mã từ chối 401/403/404/405/413/429/504 |
