# M14 – CLINICAL COPILOT (AI HỖ TRỢ BÁC SĨ)

## 14.1. Mục đích & phạm vi

AI hỗ trợ bác sĩ **trước và trong** buổi khám: tóm tắt hồ sơ, phân tích bệnh cảnh, phát hiện dữ liệu thiếu/mâu thuẫn, gợi ý câu hỏi và gợi ý nội dung tư vấn. Định vị: **trợ lý chuẩn bị, không phải công cụ chẩn đoán.** Mọi output là gợi ý cần bác sĩ xác nhận.

**Ngoài phạm vi tuyệt đối:** tự chẩn đoán, tự kê đơn, tự thay đổi thuốc, tự ghi vào hồ sơ, tự quyết định mức khẩn cấp, tư vấn y khoa trực tiếp cho bệnh nhân không qua bác sĩ.

## 14.2. Năng lực chức năng

### AI-01 – Pre-visit Briefing (tóm tắt hồ sơ)
Output có cấu trúc cố định: Bệnh nền → Thuốc đang dùng → Dị ứng → Xét nghiệm gần nhất & xu hướng → Diễn biến từ lần khám trước → **Dữ liệu còn thiếu**. Mỗi mục kèm nguồn (encounter/kết quả nào, ngày nào).

### AI-02 – Phân tích bệnh cảnh
Vấn đề chính; điểm cần chú ý; **mâu thuẫn dữ liệu** (VD: đơn ghi ngừng thuốc nhưng danh sách thuốc còn active); khả năng cần loại trừ (nêu dưới dạng câu hỏi cho bác sĩ, không phải kết luận); nguồn + thời điểm dữ liệu + mức tin cậy.

### AI-03 – Gợi ý câu hỏi khai thác
Câu hỏi kèm lý do, nhóm theo: triệu chứng, diễn biến, thuốc & tuân thủ, lối sống, dấu hiệu cảnh báo.

### AI-04 – Gợi ý nội dung tư vấn
Dàn ý giải thích kết quả, điểm giáo dục bệnh nhân; bác sĩ chọn – sửa – chèn vào note (đánh dấu nguồn gốc AI theo BR-M09-05).

## 14.3. Kiến trúc an toàn (AI-05) – bắt buộc, P0

| Nguyên tắc | Cơ chế enforce |
|---|---|
| Risk priority deterministic | Mức khẩn cấp/cảnh báo do rule engine (M11/M12) quyết định; response LLM không có quyền ghi field ưu tiên |
| Consent gating | Trước mỗi AI call, kiểm tra consent "Cho phép AI phân tích hồ sơ" (M17); thiếu → chặn, thông báo rõ |
| Data minimization | Chỉ gửi dữ liệu trong scope consent + cần thiết cho tác vụ; qua AI provider gateway tập trung |
| Không log PHI | Log kỹ thuật chỉ chứa metadata (tenant, latency, token count, model); prompt/response chứa PHI không ghi vào log thường |
| Structured output | JSON schema validate; fail schema → không hiển thị raw output, trả fallback "AI không khả dụng" |
| Human confirmation | Mọi gợi ý có nút Chấp nhận/Bỏ qua; accept/reject ghi audit event |
| Feature flag | Bật/tắt theo tenant + theo tính năng; **production mặc định OFF** đến khi được phê duyệt vận hành (§25.7 BRD v1.0) |
| Timeout & fallback | Timeout mặc định 20 giây; quá hạn → bác sĩ vẫn xem hồ sơ thường, không chặn khám |
| Quota | Entitlement theo gói (M04) |

## 14.4. User stories

- **US-M14-01:** Là bác sĩ, trước khi gọi bệnh nhân, tôi muốn đọc briefing 30 giây thay vì lật 10 trang hồ sơ (mục tiêu giảm ≥50% thời gian chuẩn bị – KPI pilot).
- **US-M14-02:** Là bác sĩ, tôi muốn thấy dữ liệu mâu thuẫn được gắn nguồn để tự kiểm chứng nhanh.
- **US-M14-03:** Là Clinic Owner, tôi muốn xem thống kê sử dụng AI (lượt gọi, tỷ lệ chấp nhận gợi ý) để đánh giá giá trị.
- **US-M14-04:** Là Platform Admin, tôi muốn tắt khẩn cấp Copilot toàn hệ thống (kill switch) khi phát hiện sự cố chất lượng.

## 14.5. Business rules

- **BR-M14-01 (P0):** Toàn bộ bảng 14.3 là điều kiện chặn go-live; vi phạm bất kỳ dòng nào là P0 finding.
- **BR-M14-02 (P0):** Copilot chỉ khả dụng cho vai trò Doctor, trong ngữ cảnh bệnh nhân thuộc phạm vi của bác sĩ đó.
- **BR-M14-03 (P1):** Mỗi khối output hiển thị disclaimer cố định: "Nội dung do AI tổng hợp để tham khảo, bác sĩ chịu trách nhiệm quyết định lâm sàng."
- **BR-M14-04 (P1):** Phiên bản prompt/model được version hóa; đổi model/prompt trên production cần quy trình phê duyệt + ghi nhận.

## 14.6. Acceptance criteria

- **AC-M14-01:** Thiếu consent AI → nút Copilot disabled kèm lý do; API gọi thẳng → 403.
- **AC-M14-02:** Giả lập LLM trả text tự do sai schema → UI hiển thị fallback, không hiển thị raw.
- **AC-M14-03:** Kiểm tra log production: không tìm thấy PHI trong log AI (test tự động bằng pattern + review mẫu).
- **AC-M14-04:** Accept một gợi ý → audit event có (bác sĩ, bệnh nhân, loại gợi ý, thời điểm).
- **AC-M14-05:** Tắt feature flag tenant → mọi entry point Copilot ẩn/chặn trong ≤ 5 phút.

---

