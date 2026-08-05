# M13 – CRM CHĂM SÓC BỆNH NHÂN

## 13.1. Mục đích & phạm vi

Giao diện làm việc của nhân viên chăm sóc: danh sách gọi theo ưu tiên (từ M12), kịch bản gọi theo lý do, ghi kết quả, tạo lịch tái khám ngay trong cuộc gọi – với nguyên tắc **hiển thị đúng mức dữ liệu cần thiết** (CRM-02).

## 13.2. Care Context – dữ liệu tối thiểu hiển thị cho nhân viên chăm sóc

Được phép: tên, SĐT, lý do liên hệ (diễn đạt vận hành, VD "quá hạn tái khám ĐTĐ 10 ngày"), lịch gần nhất/kế tiếp, kịch bản gọi, lịch sử chăm sóc.
Không được phép: nội dung clinical note, kết quả xét nghiệm chi tiết, chẩn đoán ngoài phạm vi lý do, tệp đính kèm y khoa.

## 13.3. User stories

- **US-M13-01:** Là nhân viên chăm sóc, tôi muốn màn hình gọi hiển thị kịch bản theo lý do (no-show ≠ sắp hết thuốc ≠ quá hạn XN) để trao đổi đúng trọng tâm.
- **US-M13-02:** Là nhân viên chăm sóc, tôi muốn đặt lịch tái khám ngay trong màn hình cuộc gọi, không chuyển màn hình.
- **US-M13-03:** Là Clinic Admin, tôi muốn xem lịch sử chăm sóc từng bệnh nhân: ai gọi, khi nào, kết quả, ghi chú, lịch được tạo (CRM-03).
- **US-M13-04:** Là nhân viên chăm sóc, khi bệnh nhân hỏi chuyên môn, tôi muốn chuyển ca sang "Cần bác sĩ xem" thay vì tự tư vấn.

## 13.4. Business rules

- **BR-M13-01 (P0):** API cho vai trò Care Coordinator chỉ trả về Care Context (whitelist trường); test khẳng định không trường lâm sàng nào lọt ra.
- **BR-M13-02 (P1):** Mỗi cuộc gọi ghi: thời điểm, người gọi, kết quả (danh mục chuẩn GAP-04), ghi chú, lịch hẹn tạo (nếu có).
- **BR-M13-03 (P1):** Kịch bản gọi cấu hình theo rule GAP; nội dung không chứa chi tiết y khoa vượt phạm vi.
- **BR-M13-04 (P1):** Số lần liên hệ tối đa cho một task (mặc định 3) trước khi bắt buộc chọn outcome đóng, tránh làm phiền bệnh nhân.
- **BR-M13-05 (P2):** Khung giờ gọi cấu hình (mặc định 8:30–19:30), hệ thống cảnh báo khi ghi cuộc gọi ngoài khung.

## 13.5. Acceptance criteria

- **AC-M13-01:** Response API danh sách gọi không chứa trường note/lab/diagnosis chi tiết (kiểm tra schema).
- **AC-M13-02:** Đặt lịch từ màn hình gọi tạo appointment hợp lệ và tự cập nhật outcome task.
- **AC-M13-03:** Lịch sử chăm sóc bệnh nhân hiển thị đủ chuỗi liên hệ theo thời gian.

---
