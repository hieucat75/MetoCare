# M02 – QUẢN LÝ CHI NHÁNH

## 2.1. Mục đích & phạm vi

Cho phép một phòng khám vận hành nhiều địa điểm với lịch làm việc, nhân sự, dịch vụ và hàng chờ tách biệt theo chi nhánh, nhưng dùng chung hồ sơ bệnh nhân trong phạm vi tenant.

## 2.2. Actor & quyền

| Actor | Quyền |
|---|---|
| Clinic Owner / Admin | CRUD chi nhánh, gán nhân sự & dịch vụ, tạm dừng chi nhánh |
| Nhân viên đa chi nhánh | Chuyển chi nhánh làm việc trong phạm vi membership |

## 2.3. User stories

- **US-M02-01:** Là Clinic Admin, tôi muốn tạo chi nhánh mới với địa chỉ, giờ làm việc riêng để mở rộng địa điểm khám.
- **US-M02-02:** Là bác sĩ làm việc tại 2 chi nhánh, tôi muốn chuyển ngữ cảnh chi nhánh để xem đúng lịch hẹn và hàng chờ của nơi tôi đang trực.
- **US-M02-03:** Là Clinic Admin, tôi muốn tạm dừng một chi nhánh (sửa chữa/di dời) mà không ảnh hưởng dữ liệu lịch sử.

## 2.4. Trường dữ liệu chính

| Trường | Kiểu | Bắt buộc | Ghi chú |
|---|---|---|---|
| branch_id | UUID | ✓ | |
| clinic_id | UUID | ✓ | FK tenant |
| name | string | ✓ | Unique trong tenant |
| address | object | ✓ | |
| phone | string |  | |
| working_hours | object | ✓ | Theo thứ trong tuần, hỗ trợ ca sáng/chiều |
| status | enum | ✓ | Active / Paused |
| services | array<service_id> |  | Dịch vụ áp dụng tại chi nhánh |
| staff | array<membership_id> |  | Nhân sự được gán |

## 2.5. Business rules

- **BR-M02-01 (P0):** Mọi API có ngữ cảnh chi nhánh phải lấy `branch_id` từ membership/session đã xác thực; `branch_id` do client gửi chỉ dùng để chọn trong tập chi nhánh hợp lệ của user, không được tin tuyệt đối.
- **BR-M02-02 (P0):** Không cho tạo lịch hẹn ngoài giờ làm việc của chi nhánh, trừ khi user có quyền override (ghi audit lý do).
- **BR-M02-03 (P1):** Chi nhánh Paused: chặn tạo lịch mới; lịch đã đặt hiển thị cảnh báo để lễ tân chủ động liên hệ đổi lịch.
- **BR-M02-04 (P1):** Không xóa cứng chi nhánh có dữ liệu lịch sử; chỉ Paused/Archived.

## 2.6. Acceptance criteria

- **AC-M02-01:** Nhân viên chỉ thấy chi nhánh mình được gán; chuyển chi nhánh cập nhật đúng lịch/hàng chờ hiển thị.
- **AC-M02-02:** Gọi API với `branch_id` không thuộc membership → 403.
- **AC-M02-03:** Tạm dừng chi nhánh chặn được lịch mới, không mất lịch cũ.

## 2.7. Audit

Tạo/sửa/tạm dừng chi nhánh, thay đổi gán nhân sự và dịch vụ.

---
