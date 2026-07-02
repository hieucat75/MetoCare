import type { Metadata } from 'next'
import { LegalDocument, type LegalSection } from '@/components/patient/consent/LegalDocument'
import { TERMS_VERSION } from '@/lib/legal'

export const metadata: Metadata = {
  title: 'MetoCare — Điều khoản sử dụng',
}

const SECTIONS: readonly LegalSection[] = [
  {
    heading: 'Chấp nhận điều khoản',
    body: [
      'Bằng việc tạo tài khoản và sử dụng MetoCare, bạn đồng ý với các điều khoản dưới đây. Nếu không đồng ý, vui lòng ngừng sử dụng ứng dụng.',
    ],
  },
  {
    heading: 'Dịch vụ MetoCare cung cấp',
    body: [
      'MetoCare là nền tảng hỗ trợ theo dõi và quản lý sức khỏe chuyển hóa. Ứng dụng giúp bạn lưu trữ hồ sơ sức khỏe, xem kết quả xét nghiệm, theo dõi chỉ số và thuốc.',
      'MetoCare có trợ lý AI hỗ trợ bạn hiểu dữ liệu sức khỏe của mình. AI chỉ mang tính tham khảo và không thay thế chẩn đoán hoặc điều trị của bác sĩ.',
    ],
  },
  {
    heading: 'Tài khoản của bạn',
    body: [
      'Bạn chịu trách nhiệm bảo mật thông tin đăng nhập và mọi hoạt động diễn ra trong tài khoản của mình.',
      'Bạn cam kết cung cấp thông tin chính xác và cập nhật khi sử dụng dịch vụ.',
    ],
  },
  {
    heading: 'Liên kết với bác sĩ',
    body: [
      'Khi bạn chủ động liên kết với một bác sĩ, bác sĩ đó được phép xem hồ sơ sức khỏe của bạn nhằm phục vụ việc chăm sóc.',
      'Bạn có thể chấm dứt liên kết với bác sĩ bất cứ lúc nào trong phần cài đặt.',
    ],
  },
  {
    heading: 'Giới hạn trách nhiệm y tế',
    body: [
      'MetoCare không phải là dịch vụ khám chữa bệnh cấp cứu. Trong trường hợp khẩn cấp, hãy liên hệ cơ sở y tế gần nhất hoặc gọi cấp cứu.',
      'Mọi quyết định điều trị cần dựa trên tư vấn của bác sĩ có chuyên môn.',
    ],
  },
  {
    heading: 'Ngừng sử dụng',
    body: [
      'Bạn có thể ngừng sử dụng dịch vụ và yêu cầu xóa tài khoản bất cứ lúc nào theo quy định về dữ liệu cá nhân.',
    ],
  },
  {
    heading: 'Quyền sở hữu trí tuệ',
    body: [
      'Toàn bộ nội dung, giao diện, thương hiệu và phần mềm của MetoCare thuộc quyền sở hữu của MetoCare hoặc các bên cấp phép. Bạn không được sao chép, phân phối hay tạo sản phẩm phái sinh khi chưa được phép.',
      'Dữ liệu sức khỏe bạn nhập vào vẫn thuộc về bạn; MetoCare chỉ xử lý dữ liệu này để cung cấp dịch vụ theo Chính sách quyền riêng tư.',
    ],
  },
  {
    heading: 'Giới hạn trách nhiệm',
    body: [
      'Trong phạm vi pháp luật cho phép, MetoCare không chịu trách nhiệm với các thiệt hại gián tiếp phát sinh từ việc sử dụng ứng dụng, bao gồm quyết định y tế được đưa ra chỉ dựa trên thông tin tham khảo trong ứng dụng.',
      'Dịch vụ được cung cấp trên cơ sở "hiện có". Chúng tôi nỗ lực duy trì tính chính xác và sẵn sàng của dịch vụ nhưng không cam kết không gián đoạn.',
    ],
  },
  {
    heading: 'Thay đổi điều khoản',
    body: [
      'MetoCare có thể cập nhật điều khoản theo thời gian. Khi có thay đổi quan trọng, bạn sẽ được thông báo và cần chấp nhận lại phiên bản mới trước khi tiếp tục sử dụng.',
    ],
  },
  {
    heading: 'Luật áp dụng và liên hệ',
    body: [
      'Các điều khoản này được điều chỉnh bởi pháp luật Việt Nam.',
      'Mọi thắc mắc xin liên hệ bộ phận hỗ trợ MetoCare qua email hotro@metocare.vn.',
    ],
  },
]

export default function TermsPage() {
  return (
    <LegalDocument
      title="Điều khoản sử dụng"
      version={TERMS_VERSION}
      updated="02/07/2026"
      intro="Vui lòng đọc kỹ các điều khoản sau trước khi sử dụng MetoCare."
      sections={SECTIONS}
    />
  )
}
