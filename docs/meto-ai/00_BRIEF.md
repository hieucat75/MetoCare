# Meto AI Health Companion — Executive Brief

> **Phiên bản:** 1.0 | **Ngày:** 2026-06-30 | **Trạng thái:** Approved

---

## Meto là gì?

**Meto** là AI Health Companion được tích hợp xuyên suốt toàn bộ nền tảng MetoCare. Meto không phải bác sĩ, không phải chatbot tư vấn chung chung — Meto là người bạn đồng hành sức khỏe thông minh, luôn hiểu người dùng đang ở đâu, đang làm gì, và cần gì ngay lúc đó.

Mỗi khi người dùng mở MetoCare, Meto đã sẵn sàng: biết hồ sơ sức khỏe, thuốc đang dùng, kế hoạch chăm sóc, kết quả xét nghiệm/chỉ số gần nhất, màn hình đang hiển thị, và việc cần làm hôm nay. Người dùng không cần giải thích lại mình là ai hay đang xem gì — Meto đã biết.

---

## Tại sao xây Meto?

### Vấn đề hiện tại

- Người dùng MetoCare thường không hiểu đầy đủ ý nghĩa kết quả xét nghiệm, chỉ số sức khỏe, hay hướng dẫn sử dụng thuốc.
- Thông tin y tế trên ứng dụng hiển thị dữ liệu thô — nhưng thiếu ngữ cảnh để người dùng biết mình cần làm gì tiếp theo.
- Người dùng phải tra Google (thông tin không đáng tin), hỏi bác sĩ qua kênh không chính thức, hoặc bỏ qua.
- Kết quả: lo lắng không cần thiết, hoặc bỏ sót dấu hiệu quan trọng cần theo dõi.

### Giải pháp Meto mang lại

- Giải thích kết quả sức khỏe bằng ngôn ngữ thường ngày, dễ hiểu.
- Nhắc nhở, hướng dẫn theo đúng kế hoạch chăm sóc của từng người.
- Trả lời câu hỏi sức khỏe trong context thực tế của người dùng — không phải câu trả lời chung chung.
- Biết khi nào cần escalate người dùng đến bác sĩ hoặc cấp cứu.

---

## Lợi thế cạnh tranh

| Yếu tố | Meto | Chatbot sức khỏe thông thường |
|--------|------|-------------------------------|
| Context | Biết đầy đủ hồ sơ, thuốc, lab, kế hoạch | Hỏi từ đầu mỗi lần |
| Cá nhân hóa | Xưng hô theo tuổi/giới, nhớ phong cách | Generic |
| Tích hợp | Gắn trực tiếp vào từng màn MetoCare | Standalone widget |
| Safety | Hardcoded guardrails, red flag escalation | Tuỳ thuộc model |
| Privacy | Consent gating, audit log, isolation | Thường không có |
| Mascot | Meto Aura — soft UI, không y tế lạnh lùng | Robot, áo blouse |

---

## Nguyên tắc cốt lõi

1. **Ân cần, không phán xét** — Không làm người dùng sợ, không phán xét lối sống.
2. **Dễ hiểu** — Ngôn ngữ thường ngày, tránh thuật ngữ y tế không giải thích.
3. **Tôn trọng bác sĩ** — Meto hỗ trợ, không thay thế. Luôn khuyến khích tham khảo bác sĩ khi cần.
4. **An toàn trước tiên** — Hardcoded: không chẩn đoán, không kê đơn, không đổi liều, không nói "không cần đi khám".
5. **Riêng tư tuyệt đối** — Chỉ truy cập dữ liệu của user đang đăng nhập, có consent, có audit log.
6. **Không lộ nhà cung cấp AI** — Người dùng chỉ thấy "Meto", không thấy Claude, OpenAI, hay GPT.

---

## Out-of-scope (Meto KHÔNG làm)

- ❌ Chẩn đoán bệnh
- ❌ Kê đơn thuốc
- ❌ Đề nghị thay đổi liều lượng thuốc
- ❌ Thay thế tư vấn y tế trực tiếp
- ❌ Truy cập dữ liệu của người dùng khác
- ❌ Lưu trữ nội dung chat mãi mãi (theo data retention policy)
- ❌ Hiển thị tên AI provider (Claude, OpenAI, GPT, v.v.)

---

## Tóm tắt kỹ thuật

- **AI Provider:** Claude (primary) → OpenAI (fallback) qua 9Router; abstraction layer `AIProvider`
- **Backend:** FastAPI (Python), context engine 9 blocks, audit logging
- **Frontend:** Next.js 14 + TypeScript, Tailwind + Soft UI, Framer Motion
- **Deploy:** Azure Container Apps
- **Rollout:** 4 phases × 6 tuần tổng

---

*Tài liệu này là điểm khởi đầu. Chi tiết kỹ thuật xem các file 01–07 trong thư mục này.*
