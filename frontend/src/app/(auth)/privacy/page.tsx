import type { Metadata } from 'next'
import { LegalDocument, type LegalSection } from '@/components/patient/consent/LegalDocument'
import { PRIVACY_VERSION } from '@/lib/legal'

export const metadata: Metadata = {
  title: 'MetoCare — Chính sách quyền riêng tư',
}

const SECTIONS: readonly LegalSection[] = [
  {
    heading: 'Dữ liệu chúng tôi thu thập',
    body: [
      'MetoCare thu thập thông tin bạn cung cấp: họ tên, số điện thoại, hồ sơ sức khỏe, kết quả xét nghiệm, chỉ số và thuốc.',
      'Chúng tôi cũng ghi nhận thông tin kỹ thuật cơ bản (phiên bản ứng dụng, múi giờ, thiết bị) để vận hành và bảo mật dịch vụ.',
    ],
  },
  {
    heading: 'Mục đích sử dụng dữ liệu',
    body: [
      'Dữ liệu sức khỏe được dùng để hiển thị hồ sơ, hỗ trợ theo dõi sức khỏe và để trợ lý AI phân tích nhằm đưa ra thông tin tham khảo cho bạn.',
      'Chúng tôi không bán dữ liệu cá nhân của bạn cho bên thứ ba.',
    ],
  },
  {
    heading: 'Lưu trữ và bảo mật',
    body: [
      'Hồ sơ sức khỏe của bạn được lưu trữ an toàn. Các trường dữ liệu nhạy cảm được mã hóa.',
      'Chúng tôi áp dụng các biện pháp kỹ thuật và tổ chức phù hợp để bảo vệ dữ liệu khỏi truy cập trái phép.',
    ],
  },
  {
    heading: 'Chia sẻ với bác sĩ',
    body: [
      'Hồ sơ của bạn chỉ được chia sẻ với bác sĩ khi bạn chủ động liên kết. Bạn kiểm soát và có thể thu hồi quyền này bất cứ lúc nào.',
    ],
  },
  {
    heading: 'Quyền của bạn',
    body: [
      'Bạn có quyền truy cập, chỉnh sửa và yêu cầu xóa dữ liệu cá nhân của mình.',
      'Bạn có thể rút lại sự đồng ý cho việc xử lý dữ liệu trong phần Cài đặt > Quyền riêng tư.',
    ],
  },
  {
    heading: 'Lưu giữ dữ liệu',
    body: [
      'Chúng tôi lưu giữ dữ liệu của bạn trong thời gian tài khoản còn hoạt động và trong khoảng thời gian cần thiết theo quy định pháp luật.',
      'Khi bạn yêu cầu xóa tài khoản, dữ liệu cá nhân sẽ được xóa hoặc ẩn danh, trừ phần bắt buộc phải lưu theo luật.',
    ],
  },
  {
    heading: 'Thay đổi chính sách',
    body: [
      'Chính sách này có thể được cập nhật. Khi có thay đổi quan trọng, chúng tôi sẽ thông báo trong ứng dụng và cập nhật số phiên bản.',
    ],
  },
  {
    heading: 'Liên hệ',
    body: [
      'Nếu có câu hỏi về quyền riêng tư, vui lòng liên hệ bộ phận hỗ trợ của MetoCare qua email hotro@metocare.vn.',
    ],
  },
]

export default function PrivacyPage() {
  return (
    <LegalDocument
      title="Chính sách quyền riêng tư"
      version={PRIVACY_VERSION}
      updated="02/07/2026"
      intro="MetoCare tôn trọng và bảo vệ dữ liệu sức khỏe của bạn."
      sections={SECTIONS}
    />
  )
}
