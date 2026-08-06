# PHỤ LỤC B – YÊU CẦU PHI CHỨC NĂNG ÁP DỤNG CHO MỌI MODULE

Kế thừa nguyên trạng §15 BRD v1.0, nhấn mạnh các gate:

1. **Bảo mật (P0):** tenant isolation có test chéo; RBAC backend; TLS; encryption at rest; không log PHI; controlled error (không lộ stack trace/ciphertext); rate limit; session timeout; secret scan trong CI; production security gate trước go-live.
2. **Hiệu năng:** danh sách chính < 2s, dashboard < 3s, pagination bắt buộc, tác vụ nặng background job, AI timeout + fallback.
3. **Khả dụng:** responsive; font body ≥16px; touch target ≥44px; không horizontal scroll ở 390px; loading/empty/error/retry đầy đủ; UI tiếng Việt.
4. **Mở rộng:** thiết kế cho 1.000 clinic, 10.000 nhân viên, 1 triệu hồ sơ, 10 triệu bản ghi đo/XN.

---

