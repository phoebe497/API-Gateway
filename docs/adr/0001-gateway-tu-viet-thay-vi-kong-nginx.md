# ADR 0001 — Gateway tự viết (FastAPI) thay vì Kong/Nginx

- Trạng thái: Đã chấp nhận
- Ngày: 2026-08-12

## Bối cảnh

Tuần 4 yêu cầu đặt một API Gateway trước ứng dụng thử nghiệm và cho phép "Kong,
Nginx hoặc một gateway đơn giản". Gateway phải làm bốn việc: xác thực bằng API
key, chỉ cho qua các route trong allowlist, áp giới hạn (rate/timeout/kích
thước), và — điểm cốt lõi của repo — **công bố allowlist ra ngoài** để công cụ
kiểm thử tự khám phá (`GET /_gateway/routes`) thay vì hard-code.

Yêu cầu cuối cùng mới là thứ định hình lựa chọn. Luận điểm của repo (xem ADR
0002) là guardrail phải nằm ngoài tiến trình bị kiểm thử, và công cụ không được
là nguồn sự thật về policy. Để làm được, gateway cần một endpoint trả về danh
sách route ở dạng máy đọc được, sinh trực tiếp từ file policy.

## Các phương án

1. **Kong** — gateway đầy đủ tính năng. Nhưng nặng (cần DB hoặc chế độ
   declarative), và việc phát ra một endpoint `/_gateway/routes` tùy biến từ
   allowlist đòi hỏi plugin. Quá nhiều hạ tầng cho một lab.
2. **Nginx** — nhẹ, làm được auth key + allowlist + rate limit bằng cấu hình.
   Nhưng allowlist nằm trong `nginx.conf`, và để công cụ (và về sau là LLM) chọn
   `route_id` từ một "thực đơn" máy đọc được thì phải tự sinh thêm một endpoint
   JSON song song với cấu hình — dễ lệch nhau, khó kiểm chứng bằng test.
3. **Gateway tự viết (FastAPI + httpx + pyyaml)** — một reverse proxy generic
   đọc toàn bộ quyết định từ `policy.yml`. Cùng một file vừa điều khiển việc chặn
   request, vừa là nguồn cho `/_gateway/routes`. Không có khả năng lệch nhau.

## Quyết định

Chọn **phương án 3**: gateway tự viết bằng FastAPI.

- `gateway/app.py` giữ generic tuyệt đối: mọi hằng số (allowlist, rate, timeout,
  kích thước, tên header key) đều đọc từ `policy.yml`.
- `policy.yml` là nguồn sự thật duy nhất; sửa policy nghĩa là sửa file này,
  không sửa code.
- `/_gateway/routes` sinh thẳng từ danh sách route đã nạp, và cố ý **không** lộ
  `upstream` lẫn giá trị key.

## Hệ quả

- Được: kiểm soát hoàn toàn thứ tự kiểm tra (401 → 429 → 403/405 → 413 → 504),
  và một điểm duy nhất công bố allowlist. `docker-compose.yml` đặt target trên
  network `internal: true` không publish port, biến "mọi request qua gateway"
  thành sự thật topology chứ không phải quy ước.
- Mất: ta tự chịu trách nhiệm cho phần proxy (chuyển tiếp header, cắt body theo
  kích thước, ánh xạ timeout → 504). Đây là code phải test, và đã được phủ bởi
  `scripts/smoke.sh` cùng `tests/`.
- `httpx`/`pyyaml`/`fastapi` chỉ tồn tại bên trong container gateway; công cụ
  `src/safe_probe/` vẫn stdlib-only (bất biến trong `tests/test_no_gateway_import.py`).
