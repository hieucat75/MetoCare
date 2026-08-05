# M18 – AUDIT LOG

## 18.1. Sự kiện bắt buộc (§15.5 BRD v1.0)

Đăng nhập/đăng xuất/thất bại; truy cập hồ sơ bệnh nhân; xem dữ liệu lâm sàng; tạo/finalize/amendment note; thay đổi vai trò & membership; export; thay đổi hóa đơn/giảm giá/hoàn tiền; AI call; accept/reject gợi ý AI; thay đổi consent; thay đổi trạng thái tenant; merge hồ sơ; override ưu tiên.

## 18.2. Business rules

- **BR-M18-01 (P0):** Audit log append-only, không sửa/xóa qua ứng dụng; actor, action, resource, tenant, thời điểm (UTC + hiển thị giờ VN), IP/device, trước/sau (với thay đổi dữ liệu).
- **BR-M18-02 (P0):** Nội dung audit không chứa PHI vượt mức cần thiết (tham chiếu ID thay vì chép nội dung note).
- **BR-M18-03 (P1):** Truy vấn audit theo quyền: Owner xem audit tenant mình; Platform Admin xem audit vận hành, không mặc định xem nội dung lâm sàng.
- **BR-M18-04 (P1):** Retention audit tối thiểu theo yêu cầu pháp lý (đề xuất ≥ 5 năm, chốt sau rà soát pháp lý).

## 18.3. Acceptance criteria

- **AC-M18-01:** 100% sự kiện trong danh mục 18.1 sinh audit record (test checklist).
- **AC-M18-02:** Không API nào sửa/xóa được audit record.
- **AC-M18-03:** Truy vấn "ai đã xem hồ sơ bệnh nhân X trong 30 ngày" trả kết quả đúng.

---

