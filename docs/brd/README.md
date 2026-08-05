# MetoCare Clinic SaaS – BRD

## Cấu trúc thư mục

```
docs/brd/
├── README.md                      ← file này
├── v1.0/
│   └── executive-brd.md           # BRD điều hành gốc, đã trình BOD (căn cứ §25 quyết định phê duyệt)
└── v2.0/
    ├── 00-overview.md              # Quy ước tài liệu + danh mục 18 module
    ├── m01-tenant.md               # Quản lý Tenant & Phòng khám            [C0][P0]
    ├── m02-branch.md               # Quản lý Chi nhánh                     [C0][P0]
    ├── m03-staff-rbac.md           # Nhân sự, Membership & RBAC            [C0][P0]
    ├── m04-subscription.md         # Subscription & Entitlement            [C0][P0]
    ├── m05-services-pricing.md     # Dịch vụ & Bảng giá                    [C1][P0]
    ├── m06-patient.md              # Quản lý Bệnh nhân                     [C1][P0]
    ├── m07-appointment.md          # Quản lý Lịch hẹn                      [C1][P0]
    ├── m08-checkin-queue.md        # Check-in & Hàng chờ                   [C1][P0]
    ├── m09-encounter-notes.md      # Khám bệnh & Ghi chú lâm sàng           [C1][P0]
    ├── m10-billing.md              # Thu phí & Hóa đơn                     [C1][P1]
    ├── m11-care-plan.md            # Care Plan – Kế hoạch chăm sóc         [C2][P0]
    ├── m12-care-gap-queue.md       # Care Gap Queue (module cốt lõi)       [C2][P0]
    ├── m13-crm.md                  # CRM Chăm sóc bệnh nhân                [C2][P1]
    ├── m14-clinical-copilot.md     # Clinical Copilot (AI)                 [C3][P1]
    ├── m15-notifications.md        # Thông báo & Nhắc hẹn                  [C1-C2][P0]
    ├── m16-dashboard-reports.md    # Dashboard & Báo cáo                   [C1-C2][P1]
    ├── m17-consent-privacy.md      # Consent & Quyền riêng tư              [C0][P0]
    ├── m18-audit-log.md            # Audit Log                            [C0][P0]
    ├── appendix-a-rbac-matrix.md   # Ma trận RBAC chi tiết toàn hệ thống
    ├── appendix-b-nfr.md           # Yêu cầu phi chức năng dùng chung
    └── appendix-c-traceability.md  # Truy vết module → phase → acceptance
```

## Cách dùng

- **Đọc tổng quan / cho BOD, stakeholder:** bắt đầu từ `v1.0/executive-brd.md` (bản đã phê duyệt) rồi `v2.0/00-overview.md`.
- **Triển khai dev/QA một module cụ thể:** mở thẳng file `mNN-*.md` tương ứng — mỗi file tự đủ (actor, user story, business rule mã hóa `BR-Mxx-nn`, acceptance criteria `AC-Mxx-nn`).
- **Review RBAC toàn hệ thống:** `appendix-a-rbac-matrix.md`.
- **Kiểm tra điều kiện go-live theo phase:** `appendix-c-traceability.md`.
- **Trích dẫn trong code/PR:** dùng anchor dạng `docs/brd/v2.0/m12-care-gap-queue.md#125-vòng-đời-một-care-gap`.
- **Trích dẫn trong prompt cho Claude Code / OpenClaw:** tham chiếu trực tiếp đường dẫn file, ví dụ "theo BR-M09-01 trong docs/brd/v2.0/m09-encounter-notes.md, note đã finalize phải append-only".

## Quy tắc cập nhật

- Sửa BRD → tạo PR riêng, không gộp chung PR code, để review nghiệp vụ tách khỏi review kỹ thuật.
- Thay đổi ảnh hưởng nhiều module (VD đổi state machine appointment) → cập nhật đồng thời file module liên quan + `appendix-c-traceability.md`.
- Không sửa `v1.0/executive-brd.md` — đây là bản lưu trữ đã phê duyệt; mọi thay đổi nghiệp vụ đi vào v2.0 (hoặc v3.0 khi cần bump version lớn).
