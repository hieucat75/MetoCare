'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import { Activity, Sparkles, ShieldCheck, type LucideIcon } from 'lucide-react'
import { useAuth } from '@/lib/auth/context'
import { getRoleHomePath } from '@/lib/api/auth'
import { MetoMark } from '@/components/patient/glass'

interface Slide {
  icon: LucideIcon
  title: React.ReactNode
  body: string
}

const SLIDES: Slide[] = [
  {
    icon: Activity,
    title: (
      <>
        Theo dõi chỉ số
        <br />
        chuyển hoá mỗi ngày
      </>
    ),
    body: 'Đường huyết, huyết áp, cân nặng — trực quan, dễ hiểu, có ngưỡng mục tiêu rõ ràng.',
  },
  {
    icon: Sparkles,
    title: (
      <>
        Trợ lý AI
        <br />
        đồng hành cùng bạn
      </>
    ),
    body: 'Hỏi đáp sức khoẻ tức thì và gợi ý lối sống — mọi nội dung đều chờ bác sĩ của bạn duyệt.',
  },
  {
    icon: ShieldCheck,
    title: (
      <>
        An toàn
        <br />& riêng tư
      </>
    ),
    body: 'Dữ liệu của bạn được bảo vệ. Bạn luôn là người quyết định ai được xem hồ sơ của mình.',
  },
]

export default function WelcomePage() {
  const router = useRouter()
  const { user, isLoading } = useAuth()
  const [index, setIndex] = React.useState(0)

  React.useEffect(() => {
    if (!isLoading && user) router.replace(getRoleHomePath(user.role))
  }, [isLoading, user, router])

  const slide = SLIDES[index]
  const isLast = index === SLIDES.length - 1
  const Icon = slide.icon

  return (
    <div
      className="flex min-h-screen flex-col text-white"
      style={{
        backgroundImage:
          'radial-gradient(440px 380px at 20% 4%, rgba(120,240,196,0.5), transparent 60%), linear-gradient(160deg,#0F9C6E,#0B7F5B 60%,#14916B)',
      }}
    >
      {/* Top bar: brand + skip */}
      <div className="flex items-center justify-between px-6 pt-[max(20px,env(safe-area-inset-top))]">
        <div className="flex items-center gap-2">
          <MetoMark size={28} ring="#fff" leaf="#7FE0BD" />
          <span className="text-[18px] font-bold tracking-tight">metocare</span>
        </div>
        <button
          type="button"
          onClick={() => router.push('/login')}
          className="min-h-[44px] px-2 text-[15px] font-semibold text-white/80"
        >
          Bỏ qua
        </button>
      </div>

      {/* Slide */}
      <div className="flex flex-1 flex-col items-center justify-center px-9 text-center">
        <div
          className="grid size-[210px] place-items-center rounded-full"
          style={{
            background: 'rgba(255,255,255,0.12)',
            border: '1px solid rgba(255,255,255,0.25)',
            boxShadow: 'inset 0 2px 12px rgba(255,255,255,0.2)',
          }}
        >
          <div className="grid size-[140px] place-items-center rounded-[36px] bg-white/15">
            <Icon className="size-[72px]" aria-hidden="true" />
          </div>
        </div>
        <h1 className="mt-10 text-[27px] font-extrabold leading-snug tracking-tight">{slide.title}</h1>
        <p className="mt-4 max-w-[34ch] text-[16px] leading-relaxed text-white/85">{slide.body}</p>
      </div>

      {/* Dots + CTA */}
      <div className="px-7 pb-[max(36px,env(safe-area-inset-bottom))]">
        <div className="mb-6 flex justify-center gap-2">
          {SLIDES.map((_, i) => (
            <span
              key={i}
              className="h-2 rounded-full transition-all"
              style={{
                width: i === index ? 26 : 8,
                background: i === index ? '#fff' : 'rgba(255,255,255,0.4)',
              }}
            />
          ))}
        </div>

        {isLast ? (
          <button
            type="button"
            onClick={() => router.push('/register')}
            className="h-[54px] w-full rounded-[17px] bg-white/95 text-[16.5px] font-bold text-[#0F9C6E] shadow-[0_16px_30px_-12px_rgba(0,0,0,0.3)]"
          >
            Bắt đầu ngay
          </button>
        ) : (
          <button
            type="button"
            onClick={() => setIndex((i) => Math.min(i + 1, SLIDES.length - 1))}
            className="h-[54px] w-full rounded-[17px] bg-white/95 text-[16.5px] font-bold text-[#0F9C6E] shadow-[0_16px_30px_-12px_rgba(0,0,0,0.3)]"
          >
            Tiếp tục
          </button>
        )}

        <button
          type="button"
          onClick={() => router.push('/login')}
          className="mt-4 h-11 w-full text-center text-[15px] font-medium text-white/85"
        >
          Đã có tài khoản? <span className="font-bold underline underline-offset-2">Đăng nhập</span>
        </button>
      </div>
    </div>
  )
}
