# M17 – CONSENT & QUYỀN RIÊNG TƯ

## 17.1. Danh mục consent tối thiểu (§13.1 BRD v1.0)

| Consent | Scope | Mặc định |
|---|---|---|
| C1 Chia sẻ hồ sơ với phòng khám X | Theo tenant, theo nhóm dữ liệu | Bật khi bệnh nhân đăng ký khám tại X (dữ liệu do X tạo); dữ liệu từ nơi khác: tắt |
| C2 Chia sẻ kết quả xét nghiệm | Theo tenant | Theo C1 |
| C3 Cho phép AI phân tích hồ sơ | Theo tenant | Tắt – opt-in |
| C4 Nhận thông báo | Theo kênh (Push/SMS/Email/Zalo) | Push bật; kênh khác opt-in |
| C5 Tham gia chương trình chăm sóc chủ động | Theo tenant | Hỏi khi ghi danh chương trình |

## 17.2. Business rules

- **BR-M17-01 (P0):** Mỗi consent có: scope, phiên bản nội dung, thời điểm cấp, kênh cấp (app/quầy), thời hạn (nếu có), trạng thái. Bằng chứng lưu bất biến.
- **BR-M17-02 (P0):** Thu hồi consent có hiệu lực tức thời cho xử lý tương lai; **không xóa** audit và hồ sơ nghiệp vụ hợp pháp đã phát sinh (§13.2).
- **BR-M17-03 (P0):** AI gateway kiểm tra C3 trước mỗi call (đối chiếu BR-M14-01); notification service kiểm tra C4 trước mỗi lần gửi.
- **BR-M17-04 (P1):** Bệnh nhân chưa có tài khoản app: consent thu tại quầy (giấy/ký số) do lễ tân ghi nhận, có trường người chứng kiến; khi bệnh nhân kích hoạt app, consent hiển thị để xác nhận lại.
- **BR-M17-05 (P1):** Tuân thủ pháp luật Việt Nam về bảo vệ dữ liệu cá nhân hiện hành (bao gồm quy định về dữ liệu cá nhân nhạy cảm – dữ liệu sức khỏe); phân loại dữ liệu và chính sách lưu trữ/chuyển giao cần rà soát pháp lý trước pilot.

## 17.3. Acceptance criteria

- **AC-M17-01:** Tắt C3 → mọi AI call cho bệnh nhân đó bị chặn ngay.
- **AC-M17-02:** Thu hồi C1 với phòng khám B → phòng khám B mất quyền xem dữ liệu ngoài phạm vi do B tạo; dữ liệu B tạo vẫn thuộc B theo nghĩa vụ lưu trữ.
- **AC-M17-03:** Mọi consent hiển thị được lịch sử phiên bản: cấp – thay đổi – thu hồi.

---

