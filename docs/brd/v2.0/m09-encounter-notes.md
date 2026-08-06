# M09 – KHÁM BỆNH & GHI CHÚ LÂM SÀNG

## 9.1. Mục đích & phạm vi

Quản lý encounter (lượt khám) và clinical note theo cấu trúc SOAP, với nguyên tắc **append-only** sau khi finalize – nền tảng pháp lý và chất lượng dữ liệu cho toàn bộ phân tích phía sau (Care Gap, Copilot, dashboard lâm sàng).

## 9.2. User stories

- **US-M09-01:** Là bác sĩ, tôi muốn bắt đầu encounter từ appointment với hồ sơ và AI briefing đã sẵn sàng, để không mất thời gian lục lại lịch sử.
- **US-M09-02:** Là bác sĩ, tôi muốn ghi note theo SOAP với template theo chuyên khoa (ĐTĐ, THA, tuyến giáp) để nhập nhanh và chuẩn hóa.
- **US-M09-03:** Là bác sĩ, tôi muốn lưu Draft giữa chừng và finalize khi hoàn tất; sau finalize, mọi chỉnh sửa phải qua amendment.
- **US-M09-04:** Là điều dưỡng, tôi muốn nhập sinh hiệu vào phần Objective trước khi bác sĩ khám, nhưng không sửa được Assessment/Plan.
- **US-M09-05:** Là bác sĩ, tôi muốn ghi chẩn đoán có mã (ICD-10 hoặc danh mục nội bộ chuẩn hóa) để dữ liệu dùng được cho báo cáo cohort.

## 9.3. Cấu trúc Encounter (ENCOUNTER-02)

| Thành phần | Chi tiết |
|---|---|
| Header | patient, doctor, branch, thời gian bắt đầu/kết thúc, appointment liên kết, loại (theo hẹn/walk-in/tele) |
| Lý do khám | Text + danh mục gợi ý |
| Sinh hiệu | Mạch, HA, nhiệt độ, SpO2, cân nặng, chiều cao, BMI (tự tính), đường huyết mao mạch |
| S – Subjective | Triệu chứng, bệnh sử, tuân thủ thuốc, lối sống |
| O – Objective | Khám thực thể, sinh hiệu, kết quả XN tham chiếu |
| A – Assessment | Nhận định, chẩn đoán (mã + text), đánh giá mục tiêu điều trị |
| P – Plan | Chỉ định XN, thuốc, tái khám, giáo dục bệnh nhân → liên kết Care Plan (M11) |

## 9.4. State machine của Note (NOTE-02)

```text
Draft ──(bác sĩ finalize)──▶ Finalized ──(cần sửa)──▶ + Amendment (note con, append-only)
Draft: sửa tự do bởi chính tác giả; Nurse chỉ ghi phần được phép (sinh hiệu/Objective hỗ trợ)
Finalized: immutable; không update/delete; sửa sai = amendment ghi rõ lý do
Encounter không có note finalize sau X giờ (cấu hình, mặc định 24h) → nhắc bác sĩ
```

## 9.5. Business rules

- **BR-M09-01 (P0):** Note Finalized là bất biến (append-only invariant). Backend từ chối mọi UPDATE/DELETE trực tiếp; amendment tạo bản ghi mới liên kết note gốc, hiển thị chuỗi phiên bản đầy đủ.
- **BR-M09-02 (P0):** Chỉ Doctor được finalize note và ghi Assessment/Plan; Nurse hỗ trợ Subjective/Objective, không sửa kết luận (nhất quán §7.5 BRD v1.0).
- **BR-M09-03 (P0):** Bác sĩ chỉ mở encounter cho bệnh nhân trong phạm vi phân công (lịch hẹn của mình, hàng chờ của mình, hoặc được Admin gán).
- **BR-M09-04 (P1):** Encounter phải liên kết appointment hoặc đánh dấu walk-in; một appointment tối đa một encounter chính.
- **BR-M09-05 (P1):** Nội dung AI (Copilot) không tự ghi vào note; bác sĩ chèn thủ công/chấp nhận từng phần, hệ thống đánh dấu đoạn có nguồn gốc AI (phục vụ audit AI-05).
- **BR-M09-06 (P1):** Chỉ định xét nghiệm trong Plan tự tạo mục theo dõi "chưa thực hiện" (đầu vào GAP-01).

## 9.6. Ngoại lệ & edge cases

- Mất mạng giữa lúc ghi note → autosave draft cục bộ + đồng bộ lại; không mất dữ liệu nhập.
- Bác sĩ quên finalize, nghỉ phép → Admin không được finalize thay; hệ thống nhắc bác sĩ; note quá 7 ngày ở Draft đưa vào báo cáo chất lượng.
- Hai tab cùng sửa một draft → khóa phiên bản, tab sau nhận cảnh báo xung đột.
- Bệnh nhân từ chối tiếp tục khám giữa chừng → encounter đóng với trạng thái Incomplete + lý do.

## 9.7. Acceptance criteria

- **AC-M09-01:** Update trực tiếp note Finalized qua API → bị từ chối; amendment tạo thành công và hiển thị lịch sử phiên bản.
- **AC-M09-02:** Tài khoản Nurse không ghi được Assessment/Plan, không finalize được (403).
- **AC-M09-03:** Bác sĩ A không mở được encounter của bệnh nhân chỉ thuộc phân công bác sĩ B.
- **AC-M09-04:** Autosave draft: đóng trình duyệt đột ngột, mở lại còn ≥ nội dung tại lần autosave gần nhất (≤30 giây).
- **AC-M09-05:** Chỉ định XN trong Plan xuất hiện trong danh sách "XN chưa thực hiện" của bệnh nhân.

## 9.8. Audit

Mở encounter, tạo/sửa draft (theo phiên), finalize, amendment, ai xem note của bệnh nhân nào.

---

