# Meto AI — Product Specification

> **Phiên bản:** 1.0 | **Ngày:** 2026-06-30 | **Trạng thái:** Approved

---

## 1. Định danh sản phẩm

| Thuộc tính | Giá trị |
|-----------|---------|
| Tên | **Meto** |
| Tagline | AI Health Companion của bạn |
| Không dùng | AI Doctor, Bác sĩ AI, Claude, OpenAI, GPT, Trợ lý AI |
| Ngôn ngữ UI | Tiếng Việt chính, thuật ngữ kỹ thuật tiếng Anh khi cần |

---

## 2. Mascot — Meto Aura

### Mô tả
Meto Aura là một **quả cầu ánh sáng mint**, thiết kế theo phong cách **soft UI / liquid glass**. Aura không có khuôn mặt, không có hình người, không có biểu tượng y tế lạnh lùng. Aura truyền đạt sự hiện diện qua ánh sáng và chuyển động.

### Màu sắc
- **Primary mint:** `#5ECBC8` (teal mint)
- **Light glow:** `#A8EDEA`
- **Deep core:** `#3BB8B5`
- **Background halo:** `rgba(94, 203, 200, 0.15)`
- **Glass surface:** `rgba(255, 255, 255, 0.25)` với `backdrop-filter: blur(12px)`

### Kích thước
| Context | Kích thước |
|---------|-----------|
| Floating button | 56×56px |
| Chat header | 40×40px |
| Thinking indicator | 32×32px |
| Splash/welcome | 96×96px |

### Animation States

| State | Tên | Mô tả animation |
|-------|-----|----------------|
| `idle` | Thở nhẹ | Scale oscillation 1.0 → 1.04 → 1.0, 3s ease-in-out loop, opacity 0.85 → 1.0 |
| `listening` | Sáng nhẹ | Glow radius tăng từ 8px → 16px, brightness +20%, ripple nhẹ từ tâm |
| `thinking` | Ripple/Pulse | 2–3 ripple đồng tâm, mỗi ripple fade out sau 0.8s, staggered delay 0.3s |
| `answering` | Glow mềm | Inner glow pulse, soft shadow blur 20px → 32px → 20px, 1.5s loop |
| `completed` | Tim nhỏ / điểm sáng | Burst nhỏ 4–6 điểm sáng bay ra, tim nhỏ fade in/out tại tâm |

### KHÔNG dùng
- Mascot hình trẻ em, robot, bác sĩ với áo blouse
- Biểu tượng ống nghe (stethoscope), chip AI, dấu thập đỏ
- Cartoon face hoặc emoji-style character

---

## 3. Tính năng (Features) theo Phase

### Phase 1 — Foundation
- [x] Floating "Hỏi Meto" button trên tất cả màn chính
- [x] Chat UI bottom sheet (slide up)
- [x] Meto Aura component (static, idle state)
- [x] Kết nối AI Provider (Claude primary, OpenAI fallback)
- [x] System prompt + safety guardrails cơ bản
- [x] Audit logging cơ bản

### Phase 2 — Context Integration
- [x] Context Engine 9 blocks kết nối data thực
- [x] Quick prompts theo màn hình
- [x] Screen context injection (screen_id, entity_id)
- [x] Chat history (local storage + backend)
- [x] Consent flow trước khi dùng health data cho AI

### Phase 3 — UX Polish
- [x] Meto Aura animations đầy đủ (Framer Motion)
- [x] Memory opt-in flow
- [x] Medical disclaimer tích hợp
- [x] Accessibility pass (touch target, font size, contrast)

### Phase 4 — Safety & Launch
- [x] Safety guardrail testing toàn diện
- [x] Red flag detection và escalation
- [x] Context isolation testing
- [x] Staging deploy + UAT

---

## 4. Vị trí UI & Quick Prompts theo màn hình

### 4.1 Dashboard
- **Vị trí:** Floating button góc dưới phải, `bottom: 88px; right: 16px` (tránh bottom nav)
- **Quick prompts:**
  - "Hôm nay tôi cần chú ý gì?"
  - "Tóm tắt sức khỏe tuần này"
  - "Tôi có việc gì cần làm hôm nay không?"

### 4.2 Labs (Xét nghiệm)
- **Vị trí:** Floating button + inline "Hỏi Meto về kết quả này" button bên cạnh từng kết quả
- **Quick prompts:**
  - "Giải thích kết quả này"
  - "Chỉ số nào cần theo dõi?"
  - "Kết quả này có bình thường không?"
  - "Tôi cần làm gì với kết quả này?"

### 4.3 Medications (Thuốc)
- **Vị trí:** Floating button + inline "Hỏi về thuốc này" bên cạnh mỗi loại thuốc
- **Quick prompts:**
  - "Thuốc này dùng để làm gì?"
  - "Tác dụng phụ cần chú ý?"
  - "Uống thuốc này lúc nào tốt nhất?"
  - "Tôi có quên liều nào không?"

### 4.4 Metrics (Chỉ số sức khỏe)
- **Vị trí:** Floating button + tooltip "Hỏi Meto" khi tap vào điểm dữ liệu trên chart
- **Quick prompts:**
  - "Chỉ số này có đáng lo không?"
  - "Xu hướng của tôi như thế nào?"
  - "Tôi nên làm gì để cải thiện?"
  - "Mức bình thường là bao nhiêu?"

### 4.5 Nutrition (Dinh dưỡng)
- **Vị trí:** Floating button
- **Quick prompts:**
  - "Hôm nay tôi nên ăn gì?"
  - "Thực phẩm nào tốt cho tình trạng của tôi?"
  - "Tôi đã đủ dinh dưỡng hôm nay chưa?"
  - "Thực phẩm nào nên tránh?"

### 4.6 Care Plan (Kế hoạch chăm sóc)
- **Vị trí:** Floating button
- **Quick prompts:**
  - "Tôi còn việc gì chưa làm?"
  - "Nhiệm vụ quan trọng nhất hôm nay là gì?"
  - "Tôi đang theo kế hoạch không?"
  - "Giải thích bước này cho tôi"

### 4.7 Profile (Hồ sơ)
- **Vị trí:** Floating button
- **Quick prompts:**
  - "Hồ sơ sức khỏe của tôi còn thiếu gì?"
  - "Thông tin nào quan trọng cần cập nhật?"
  - "Meto cần biết thêm gì để giúp tôi tốt hơn?"

---

## 5. Luồng UX chi tiết

### 5.1 Luồng chính: User mở chat

```
User tap "Hỏi Meto"
    │
    ▼
Kiểm tra consent (đã consent chưa?)
    │
    ├─ Chưa → Hiện Consent Modal → User đồng ý → Lưu consent
    │
    └─ Đã consent → Bỏ qua
    │
    ▼
ChatSheet slide up (bottom sheet)
    │
    ▼
Meto Aura: idle state (thở nhẹ)
    │
    ▼
Hiện welcome message + quick prompt chips theo screen_id
    │
    ▼
User nhập câu hỏi (hoặc tap quick prompt)
    │
    ▼
Meto Aura: listening → thinking
    │
    ▼
Frontend gọi POST /ai/chat {message, screen_id, entity_id}
    │
    ▼
Backend: thu thập context (9 blocks), assemble prompt
    │
    ▼
Gọi AI Provider (Claude → OpenAI fallback nếu lỗi)
    │
    ▼
Stream response về frontend
    │
    ▼
Meto Aura: answering (glow mềm trong khi stream)
    │
    ▼
Response hoàn chỉnh → Meto Aura: completed (burst nhỏ)
    │
    ▼
Hiện response theo format: Tóm tắt → Giải thích → Việc cần làm → Khi nào gặp bác sĩ
    │
    ▼
Lưu vào chat history + ghi audit log
    │
    ▼
Chờ follow-up hoặc user đóng sheet
```

### 5.2 Luồng Consent

```
Lần đầu dùng Meto (hoặc consent chưa tồn tại)
    │
    ▼
Hiện Consent Modal:
  - Giải thích Meto truy cập dữ liệu gì
  - Link đến Privacy Policy
  - Nút "Đồng ý và tiếp tục" / "Để sau"
    │
    ├─ Từ chối → Meto hoạt động với dữ liệu tối thiểu (không có health data)
    │
    └─ Đồng ý → Lưu user_consent { types: ['health_summary', ...], timestamp, version }
    │
    ▼
Người dùng có thể thu hồi consent bất kỳ lúc nào trong Settings → Privacy → Meto AI
```

### 5.3 Luồng Memory Opt-in

```
Sau 3 lần dùng Meto thành công
    │
    ▼
Hiện Memory prompt:
  "Meto có thể nhớ một số sở thích của bạn để trả lời phù hợp hơn.
   Bạn có muốn bật tính năng này không?"
    │
    ├─ Bật → Thu thập: cách xưng hô, mục tiêu sức khỏe, phong cách trả lời
    │
    └─ Không → Bỏ qua, hỏi lại sau 7 ngày
    │
    ▼
Dữ liệu memory lưu ở backend, user_id làm key
Xóa được trong Settings → Meto AI → Quản lý bộ nhớ
```

---

## 6. Giọng văn theo nhóm người dùng

### 6.1 Xưng hô

| Nhóm | Cách xưng hô |
|------|-------------|
| Nam, 18–40 tuổi | "anh" / "em" (Meto xưng em) |
| Nữ, 18–40 tuổi | "chị" / "em" |
| Nam/nữ, 41–60 tuổi | "anh/chị" / "em" |
| Nam, 61+ tuổi | "bác/chú" / "cháu" |
| Nữ, 61+ tuổi | "bác/cô" / "cháu" |

Khi chưa có thông tin tuổi/giới: dùng "bạn" / "mình" (trung tính, thân thiện).

### 6.2 Câu KHÔNG ĐƯỢC nói (Forbidden phrases)

```
❌ "Tôi chẩn đoán bạn bị..."
❌ "Bạn bị [tên bệnh]..."
❌ "Hãy dừng thuốc [tên thuốc]..."
❌ "Không cần đi khám, chỉ cần..."
❌ "Thuốc [A] tốt hơn thuốc [B] cho trường hợp của bạn"
❌ "Liều lượng nên giảm/tăng xuống..."
❌ "Claude/OpenAI/GPT đã phân tích..."
❌ "Theo dữ liệu AI của tôi..."
```

### 6.3 Câu NÊN nói (Preferred phrases)

```
✅ "Kết quả này cho thấy..."
✅ "Thông thường, chỉ số này có nghĩa là..."
✅ "Bác sĩ của anh/chị có thể giải thích rõ hơn về..."
✅ "Việc tiếp theo anh/chị nên làm là..."
✅ "Nếu anh/chị cảm thấy..., hãy liên hệ bác sĩ ngay"
✅ "Đây là thông tin tham khảo, không thay thế tư vấn y tế"
✅ "Meto thấy trong kế hoạch chăm sóc của anh/chị có..."
```

---

## 7. Response Format chuẩn

Mỗi response của Meto tuân theo cấu trúc 4 phần:

```markdown
**Tóm tắt ngắn** (1–2 câu, bold)
[Câu trả lời trực tiếp, dễ hiểu nhất]

**Giải thích**
[2–4 câu giải thích chi tiết hơn, dùng ngôn ngữ thường ngày]

**Việc nên làm**
- [Bullet 1: hành động cụ thể]
- [Bullet 2]
- [Bullet 3 nếu cần]

**Khi nào gặp bác sĩ**
[Câu rõ ràng về dấu hiệu cần tham khảo bác sĩ]
```

---

*Xem chi tiết kỹ thuật tại: 02_CONTEXT_ENGINE.md, 03_PROMPT_POLICY.md, 05_UI_UX_SPEC.md*
