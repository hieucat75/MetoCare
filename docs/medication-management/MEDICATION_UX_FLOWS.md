# MEDICATION_UX_FLOWS.md
# MetoCare — Medication Management: UX Flows

**Version:** 1.0  
**Date:** 2026-07-10  
**Target User:** Vietnamese metabolic health patient, 45–70 years old  
**Design Principle:** Patient can use WITHOUT assistance. Large font, simple Vietnamese, clear actions.

---

## 1. Flow Overview

| Flow ID | Flow Name | Phase | Status |
|---------|-----------|-------|--------|
| MF-01 | Add Medication (manual) | P0 | ✅ Exists (partial) |
| MF-02 | Add Medication (from drug catalog) | P0 | ✅ Exists (partial) |
| MF-03 | View Medication Detail | P0 | ❌ Missing |
| MF-04 | Edit Medication | P0 | ✅ Exists |
| MF-05 | Mark Dose Taken / Skipped | P0 | ✅ Exists |
| MF-06 | View Adherence Summary | P0 | ✅ Exists (approximated) |
| MF-07 | Per-Day Adherence History | P1 | ❌ Missing |
| MF-08 | Set Reminder Schedule | P1 | ❌ Missing |
| MF-09 | Add Allergy | P3 | ❌ Missing |
| MF-10 | View Interaction Warnings | P3 | ❌ Missing |
| MF-11 | OCR Prescription Capture | P2 | ❌ Missing |
| MF-12 | Refill Tracking | P4 | ❌ Missing |
| MF-13 | Caregiver View | P4 | ❌ Missing |
| MF-14 | Export for Doctor Visit | P4 | ❌ Missing |
| MF-15 | Supplement / Traditional Medicine Entry | P0 | ❌ Missing |

---

## 2. MF-01 — Add Medication (Manual Entry) [Enhanced]

**Current state:** Exists. Missing: status, start_date, end_date, is_prn, indication, prescribed_by, supplement flag.

### Screen: Add Medication Bottom Sheet

```
┌─────────────────────────────────────────────────────┐
│  ← Thêm thuốc                                   [X] │
├─────────────────────────────────────────────────────┤
│  Tên thuốc *                                         │
│  [Metformin________________________] [🔍 Tìm]        │
│  → Autocomplete dropdown appears                     │
│                                                      │
│  Đây là thực phẩm chức năng / thuốc Đông y?         │
│  [○ Không]  [○ Có]                                   │
│                                                      │
│  Liều dùng                                           │
│  [500mg___________________________]                  │
│                                                      │
│  Tần suất                                            │
│  [2 lần/ngày, sáng & tối__________]                  │
│  → OR: [QD] [BID] [TID] [PRN] chip selector         │
│                                                      │
│  Trạng thái                                          │
│  [● Đang dùng] [○ Tạm dừng] [○ Đã ngừng]           │
│                                                      │
│  Ngày bắt đầu                                        │
│  [Hôm nay ▼]                                         │
│                                                      │
│  Lý do dùng (tùy chọn)                               │
│  [Tiểu đường type 2________________]                 │
│                                                      │
│  Bác sĩ kê đơn (tùy chọn)                           │
│  [BS. Nguyễn Văn A_________________]                 │
│                                                      │
│  Ghi chú (tùy chọn)                                  │
│  [Uống sau ăn sáng________________]                  │
│                                                      │
│  ⚠️ Chỉ dùng thuốc theo chỉ định của bác sĩ.         │
│                                                      │
│  [          LƯU THUỐC          ]                     │
└─────────────────────────────────────────────────────┘
```

**Edge cases:**
- If `is_supplement = Yes` → show supplement_category selector (Thảo dược / Vitamin / Thực phẩm chức năng / Đông y)
- If drug_catalog match found AND allergy conflict → show CRITICAL warning BEFORE save
- If drug_catalog match found AND duplicate ingredient → show HIGH warning BEFORE save
- Patient can proceed past MEDIUM/LOW warnings; CRITICAL blocks save
- Name is the only required field

---

## 3. MF-03 — Medication Detail Screen [NEW]

**Route:** `/medications/[id]`

```
┌─────────────────────────────────────────────────────┐
│  ← Metformin                            [Sửa] [···] │
├─────────────────────────────────────────────────────┤
│  🟢 Đang dùng                                        │
│                                                      │
│  💊 Metformin (Glucophage)                           │
│  Hoạt chất: metformin hydrochloride                  │
│  Nhóm: Biguanide                                     │
│                                                      │
│  ─────────────────────────────────────────────────  │
│  LIỀU DÙNG                                           │
│  500mg — 2 lần/ngày                                  │
│  Sáng sau ăn · Tối sau ăn                            │
│                                                      │
│  ─────────────────────────────────────────────────  │
│  THỜI GIAN                                           │
│  Bắt đầu: 01/01/2026                                 │
│  Bác sĩ kê: BS. Nguyễn Văn A                         │
│                                                      │
│  ─────────────────────────────────────────────────  │
│  TUÂN THỦ HÔM NAY                                    │
│  ✅ Đã uống (08:30)     ○ Chưa uống (tối)           │
│                                                      │
│  ─────────────────────────────────────────────────  │
│  LỊCH SỬ 7 NGÀY                                      │
│  T2  T3  T4  T5  T6  T7  CN                         │
│  ✅  ✅  ✅  ❌  ✅  ✅  ✅                           │
│  Tuần này: 86%                                       │
│                                                      │
│  ─────────────────────────────────────────────────  │
│  ⚠️ CẢNH BÁO [1]                                     │
│  [Mức độ CAO] Warfarin + Aspirin: nguy cơ chảy máu  │
│  → Xem chi tiết                                      │
│                                                      │
│  ─────────────────────────────────────────────────  │
│  [🔔 Đặt nhắc nhở]  [📤 Xuất cho bác sĩ]            │
└─────────────────────────────────────────────────────┘
```

**Actions available from detail screen:**
- Mark dose taken/skipped inline
- Set/edit reminder schedule
- View full adherence history (list of dose events)
- Dismiss MEDIUM/LOW warnings (with acknowledgment)
- Export medication summary
- Soft delete medication (via "···" menu → confirm)

---

## 4. MF-08 — Set Reminder Schedule [NEW — Phase P1]

**Trigger:** Patient taps "Đặt nhắc nhở" from medication detail or list.

```
┌─────────────────────────────────────────────────────┐
│  ← Nhắc nhở thuốc: Metformin                   [X] │
├─────────────────────────────────────────────────────┤
│  Thuốc này uống 2 lần/ngày                          │
│                                                      │
│  Nhắc nhở 1                                          │
│  [08:00 ▼]  Mỗi ngày                                │
│                                                      │
│  Nhắc nhở 2                                          │
│  [20:00 ▼]  Mỗi ngày                                │
│                                                      │
│  [+ Thêm nhắc nhở]                                  │
│                                                      │
│  Thiết bị thông báo:                                 │
│  [● Bật thông báo]  [○ Tắt]                          │
│                                                      │
│  ⚠️ Thông báo sẽ không hiển thị tên liều/tần suất    │
│  để bảo vệ thông tin y tế của bạn.                  │
│                                                      │
│  [          LƯU NHẮC NHỞ          ]                 │
└─────────────────────────────────────────────────────┘
```

**Edge cases:**
- Max 4 reminders per medication
- If `notify_medication = False` in profile settings, show prompt to enable
- Reminder notification: "Đến giờ uống thuốc" (no PHI in notification body)
- Patient can delete individual reminders

---

## 5. MF-09 — Add Allergy [NEW — Phase P3]

**Route:** Patient Profile → "Dị ứng" tab (or accessible from add-medication warning screen)

```
┌─────────────────────────────────────────────────────┐
│  ← Thêm dị ứng                                 [X] │
├─────────────────────────────────────────────────────┤
│  Loại dị ứng *                                       │
│  [● Thuốc]  [○ Thực phẩm]  [○ Khác]                │
│                                                      │
│  Tên chất gây dị ứng *                               │
│  [Penicillin______________________]  [🔍 Tìm]        │
│  → Drug catalog autocomplete                         │
│                                                      │
│  Phản ứng dị ứng                                     │
│  [● Phát ban]  [○ Sốc phản vệ]  [○ Rối loạn tiêu hóa]  [○ Khác]
│                                                      │
│  Mức độ nghiêm trọng                                 │
│  [○ Nhẹ]  [○ Trung bình]  [● Nặng]  [○ Nguy hiểm tính mạng]
│                                                      │
│  Ghi chú (tùy chọn)                                  │
│  [______________________________________]            │
│                                                      │
│  ⚠️ Đây là dị ứng tự báo cáo, chưa xác nhận bởi bác sĩ.
│                                                      │
│  [          LƯU DỊ ỨNG          ]                   │
└─────────────────────────────────────────────────────┘
```

**Post-save action:**
- System immediately runs reverse check: does current medication list contain this allergen?
- If yes → surface CRITICAL warning for each conflicting medication

---

## 6. MF-10 — View Interaction Warnings [NEW — Phase P3]

**Route:** Medication List → Warning Banner → "Xem tất cả cảnh báo"

```
┌─────────────────────────────────────────────────────┐
│  ← Cảnh báo tương tác thuốc                         │
├─────────────────────────────────────────────────────┤
│  🔴 KHẨN CẤP (1)                                    │
│  ┌─────────────────────────────────────────────────┐ │
│  │ ⚠️ Warfarin + Aspirin                           │ │
│  │ Nguy cơ chảy máu nghiêm trọng                  │ │
│  │                                                 │ │
│  │ Warfarin làm loãng máu. Aspirin cũng ức chế    │ │
│  │ tiểu cầu. Dùng chung có thể gây xuất huyết    │ │
│  │ nguy hiểm.                                      │ │
│  │                                                 │ │
│  │ Khuyến nghị: Hỏi ngay bác sĩ về sự an toàn    │ │
│  │ khi dùng hai thuốc này cùng nhau.              │ │
│  │                                                 │ │
│  │ Nguồn: MetoCare Drug Catalog v1.0               │ │
│  │ Độ tin cậy bằng chứng: Mức B                   │ │
│  │                                                 │ │
│  │ ❗ Không thể bỏ qua cảnh báo khẩn cấp.         │ │
│  │ [📞 Liên hệ bác sĩ]                            │ │
│  └─────────────────────────────────────────────────┘ │
│                                                      │
│  🟠 MỨC ĐỘ CAO (1)                                  │
│  ┌─────────────────────────────────────────────────┐ │
│  │ ⚠️ Rosuvastatin + Fenofibrate                   │ │
│  │ Nguy cơ bệnh cơ (myopathy)                     │ │
│  │ [Xem chi tiết]          [Tôi đã hỏi bác sĩ ✓] │ │
│  └─────────────────────────────────────────────────┘ │
│                                                      │
│  ⚠️ Đây là cảnh báo tham khảo, không phải chẩn     │
│  đoán y khoa. Luôn hỏi bác sĩ trước khi thay đổi  │
│  thuốc.                                             │
└─────────────────────────────────────────────────────┘
```

---

## 7. MF-11 — OCR Prescription Capture [NEW — Phase P2]

**Trigger:** Medication list FAB → "Chụp đơn thuốc"

### Screen 1: Capture
```
┌─────────────────────────────────────────────────────┐
│  ← Chụp đơn thuốc                              [X] │
├─────────────────────────────────────────────────────┤
│                                                      │
│  Chụp ảnh đơn thuốc của bạn                         │
│                                                      │
│  [    📷 Chụp ảnh    ]  [    🖼️ Chọn từ Album    ]   │
│                                                      │
│  ─────────────────────────────────────────────────  │
│  Hoặc nhập tay:                                      │
│  [    ✍️ Nhập thủ công    ]                           │
│                                                      │
│  ────────────────────────────────────────────────── │
│  ⚠️ Hệ thống sẽ đọc và trích xuất thông tin thuốc. │
│  Bạn PHẢI xác nhận từng thuốc trước khi lưu.       │
│                                                      │
│  Thông tin ảnh của bạn được bảo mật và mã hóa.     │
└─────────────────────────────────────────────────────┘
```

### Screen 2: OCR Review (one medication at a time)
```
┌─────────────────────────────────────────────────────┐
│  ← Kiểm tra thông tin thuốc (1/3)              [X] │
├─────────────────────────────────────────────────────┤
│  Hệ thống đã đọc được:                              │
│                                                      │
│  Tên thuốc *               [Độ chính xác: 95% 🟢]  │
│  [Metformin 500mg__________]                         │
│                                                      │
│  Liều dùng                 [Độ chính xác: 82% 🟡]  │
│  [500mg___________________] Vui lòng kiểm tra lại   │
│                                                      │
│  Tần suất                  [Độ chính xác: 45% 🔴]  │
│  [___________________] Không đọc được — nhập thủ công
│                                                      │
│  Bác sĩ kê đơn             [Độ chính xác: 88% 🟡]  │
│  [BS. Nguyễn Văn A_________]                         │
│                                                      │
│  ─────────────────────────────────────────────────  │
│  Hoạt chất:  metformin hydrochloride                │
│  Nhóm thuốc: Biguanide (tiểu đường type 2)          │
│                                                      │
│  ⚠️ Kiểm tra kỹ thông tin trước khi xác nhận.       │
│                                                      │
│  [    BỎ QUA THUỐC NÀY    ]  [    XÁC NHẬN    ]     │
└─────────────────────────────────────────────────────┘
```

### Screen 3: OCR Summary
```
┌─────────────────────────────────────────────────────┐
│  ← Kết quả đọc đơn thuốc                            │
├─────────────────────────────────────────────────────┤
│  ✅ Đã xác nhận (2):                                 │
│  • Metformin 500mg                                   │
│  • Rosuvastatin 10mg                                 │
│                                                      │
│  ❌ Đã bỏ qua (1):                                   │
│  • Vitamin D3 (không rõ liều)                        │
│                                                      │
│  ⚠️ Phát hiện cảnh báo:                              │
│  [Mức CAO] Rosuvastatin + Fenofibrate               │
│                                                      │
│  [    LƯU VÀO DANH SÁCH THUỐC    ]                  │
└─────────────────────────────────────────────────────┘
```

---

## 8. MF-12 — Refill Tracking [NEW — Phase P4]

**Trigger:** Medication detail → "Tái khám / Cấp thêm"

```
┌─────────────────────────────────────────────────────┐
│  ← Theo dõi lấy thuốc: Metformin               [X] │
├─────────────────────────────────────────────────────┤
│  Số ngày thuốc còn lại (ước tính): 12 ngày          │
│  ██████████░░░░░░░░░░                                │
│                                                      │
│  ─────────────────────────────────────────────────  │
│  THÊM LẦN LẤY THUỐC                                 │
│                                                      │
│  Ngày lấy: [Hôm nay ▼]                              │
│  Số ngày cung cấp: [30_] ngày                        │
│  Số viên: [60____] viên (tùy chọn)                  │
│  Nguồn: [● Nhà thuốc] [○ Phòng khám] [○ Tự mua]    │
│                                                      │
│  [          LƯU          ]                           │
│                                                      │
│  ─────────────────────────────────────────────────  │
│  LỊCH SỬ LẤY THUỐC                                  │
│  15/06/2026 — 30 ngày (Nhà thuốc)                   │
│  15/05/2026 — 30 ngày (Phòng khám)                  │
└─────────────────────────────────────────────────────┘
```

---

## 9. MF-15 — Supplement / Traditional Medicine Entry [NEW — Phase P0 Enhancement]

When patient selects "Có" to "Thực phẩm chức năng / thuốc Đông y":

```
┌─────────────────────────────────────────────────────┐
│  Phân loại:                                          │
│  [● Thảo dược]  [○ Vitamin/Khoáng chất]             │
│  [○ Thực phẩm chức năng]  [○ Thuốc Đông y]          │
│                                                      │
│  ⚠️ Lưu ý quan trọng:                                │
│  Thực phẩm chức năng và thuốc Đông y có thể tương   │
│  tác với thuốc điều trị. Luôn báo đầy đủ cho bác   │
│  sĩ biết những gì bạn đang dùng.                    │
│                                                      │
│  Bằng chứng khoa học về sản phẩm này còn hạn chế.  │
└─────────────────────────────────────────────────────┘
```

---

## 10. Medication List — Enhanced State

### Warning Banner (top of list when warnings exist)
```
┌─────────────────────────────────────────────────────┐
│  ⚠️ 1 cảnh báo tương tác thuốc KHẨN CẤP            │
│  [Xem chi tiết →]                                   │
└─────────────────────────────────────────────────────┘
```

### Medication Row — Enhanced
```
┌─────────────────────────────────────────────────────┐
│  💊 Metformin                         [Sửa] [Xóa]   │
│  500mg · 2 lần/ngày · Đang dùng                     │
│  Hoạt chất: metformin hydrochloride                  │
│  🟢 Đã uống sáng  ○ Chưa uống tối                   │
│  [✅ Đã uống]  [❌ Bỏ qua]                          │
└─────────────────────────────────────────────────────┘
```

```
┌─────────────────────────────────────────────────────┐
│  💊 Rosuvastatin                  ⚠️ [Sửa] [Xóa]   │
│  10mg · 1 lần/ngày buổi tối · Đang dùng             │
│  ⚠️ Cảnh báo tương tác: Xem chi tiết                │
│  ○ Chưa uống hôm nay                                │
│  [✅ Đã uống]  [❌ Bỏ qua]                          │
└─────────────────────────────────────────────────────┘
```

---

## 11. Accessibility Requirements (Target: 45–70 year old users)

| Element | Minimum Size | Rationale |
|---------|-------------|-----------|
| Medication name | 18px bold | Primary label — must be readable at arm's length |
| Dose/frequency | 16px | Secondary but important |
| Warning text | 16px | Safety-critical — cannot be small |
| Buttons (Taken/Skipped) | 44px min height | Touch target for older users |
| Allergy/warning badges | 15px with color + icon | Never color-only |
| Confirmation prompts | 18px minimum | User must be able to read before confirming |
| All warning banners | Distinct icon + color + text | WCAG 2.1 AA compliance |
