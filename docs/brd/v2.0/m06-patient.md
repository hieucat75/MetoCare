# M06 – QUẢN LÝ BỆNH NHÂN

## 6.1. Mục đích & phạm vi

Quản lý hồ sơ hành chính và hồ sơ sức khỏe theo thời gian của bệnh nhân; chống trùng; kết nối tài khoản MetoCare Patient; import dữ liệu từ hệ thống cũ. Đây là "single source of truth" về bệnh nhân trong tenant, đồng thời kết nối với hồ sơ cốt lõi cấp platform (BRD v1.0 §8.2).

## 6.2. Actor & quyền

| Actor | Quyền |
|---|---|
| Receptionist | Tạo/sửa hồ sơ hành chính; không xem hồ sơ lâm sàng |
| Nurse | Ghi sinh hiệu, đính kèm kết quả |
| Doctor | Xem/ghi hồ sơ lâm sàng bệnh nhân trong phạm vi phân công |
| Care Coordinator | Xem care context rút gọn |
| Clinic Admin | Merge hồ sơ trùng, import |
| Bệnh nhân (Patient app) | Xem hồ sơ của mình, quản lý consent |

## 6.3. User stories

- **US-M06-01:** Là lễ tân, tôi muốn tạo bệnh nhân mới trong <60 giây với thông tin tối thiểu để không ùn tắc quầy.
- **US-M06-02:** Là lễ tân, khi nhập SĐT đã tồn tại, tôi muốn hệ thống hiển thị hồ sơ nghi trùng để chọn dùng lại thay vì tạo mới.
- **US-M06-03:** Là Clinic Admin, tôi muốn merge hai hồ sơ trùng có kiểm soát, giữ toàn bộ lịch sử và audit.
- **US-M06-04:** Là bác sĩ, tôi muốn xem timeline chỉ số (HbA1c, huyết áp, LDL-C, cân nặng…) theo thời gian để đánh giá diễn biến.
- **US-M06-05:** Là Clinic Admin, tôi muốn import danh sách bệnh nhân từ Excel với preview và báo lỗi từng dòng để chuyển đổi từ hệ thống cũ.
- **US-M06-06:** Là bệnh nhân, tôi muốn kích hoạt tài khoản MetoCare từ lời mời của phòng khám để xem lịch, kết quả và nhận nhắc hẹn.

## 6.4. Cấu trúc hồ sơ sức khỏe (PATIENT-04)

| Nhóm | Nội dung | Người ghi |
|---|---|---|
| Hành chính | Họ tên, SĐT, ngày sinh, giới tính, địa chỉ, người liên hệ khẩn cấp, mã BN | Receptionist |
| Tiền sử | Bệnh nền, phẫu thuật, gia đình | Doctor/Nurse |
| Dị ứng | Chất gây dị ứng, mức độ, phản ứng | Doctor/Nurse |
| Thuốc | Thuốc đang dùng: tên, liều, tần suất, ngày bắt đầu/kết thúc | Doctor |
| Xét nghiệm | Kết quả có cấu trúc: chỉ số, giá trị, đơn vị, khoảng tham chiếu, ngày, nguồn | Nurse/Doctor/OCR |
| Chỉ số sức khỏe | Sinh hiệu, cân nặng, đường huyết mao mạch, HA tại nhà | Nurse/Patient app |
| Chẩn đoán | Mã + mô tả, ngày, trạng thái (active/resolved) | Doctor |
| Encounter & Notes | Xem M09 | Doctor |
| Care plan | Xem M11 | Doctor |
| Tệp đính kèm | Ảnh/PDF kết quả, đơn thuốc cũ; phân loại + ngày | Mọi vai trò lâm sàng |

## 6.5. Luồng nghiệp vụ: Chống trùng (PATIENT-02)

```text
1. Lễ tân nhập SĐT/họ tên + ngày sinh
2. Hệ thống tìm ứng viên trùng theo thứ tự ưu tiên:
   a. SĐT trùng chính xác        → cảnh báo mức CAO
   b. Email trùng                 → cảnh báo mức CAO
   c. CCCD trùng (nếu được lưu)   → cảnh báo mức CAO
   d. Họ tên chuẩn hóa + ngày sinh→ cảnh báo mức TRUNG BÌNH
3. Lễ tân chọn: dùng hồ sơ có sẵn / vẫn tạo mới (ghi lý do)
4. Hồ sơ nghi trùng được đưa vào danh sách chờ Admin review merge
```

**Merge có kiểm soát:** chỉ Clinic Admin; chọn hồ sơ chính; toàn bộ encounter/lịch/hóa đơn của hồ sơ phụ trỏ sang hồ sơ chính; hồ sơ phụ chuyển trạng thái Merged (không xóa); có thể un-merge trong 30 ngày; audit đầy đủ. **Không bao giờ auto-merge.**

## 6.6. Luồng nghiệp vụ: Import (PATIENT-05)

```text
1. Admin tải template CSV/XLSX chuẩn
2. Upload file → hệ thống parse, validate từng dòng:
   - Trường bắt buộc, định dạng SĐT/ngày sinh, mã BN unique
   - Đối chiếu trùng với dữ liệu hiện có
3. Màn hình preview: tổng dòng hợp lệ / lỗi / nghi trùng, chi tiết lỗi từng dòng
4. Admin xác nhận import phần hợp lệ hoặc sửa file và upload lại
5. Import chạy background job; thất bại giữa chừng → rollback toàn bộ batch
6. Kết quả: báo cáo import + danh sách nghi trùng cần review
```

## 6.7. Business rules

- **BR-M06-01 (P0):** Hồ sơ bệnh nhân không bị xóa cứng; chỉ Inactive/Merged. Yêu cầu xóa dữ liệu cá nhân của bệnh nhân đi theo quy trình riêng của M17.
- **BR-M06-02 (P0):** Bệnh nhân đa phòng khám: clinic chỉ xem dữ liệu do mình tạo + dữ liệu bệnh nhân consent chia sẻ (M17); mặc định không chia sẻ.
- **BR-M06-03 (P0):** Receptionist không có API trả về nội dung lâm sàng (chẩn đoán, note, kết quả XN).
- **BR-M06-04 (P1):** Mã bệnh nhân sinh tự động theo cấu hình tenant, unique trong tenant, immutable.
- **BR-M06-05 (P1):** Kết quả xét nghiệm nhập tay phải có: tên chỉ số (danh mục chuẩn), giá trị, đơn vị, ngày lấy mẫu; đơn vị lệch danh mục → cảnh báo quy đổi, không auto-đổi.
- **BR-M06-06 (P1):** Danh sách bệnh nhân bắt buộc pagination; không endpoint nào trả toàn bộ dataset.
- **BR-M06-07 (P2):** CCCD chỉ lưu nếu tenant bật tùy chọn và có cơ sở pháp lý; lưu mã hóa, hiển thị che một phần.

## 6.8. Ngoại lệ & edge cases

- Bệnh nhân không có SĐT (người cao tuổi dùng SĐT người thân) → cho phép đánh dấu "SĐT người giám hộ", chống trùng chuyển sang họ tên + ngày sinh.
- Hai bệnh nhân dùng chung một SĐT (vợ chồng) → cảnh báo trùng nhưng cho phép tạo, gắn nhãn quan hệ.
- Import 10.000 dòng → xử lý background, hiển thị tiến độ, không khóa UI.
- Kết quả XN chụp ảnh mờ, OCR confidence thấp → bắt buộc người dùng xác nhận/sửa từng trường trước khi lưu (nhất quán nguyên tắc human-confirmation).

## 6.9. Acceptance criteria

- **AC-M06-01:** Tạo bệnh nhân với 4 trường tối thiểu (họ tên, SĐT, ngày sinh, giới tính) thành công < 60 giây thao tác.
- **AC-M06-02:** Nhập SĐT trùng → cảnh báo hiển thị hồ sơ hiện có trước khi cho tạo mới.
- **AC-M06-03:** Merge rồi un-merge trong 30 ngày khôi phục đúng trạng thái trước merge.
- **AC-M06-04:** Import file có 3 dòng lỗi → 3 dòng bị từ chối kèm lý do, các dòng hợp lệ import đủ; kill job giữa chừng → không có bản ghi nửa vời.
- **AC-M06-05:** Tài khoản Receptionist gọi API chi tiết lâm sàng → 403.
- **AC-M06-06:** Timeline chỉ số hiển thị đúng thứ tự thời gian, đúng đơn vị, kèm khoảng tham chiếu.

## 6.10. Audit

Tạo/sửa hồ sơ, xem hồ sơ lâm sàng (ai xem hồ sơ ai, khi nào), merge/un-merge, import batch, export.

---

