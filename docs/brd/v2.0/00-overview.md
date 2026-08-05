# BRD CHI TIẾT – METOCARE CLINIC SAAS
## Hệ thống quản lý bệnh nhân mạn tính & tăng tỷ lệ tái khám cho phòng khám Nội tiết – Tim mạch – Chuyển hóa

| Thuộc tính | Giá trị |
|---|---|
| Phiên bản | 2.0 – Detailed Module Specification |
| Trạng thái | Draft for Approval |
| Kế thừa | BRD v1.0 (Executive BRD) |
| Chủ sở hữu sản phẩm | MetoCare |
| Ngày cập nhật | 07/2026 |
| Người đọc mục tiêu | BOD, Product, Engineering, QA, Pilot Clinic |

---

## Quy ước tài liệu

- **Mã module:** M01–M18.
- **Mã user story:** `US-<module>-<số>` (ví dụ US-M06-03).
- **Mã business rule:** `BR-<module>-<số>`. Business rule là bắt buộc, enforce tại backend.
- **Mã acceptance criteria:** `AC-<module>-<số>`. Dùng làm điều kiện nghiệm thu và cơ sở viết test case.
- **Mức ưu tiên:** P0 (chặn go-live), P1 (bắt buộc trong phase), P2 (nice-to-have trong phase).
- **PHI:** Protected Health Information – dữ liệu sức khỏe định danh được của bệnh nhân.
- Tất cả quyền truy cập mô tả trong tài liệu này phải được kiểm soát tại **backend (API layer)**; việc ẩn/hiện menu ở frontend chỉ là UX, không phải cơ chế bảo mật.

## Danh mục module

| Mã | Module | Phase | Ưu tiên |
|---|---|---|---|
| M01 | Quản lý Tenant & Phòng khám | C0 | P0 |
| M02 | Quản lý Chi nhánh | C0 | P0 |
| M03 | Nhân sự, Membership & RBAC | C0 | P0 |
| M04 | Subscription & Entitlement | C0 | P0 |
| M05 | Dịch vụ & Bảng giá | C1 | P0 |
| M06 | Quản lý Bệnh nhân | C1 | P0 |
| M07 | Quản lý Lịch hẹn | C1 | P0 |
| M08 | Check-in & Hàng chờ | C1 | P0 |
| M09 | Khám bệnh & Ghi chú lâm sàng | C1 | P0 |
| M10 | Thu phí & Hóa đơn | C1 | P1 |
| M11 | Care Plan – Kế hoạch chăm sóc | C2 | P0 |
| M12 | Care Gap Queue | C2 | P0 |
| M13 | CRM Chăm sóc bệnh nhân | C2 | P1 |
| M14 | Clinical Copilot (AI) | C3 | P1 |
| M15 | Thông báo & Nhắc hẹn | C1–C2 | P0 |
| M16 | Dashboard & Báo cáo | C1–C2 | P1 |
| M17 | Consent & Quyền riêng tư | C0 | P0 |
| M18 | Audit Log | C0 | P0 |

---

