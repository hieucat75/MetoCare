# M05 – DỊCH VỤ & BẢNG GIÁ

## 5.1. Mục đích & phạm vi

Quản lý danh mục dịch vụ khám/tư vấn, giá, thời lượng và gói chăm sóc dài hạn (3/6/12 tháng) – nền cho đặt lịch (M07), thu phí (M10) và chương trình bệnh mạn (M11).

## 5.2. User stories

- **US-M05-01:** Là Clinic Admin, tôi muốn tạo dịch vụ với giá và thời lượng chuẩn để lễ tân đặt lịch nhất quán.
- **US-M05-02:** Là Clinic Admin, tôi muốn tạo gói "Quản lý Đái tháo đường 6 tháng" gồm 6 lượt khám + 2 lượt đọc xét nghiệm + nhắc thuốc để bán chương trình điều trị.
- **US-M05-03:** Là Clinic Admin, tôi muốn giới hạn dịch vụ theo chi nhánh và theo bác sĩ đủ chuyên môn.

## 5.3. Trường dữ liệu Dịch vụ

| Trường | Kiểu | Bắt buộc | Validation |
|---|---|---|---|
| service_id / clinic_id | UUID | ✓ | |
| name | string | ✓ | Unique trong tenant |
| code | string | ✓ | Unique, [A-Z0-9-] |
| specialty | enum | ✓ | Danh mục chuẩn |
| price | decimal | ✓ | ≥ 0, VND |
| duration_minutes | int | ✓ | 5–240 |
| branches | array | ✓ | ⊆ chi nhánh tenant |
| doctors | array |  | ⊆ bác sĩ tenant |
| type | enum | ✓ | single / package |
| status | enum | ✓ | Active / Inactive |

**Gói chăm sóc (type=package) bổ sung:** duration_months (3/6/12), included_items (số lượt khám, lượt đọc XN, lượt tư vấn từ xa), benefits (nhắc thuốc, nhắc tái khám, theo dõi chỉ số), giá gói, chính sách hoàn khi hủy giữa chừng.

## 5.4. Business rules

- **BR-M05-01 (P0):** Đổi giá dịch vụ không hồi tố: lịch hẹn/hóa đơn đã tạo giữ giá tại thời điểm tạo (lưu snapshot giá).
- **BR-M05-02 (P0):** Mọi thay đổi giá ghi audit (người, thời điểm, giá cũ→mới).
- **BR-M05-03 (P1):** Không Inactive dịch vụ đang có lịch hẹn tương lai nếu chưa xử lý (cảnh báo + danh sách lịch bị ảnh hưởng).
- **BR-M05-04 (P1):** Sử dụng quyền lợi gói phải trừ đúng số lượt còn lại; hết lượt → cảnh báo và chuyển tính phí lẻ theo xác nhận của lễ tân.

## 5.5. Acceptance criteria

- **AC-M05-01:** Đổi giá sau khi đặt lịch → hóa đơn dùng giá cũ.
- **AC-M05-02:** Gói 6 lượt khám: lượt thứ 7 hiển thị cảnh báo hết quyền lợi.
- **AC-M05-03:** Dịch vụ giới hạn chi nhánh A không xuất hiện khi đặt lịch tại chi nhánh B.

---
