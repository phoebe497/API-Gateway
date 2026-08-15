# API Gateway + safe_probe

Một **API Gateway** đặt trước ứng dụng thử nghiệm, và một **Python tool** chỉ biết
đúng một địa chỉ: gateway. Tool gửi request kiểm thử với payload an toàn; **gateway
là thứ duy nhất quyết định request nào đi tiếp**.

> Luận điểm cốt lõi: *guardrail nằm ngoài tiến trình đang bị kiểm thử.* Một agent
> bị prompt injection có thể tự thuyết phục mình bỏ qua allowlist của chính nó —
> nhưng nó không sửa được cấu hình của một process khác. Chi tiết:
> [`docs/adr/0002`](docs/adr/0002-guardrail-hai-lop.md).

## Kiến trúc

```
   safe_probe (tool)  ──X-API-Key──►  gateway  ──►  demo-api
   stdlib-only,                       (policy.yml,   (internal: true,
   biết 1 URL                          allowlist,     KHÔNG publish port)
                                       401/403/404/
                                       405/413/429/504)
```

- **`gateway/`** — reverse proxy generic (FastAPI). Mọi quyết định (allowlist,
  rate limit, timeout, kích thước) đọc từ [`gateway/policy.yml`](gateway/policy.yml);
  `app.py` không hard-code gì. Công bố allowlist qua `GET /_gateway/routes`.
- **`targets/demo-api/`** — target chỉ-đọc/phản chiếu, nằm trên mạng
  `internal: true` **không publish port** → mọi request đều phải qua gateway.
- **`src/safe_probe/`** — công cụ Python **stdlib-only**: khám phá allowlist từ
  gateway, gửi GET/POST với payload an toàn, xử lý timeout/lỗi kết nối, redact
  API key tại sink khi ghi log.

## Chạy nhanh

Yêu cầu: Docker + Docker Compose, Python 3.11+.

```bash
bash scripts/up.sh                 # sinh API key -> .env, dựng gateway + demo-api
set -a; . ./.env; set +a           # nạp SAFE_PROBE_API_KEY cho công cụ

PYTHONPATH=src python3 -m safe_probe.cli routes                 # allowlist gateway công bố
PYTHONPATH=src python3 -m safe_probe.cli get /api/items         # 200
PYTHONPATH=src python3 -m safe_probe.cli get /ftp               # 403 (bị chặn)
PYTHONPATH=src python3 -m safe_probe.cli post /echo --payload wrong-type-int
PYTHONPATH=src python3 -m safe_probe.cli plan --goal "input validation"   # Agent đề xuất + thực hiện

bash scripts/down.sh               # hạ toàn bộ
```

## Kiểm chứng

```bash
bash scripts/smoke.sh      # chứng minh 401/403/404/405/413/429/504 bằng curl
bash scripts/verify.sh     # ruff + pytest (27) + grep key + ggshield
bash scripts/evidence.sh   # sinh lại toàn bộ bằng chứng -> reports/evidence/
```

Bằng chứng đã chốt: [`reports/evidence/`](reports/evidence/) · Báo cáo:
[`reports/2026-08-14_...Week4.md`](reports/2026-08-14_NguyenNhuYenPhuong_Week4.md).

## Cấu trúc thư mục

| Thư mục | Chứa gì |
|---|---|
| `gateway/` | Gateway: `app.py` + `policy.yml` + Dockerfile |
| `targets/demo-api/` | Ứng dụng thử nghiệm (FastAPI) |
| `src/safe_probe/` | Công cụ Python: config, client, limits, payloads, audit, plan, cli |
| `scripts/` | Entrypoint bash: up/down/smoke/verify/evidence |
| `docs/` | Quá trình: ADR + onboarding |
| `data/` | Output thô (audit log) — regenerate, không commit |
| `reports/` | Kết quả: báo cáo + bằng chứng |
| `tests/` | pytest |

Người mới nên đọc [`docs/onboarding.md`](docs/onboarding.md) trước.

## Bất biến bảo mật

1. Không publish port của target (bằng chứng topology).
2. `src/safe_probe/` không import `gateway/` (không chia sẻ code).
3. Không hard-code allowlist trong tool — hỏi `GET /_gateway/routes`.
4. Chỉ payload an toàn; SQLi/XSS/traversal bị chặn bởi `FORBIDDEN_PATTERNS`.
5. Không ghi API key ra bất cứ đâu — redaction tại sink (`audit.py`).
6. LLM không tự viết URL — `plan.py` chỉ trả `route_id`/`payload_id`.

Mỗi bất biến được cố định bằng test trong [`tests/`](tests/).
