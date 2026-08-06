# M15 – THÔNG BÁO & NHẮC HẸN

## 15.1. Mục đích & phạm vi

Hạ tầng notification đa kênh (Push, Email; SMS/Zalo OA giai đoạn sau) với template theo tenant, lịch gửi, trạng thái gửi và lịch sử – phục vụ M07 (nhắc lịch), M11 (nhắc thuốc/XN/tái khám) và truyền thông phòng khám.

## 15.2. Danh mục template (§12 BRD v1.0)

Xác nhận lịch; nhắc lịch 24h/2h; đổi lịch; hủy lịch; nhắc xét nghiệm; nhắc thuốc; nhắc tái khám; kế hoạch chăm sóc mới; tin nhắn từ phòng khám; cảnh báo cần liên hệ (chỉ nội dung vận hành, không nội dung y khoa nhạy cảm).

Mỗi template: kênh, thời điểm/trigger, nội dung (biến động: tên, giờ, chi nhánh, bác sĩ), branding tenant, trạng thái bật/tắt.

## 15.3. Business rules

- **BR-M15-01 (P0):** Nội dung gửi qua kênh ngoài (SMS/Zalo/Email) không chứa chẩn đoán, kết quả xét nghiệm, tên thuốc – chỉ thông tin lịch/vận hành; chi tiết y khoa xem trong app sau đăng nhập.
- **BR-M15-02 (P0):** Tôn trọng consent kênh (M17): bệnh nhân tắt kênh nào → không gửi kênh đó (trừ thông báo an toàn/pháp lý tối thiểu).
- **BR-M15-03 (P1):** Mỗi lần gửi lưu: template, kênh, người nhận, thời điểm, trạng thái (Queued/Sent/Delivered/Failed), mã lỗi nếu fail; retry có giới hạn.
- **BR-M15-04 (P1):** Idempotency: một trigger không gửi trùng thông báo (dedupe key theo sự kiện).
- **BR-M15-05 (P2):** Giới hạn tần suất: tối đa N thông báo marketing/tuần/bệnh nhân (cấu hình).

## 15.4. Acceptance criteria

- **AC-M15-01:** Nhắc 24h gửi đúng ±5 phút; job chạy lại không gửi trùng.
- **AC-M15-02:** Nội dung SMS mẫu qua review: không chứa PHI y khoa.
- **AC-M15-03:** Tắt consent Email → không email nào được gửi tới bệnh nhân đó (trừ nhóm bắt buộc định nghĩa trước).

---

