# Bắt đầu với repo này (đọc trước khi code)

Tài liệu này dành cho người mới: nên đọc gì, theo thứ tự nào, và cách tự kiểm
chứng mọi khẳng định thay vì phải tin lời.

## 1. Một câu để nhớ

**Guardrail nằm ngoài tiến trình bị kiểm thử.** Công cụ Python (`safe_probe`) là
"thứ đang bị test"; nó chỉ biết đúng một địa chỉ là gateway. Gateway — một tiến
trình *khác* — mới là nơi quyết định request nào được đi tiếp. Công cụ không sửa
được cấu hình của gateway, nên dù công cụ có bị chiếm quyền cũng không vượt rào
được. Đây là toàn bộ luận điểm; mọi quy tắc còn lại chỉ để bảo vệ điều này.

## 2. Mô hình tư duy (30 giây)

```
  safe_probe  ──API key──►  gateway  ──►  demo-api
  (stdlib,                  (policy.yml,   (internal: true,
   biết 1 URL)               allowlist)     không publish port)
```

- Công cụ đề xuất → gateway phán xử → target chỉ nhận request đã qua cửa.
- Ba thứ tách biệt cứng: **code** (generic), **policy** (`policy.yml`), **output**
  (`data/`). Đừng trộn chúng.

## 3. Lộ trình đọc (theo thứ tự)

1. `AGENTS.md` — luật chơi và "việc tuyệt đối không làm". Đọc kỹ phần bảng thư mục.
2. `docs/adr/0002-guardrail-hai-lop.md` — *vì sao* có kiến trúc này (đọc trước code).
3. `docs/adr/0001-…` — *vì sao* chọn gateway tự viết thay vì Kong/Nginx.
4. `gateway/policy.yml` — nguồn sự thật về allowlist/limit. Đọc file này là hiểu
   "được phép làm gì".
5. `gateway/app.py` — proxy generic; để ý thứ tự kiểm tra 401 → 429 → 403/405 →
   413 → 504.
6. `src/safe_probe/` — đọc theo mạch: `config` → `client` → `payloads` → `audit`
   → `plan` → `cli`.
7. `targets/demo-api/app.py` — target chỉ-đọc/phản chiếu, cố tình nhàm chán.
8. `reports/2026-08-14_NguyenNhuYenPhuong_Week4.md` + `reports/evidence/` — kết
   quả và bằng chứng.

## 4. Tự kiểm chứng trong 5 phút

```bash
bash scripts/up.sh                 # dựng gateway + demo-api, sinh key -> .env
set -a; . ./.env; set +a           # nạp key cho công cụ
bash scripts/evidence.sh           # sinh lại TOÀN BỘ bằng chứng vào reports/evidence/
bash scripts/down.sh
```

Rồi mở `reports/evidence/00-INDEX.md` — mỗi file chứng minh đúng một điều. Không
tin? Xoá `reports/evidence/` và chạy lại `evidence.sh`; kết quả phải như cũ. Đó
là ý nghĩa của "bằng chứng đáng tin": **tái sinh được, không chép tay**.

## 5. Phân biệt data/ vs reports/ (hay nhầm)

- `data/` = output thô lúc chạy (audit log), **regenerate được**, KHÔNG commit,
  xoá đi không mất gì.
- `reports/` = kết quả cho người đọc: báo cáo + `evidence/` (ảnh chụp bằng chứng
  đã đóng băng) + bảng suite. Được commit.
- Khác nhau ở chỗ: `data/` là "đang chạy", `reports/evidence/` là "đã chốt để
  trình bày".

## 6. Cạm bẫy thường gặp (đều nằm trong AGENTS.md)

- Đừng thêm `ports:` cho target — phá bằng chứng topology.
- Đừng cho `safe_probe` import `gateway/` — guardrail lại chui vào trong tiến trình.
- Đừng hard-code allowlist trong công cụ — nó phải hỏi `GET /_gateway/routes`.
- Đừng để LLM tự ghép URL — `plan.py` chỉ trả `route_id`/`payload_id`.
- Đừng ghi API key ra đâu cả — redaction đặt tại sink `audit.py::_clean`.

## 7. Cách trình bày project cho người khác

Theo trình tự nhân-quả, không theo trình tự file:

1. **Vấn đề**: Tuần 3 để allowlist chung tiến trình với agent → prompt injection
   tự bỏ rào.
2. **Ý tưởng**: tách guardrail ra tiến trình riêng (gateway) + thu hẹp đầu ra của
   planner.
3. **Bằng chứng**: chạy `scripts/evidence.sh`, chỉ vào `reports/evidence/` —
   topology, 7 mã từ chối, redaction, suite.
4. **Giới hạn**: rate limit in-memory; planner rule-based (chủ ý).

Demo sống 3 lệnh: `safe_probe routes` (thực đơn) → `safe_probe get /ftp` (bị chặn
403) → `safe_probe plan --goal "input validation"` (agent đề xuất, công cụ thực
hiện).
