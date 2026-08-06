# M16 – DASHBOARD & BÁO CÁO

## 16.1. Ba dashboard (§10.14 BRD v1.0)

**Vận hành (realtime/ngày):** lịch hôm nay, đang chờ, no-show, bác sĩ đang làm việc, thời gian chờ trung bình, Care Gap cần xử lý.
**Kinh doanh:** doanh thu (ngày/tuần/tháng), lượt khám, doanh thu theo bác sĩ/dịch vụ, tỷ lệ tái khám, bệnh nhân mới vs quay lại, retention cohort 3/6/12 tháng.
**Lâm sàng:** tỷ lệ đạt mục tiêu điều trị; phân bố & xu hướng HbA1c, huyết áp, LDL-C, cân nặng theo cohort; tỷ lệ hoàn thành XN; danh sách nguy cơ xấu đi.

## 16.2. Định nghĩa chỉ số then chốt (metric dictionary – bắt buộc thống nhất trước build)

| Chỉ số | Định nghĩa |
|---|---|
| Tỷ lệ tái khám đúng hạn | Số lịch tái khám Completed trong [due−7; due+7 ngày] / tổng lịch tái khám đến hạn kỳ báo cáo |
| No-show rate | Lịch No-show / (Completed + No-show) trong kỳ |
| Retention 3 tháng | % bệnh nhân có ≥1 encounter trong 90 ngày sau lần khám đầu của cohort |
| Bệnh nhân được chăm sóc chủ động | Số bệnh nhân distinct có ≥1 hoạt động chăm sóc (M13) trong tuần |
| Chuyển đổi chăm sóc → tái khám | Task outcome "Đã đặt lịch" có appointment Completed / tổng task đóng trong kỳ |
| Đạt mục tiêu điều trị | % bệnh nhân active có care plan mà chỉ số mục tiêu gần nhất đạt ngưỡng |

## 16.3. Business rules

- **BR-M16-01 (P0):** Báo cáo tôn trọng RBAC: kế toán không thấy dashboard lâm sàng; bác sĩ mặc định thấy số liệu của mình, số liệu toàn phòng khám theo quyền Owner cấp.
- **BR-M16-02 (P0):** Export CSV/XLSX theo quyền; **không export PHI hàng loạt** cho vai trò không có quyền; mọi export ghi audit (ai, báo cáo gì, bộ lọc, số dòng).
- **BR-M16-03 (P1):** Dashboard lâm sàng chỉ tổng hợp từ dữ liệu trong phạm vi consent & quyền truy cập.
- **BR-M16-04 (P1):** Số liệu tổng hợp nặng tính bằng background job/materialized view; dashboard tải < 3 giây (NFR §15.2).
- **BR-M16-05 (P2):** Cohort ẩn danh khi nhóm < 5 bệnh nhân (chống suy đoán danh tính từ số liệu nhỏ).

## 16.4. Acceptance criteria

- **AC-M16-01:** Cùng một kỳ, tỷ lệ tái khám trên dashboard = kết quả truy vấn theo metric dictionary (test đối soát).
- **AC-M16-02:** Accountant mở dashboard lâm sàng → 403.
- **AC-M16-03:** Export danh sách bệnh nhân bằng vai trò không đủ quyền → chặn; đủ quyền → có audit record.

---

