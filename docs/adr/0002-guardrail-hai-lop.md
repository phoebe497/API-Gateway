# ADR 0002 — Guardrail hai lớp: gateway ngoài tiến trình + planner bị ràng buộc

- Trạng thái: Đã chấp nhận
- Ngày: 2026-08-12

## Bối cảnh

Tuần 3 đặt allowlist ngay trong `llm/agent.py::_build_url` — cùng một tiến trình
đọc response của target vào prompt. Vấn đề: nếu agent bị prompt injection, nó có
thể tự thuyết phục mình bỏ qua chính allowlist của nó. Guardrail và thứ bị canh
giữ nằm chung một tiến trình, nên guardrail vô nghĩa.

Tuần 4 phải cho phép "Agent đề xuất và gửi request kiểm thử", tức là lại có một
lớp ra quyết định có thể bị thao túng. Câu hỏi: đặt guardrail ở đâu để một agent
bị chiếm quyền vẫn không thể vượt rào?

## Quyết định

Tách guardrail thành **hai lớp độc lập**, không lớp nào tin lớp trên nó.

### Lớp 1 — Gateway ngoài tiến trình (bắt buộc)

Gateway là một process riêng (container riêng). Công cụ chỉ biết đúng một địa
chỉ và không import được `gateway/`. Dù công cụ có bị viết lại hoàn toàn, nó vẫn:

- phải gửi đúng API key (sai → 401),
- chỉ chạm được route trong `policy.yml` (ngoài allowlist → 403),
- bị chặn bởi rate/timeout/kích thước.

Đây là ranh giới cứng: một tiến trình không sửa được cấu hình của tiến trình
khác. Bằng chứng topology: target nằm trên network `internal: true`, không
publish port — không có đường nào tới target ngoài gateway.

### Lớp 2 — Planner chỉ được chọn từ thực đơn

`plan.py` là chỗ về sau có thể cắm một LLM thật. Nhưng đầu ra của nó bị giới hạn
thành **ký hiệu**: chỉ `route_id` (có trong policy) và `payload_id` (có trong
catalogue). Planner:

- không ghép URL, không đặt header, không bao giờ nhìn thấy API key;
- không tự chọn được path — `route_id` được executor tra ngược ra path từ **thực
  đơn do gateway công bố**, không phải từ chuỗi planner sinh ra.

`plan.validate()` từ chối bất kỳ bước nào tham chiếu id lạ, bất kể ai sinh ra nó
(luật hôm nay, LLM ngày mai). Ngay cả khi planner bị injection, nó nhiều nhất
chỉ chọn sai món trong một thực đơn nó không viết ra — và gateway (Lớp 1) vẫn là
người quyết định cuối cùng.

## Hệ quả

- Hai lớp thất bại độc lập: phá được planner vẫn vướng gateway; phá được công cụ
  vẫn vướng gateway.
- `payloads.py` chỉ chứa giá trị an toàn; `is_forbidden()` chặn SQLi/XSS/traversal/…
  ở cả thời điểm test lẫn thời điểm dùng (`tests/test_payloads.py`).
- Redaction đặt tại sink (`audit.py::_clean`) nên không chỗ gọi nào làm lộ key
  (`tests/test_redaction.py`).
- Giá phải trả: planner rule-based hiện tại "ngốc" hơn một LLM tự do. Đó là chủ
  ý — sự an toàn đến từ việc thu hẹp đầu ra, không từ việc tin tưởng đầu vào.
