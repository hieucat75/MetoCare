# M04 – SUBSCRIPTION & ENTITLEMENT

## 4.1. Mục đích & phạm vi

Quản lý gói dịch vụ của tenant và **enforce entitlement tại backend**: giới hạn số chi nhánh, số bác sĩ, số bệnh nhân active, quyền dùng Clinical Copilot, automation, multi-branch, API…

## 4.2. Cấu trúc gói (kế thừa BRD v1.0 §17)

| Entitlement | Trial | Basic | Professional | Enterprise |
|---|---|---|---|---|
| Chi nhánh | 1 | 1 | ≤3 | Không giới hạn/custom |
| Bác sĩ | 2 | Theo hợp đồng | Theo hợp đồng | Custom |
| Bệnh nhân active | Giới hạn (đề xuất 200) | Theo gói | Theo gói | Custom |
| Lịch hẹn, hồ sơ, note | ✓ | ✓ | ✓ | ✓ |
| Care Gap cơ bản | ✓ | ✓ | ✓ | ✓ |
| Clinical Copilot | Giới hạn lượt | ✗ | ✓ | ✓ |
| CRM chăm sóc + Automation | ✗ | ✗ | ✓ | ✓ |
| Báo cáo nâng cao | ✗ | ✗ | ✓ | ✓ |
| API / SSO / SLA | ✗ | ✗ | ✗ | ✓ |
| Thời hạn | 30 ngày | Theo chu kỳ | Theo chu kỳ | Hợp đồng |

## 4.3. User stories

- **US-M04-01:** Là Platform Admin, tôi muốn gán/đổi gói cho tenant với ngày hiệu lực để phản ánh hợp đồng thương mại.
- **US-M04-02:** Là Clinic Owner, tôi muốn thấy rõ hạn mức đang dùng (số bác sĩ, bệnh nhân, lượt AI) để chủ động nâng gói.
- **US-M04-03:** Là hệ thống, khi tenant chạm hạn mức, tôi phải chặn hành động vượt hạn kèm thông báo hướng dẫn nâng gói, không lỗi mù.

## 4.4. Business rules

- **BR-M04-01 (P0):** Entitlement enforce ở API: request vượt hạn mức trả HTTP 403 + error code `ENTITLEMENT_EXCEEDED` + thông điệp tiếng Việt.
- **BR-M04-02 (P0):** Hạ gói không xóa dữ liệu vượt hạn mức; dữ liệu vượt chuyển read-only cho đến khi nâng gói hoặc giảm sử dụng.
- **BR-M04-03 (P1):** Trial hết hạn → tenant sang Expired theo state machine M01; cảnh báo trước 7, 3, 1 ngày.
- **BR-M04-04 (P1):** Lượt Clinical Copilot được đếm theo AI call thành công; hiển thị quota còn lại cho bác sĩ.

## 4.5. Acceptance criteria

- **AC-M04-01:** Gói Basic gọi API Copilot → 403 `ENTITLEMENT_EXCEEDED`.
- **AC-M04-02:** Tạo bác sĩ thứ 3 trên gói Trial → bị chặn với thông điệp rõ ràng.
- **AC-M04-03:** Hạ gói Professional→Basic khi có 3 chi nhánh → chi nhánh 2,3 read-only, không mất dữ liệu.

---

