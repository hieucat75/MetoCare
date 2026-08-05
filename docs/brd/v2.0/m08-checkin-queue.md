# M08 – CHECK-IN & HÀNG CHỜ

## 8.1. Mục đích & phạm vi

Điều phối bệnh nhân tại phòng khám: check-in theo lịch hoặc walk-in, cấp số thứ tự, hiển thị hàng chờ theo bác sĩ/phòng, đo thời gian chờ thực tế.

## 8.2. User stories

- **US-M08-01:** Là lễ tân, tôi muốn check-in bệnh nhân có lịch bằng SĐT/mã BN trong vài giây.
- **US-M08-02:** Là lễ tân, tôi muốn tiếp nhận walk-in: tìm/tạo hồ sơ → chọn dịch vụ & bác sĩ → vào hàng chờ.
- **US-M08-03:** Là bác sĩ, tôi muốn thấy hàng chờ của mình theo thời gian thực và gọi bệnh nhân tiếp theo.
- **US-M08-04:** Là điều dưỡng, tôi muốn ghi sinh hiệu ngay khi bệnh nhân chờ, để bác sĩ có dữ liệu trước khi vào khám.
- **US-M08-05:** Là lễ tân, tôi muốn nâng ưu tiên một bệnh nhân (cao tuổi, hẹn trước bị trễ do phòng khám) với lý do được ghi lại.

## 8.3. Thông tin hàng chờ hiển thị (QUEUE-02)

Số thứ tự, tên bệnh nhân (che một phần trên màn hình công cộng), bác sĩ, dịch vụ, giờ hẹn, giờ đến, thời gian chờ tích lũy, cờ ưu tiên. Trên màn hình công cộng: chỉ số thứ tự + tên viết tắt, không hiển thị dịch vụ/chẩn đoán.

## 8.4. Business rules

- **BR-M08-01 (P0):** Check-in chuyển appointment sang Arrived → In queue; walk-in tạo appointment tương ứng.
- **BR-M08-02 (P0):** Hệ thống **không tự phán định cấp cứu** (QUEUE-03). Cờ ưu tiên là thao tác của con người, có lý do, có audit; rule lâm sàng chỉ tạo **gợi ý** cần người có chuyên môn xác nhận.
- **BR-M08-03 (P1):** Số thứ tự sinh theo cấu hình tenant (reset theo ngày/chi nhánh/bác sĩ); không cấp trùng trong cùng phạm vi reset.
- **BR-M08-04 (P1):** Gọi bệnh nhân → In consultation; bệnh nhân vắng khi gọi → trả về hàng chờ với cờ "gọi nhỡ" (tối đa N lần cấu hình) trước khi lễ tân xử lý.
- **BR-M08-05 (P1):** Thời gian chờ đo từ check-in đến In consultation; lưu để báo cáo (M16).

## 8.5. Acceptance criteria

- **AC-M08-01:** Check-in ≤ 3 thao tác từ màn hình lịch hôm nay.
- **AC-M08-02:** Hàng chờ cập nhật realtime (hoặc polling ≤10 giây) trên màn hình bác sĩ và lễ tân.
- **AC-M08-03:** Màn hình công cộng không lộ họ tên đầy đủ/dịch vụ.
- **AC-M08-04:** Nâng ưu tiên bắt buộc nhập lý do và xuất hiện trong audit.

---
