# PHỤ LỤC A – MA TRẬN RBAC CHI TIẾT

Ký hiệu: ✓ toàn quyền · R chỉ đọc · L hạn chế (theo scope mô tả trong module) · ✗ cấm

| Resource / Action | Owner | Admin | Doctor | Nurse | Reception | Care | Accountant |
|---|---|---|---|---|---|---|---|
| Cấu hình clinic (M01) | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Chi nhánh (M02) | ✓ | ✓ | R | R | R | R | ✗ |
| Staff & vai trò (M03) | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Subscription (M04) | ✓ | R | ✗ | ✗ | ✗ | ✗ | R |
| Dịch vụ & giá (M05) | ✓ | ✓ | R | R | R | R | R |
| Hồ sơ hành chính BN (M06) | ✓ | ✓ | R | R | ✓ | L (care context) | ✗ |
| Hồ sơ lâm sàng (M06/M09) | L (theo quyền) | L (theo quyền) | ✓ (phạm vi phân công) | L (hỗ trợ) | ✗ | ✗ | ✗ |
| Lịch hẹn (M07) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ |
| Check-in/Hàng chờ (M08) | ✓ | ✓ | ✓ (của mình) | ✓ | ✓ | R | ✗ |
| Clinical note (M09) | ✗ | ✗ | ✓ | L (S/O hỗ trợ) | ✗ | ✗ | ✗ |
| Finalize note | ✗ | ✗ | ✓ | ✗ | ✗ | ✗ | ✗ |
| Clinical Copilot (M14) | ✗ | ✗ | ✓ | ✗ | ✗ | ✗ | ✗ |
| Care plan (M11) | R | R | ✓ | R | ✗ | L (item vận hành) | ✗ |
| Care Gap Queue (M12) | ✓ | ✓ | ✓ (ca Cần bác sĩ) | ✓ | L | ✓ | ✗ |
| CRM chăm sóc (M13) | ✓ | ✓ | R | ✓ | L | ✓ | ✗ |
| Hóa đơn (M10) | ✓ | ✓ | L (xem của encounter mình) | ✗ | ✓ (tạo/thu) | ✗ | ✓ |
| Refund/điều chỉnh giá | ✓ | ✓ | ✗ | ✗ | L (trong trần) | ✗ | R |
| Báo cáo doanh thu (M16) | ✓ | ✓ | L (của mình) | ✗ | L | ✗ | ✓ |
| Dashboard lâm sàng (M16) | L | L | ✓ (của mình) | L | ✗ | ✗ | ✗ |
| Export dữ liệu | ✓ | ✓ | L | ✗ | ✗ | ✗ | L (tài chính) |
| Consent (M17) | R | R | R | R | L (ghi tại quầy) | R (trạng thái) | ✗ |
| Audit (M18) | R | R | ✗ | ✗ | ✗ | ✗ | ✗ |

---

