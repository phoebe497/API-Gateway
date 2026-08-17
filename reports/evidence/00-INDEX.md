# Evidence — Tuần 4

Sinh tự động bởi `scripts/evidence.sh` lúc 2026-08-17T10:16:40+07:00.
Tái tạo: `bash scripts/up.sh && set -a; . ./.env; set +a && bash scripts/evidence.sh`

| File | Chứng minh điều gì |
|---|---|
| 01-topology.txt | Chỉ gateway có port; demo-api không truy cập trực tiếp được |
| 02-routes.txt   | Allowlist do gateway công bố (công cụ không hard-code) |
| 03-plan.txt     | Agent đề xuất request, công cụ thực hiện qua gateway |
| 04-suite.txt    | Bảng suite: mọi payload an toàn × mọi route |
| 05-redaction.txt| Cả hai log không lưu API key (grep = 0 + test sentinel) |
| 06-verify.txt   | ruff + pytest (27) + quét secret |
| 07-smoke.txt    | Đủ mã từ chối 401/403/404/405/413/429/504 |
| 08-request-log.txt | Nhật ký request/response phía gateway (who/when/where/method/headers, key đã che) |
