# M11 – CARE PLAN (KẾ HOẠCH CHĂM SÓC)

## 11.1. Mục đích & phạm vi

Chuẩn hóa kế hoạch điều trị dài hạn cho bệnh nhân mạn: mục tiêu, thuốc, lịch theo dõi, xét nghiệm định kỳ, tái khám, lối sống và ngưỡng cảnh báo. Care plan là "hợp đồng điều trị" giữa bác sĩ và bệnh nhân, đồng thời là nguồn rule chính cho Care Gap Queue (M12).

## 11.2. User stories

- **US-M11-01:** Là bác sĩ, tôi muốn tạo care plan từ template chuyên khoa (VD: ĐTĐ típ 2 mới chẩn đoán – HbA1c mỗi 3 tháng, tái khám mỗi 1–3 tháng) và tùy chỉnh cho từng bệnh nhân.
- **US-M11-02:** Là bác sĩ, tôi muốn đặt mục tiêu định lượng (HbA1c <7%, HA <130/80, LDL-C <70 mg/dL, giảm 5% cân nặng) để hệ thống theo dõi tiến độ.
- **US-M11-03:** Là bệnh nhân, tôi chỉ xem nội dung đã được bác sĩ xác nhận, diễn đạt dễ hiểu, kèm nhắc thuốc và nhắc lịch.
- **US-M11-04:** Là Care Coordinator, tôi muốn thấy mục nào của care plan quá hạn để đưa vào danh sách chăm sóc.

## 11.3. Cấu trúc Care Plan (CARE-01)

| Thành phần | Trường | Theo dõi trạng thái (CARE-03) |
|---|---|---|
| Mục tiêu điều trị | Chỉ số, giá trị mục tiêu, hạn đạt | Đạt / Chưa đạt / Cải thiện / Xấu đi |
| Thuốc | Tên, liều, tần suất, thời gian, số ngày cấp | Ước tính ngày hết thuốc → nhắc |
| Theo dõi tại nhà | Chỉ số, tần suất đo (HA, đường huyết, cân nặng) | Đã ghi / Bỏ sót |
| Xét nghiệm định kỳ | Loại XN, chu kỳ, lần kế tiếp | Đã thực hiện / Chưa / Quá hạn |
| Tái khám | Chu kỳ hoặc ngày cụ thể, liên kết appointment | Đã đặt / Chưa đặt / Quá hạn |
| Lối sống | Khuyến nghị ăn uống, vận động | Ghi nhận tư vấn |
| Ngưỡng cảnh báo | Điều kiện cần liên hệ (VD đường huyết >16.7 mmol/L, HA >180/110) | Kích hoạt rule M12 |

## 11.4. Business rules

- **BR-M11-01 (P0):** Chỉ Doctor tạo/sửa/kích hoạt care plan; bản active tại một thời điểm là duy nhất cho mỗi chương trình bệnh; sửa tạo phiên bản mới, giữ lịch sử.
- **BR-M11-02 (P0):** Bệnh nhân chỉ thấy nội dung bác sĩ đã xác nhận publish (CARE-02); nội dung nháp/ghi chú nội bộ không đẩy sang Patient app.
- **BR-M11-03 (P1):** Mỗi item có due date/chu kỳ; hệ thống tự sinh trạng thái Đã thực hiện/Chưa/Quá hạn/Bỏ qua/Không liên hệ được và đẩy sự kiện sang M12.
- **BR-M11-04 (P1):** Ngưỡng cảnh báo là rule deterministic; kích hoạt tạo Care Gap mức ưu tiên cao, cần người có chuyên môn xác nhận, không tự nhắn nội dung y khoa cho bệnh nhân.
- **BR-M11-05 (P2):** Template care plan quản lý ở cấp tenant, có thể nhân bản từ thư viện mẫu MetoCare.

## 11.5. Acceptance criteria

- **AC-M11-01:** Tạo care plan từ template ≤ 2 phút thao tác cho ca chuẩn.
- **AC-M11-02:** Item tái khám quá hạn 1 ngày → xuất hiện trong Care Gap Queue với đúng ưu tiên.
- **AC-M11-03:** Patient app không hiển thị bất kỳ nội dung chưa publish.
- **AC-M11-04:** Sửa care plan tạo version mới; version cũ đọc được, không sửa được.

---

