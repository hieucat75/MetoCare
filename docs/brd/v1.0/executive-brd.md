# BRD – MetoCare Clinic SaaS

## Hệ thống quản lý bệnh nhân mạn tính và tăng tỷ lệ tái khám cho phòng khám Nội tiết – Tim mạch – Chuyển hóa

**Phiên bản:** 1.0
**Trạng thái:** Draft for Approval
**Chủ sở hữu sản phẩm:** MetoCare
**Đối tượng triển khai đầu tiên:** Phòng khám tư nhân chuyên Nội tiết, Đái tháo đường, Tuyến giáp, Tim mạch, Tăng huyết áp, Béo phì và Rối loạn chuyển hóa

---

# 1. Tóm tắt điều hành

MetoCare Clinic SaaS là nền tảng vận hành và quản lý bệnh nhân mạn tính dành cho các phòng khám tư nhân có lượng bệnh nhân tái khám định kỳ.

Sản phẩm không định vị là một HIS/EMR tổng quát thay thế toàn bộ phần mềm phòng khám. Điểm khác biệt trọng tâm là:

> Giúp phòng khám giữ bệnh nhân trong chương trình điều trị, phát hiện bệnh nhân có nguy cơ bỏ theo dõi và giúp bác sĩ hiểu toàn bộ bệnh cảnh trước khi khám.

Hệ thống kết nối bốn năng lực chính:

1. Quản lý hoạt động phòng khám.
2. Quản lý hồ sơ sức khỏe theo thời gian.
3. Quản lý tái khám và chăm sóc bệnh mạn.
4. AI hỗ trợ bác sĩ phân tích hồ sơ và chuẩn bị tư vấn.

---

# 2. Bối cảnh nghiệp vụ

Các phòng khám Nội tiết, Tim mạch và Chuyển hóa thường quản lý bệnh nhân trong thời gian dài. Một bệnh nhân có thể tái khám nhiều lần trong năm, thực hiện nhiều xét nghiệm, thay đổi thuốc và được theo dõi nhiều chỉ số.

Tuy nhiên, dữ liệu hiện thường phân tán trên:

* Hồ sơ giấy.
* Phần mềm thu ngân hoặc đặt lịch.
* Excel.
* Zalo.
* Ảnh kết quả xét nghiệm.
* Đơn thuốc giấy.
* Hệ thống của các bệnh viện và phòng xét nghiệm khác nhau.

Phần lớn phòng khám chưa có công cụ trả lời nhanh các câu hỏi:

* Bệnh nhân nào đã quá hạn tái khám?
* Bệnh nhân nào chưa thực hiện xét nghiệm được chỉ định?
* Chỉ số của ai đang xấu đi?
* Bệnh nhân nào có nguy cơ bỏ điều trị?
* Nhân viên chăm sóc cần gọi ai hôm nay?
* Bác sĩ cần chú ý điều gì trước khi khám?
* Tỷ lệ bệnh nhân quay lại của từng bác sĩ là bao nhiêu?
* Chương trình điều trị nào mang lại kết quả và doanh thu tốt?

---

# 3. Vấn đề cần giải quyết

## 3.1. Đối với chủ phòng khám

* Không kiểm soát được tỷ lệ tái khám.
* Không có danh sách bệnh nhân đang rơi khỏi chương trình điều trị.
* Không đo được hiệu quả chăm sóc bệnh nhân mạn.
* Không kết nối được kết quả điều trị với hiệu quả kinh doanh.
* Không có dashboard thống nhất cho nhiều bác sĩ hoặc nhiều chi nhánh.
* Phụ thuộc vào nhân viên và quy trình thủ công.

## 3.2. Đối với bác sĩ

* Mất thời gian đọc lại nhiều hồ sơ và xét nghiệm.
* Không thấy rõ diễn biến chỉ số theo thời gian.
* Khó nhận biết dữ liệu còn thiếu hoặc mâu thuẫn.
* Khó theo dõi việc bệnh nhân dùng thuốc và thực hiện kế hoạch.
* Ghi chú lâm sàng và kế hoạch chăm sóc thiếu chuẩn hóa.
* Không có AI hỗ trợ trong đúng ngữ cảnh bệnh nhân.

## 3.3. Đối với lễ tân và nhân viên chăm sóc

* Quản lý lịch bằng nhiều công cụ.
* Không biết ưu tiên bệnh nhân nào cần liên hệ.
* Không có kịch bản gọi lại theo từng lý do.
* Không theo dõi được kết quả chăm sóc.
* Dễ bỏ sót bệnh nhân quá hạn tái khám hoặc sắp hết thuốc.

## 3.4. Đối với bệnh nhân

* Không hiểu kết quả xét nghiệm.
* Không nhớ lịch tái khám hoặc lịch xét nghiệm.
* Không biết mục tiêu điều trị.
* Không có một nơi lưu toàn bộ hồ sơ sức khỏe.
* Khó duy trì tuân thủ điều trị dài hạn.

---

# 4. Mục tiêu kinh doanh

## 4.1. Mục tiêu cho phòng khám

* Tăng tỷ lệ bệnh nhân tái khám đúng hạn.
* Giảm tỷ lệ bệnh nhân mất theo dõi.
* Giảm thời gian bác sĩ chuẩn bị trước mỗi lượt khám.
* Tăng số bệnh nhân được chăm sóc chủ động.
* Tăng doanh thu tái khám và doanh thu trên mỗi bệnh nhân.
* Chuẩn hóa quy trình vận hành và chăm sóc bệnh mạn.

## 4.2. Mục tiêu cho MetoCare

* Xây dựng sản phẩm SaaS có doanh thu định kỳ.
* Tạo mô hình B2B2C kết nối phòng khám, bác sĩ và bệnh nhân.
* Tăng lượng hồ sơ sức khỏe được quản lý trên MetoCare.
* Tạo lợi thế cạnh tranh bằng Clinical Copilot và Lab Intelligence.
* Xây dựng mạng lưới phòng khám chuyên khoa có kiểm soát.
* Tạo nền tảng cho marketplace, teleconsultation và thanh toán.

---

# 5. Chỉ số thành công

## 5.1. Chỉ số vận hành phòng khám

* Tỷ lệ bệnh nhân tái khám đúng hạn.
* Tỷ lệ no-show.
* Tỷ lệ lịch được xác nhận.
* Thời gian chờ trung bình.
* Số bệnh nhân được chăm sóc chủ động mỗi tuần.
* Tỷ lệ hoàn thành xét nghiệm theo chỉ định.

## 5.2. Chỉ số lâm sàng

* Tỷ lệ bệnh nhân đạt mục tiêu điều trị.
* Tỷ lệ bệnh nhân có chỉ số cải thiện.
* Tỷ lệ bệnh nhân được cập nhật đầy đủ xét nghiệm.
* Tỷ lệ bệnh nhân có kế hoạch chăm sóc.
* Số cảnh báo lâm sàng được bác sĩ xử lý.

## 5.3. Chỉ số kinh doanh

* Doanh thu tái khám.
* Doanh thu trung bình trên bệnh nhân.
* Tỷ lệ giữ chân bệnh nhân 3, 6 và 12 tháng.
* Số lượt khám trên mỗi bệnh nhân.
* Chi phí chăm sóc trên mỗi lượt tái khám thành công.
* Số phòng khám trả phí.
* MRR và ARR từ Clinic SaaS.

## 5.4. Mục tiêu pilot đề xuất

* Tăng tỷ lệ tái khám ít nhất 15%.
* Giảm no-show ít nhất 20%.
* Giảm thời gian bác sĩ chuẩn bị hồ sơ ít nhất 50%.
* Ít nhất 60% bệnh nhân mạn có kế hoạch tái khám.
* Ít nhất 70% bệnh nhân pilot được số hóa hồ sơ xét nghiệm.

---

# 6. Phạm vi sản phẩm

MetoCare Clinic SaaS gồm ba lớp.

## 6.1. MetoCare Clinic

Dành cho chủ phòng khám, quản lý, lễ tân, điều dưỡng, chăm sóc khách hàng và kế toán.

## 6.2. MetoCare Doctor

Dành cho bác sĩ khám, xem hồ sơ, ghi chú lâm sàng, chỉ định và sử dụng Clinical Copilot.

## 6.3. MetoCare Patient

Dành cho bệnh nhân xem hồ sơ, lịch hẹn, kế hoạch chăm sóc, nhắc thuốc, nhắc xét nghiệm và nội dung tư vấn.

---

# 7. Đối tượng sử dụng

## 7.1. Platform Super Admin

* Quản lý toàn bộ phòng khám trên hệ thống.
* Tạo, khóa hoặc kích hoạt tenant.
* Quản lý gói dịch vụ.
* Xem tình trạng vận hành, không mặc định xem nội dung lâm sàng chi tiết.

## 7.2. Clinic Owner

* Quản lý phòng khám.
* Quản lý chi nhánh, nhân sự, gói dịch vụ và báo cáo.
* Phân quyền Clinic Admin.

## 7.3. Clinic Admin

* Quản lý vận hành.
* Thêm nhân viên, bác sĩ, dịch vụ, lịch làm việc.
* Xem dashboard và báo cáo.

## 7.4. Bác sĩ

* Xem bệnh nhân trong phạm vi được phân công.
* Xem lịch hẹn và hàng chờ.
* Ghi chú lâm sàng.
* Tạo kế hoạch chăm sóc.
* Sử dụng Clinical Copilot.

## 7.5. Điều dưỡng hoặc trợ lý bác sĩ

* Ghi nhận sinh hiệu.
* Chuẩn bị hồ sơ.
* Hỗ trợ theo dõi bệnh nhân.
* Không được sửa kết luận của bác sĩ.

## 7.6. Lễ tân

* Tạo bệnh nhân.
* Đặt lịch, check-in, điều phối hàng chờ.
* Thu phí cơ bản.
* Không được xem dữ liệu lâm sàng không cần thiết.

## 7.7. Nhân viên chăm sóc khách hàng

* Xem danh sách bệnh nhân cần liên hệ.
* Ghi nhận kết quả cuộc gọi.
* Tạo lịch tái khám.
* Không được xem toàn bộ hồ sơ y tế.

## 7.8. Kế toán

* Xem giao dịch, hóa đơn, công nợ và báo cáo doanh thu.
* Không được truy cập ghi chú lâm sàng.

## 7.9. Bệnh nhân

* Xem hồ sơ cá nhân.
* Nhận nhắc lịch, nhắc thuốc, nhắc xét nghiệm.
* Xem nội dung được bác sĩ phê duyệt.

---

# 8. Mô hình multi-tenant

## 8.1. Nguyên tắc

Mỗi phòng khám là một tenant độc lập.

Dữ liệu của phòng khám A không được hiển thị hoặc truy cập từ phòng khám B, kể cả khi người dùng cố tình thay đổi ID trên request.

## 8.2. Dữ liệu toàn cục

Các dữ liệu sau có thể tồn tại ở cấp platform:

* Tài khoản người dùng.
* Hồ sơ cá nhân cốt lõi của bệnh nhân.
* Hồ sơ bác sĩ.
* Danh mục chuẩn.
* Consent của người dùng.
* Tài khoản MetoCare.
* Subscription plan.

## 8.3. Dữ liệu thuộc phòng khám

* Membership.
* Chi nhánh.
* Dịch vụ.
* Bảng giá.
* Lịch làm việc.
* Lịch hẹn.
* Check-in.
* Encounter.
* Ghi chú lâm sàng.
* Kế hoạch chăm sóc của phòng khám.
* Hóa đơn.
* Thanh toán.
* Hoạt động chăm sóc.
* Báo cáo phòng khám.

## 8.4. Bệnh nhân nhiều phòng khám

Một bệnh nhân có thể có quan hệ với nhiều phòng khám.

Mỗi phòng khám chỉ được xem:

* Dữ liệu do phòng khám đó tạo.
* Dữ liệu bệnh nhân cho phép chia sẻ.
* Dữ liệu cần thiết cho consultation hiện tại.
* Dữ liệu thuộc phạm vi consent.

---

# 9. Quy trình nghiệp vụ tổng thể

```text
Thu hút bệnh nhân
→ Tạo hoặc kết nối hồ sơ
→ Đặt lịch
→ Xác nhận
→ Check-in
→ Hàng chờ
→ Bác sĩ xem hồ sơ và AI briefing
→ Khám
→ Ghi chú lâm sàng
→ Kế hoạch chăm sóc
→ Thu phí
→ Nhắc xét nghiệm/thuốc/tái khám
→ Care Gap Queue
→ Nhân viên chăm sóc liên hệ
→ Bệnh nhân quay lại
```

---

# 10. Yêu cầu chức năng

# 10.1. Quản lý phòng khám

### CLINIC-01 – Tạo phòng khám

Platform Super Admin có thể tạo một tenant phòng khám với:

* Tên phòng khám.
* Loại hình.
* Chuyên khoa.
* Người đại diện.
* Số điện thoại.
* Email.
* Địa chỉ.
* Mã số thuế.
* Giấy phép hoạt động.
* Trạng thái.

### CLINIC-02 – Cấu hình phòng khám

Clinic Owner có thể cấu hình:

* Logo.
* Tên thương hiệu.
* Màu sắc.
* Thông tin liên hệ.
* Giờ làm việc.
* Nội dung nhắc lịch.
* Chính sách hủy lịch.
* Cấu hình số thứ tự.

### CLINIC-03 – Quản lý trạng thái

Trạng thái gồm:

* Trial.
* Active.
* Suspended.
* Expired.
* Deactivated.

Khi tenant bị suspend:

* Nhân viên không được thực hiện nghiệp vụ mới.
* Dữ liệu không bị xóa.
* Platform Admin vẫn xem được trạng thái và audit.

---

# 10.2. Quản lý chi nhánh

### BRANCH-01

Clinic Admin có thể:

* Tạo chi nhánh.
* Cập nhật địa chỉ.
* Khai báo giờ làm việc.
* Gán nhân viên.
* Gán dịch vụ.
* Tạm dừng chi nhánh.

### BRANCH-02

Người dùng thuộc nhiều chi nhánh có thể chuyển chi nhánh đang làm việc.

Mọi API phải lấy branch context từ membership hoặc session đã xác thực, không tin hoàn toàn `branch_id` do client gửi.

---

# 10.3. Quản lý nhân sự và phân quyền

### STAFF-01 – Mời nhân viên

Clinic Owner hoặc Clinic Admin có thể gửi lời mời bằng email hoặc số điện thoại.

### STAFF-02 – Vai trò

* Clinic Owner.
* Clinic Admin.
* Doctor.
* Nurse.
* Receptionist.
* Care Coordinator.
* Accountant.

### STAFF-03 – Một người nhiều vai trò

Một user có thể có nhiều vai trò trong cùng clinic nếu được cho phép.

### STAFF-04 – Một bác sĩ nhiều clinic

Bác sĩ có thể thuộc nhiều phòng khám, nhưng:

* Quyền tại từng clinic độc lập.
* Không được xem chéo bệnh nhân.
* Lịch làm việc tách theo từng clinic.

### STAFF-05 – Khóa nhân viên

Khi nhân viên bị suspend:

* Không truy cập được clinic.
* Không mất dữ liệu đã tạo.
* Audit phải ghi nhận người thực hiện và thời điểm.

---

# 10.4. Quản lý dịch vụ và bảng giá

### SERVICE-01

Clinic Admin có thể tạo dịch vụ:

* Khám nội tiết.
* Khám tim mạch.
* Tư vấn đái tháo đường.
* Theo dõi tuyến giáp.
* Quản lý béo phì.
* Đọc kết quả xét nghiệm.
* Tư vấn từ xa.
* Gói quản lý bệnh mạn.

### SERVICE-02

Mỗi dịch vụ có:

* Tên.
* Mã dịch vụ.
* Giá.
* Thời lượng.
* Chuyên khoa.
* Chi nhánh áp dụng.
* Bác sĩ thực hiện.
* Trạng thái.

### SERVICE-03 – Gói chăm sóc

Hỗ trợ gói 3, 6 hoặc 12 tháng:

* Số lượt khám.
* Số lần đọc xét nghiệm.
* Số lượt tư vấn.
* Nhắc thuốc.
* Nhắc tái khám.
* Theo dõi chỉ số.

---

# 10.5. Quản lý bệnh nhân

### PATIENT-01 – Tạo bệnh nhân

Lễ tân có thể tạo hồ sơ với:

* Họ tên.
* Số điện thoại.
* Ngày sinh.
* Giới tính.
* Địa chỉ.
* Người liên hệ.
* Mã bệnh nhân.

### PATIENT-02 – Chống trùng

Hệ thống cảnh báo trùng theo:

* Số điện thoại.
* Email.
* Căn cước nếu được phép lưu.
* Họ tên và ngày sinh.

Không tự động hợp nhất nếu chưa có người có thẩm quyền xác nhận.

### PATIENT-03 – Kết nối tài khoản MetoCare

Bệnh nhân được mời kích hoạt tài khoản MetoCare để:

* Xem lịch.
* Nhận nhắc.
* Xem kết quả.
* Tải hồ sơ.
* Quản lý consent.

### PATIENT-04 – Hồ sơ sức khỏe

Hỗ trợ:

* Tiền sử bệnh.
* Dị ứng.
* Thuốc.
* Xét nghiệm.
* Chỉ số sức khỏe.
* Chẩn đoán.
* Encounter.
* Clinical notes.
* Care plan.
* Tệp đính kèm.

### PATIENT-05 – Import

Hỗ trợ import CSV/XLSX với:

* Preview.
* Validation.
* Báo lỗi từng dòng.
* Chống trùng.
* Rollback nếu import thất bại.

---

# 10.6. Quản lý lịch hẹn

### APPT-01 – Tạo lịch

Nguồn tạo:

* Lễ tân.
* Bác sĩ.
* Bệnh nhân.
* Marketplace.
* Care Coordinator.
* API đối tác.

### APPT-02 – Trạng thái

* Pending.
* Confirmed.
* Arrived.
* In queue.
* In consultation.
* Completed.
* Cancelled.
* No-show.

### APPT-03 – Quy tắc chuyển trạng thái

Không cho phép chuyển trạng thái tùy ý.

Ví dụ:

```text
Pending → Confirmed → Arrived → In queue → In consultation → Completed
Pending/Confirmed → Cancelled
Confirmed → No-show
Cancelled không được chuyển trực tiếp sang Completed
```

### APPT-04 – Nhắc lịch

Hỗ trợ:

* Push notification.
* SMS.
* Email.
* Zalo nếu tích hợp.
* Nhắc trước 24 giờ.
* Nhắc trước 2 giờ.

### APPT-05 – Đổi và hủy lịch

Lưu:

* Người thực hiện.
* Lý do.
* Thời điểm.
* Lịch cũ.
* Lịch mới.

---

# 10.7. Check-in và hàng chờ

### QUEUE-01

Lễ tân check-in bệnh nhân theo lịch hoặc walk-in.

### QUEUE-02

Hàng chờ hiển thị:

* Số thứ tự.
* Bệnh nhân.
* Bác sĩ.
* Dịch vụ.
* Giờ hẹn.
* Giờ đến.
* Thời gian chờ.
* Trạng thái ưu tiên.

### QUEUE-03

Không tự động coi bệnh nhân là cấp cứu. Các cảnh báo y tế phải theo rule lâm sàng và cần người có chuyên môn xác nhận.

---

# 10.8. Khám và ghi chú lâm sàng

### ENCOUNTER-01

Bác sĩ bắt đầu một encounter từ appointment hoặc walk-in.

### ENCOUNTER-02

Thông tin gồm:

* Lý do khám.
* Triệu chứng.
* Sinh hiệu.
* Bệnh sử.
* Tiền sử.
* Thuốc đang dùng.
* Dị ứng.
* Xét nghiệm.
* Nhận định.
* Kế hoạch.

### NOTE-01 – Ghi chú

Hỗ trợ cấu trúc SOAP:

* Subjective.
* Objective.
* Assessment.
* Plan.

### NOTE-02 – Draft và finalize

* Có trạng thái Draft.
* Bác sĩ finalize khi hoàn tất.
* Note đã finalize không được sửa trực tiếp.
* Điều chỉnh sau finalize phải tạo amendment hoặc note mới.
* Giữ append-only invariant.

### NOTE-03 – Audit

Lưu:

* Người tạo.
* Thời điểm.
* Consultation.
* Phiên bản.
* Trạng thái.

---

# 10.9. Clinical Copilot

### AI-01 – Tóm tắt hồ sơ

AI tạo tóm tắt có cấu trúc:

* Bệnh nền.
* Thuốc.
* Dị ứng.
* Xét nghiệm.
* Diễn biến.
* Dữ liệu còn thiếu.

### AI-02 – Phân tích bệnh cảnh

Hiển thị:

* Vấn đề chính.
* Điểm cần chú ý.
* Mâu thuẫn dữ liệu.
* Khả năng cần loại trừ.
* Nguồn dữ liệu.
* Thời điểm dữ liệu.
* Mức độ tin cậy.

### AI-03 – Gợi ý câu hỏi

Gợi ý câu hỏi kèm lý do:

* Triệu chứng.
* Diễn biến.
* Thuốc.
* Tuân thủ.
* Lối sống.
* Dấu hiệu cảnh báo.

### AI-04 – Gợi ý tư vấn

Chỉ là gợi ý hỗ trợ:

* Không tự chẩn đoán.
* Không tự kê đơn.
* Không tự thay đổi thuốc.
* Không tự ghi vào hồ sơ.
* Bác sĩ phải xác nhận.

### AI-05 – An toàn

* Risk priority do rule deterministic quyết định.
* LLM không được thay đổi mức khẩn cấp.
* Không gửi dữ liệu ngoài scope consent.
* Không log PHI.
* Không trả raw output.
* Có feature flag.
* Có audit event.
* Production mặc định off cho đến khi được phê duyệt.

---

# 10.10. Care Plan

### CARE-01

Bác sĩ tạo kế hoạch:

* Mục tiêu điều trị.
* Thuốc.
* Theo dõi.
* Xét nghiệm.
* Tái khám.
* Lối sống.
* Cảnh báo cần liên hệ.

### CARE-02

Bệnh nhân chỉ xem nội dung đã được bác sĩ xác nhận.

### CARE-03

Hệ thống theo dõi:

* Đã thực hiện.
* Chưa thực hiện.
* Quá hạn.
* Bỏ qua.
* Không liên hệ được.

---

# 10.11. Care Gap Queue

Đây là module khác biệt cốt lõi.

### GAP-01 – Phát hiện bệnh nhân cần can thiệp

Hệ thống tạo danh sách theo rule:

* Quá hạn tái khám.
* Chưa thực hiện xét nghiệm.
* Sắp hết thuốc.
* Chỉ số xấu đi.
* Bỏ theo dõi.
* No-show.
* Chưa có care plan.
* Dữ liệu thiếu.
* Bác sĩ yêu cầu follow-up.

### GAP-02 – Ưu tiên

Mức:

* Khẩn cấp.
* Cần xử lý sớm.
* Cần theo dõi.
* Thông thường.

### GAP-03 – Giao việc

Clinic Admin hoặc Care Coordinator có thể:

* Giao bệnh nhân cho nhân viên.
* Đặt hạn xử lý.
* Thêm kịch bản liên hệ.
* Theo dõi kết quả.

### GAP-04 – Kết quả chăm sóc

* Đã liên hệ.
* Không liên hệ được.
* Đã đặt lịch.
* Từ chối tái khám.
* Đang điều trị nơi khác.
* Cần bác sĩ xem.
* Đã đóng.

---

# 10.12. CRM chăm sóc bệnh nhân

### CRM-01

Danh sách gọi theo ưu tiên.

### CRM-02

Hiển thị đúng mức dữ liệu cần thiết:

* Tên.
* Số điện thoại.
* Lý do liên hệ.
* Lịch tái khám.
* Hướng dẫn gọi.

Không hiển thị toàn bộ hồ sơ lâm sàng cho nhân viên chăm sóc.

### CRM-03

Lưu lịch sử:

* Thời gian gọi.
* Người gọi.
* Kết quả.
* Ghi chú.
* Lịch hẹn được tạo.

---

# 10.13. Thu phí và hóa đơn

## Phạm vi MVP

### BILL-01

Tạo hóa đơn từ:

* Dịch vụ.
* Gói chăm sóc.
* Phụ phí.
* Giảm giá.

### BILL-02

Thanh toán:

* Tiền mặt.
* Chuyển khoản.
* Thẻ.
* Ví điện tử trong giai đoạn sau.

### BILL-03

Trạng thái:

* Unpaid.
* Partially paid.
* Paid.
* Refunded.
* Cancelled.

### BILL-04

Không cho lễ tân sửa hóa đơn đã khóa nếu không có quyền.

### BILL-05

Audit tất cả điều chỉnh giá, giảm giá và hoàn tiền.

---

# 10.14. Dashboard phòng khám

## Dashboard vận hành

* Lịch hôm nay.
* Bệnh nhân đang chờ.
* No-show.
* Bác sĩ đang làm việc.
* Thời gian chờ.
* Care Gap cần xử lý.

## Dashboard kinh doanh

* Doanh thu.
* Số lượt khám.
* Doanh thu theo bác sĩ.
* Doanh thu theo dịch vụ.
* Tỷ lệ tái khám.
* Bệnh nhân mới và quay lại.
* Doanh thu theo cohort.

## Dashboard lâm sàng

* Tỷ lệ bệnh nhân đạt mục tiêu.
* HbA1c.
* Huyết áp.
* LDL-C.
* Cân nặng.
* Tỷ lệ hoàn thành xét nghiệm.
* Bệnh nhân có nguy cơ xấu đi.

Dashboard lâm sàng chỉ dùng dữ liệu phù hợp consent và quyền truy cập.

---

# 11. Báo cáo

Hệ thống cần hỗ trợ:

* Báo cáo lịch hẹn.
* Báo cáo no-show.
* Báo cáo tái khám.
* Báo cáo bệnh nhân quá hạn.
* Báo cáo hiệu suất bác sĩ.
* Báo cáo chăm sóc.
* Báo cáo doanh thu.
* Báo cáo dịch vụ.
* Báo cáo bệnh nhân theo chương trình.
* Báo cáo chỉ số lâm sàng theo cohort.
* Export CSV/XLSX theo quyền.

Không export PHI hàng loạt nếu user không có quyền phù hợp.

---

# 12. Thông báo

Hỗ trợ notification template:

* Xác nhận lịch.
* Nhắc lịch.
* Đổi lịch.
* Hủy lịch.
* Nhắc xét nghiệm.
* Nhắc thuốc.
* Nhắc tái khám.
* Kế hoạch chăm sóc mới.
* Tin nhắn từ phòng khám.
* Cảnh báo cần liên hệ.

Mỗi template có:

* Kênh.
* Thời điểm.
* Nội dung.
* Clinic branding.
* Trạng thái gửi.
* Lịch sử gửi.

---

# 13. Consent và quyền riêng tư

## 13.1. Consent tối thiểu

* Chia sẻ hồ sơ với phòng khám.
* Chia sẻ kết quả xét nghiệm.
* Cho phép AI phân tích hồ sơ.
* Cho phép nhận thông báo.
* Cho phép tham gia chương trình chăm sóc.

## 13.2. Nguyên tắc

* Consent phải có scope.
* Consent có thời hạn nếu cần.
* Người dùng có thể thu hồi.
* Thu hồi consent không xóa audit hoặc hồ sơ nghiệp vụ hợp pháp.
* AI không được gọi provider nếu thiếu consent tương ứng.

---

# 14. RBAC matrix tóm tắt

| Chức năng          |      Owner |      Admin |  Doctor |   Nurse | Reception |    Care | Accountant |
| ------------------ | ---------: | ---------: | ------: | ------: | --------: | ------: | ---------: |
| Cấu hình clinic    |          ✓ |          ✓ |         |         |           |         |            |
| Quản lý staff      |          ✓ |          ✓ |         |         |           |         |            |
| Xem lịch           |          ✓ |          ✓ |       ✓ |       ✓ |         ✓ |       ✓ |            |
| Tạo lịch           |          ✓ |          ✓ |       ✓ |       ✓ |         ✓ |       ✓ |            |
| Xem hồ sơ lâm sàng | Theo quyền | Theo quyền |       ✓ | Hạn chế |           | Hạn chế |            |
| Ghi chú lâm sàng   |            |            |       ✓ |  Hỗ trợ |           |         |            |
| Clinical Copilot   |            |            |       ✓ |         |           |         |            |
| Care Gap Queue     |          ✓ |          ✓ |       ✓ |       ✓ |   Hạn chế |       ✓ |            |
| Hóa đơn            |          ✓ |          ✓ | Hạn chế |         |         ✓ |         |          ✓ |
| Báo cáo doanh thu  |          ✓ |          ✓ | Hạn chế |         |   Hạn chế |         |          ✓ |

Chi tiết quyền phải được kiểm soát tại backend.

---

# 15. Yêu cầu phi chức năng

## 15.1. Bảo mật

* Tenant isolation.
* RBAC backend.
* Audit log.
* Encryption at rest.
* TLS.
* Không log PHI.
* Không expose ciphertext.
* Controlled error.
* Secret scan.
* Session timeout.
* Rate limit.
* Optional MFA trong build/test.
* Production security gate trước khi go-live.

## 15.2. Hiệu năng

* Danh sách chính tải dưới 2 giây trong điều kiện bình thường.
* Dashboard dưới 3 giây.
* Pagination bắt buộc.
* Không tải toàn bộ patient dataset lên frontend.
* AI có timeout và fallback.
* Tác vụ nặng chạy background job.

## 15.3. Khả dụng

* Responsive desktop, tablet, mobile.
* Font body tối thiểu 16px.
* Touch target tối thiểu 44px.
* Không horizontal scroll ở 390px.
* Loading, empty, error và retry rõ ràng.
* UI tiếng Việt.

## 15.4. Khả năng mở rộng

Mục tiêu kỹ thuật ban đầu:

* 1.000 phòng khám.
* 10.000 nhân viên.
* 1 triệu hồ sơ bệnh nhân.
* 10 triệu lần đo và kết quả xét nghiệm.
* Multi-branch.
* Feature entitlement theo plan.

## 15.5. Audit

Audit tối thiểu cho:

* Đăng nhập.
* Truy cập hồ sơ.
* Xem dữ liệu lâm sàng.
* Tạo hoặc finalize note.
* Thay đổi vai trò.
* Export.
* Thay đổi hóa đơn.
* Gọi AI.
* Accept/reject gợi ý AI.

---

# 16. Tích hợp

## MVP

* MetoCare Patient.
* MetoCare Doctor.
* Notification service.
* AI provider gateway.
* OCR.
* Lab Intelligence.
* Email.

## Giai đoạn sau

* SMS.
* Zalo OA.
* Payment gateway.
* Hóa đơn điện tử.
* Phòng xét nghiệm.
* Thiết bị đo tại nhà.
* Nhà thuốc.
* HIS/EMR khác.
* Bảo hiểm.

---

# 17. Subscription và entitlement

## Gói Trial

* 1 chi nhánh.
* 2 bác sĩ.
* Giới hạn bệnh nhân.
* Clinical Copilot giới hạn.
* Thời hạn 30 ngày.

## Gói Basic

* Lịch hẹn.
* Hồ sơ bệnh nhân.
* Ghi chú.
* Care Gap cơ bản.
* Báo cáo cơ bản.

## Gói Professional

* Clinical Copilot.
* Chăm sóc bệnh nhân.
* Automation.
* Gói điều trị.
* Báo cáo nâng cao.
* Multi-branch giới hạn.

## Gói Enterprise

* Không giới hạn hoặc custom limit.
* API.
* SSO.
* SLA.
* Tích hợp.
* Báo cáo tùy chỉnh.
* Private deployment nếu cần.

Entitlement phải được enforce ở backend, không chỉ ẩn menu.

---

# 18. Phân kỳ triển khai

## Phase C0 – Multi-tenant Foundation

* Clinic.
* Branch.
* Membership.
* Clinic RBAC.
* Invitation.
* Settings.
* Subscription model.
* Tenant isolation.
* Audit.
* Clinic Admin shell.

## Phase C1 – Clinic Operations MVP

* Staff.
* Doctors.
* Patients.
* Services.
* Appointments.
* Check-in.
* Queue.
* Consultation.
* Clinical notes.
* Billing cơ bản.
* Dashboard.

## Phase C2 – Chronic Care Engine

* Care Plan.
* Care Gap Queue.
* CRM chăm sóc.
* Nhắc tái khám.
* Nhắc xét nghiệm.
* Retention dashboard.
* Clinical outcome dashboard.

## Phase C3 – AI and Automation

* Clinical Copilot mở rộng.
* SOAP draft.
* Post-consultation summary.
* Suggested outreach.
* AI-generated patient education.
* AI usage analytics.

## Phase C4 – Ecosystem

* Lab integration.
* Pharmacy.
* Payment.
* E-invoice.
* Teleconsultation.
* Corporate health.
* API partners.

---

# 19. Ngoài phạm vi MVP

Chưa xây trong C0–C1:

* HIS bệnh viện đầy đủ.
* Quản lý giường bệnh.
* Phẫu thuật.
* ICU.
* PACS.
* Bảo hiểm y tế.
* Quản lý kho thuốc nâng cao.
* Kế toán tổng hợp.
* Payroll.
* Đơn thuốc quốc gia.
* Chẩn đoán hoặc kê đơn tự động bằng AI.

---

# 20. Giả định

* Phòng khám có kết nối internet ổn định.
* Bệnh nhân sử dụng số điện thoại cá nhân.
* Clinic chịu trách nhiệm xác minh bác sĩ và giấy phép.
* Phòng khám pilot đồng ý chuẩn hóa quy trình.
* Clinical Copilot chỉ bật khi consent và feature flag hợp lệ.
* MetoCare không thay thế trách nhiệm chuyên môn của bác sĩ.

---

# 21. Rủi ro

## 21.1. Tenant isolation sai

Mức độ: P0.

Biện pháp:

* Scope tại query/service.
* Cross-clinic tests.
* Không tin `clinic_id` từ client.
* Codex security review bắt buộc.

## 21.2. Phòng khám không thay đổi quy trình

Biện pháp:

* Onboarding đơn giản.
* Import dữ liệu.
* Pilot theo từng workflow.
* Không bắt triển khai toàn bộ cùng lúc.

## 21.3. AI đưa gợi ý sai

Biện pháp:

* Structured output.
* Deterministic risk.
* Citation.
* Confidence.
* Consent.
* Doctor confirmation.
* Feature flag.
* Audit.

## 21.4. Dữ liệu bệnh nhân trùng

Biện pháp:

* Matching.
* Duplicate warning.
* Merge có kiểm soát.
* Không tự động merge.

## 21.5. Scope sản phẩm quá rộng

Biện pháp:

* Beachhead nội tiết/chuyển hóa.
* C0 trước C1.
* Care retention trước ERP đầy đủ.
* Mỗi phase có acceptance rõ.

---

# 22. Acceptance criteria cấp chương trình

Module được coi là đủ điều kiện pilot khi:

1. Mỗi phòng khám là một tenant độc lập.
2. Cross-clinic access bị chặn bằng backend tests.
3. Clinic có thể tạo chi nhánh, nhân viên, bác sĩ và dịch vụ.
4. Lễ tân tạo bệnh nhân và lịch hẹn.
5. Bệnh nhân check-in và vào hàng chờ.
6. Bác sĩ xem đúng hồ sơ thuộc phạm vi.
7. Bác sĩ tạo và finalize clinical note.
8. Phòng khám tạo care plan và lịch tái khám.
9. Hệ thống tạo danh sách bệnh nhân quá hạn.
10. Nhân viên chăm sóc ghi nhận kết quả liên hệ.
11. Clinic Owner xem retention và doanh thu cơ bản.
12. UI sử dụng được trên desktop và mobile.
13. Không có P0/P1 security finding còn mở.
14. CI, migration, deploy và authenticated smoke đều PASS.

---

# 23. MVP thương mại đề xuất

Không bán toàn bộ hệ thống ngay trong pilot.

Gói pilot nên tập trung vào:

1. Hồ sơ bệnh nhân mạn tính.
2. Nhập và đọc xét nghiệm.
3. Timeline chỉ số.
4. Lịch hẹn và tái khám.
5. Care Gap Queue.
6. CRM gọi lại.
7. Clinical Copilot.
8. Dashboard retention.

Thông điệp bán hàng:

> MetoCare giúp phòng khám biết bệnh nhân nào cần được chăm sóc hôm nay, giúp bác sĩ nắm hồ sơ trước khi khám và tăng tỷ lệ bệnh nhân quay lại điều trị.

---

# 24. Đề xuất rollout

## Pilot 1

* 1 phòng khám nội tiết.
* 2–5 bác sĩ.
* 500–2.000 bệnh nhân.
* 8–12 tuần.
* Import dữ liệu giới hạn.
* Đo baseline trước triển khai.

## Pilot 2

* 3–5 phòng khám.
* Có tim mạch hoặc chuyển hóa.
* Kiểm tra multi-tenant.
* So sánh retention giữa các clinic.

## Commercial launch

Chỉ thực hiện khi:

* Tenant isolation được audit độc lập.
* Production auth hardening hoàn thành.
* Clinical Copilot được phê duyệt vận hành.
* Có ít nhất hai pilot đạt KPI.
* Có quy trình hỗ trợ và SLA.

---

# 25. Quyết định cần BOD phê duyệt

1. Phê duyệt niche: Nội tiết – Tim mạch – Chuyển hóa.
2. Phê duyệt định vị: Chronic Care and Retention Platform.
3. Phê duyệt Phase C0 và C1.
4. Phê duyệt ngân sách pilot.
5. Phê duyệt mô hình giá.
6. Phê duyệt danh sách phòng khám pilot.
7. Phê duyệt nguyên tắc sử dụng AI và dữ liệu.
8. Phê duyệt production security gate.

---

# 26. Kết luận

MetoCare Clinic SaaS không nên cạnh tranh bằng việc có nhiều chức năng hành chính hơn các phần mềm phòng khám khác.

Lợi thế cốt lõi cần tập trung là:

* Hồ sơ sức khỏe theo thời gian.
* Quản lý bệnh nhân mạn.
* Care Gap Queue.
* Clinical Copilot.
* Tăng tỷ lệ tái khám.
* Kết nối hiệu quả lâm sàng với hiệu quả kinh doanh.

**Sản phẩm cần được xây theo hướng: tenant foundation trước, vận hành phòng khám sau, chronic care và AI là lợi thế cạnh tranh.**
