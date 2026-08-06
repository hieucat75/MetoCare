# M03 – NHÂN SỰ, MEMBERSHIP & RBAC

## 3.1. Mục đích & phạm vi

Quản lý danh tính người dùng, quan hệ làm việc (membership) giữa user và phòng khám, vai trò và quyền hạn. Tách bạch hai khái niệm:

- **User account (cấp platform):** một người – một tài khoản, dùng chung trên toàn MetoCare.
- **Membership (cấp tenant):** quan hệ user ↔ clinic, mang vai trò, chi nhánh và trạng thái riêng.

## 3.2. Vai trò chuẩn

| Vai trò | Mô tả ngắn | Giới hạn quan trọng |
|---|---|---|
| Clinic Owner | Chủ phòng khám, toàn quyền trong tenant | Tối thiểu 1 Owner active/tenant |
| Clinic Admin | Quản lý vận hành | Không đổi được Owner |
| Doctor | Khám, ghi chú lâm sàng, Copilot | Chỉ xem bệnh nhân trong phạm vi phân công |
| Nurse | Sinh hiệu, chuẩn bị hồ sơ | Không sửa kết luận bác sĩ |
| Receptionist | Bệnh nhân, lịch, check-in, thu phí cơ bản | Không xem dữ liệu lâm sàng không cần thiết |
| Care Coordinator | Chăm sóc chủ động, Care Gap, CRM | Không xem toàn bộ hồ sơ y tế |
| Accountant | Giao dịch, hóa đơn, công nợ, báo cáo doanh thu | Không truy cập ghi chú lâm sàng |

## 3.3. User stories

- **US-M03-01:** Là Clinic Owner, tôi muốn mời nhân viên qua email/SĐT với vai trò định trước để họ tự kích hoạt tài khoản.
- **US-M03-02:** Là Clinic Admin, tôi muốn gán một user nhiều vai trò (VD: Nurse + Care Coordinator) để phù hợp thực tế nhân sự mỏng.
- **US-M03-03:** Là bác sĩ hợp tác nhiều phòng khám, tôi muốn một tài khoản duy nhất nhưng quyền và dữ liệu tách bạch tuyệt đối giữa các phòng khám.
- **US-M03-04:** Là Clinic Owner, tôi muốn khóa ngay lập tức membership của nhân viên nghỉ việc mà không mất dữ liệu họ đã tạo.

## 3.4. Luồng nghiệp vụ: Mời & kích hoạt nhân viên

```text
1. Owner/Admin tạo lời mời: email/SĐT + vai trò + chi nhánh
2. Hệ thống kiểm tra user đã tồn tại trên platform chưa
   - Đã có: gửi lời mời join clinic → user chấp nhận → membership Active
   - Chưa có: gửi link đăng ký → tạo account → membership Active
3. Lời mời hết hạn sau 7 ngày; có thể thu hồi trước khi được chấp nhận
```

## 3.5. Trường dữ liệu Membership

| Trường | Kiểu | Bắt buộc |
|---|---|---|
| membership_id | UUID | ✓ |
| user_id / clinic_id | UUID | ✓ |
| roles | array<enum> | ✓ (≥1) |
| branches | array<branch_id> | ✓ (≥1) |
| status | enum | Invited / Active / Suspended / Removed |
| doctor_profile_ref | UUID | Bắt buộc nếu role = Doctor |

## 3.6. Business rules

- **BR-M03-01 (P0):** Mọi endpoint phải kiểm tra quyền theo (membership.roles × resource × action) tại backend. Ma trận RBAC chi tiết ở Phụ lục A là nguồn chân lý.
- **BR-M03-02 (P0):** Bác sĩ đa phòng khám: membership, lịch làm việc, danh sách bệnh nhân độc lập theo từng clinic; nghiêm cấm truy vấn chéo.
- **BR-M03-03 (P0):** Suspend membership có hiệu lực tức thời (revoke session/token trong ≤ 60 giây); dữ liệu do user tạo giữ nguyên với attribution cũ.
- **BR-M03-04 (P0):** Không cho tự hạ cấp/khóa Owner cuối cùng của tenant.
- **BR-M03-05 (P1):** Vai trò Doctor yêu cầu hồ sơ bác sĩ (họ tên, số chứng chỉ hành nghề, chuyên khoa). Clinic chịu trách nhiệm xác minh (giả định A-03, BRD v1.0 §20).
- **BR-M03-06 (P1):** Nguyên tắc least-privilege cho dữ liệu lâm sàng: Receptionist/Accountant không có API nào trả về nội dung note, chẩn đoán, kết quả xét nghiệm; Care Coordinator chỉ nhận "care context" rút gọn (M13).

## 3.7. Ngoại lệ & edge cases

- User được mời bằng SĐT nhưng đăng ký bằng email khác → đối chiếu bằng mã lời mời, không auto-merge.
- Một user vừa là bệnh nhân vừa là nhân viên của cùng phòng khám → hai ngữ cảnh tách biệt; giao diện nhân viên không tự hiển thị hồ sơ bệnh nhân của chính họ ngoài quyền vai trò.
- Nhân viên bị khóa đang giữ việc trong Care Gap Queue → task tự chuyển về trạng thái Unassigned để Admin phân công lại.

## 3.8. Acceptance criteria

- **AC-M03-01:** Mỗi vai trò trong Phụ lục A có test khẳng định hành động được phép và test khẳng định hành động bị cấm (403).
- **AC-M03-02:** Suspend membership → token cũ không gọi được API sau tối đa 60 giây.
- **AC-M03-03:** Bác sĩ 2 clinic đăng nhập một tài khoản, chuyển ngữ cảnh, không API nào lộ dữ liệu chéo.
- **AC-M03-04:** Không thể xóa/khóa Owner cuối cùng (lỗi có kiểm soát).

## 3.9. Audit

Mời, chấp nhận, đổi vai trò, đổi chi nhánh, suspend/restore, chuyển Owner. Ghi actor, target, trước/sau.

---

