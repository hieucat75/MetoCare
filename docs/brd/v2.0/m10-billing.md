# M10 – THU PHÍ & HÓA ĐƠN

## 10.1. Mục đích & phạm vi (MVP)

Ghi nhận doanh thu tại quầy: hóa đơn từ dịch vụ/gói/phụ phí/giảm giá, thanh toán đa phương thức, trạng thái công nợ và audit chỉnh sửa. **Ngoài phạm vi MVP:** hóa đơn điện tử, payment gateway, ví điện tử (Phase C4), kế toán tổng hợp.

## 10.2. User stories

- **US-M10-01:** Là lễ tân, tôi muốn tạo hóa đơn từ encounter với dịch vụ đã dùng để thu tiền một lần, không nhập lại.
- **US-M10-02:** Là lễ tân, tôi muốn ghi nhận thanh toán một phần (đặt cọc gói) và theo dõi phần còn lại.
- **US-M10-03:** Là kế toán, tôi muốn xem toàn bộ giao dịch, công nợ và các hóa đơn bị điều chỉnh/hoàn tiền kèm lý do.
- **US-M10-04:** Là Clinic Owner, tôi muốn giảm giá vượt ngưỡng phải được người có quyền phê duyệt.

## 10.3. Trạng thái hóa đơn (BILL-03)

```text
Draft → Issued → Unpaid → Partially paid → Paid
Issued/Unpaid → Cancelled (lý do bắt buộc)
Paid → Refunded (một phần/toàn bộ, quyền + lý do + audit)
Hóa đơn Paid bị khóa: không sửa dòng hàng; điều chỉnh = credit note/refund
```

## 10.4. Business rules

- **BR-M10-01 (P0):** Lễ tân không sửa được hóa đơn đã khóa (BILL-04); mọi điều chỉnh giá/giảm giá/hoàn tiền ghi audit (BILL-05) với giá trị trước/sau và lý do.
- **BR-M10-02 (P0):** Giá dòng hàng lấy từ price_snapshot (BR-M05-01); giảm giá thủ công có trần theo vai trò (cấu hình, VD lễ tân ≤10%, Admin ≤30%, vượt trần cần phê duyệt).
- **BR-M10-03 (P1):** Một encounter/appointment liên kết tối đa một hóa đơn chính; dịch vụ phát sinh thêm ghi bổ sung vào hóa đơn trước khi khóa hoặc tạo hóa đơn phụ.
- **BR-M10-04 (P1):** Sử dụng lượt trong gói chăm sóc tạo dòng hàng giá 0 + ghi giảm số dư quyền lợi (đối soát với M05).
- **BR-M10-05 (P1):** Số hóa đơn liên tục theo tenant/chi nhánh, không tái sử dụng số của hóa đơn Cancelled.

## 10.5. Acceptance criteria

- **AC-M10-01:** Hóa đơn Paid: API sửa dòng hàng bị từ chối; refund tạo bản ghi riêng với audit.
- **AC-M10-02:** Giảm giá 15% bằng tài khoản lễ tân (trần 10%) → yêu cầu phê duyệt hoặc từ chối.
- **AC-M10-03:** Thanh toán 2 lần (50% + 50%) → trạng thái chuyển Partially paid → Paid đúng số dư.
- **AC-M10-04:** Kế toán xem được báo cáo doanh thu nhưng không mở được clinical note (403).

---

