# M07 – QUẢN LÝ LỊCH HẸN

## 7.1. Mục đích & phạm vi

Quản lý toàn bộ vòng đời lịch hẹn từ nhiều nguồn tạo, với state machine chặt chẽ, nhắc lịch đa kênh và lưu vết đổi/hủy. Là đầu vào trực tiếp của chỉ số tái khám và no-show.

## 7.2. Nguồn tạo lịch (APPT-01)

Lễ tân, bác sĩ, bệnh nhân (Patient app), Care Coordinator, Marketplace, API đối tác. Mỗi lịch lưu `created_by_source` để phân tích kênh.

## 7.3. User stories

- **US-M07-01:** Là lễ tân, tôi muốn thấy khung giờ trống theo bác sĩ và chi nhánh để đặt lịch không trùng.
- **US-M07-02:** Là bệnh nhân, tôi muốn tự đặt lịch tái khám từ app theo khung giờ phòng khám mở cho đặt online.
- **US-M07-03:** Là lễ tân, tôi muốn đổi lịch với lý do được lưu vết để đối soát khi có khiếu nại.
- **US-M07-04:** Là Clinic Admin, tôi muốn hệ thống tự đánh dấu no-show cuối ngày cho các lịch Confirmed không check-in, để số liệu chính xác.
- **US-M07-05:** Là bác sĩ, tôi muốn đặt lịch tái khám ngay khi kết thúc khám (từ care plan) để chốt hẹn khi bệnh nhân còn ở phòng khám.

## 7.4. Trường dữ liệu chính

| Trường | Kiểu | Bắt buộc |
|---|---|---|
| appointment_id / clinic_id / branch_id | UUID | ✓ |
| patient_id | UUID | ✓ |
| doctor_id | UUID | ✓ (trừ dịch vụ không cần bác sĩ) |
| service_id + price_snapshot | UUID + decimal | ✓ |
| start_time / end_time | datetime | ✓ |
| status | enum | ✓ |
| created_by / created_by_source | UUID / enum | ✓ |
| linked_care_plan_item | UUID |  |
| reschedule_history | array | Hệ thống ghi |
| cancellation | object | Người, lý do, thời điểm |

## 7.5. State machine (APPT-02/03)

```text
Pending → Confirmed → Arrived → In queue → In consultation → Completed
Pending | Confirmed → Cancelled
Confirmed → No-show (quá giờ + grace period, tự động hoặc lễ tân)
No-show → Arrived (bệnh nhân đến rất muộn, lễ tân override có lý do)
Cancelled: trạng thái cuối, KHÔNG chuyển sang Completed
Đổi lịch = Cancelled(lịch cũ, reason=rescheduled) + lịch mới liên kết
```

## 7.6. Nhắc lịch (APPT-04)

| Mốc | Kênh mặc định | Nội dung |
|---|---|---|
| Ngay khi đặt | Push/Zalo/SMS/Email theo cấu hình | Xác nhận lịch |
| Trước 24h | Push + SMS/Zalo | Nhắc + nút xác nhận/đổi lịch |
| Trước 2h | Push | Nhắc gần giờ |
| Sau no-show | Đưa vào Care Gap Queue (M12) | Không nhắn tự động nội dung nhạy cảm |

Bệnh nhân bấm "Xác nhận" → Pending → Confirmed. Không phản hồi sau nhắc 24h → giữ Pending và gắn cờ cho lễ tân gọi xác nhận.

## 7.7. Business rules

- **BR-M07-01 (P0):** Chuyển trạng thái ngoài state machine → từ chối, lỗi có kiểm soát; mọi transition ghi audit.
- **BR-M07-02 (P0):** Chống double-booking: một bác sĩ không có 2 lịch chồng giờ tại cùng thời điểm, trừ khi tenant bật chế độ overbooking có kiểm soát (giới hạn %, ghi nhận rõ).
- **BR-M07-03 (P0):** Lịch chỉ được đặt trong giờ làm việc chi nhánh + lịch làm việc bác sĩ; override cần quyền và lý do.
- **BR-M07-04 (P1):** Hủy lịch trong thời hạn chính sách hủy (M01) → cảnh báo, ghi nhận vi phạm chính sách để báo cáo.
- **BR-M07-05 (P1):** Auto no-show chạy cuối ngày làm việc chi nhánh (job idempotent); grace period cấu hình được (mặc định 60 phút sau giờ hẹn).
- **BR-M07-06 (P1):** Bệnh nhân tự đặt online chỉ thấy khung giờ tenant mở cho online booking, không thấy tên bệnh nhân khác.

## 7.8. Ngoại lệ & edge cases

- Walk-in không có lịch → tạo appointment tức thời trạng thái Arrived (phục vụ thống kê) hoặc luồng walk-in của M08.
- Bác sĩ nghỉ đột xuất → công cụ hủy/đổi hàng loạt lịch trong ngày của bác sĩ, kèm gửi thông báo và đưa bệnh nhân vào danh sách gọi lại.
- Hai lễ tân đặt cùng slot cùng lúc → khóa lạc quan/bi quan ở backend, người sau nhận lỗi slot đã được đặt.
- Đổi lịch nhiều lần → chuỗi liên kết đầy đủ, báo cáo đếm đúng 1 lượt bệnh nhân.

## 7.9. Acceptance criteria

- **AC-M07-01:** Mọi transition hợp lệ pass, mọi transition không hợp lệ bị chặn (test bảng transition đầy đủ).
- **AC-M07-02:** Gửi 2 request đặt trùng slot đồng thời → đúng 1 thành công.
- **AC-M07-03:** Nhắc 24h/2h gửi đúng mốc theo múi giờ Việt Nam; trạng thái gửi lưu lại được.
- **AC-M07-04:** Cuối ngày, lịch Confirmed không check-in chuyển No-show và xuất hiện trong Care Gap Queue.
- **AC-M07-05:** Đổi lịch giữ đủ vết: lịch cũ, lịch mới, người thực hiện, lý do.

---

