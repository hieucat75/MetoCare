import type { Metadata } from 'next'
import Link from 'next/link'
import { Mail, Phone, Headset, ArrowLeft } from 'lucide-react'

export const metadata: Metadata = {
  title: 'Liên hệ · MetoCare',
  description: 'Các kênh liên hệ và chăm sóc khách hàng của MetoCare.',
}

type ContactChannel = {
  icon: typeof Mail
  label: string
  value: string
  href: string
}

const CHANNELS: ContactChannel[] = [
  {
    icon: Mail,
    label: 'Email hỗ trợ chung',
    value: 'contact@metocare.me',
    href: 'mailto:contact@metocare.me',
  },
  {
    icon: Headset,
    label: 'Chăm sóc khách hàng (CSKH)',
    value: 'cskh@metocare.me',
    href: 'mailto:cskh@metocare.me',
  },
  {
    icon: Phone,
    label: 'Điện thoại / Hotline',
    value: '+84 904 641 819',
    href: 'tel:+84904641819',
  },
]

export default function ContactPage() {
  return (
    <div className="min-h-screen bg-background px-4 py-10">
      <div className="mx-auto w-full max-w-lg">
        <Link
          href="/"
          className="mb-6 inline-flex min-h-[44px] items-center gap-2 text-body-sm text-text-muted transition-colors hover:text-text"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          Về trang chủ
        </Link>

        <h1 className="text-display-xs font-bold text-text">Liên hệ MetoCare</h1>
        <p className="mt-2 text-body-md text-text-muted">
          Chúng tôi luôn sẵn sàng hỗ trợ bạn. Vui lòng liên hệ qua các kênh dưới đây.
        </p>

        <ul className="mt-8 space-y-3">
          {CHANNELS.map((c) => {
            const Icon = c.icon
            return (
              <li key={c.href}>
                <a
                  href={c.href}
                  className="flex min-h-[64px] items-center gap-4 rounded-2xl border border-border bg-white p-4 transition-colors hover:bg-secondary-50"
                >
                  <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
                    <Icon className="h-5 w-5" aria-hidden="true" />
                  </span>
                  <span className="min-w-0">
                    <span className="block text-body-xs text-text-muted">{c.label}</span>
                    <span className="block break-words text-body-md font-semibold text-text">
                      {c.value}
                    </span>
                  </span>
                </a>
              </li>
            )
          })}
        </ul>

        <p className="mt-8 text-body-xs text-text-subtle">
          Thời gian hỗ trợ: 8:00–20:00 (Thứ 2 – Chủ nhật). MetoCare không thay thế cấp cứu hoặc khám
          trực tiếp khi có dấu hiệu nguy hiểm.
        </p>
      </div>
    </div>
  )
}
