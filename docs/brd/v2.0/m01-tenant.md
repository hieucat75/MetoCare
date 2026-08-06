# M01 – QUẢN LÝ TENANT & PHÒNG KHÁM

## 1.1. Mục đích & phạm vi

Cung cấp năng lực khởi tạo, cấu hình và quản lý vòng đời của một phòng khám (tenant) trên nền tảng MetoCare. Đây là module nền tảng của kiến trúc multi-tenant: mọi dữ liệu nghiệp vụ phía sau đều gắn với một `clinic_id`.

**Trong phạm vi:** tạo tenant, cấu hình thông tin/branding, quản lý trạng thái vòng đời, cấu hình chính sách vận hành (giờ làm việc, chính sách hủy lịch, số thứ tự).
**Ngoài phạm vi:** thanh toán subscription (M04), quản lý chi nhánh (M02).

## 1.2. Actor & quyền

| Actor | Quyền chính |
|---|---|
| Platform Super Admin | Tạo/khóa/kích hoạt tenant, xem trạng thái vận hành & audit; **không** mặc định xem nội dung lâm sàng |
| Clinic Owner | Cấu hình phòng khám, xem toàn bộ cấu hình |
| Clinic Admin | Cấu hình vận hành theo phân quyền của Owner |

## 1.3. User stories

- **US-M01-01:** Là Platform Super Admin, tôi muốn tạo tenant phòng khám mới với đầy đủ thông tin pháp lý để đưa phòng khám vào hệ thống.
- **US-M01-02:** Là Clinic Owner, tôi muốn cấu hình logo, màu thương hiệu và nội dung nhắc lịch để thông điệp gửi bệnh nhân mang thương hiệu phòng khám của tôi.
- **US-M01-03:** Là Platform Super Admin, tôi muốn suspend một tenant vi phạm/hết hạn thanh toán mà không mất dữ liệu, để có thể khôi phục khi phòng khám hoàn tất nghĩa vụ.
- **US-M01-04:** Là Clinic Owner, tôi muốn khai báo chính sách hủy lịch (thời hạn tối thiểu, phí nếu có) để hệ thống áp dụng thống nhất.

## 1.4. Luồng nghiệp vụ: Khởi tạo tenant

```text
1. Platform Admin tạo tenant (trạng thái Trial hoặc Active theo hợp đồng)
2. Hệ thống sinh clinic_id, khởi tạo cấu hình mặc định + gói Trial (M04)
3. Hệ thống gửi lời mời kích hoạt cho Clinic Owner (email/SĐT)
4. Owner kích hoạt tài khoản, hoàn tất onboarding checklist:
   a. Thông tin phòng khám  b. Chi nhánh đầu tiên  c. Giờ làm việc
   d. Dịch vụ cơ bản        e. Mời nhân viên
5. Tenant sẵn sàng vận hành
```

## 1.5. Trường dữ liệu chính

| Trường | Kiểu | Bắt buộc | Validation |
|---|---|---|---|
| clinic_id | UUID | ✓ | Hệ thống sinh, immutable |
| name | string(255) | ✓ | Không rỗng |
| legal_name | string(255) |  | |
| clinic_type | enum |  | Phòng khám đa khoa / chuyên khoa / chuỗi |
| specialties | array<enum> | ✓ | Danh mục chuẩn (Nội tiết, Tim mạch, Chuyển hóa…) |
| representative_name | string | ✓ | |
| phone | string | ✓ | Định dạng SĐT VN, unique cảnh báo |
| email | string | ✓ | RFC email |
| address | object | ✓ | Tỉnh/TP, Quận, Địa chỉ chi tiết |
| tax_code | string |  | 10 hoặc 13 số |
| license_no / license_file | string / file |  | Giấy phép hoạt động KCB |
| status | enum | ✓ | Trial / Active / Suspended / Expired / Deactivated |
| branding | object |  | logo, primary_color, display_name |
| cancellation_policy | object |  | min_hours_before, note |
| queue_config | object |  | Cách sinh số thứ tự, reset theo ngày/chi nhánh |

## 1.6. Trạng thái & chuyển trạng thái

```text
Trial ──(kích hoạt hợp đồng)──▶ Active
Trial ──(hết 30 ngày)─────────▶ Expired
Active ──(vi phạm/nợ phí)─────▶ Suspended ──(khắc phục)──▶ Active
Active/Expired ──(chấm dứt)───▶ Deactivated (terminal, chỉ Platform Admin)
```

## 1.7. Business rules

- **BR-M01-01 (P0):** Mọi bản ghi nghiệp vụ phải có `clinic_id`; API không được trả dữ liệu khác `clinic_id` trong session context, kể cả khi client gửi ID khác.
- **BR-M01-02 (P0):** Khi tenant ở trạng thái Suspended/Expired: chặn mọi thao tác ghi nghiệp vụ (tạo lịch, tạo hóa đơn, ghi note…); cho phép đọc ở mức tối thiểu theo chính sách; dữ liệu không bị xóa.
- **BR-M01-03 (P0):** Deactivated là trạng thái cuối; muốn khôi phục phải qua quy trình phê duyệt Platform, có audit.
- **BR-M01-04 (P1):** Thay đổi thông tin pháp lý (tên pháp nhân, MST, giấy phép) chỉ Owner thực hiện và ghi audit đầy đủ giá trị cũ/mới.
- **BR-M01-05 (P1):** Nội dung nhắc lịch tùy biến không được chứa PHI ngoài phạm vi cần thiết (tên, giờ hẹn, chi nhánh); không nhúng chẩn đoán vào SMS/Zalo.

## 1.8. Ngoại lệ & edge cases

- Trùng SĐT/email khi tạo tenant → cảnh báo, cho phép Platform Admin xác nhận override (có audit).
- Tenant bị suspend giữa lúc bệnh nhân đang trong hàng chờ → cho phép hoàn tất các encounter đang mở trong ngày, chặn phát sinh mới.
- Owner mất quyền truy cập email → quy trình chuyển quyền Owner do Platform Admin thực hiện, yêu cầu xác minh.

## 1.9. Acceptance criteria

- **AC-M01-01:** Tạo tenant thành công sinh `clinic_id`, gói Trial và lời mời Owner.
- **AC-M01-02:** Test tự động chứng minh user thuộc clinic A không đọc/ghi được bất kỳ resource nào của clinic B (đổi ID trên request phải trả 403/404).
- **AC-M01-03:** Suspend tenant → mọi API ghi nghiệp vụ trả lỗi có kiểm soát; dữ liệu còn nguyên khi re-activate.
- **AC-M01-04:** Cấu hình branding phản ánh đúng trong thông báo gửi bệnh nhân.

## 1.10. Audit & security

Sự kiện bắt buộc audit: tạo tenant, đổi trạng thái, đổi thông tin pháp lý, đổi chính sách hủy lịch, chuyển quyền Owner. Mỗi event ghi: actor, thời điểm, IP, giá trị trước/sau.

---

