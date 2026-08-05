# M12 – CARE GAP QUEUE (MODULE KHÁC BIỆT CỐT LÕI)

## 12.1. Mục đích & phạm vi

Trả lời câu hỏi trung tâm của sản phẩm: **"Hôm nay phòng khám cần chủ động chăm sóc bệnh nhân nào, vì lý do gì, ai phụ trách, kết quả ra sao?"** Hệ thống phát hiện bệnh nhân rơi khỏi chương trình điều trị theo rule, xếp ưu tiên, giao việc và đo kết quả khép kín.

## 12.2. Rule phát hiện (GAP-01)

| Mã rule | Điều kiện (mặc định, cấu hình được) | Ưu tiên mặc định |
|---|---|---|
| GAP-R1 Quá hạn tái khám | Quá due date tái khám ≥ X ngày (mặc định 3) | Cần xử lý sớm |
| GAP-R2 XN chưa thực hiện | Chỉ định/chu kỳ XN quá hạn ≥ 7 ngày | Cần xử lý sớm |
| GAP-R3 Sắp hết thuốc | Ước tính hết thuốc trong ≤ 7 ngày, chưa có lịch | Cần theo dõi |
| GAP-R4 Chỉ số xấu đi | Chỉ số vượt ngưỡng cảnh báo care plan hoặc xu hướng xấu qua N lần đo | Khẩn cấp / Cần xử lý sớm (theo ngưỡng) |
| GAP-R5 Bỏ theo dõi | Không tương tác (khám/XN/đo) ≥ 90 ngày với bệnh nhân mạn active | Cần xử lý sớm |
| GAP-R6 No-show | Lịch chuyển No-show | Cần xử lý sớm |
| GAP-R7 Chưa có care plan | Bệnh nhân có chẩn đoán mạn active, chưa có care plan sau 2 lượt khám | Cần theo dõi |
| GAP-R8 Dữ liệu thiếu | Thiếu chỉ số then chốt theo chương trình (VD ĐTĐ chưa có HbA1c 6 tháng) | Thông thường |
| GAP-R9 Bác sĩ yêu cầu | Bác sĩ tạo follow-up thủ công | Theo bác sĩ đặt |

## 12.3. Vòng đời một Care Gap

```text
Detected (rule engine, chạy job hằng đêm + realtime cho GAP-R4/R6/R9)
→ Triaged (ưu tiên tự động theo rule; người có quyền được nâng/hạ có lý do)
→ Assigned (Admin/Care Coordinator giao việc + hạn xử lý + kịch bản liên hệ)
→ In progress (nhân viên liên hệ, ghi kết quả từng lần)
→ Resolved | Closed với outcome (GAP-04):
   Đã liên hệ / Không liên hệ được / Đã đặt lịch / Từ chối tái khám /
   Đang điều trị nơi khác / Cần bác sĩ xem / Đã đóng
```

## 12.4. User stories

- **US-M12-01:** Là Care Coordinator, mỗi sáng tôi muốn thấy danh sách bệnh nhân cần liên hệ hôm nay, xếp theo ưu tiên và hạn xử lý.
- **US-M12-02:** Là Clinic Admin, tôi muốn giao việc theo nhân viên và theo dõi tỷ lệ xử lý đúng hạn.
- **US-M12-03:** Là bác sĩ, tôi muốn được chuyển các ca "Cần bác sĩ xem" (chỉ số xấu đi) để quyết định hướng xử lý.
- **US-M12-04:** Là Clinic Owner, tôi muốn biết mỗi tuần bao nhiêu bệnh nhân được chăm sóc chủ động và bao nhiêu quay lại nhờ chăm sóc (đo ROI của module).

## 12.5. Business rules

- **BR-M12-01 (P0):** Ưu tiên khởi tạo do **rule deterministic** quyết định; AI/LLM không được thay đổi mức khẩn cấp (nhất quán AI-05). Thay đổi ưu tiên thủ công cần lý do + audit.
- **BR-M12-02 (P0):** Dedupe: một bệnh nhân có nhiều rule trùng thời điểm → gộp thành một task đa lý do, lấy ưu tiên cao nhất; không spam nhiều task trùng.
- **BR-M12-03 (P1):** Rule engine idempotent: chạy lại không tạo task trùng cho cùng (bệnh nhân, rule, chu kỳ).
- **BR-M12-04 (P1):** Task quá hạn xử lý → escalate lên Admin; task "Khẩn cấp" phải có người nhận trong ≤ 4 giờ làm việc.
- **BR-M12-05 (P1):** Outcome "Đã đặt lịch" phải liên kết appointment thực để báo cáo đo được chuyển đổi chăm sóc → tái khám.
- **BR-M12-06 (P1):** Bệnh nhân rút consent tham gia chương trình chăm sóc → đóng task đang mở với outcome tương ứng, ngừng sinh task mới (trừ nghĩa vụ an toàn do bác sĩ quyết định).

## 12.6. Ngoại lệ & edge cases

- Bệnh nhân đã tử vong/chuyển viện → trạng thái hồ sơ tương ứng chặn sinh task mới; task cũ đóng hàng loạt có kiểm soát.
- Import dữ liệu cũ tạo hàng nghìn task quá hạn ngày đầu → chế độ "khởi tạo baseline": phân lô, không đánh dấu quá hạn xử lý ngay.
- Hai chi nhánh cùng chăm một bệnh nhân → task gắn theo tenant, hiển thị chi nhánh khám gần nhất để phân công hợp lý.

## 12.7. Acceptance criteria

- **AC-M12-01:** Bộ test rule: mỗi GAP-R1…R9 có case sinh đúng task, đúng ưu tiên; chạy job 2 lần không nhân đôi task.
- **AC-M12-02:** Bệnh nhân quá hạn tái khám + sắp hết thuốc → 1 task với 2 lý do.
- **AC-M12-03:** Kết quả "Đã đặt lịch" liên kết được đến appointment tồn tại.
- **AC-M12-04:** Dashboard tuần hiển thị: số task sinh ra, xử lý đúng hạn, tỷ lệ chuyển thành lịch tái khám.

---

