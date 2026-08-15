# Tuần 4 — API Gateway và kiểm thử request an toàn

- Ngày: 2026-08-12
- Phạm vi: đặt gateway trước ứng dụng thử nghiệm; công cụ Python gửi request qua
  gateway; agent đề xuất request và công cụ thực hiện.

## 1. Kiến trúc

```
                         published :8080
   safe_probe (tool)  ─────────────────────►  gateway  ──►  demo-api
   stdlib-only, biết                          (policy.yml)    (internal: true,
   đúng 1 địa chỉ                              401/403/404/     KHÔNG publish port)
                                               405/413/429/504
```

- `gateway/` — reverse proxy generic, mọi quyết định đọc từ `gateway/policy.yml`.
- `targets/demo-api/` — target chỉ-đọc/phản chiếu (`/health`, `/api/items`,
  `/api/items/{id}`, `/slow`, `/echo`, `/login`).
- `src/safe_probe/` — công cụ Python stdlib-only: `client · limits · payloads ·
  audit · plan · cli`.
- Lý do thiết kế: `docs/adr/0001` (chọn gateway tự viết) và `docs/adr/0002`
  (guardrail hai lớp).

## 2. Bằng chứng theo tiêu chí hoàn thành

> **Bằng chứng tái sinh được.** Mọi output dưới đây được sinh tự động bởi
> `scripts/evidence.sh` và lưu thô trong `reports/evidence/` (xem
> `reports/evidence/00-INDEX.md`). Không chép tay — xoá thư mục và chạy lại
> `bash scripts/evidence.sh` sẽ cho kết quả tương đương. Trích đoạn dưới đây chỉ
> để tiện đọc; nguồn gốc là các file trong `reports/evidence/`.

| Tiêu chí | File bằng chứng |
|---|---|
| Endpoint bị cấm không gọi được | `evidence/07-smoke.txt` (403) |
| Mọi request qua gateway (topology) | `evidence/01-topology.txt` |
| Allowlist do gateway công bố | `evidence/02-routes.txt` |
| Agent đề xuất + công cụ thực hiện | `evidence/03-plan.txt` |
| Bảng suite payload × route | `evidence/04-suite.txt` |
| Nhật ký không lưu key | `evidence/05-redaction.txt` |
| Đủ mã 401/403/404/405/413/429/504 | `evidence/07-smoke.txt` |
| ruff + pytest + quét secret | `evidence/06-verify.txt` |

### 2.1 Không thể gọi trực tiếp endpoint bị cấm

`safe_probe get /ftp` → **403** (không chạm tới upstream):

```
403 {"error":"forbidden: not in allowlist"}
```

Công cụ **không** hard-code allowlist; nó khám phá qua `GET /_gateway/routes`.
Nếu đoán sai path, gateway từ chối — đúng như thiết kế.

### 2.2 Mọi request đều đi qua gateway (bằng chứng topology)

`docker compose ps` — chỉ gateway có port; demo-api trống cột PORTS:

```
SERVICE   STATUS        PORTS
gateway   Up            0.0.0.0:8080->8080/tcp, [::]:8080->8080/tcp
demo-api  Up
```

Thử truy cập thẳng demo-api (`curl http://localhost:8000/health`) → `000`
(unreachable). Không có đường nào tới target ngoài gateway.

### 2.3 Đầy đủ mã từ chối — `scripts/smoke.sh`

```
== gateway policy smoke ==
PASS  401 missing key              401
PASS  403 not in allowlist         403
PASS  404 upstream passthrough     404
PASS  405 wrong method             405
PASS  413 payload too large        413
PASS  504 upstream timeout         504
PASS  429 rate limit (drain)       429
all checks passed
```

### 2.4 Công cụ xử lý lỗi timeout và lỗi kết nối

`safe_probe` trả về kết quả có cấu trúc, phân biệt rõ hai loại lỗi:

- timeout → `error="timeout"`
- mất kết nối → `error="connection error: [Errno 111] Connection refused"`

Được phủ bởi `tests/test_client.py::test_timeout_is_handled` và
`::test_connection_error_is_handled`.

### 2.5 Nhật ký không lưu API key

`data/tool-audit.jsonl` ghi path/status/route/response, nhưng grep giá trị key →
**0** lần. Redaction đặt tại sink (`audit.py::_clean`, quét đệ quy header, field
lồng nhau, và chuỗi phản chiếu). `scripts/verify.sh`:

```
== secret scan: API key must not be tracked ==
PASS: key value not present outside .env
== audit logs must not contain the key ==
PASS: no key in audit log
```

## 3. Demo: Agent đề xuất, công cụ thực hiện

`safe_probe plan --goal "input validation"` — planner (Lớp 2) chỉ phát ra
`route_id + payload_id` từ thực đơn gateway công bố; công cụ tra ngược ra path và
thực hiện:

```
# Agent proposes 11 step(s) for goal: 'input validation'
   4. POST route=echo  payload=empty-string     # exercise input handling
   5. POST route=echo  payload=wrong-type-int   # exercise input handling
   ...
# Tool executes (via gateway):
   4. POST /echo  [empty-string]    -> 200 echo
   8. POST /login [empty-string]    -> 422 login   # target từ chối input sai
```

Planner không ghép URL, không đặt header, không thấy key; `plan.validate()` từ
chối mọi id ngoài thực đơn (`tests/test_plan.py`).

## 4. Chất lượng

- `ruff check` — sạch.
- `pytest` — 27/27 pass (payloads, redaction, plan, client, bất biến no-import).

## 5. Cách tái lập

```bash
bash scripts/up.sh                 # sinh key -> .env, dựng gateway + demo-api
set -a; . ./.env; set +a           # nạp SAFE_PROBE_API_KEY cho công cụ
bash scripts/smoke.sh              # 401/403/404/405/413/429/504
PYTHONPATH=src python3 -m safe_probe.cli plan --goal "input validation"
bash scripts/verify.sh             # ruff + pytest + grep key
bash scripts/evidence.sh           # sinh lại toàn bộ bằng chứng -> reports/evidence/
bash scripts/down.sh
```

Lưu ý: `smoke.sh` làm cạn rate bucket ở bước cuối; chờ ~70s trước khi chạy lại.

## 6. Bàn giao

| Sản phẩm | Trạng thái |
|---|---|
| API Gateway hoạt động | ✅ `gateway/` + `docker-compose.yml` |
| Python Tool gửi request qua Gateway | ✅ `src/safe_probe/` |
| Tệp cấu hình allowlist | ✅ `gateway/policy.yml` |
| Nhật ký request và response | ✅ `data/tool-audit.jsonl` |
| Demo Agent đề xuất + công cụ thực hiện | ✅ `safe_probe plan` |

## 7. Hạn chế và bước tiếp theo

- Planner hiện là rule-based (chủ ý — an toàn đến từ thu hẹp đầu ra). Có thể cắm
  LLM thật vào đúng chỗ `plan.propose` mà không đổi bất biến, miễn là đầu ra vẫn
  đi qua `plan.validate`.
- Rate limit và bucket là in-memory theo tiến trình gateway; nếu chạy nhiều
  replica cần một store dùng chung.
- `ggshield` chưa cài trong môi trường; `verify.sh` báo SKIP thay vì fail.
