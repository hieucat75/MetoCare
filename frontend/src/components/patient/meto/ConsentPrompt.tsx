'use client'
/**
 * ConsentPrompt — shown when backend returns consent_required: true.
 *
 * Implements the concise action-oriented consent pattern from the spec:
 * - Short explanation of what Meto needs
 * - List of data types it can access
 * - Three CTA chips: "Mở Quyền riêng tư", "Hỏi chung", "Để sau"
 */
import * as React from 'react'
import { useRouter } from 'next/navigation'
import { ShieldCheck } from 'lucide-react'

interface Props {
  onAskGeneral: () => void
  onDismiss: () => void
}

const CONSENT_MESSAGE = `Để cá nhân hóa cho bạn, Meto cần quyền đọc một số dữ liệu sức khỏe trong hồ sơ.`

const CONSENT_DATA_TYPES = [
  'Thuốc đang dùng',
  'Chỉ số sức khỏe',
  'Kế hoạch chăm sóc',
  'Lịch nhắc và lịch tái khám',
]

const CONSENT_SETTINGS_NOTE = 'Bạn có thể bật quyền này trong Cài đặt > Quyền riêng tư.'

export function ConsentPrompt({ onAskGeneral, onDismiss }: Props) {
  const router = useRouter()

  function handleOpenSettings() {
    // Navigate to consents settings page
    router.push('/consents')
  }

  return (
    <div
      className="rounded-[18px] rounded-tl-[6px] bg-[#F0F8F5] border border-[#0F9C6E]/20 px-4 py-3 space-y-2.5"
      data-testid="consent-prompt"
      role="region"
      aria-label="Yêu cầu quyền riêng tư"
    >
      {/* Icon + message */}
      <div className="flex gap-2 items-start">
        <ShieldCheck className="w-5 h-5 text-[#0F9C6E] shrink-0 mt-0.5" aria-hidden="true" />
        <div className="space-y-1.5">
          <p className="text-[15px] text-[#1A2E25] leading-relaxed">{CONSENT_MESSAGE}</p>
          <p className="text-[14px] font-semibold text-[#1A2E25]">Meto có thể dùng:</p>
          <ul className="space-y-0.5">
            {CONSENT_DATA_TYPES.map((item) => (
              <li key={item} className="flex items-center gap-1.5 text-[14px] text-[#2D4A3E]">
                <span className="w-1 h-1 rounded-full bg-[#0F9C6E] shrink-0" aria-hidden="true" />
                {item}
              </li>
            ))}
          </ul>
          <p className="text-[13px] text-[#6B7E77] leading-snug">{CONSENT_SETTINGS_NOTE}</p>
        </div>
      </div>

      {/* CTA chips */}
      <div className="flex flex-wrap gap-2 pt-0.5">
        <button
          type="button"
          onClick={handleOpenSettings}
          data-testid="consent-open-settings"
          className="shrink-0 rounded-full bg-[#0F9C6E] px-4 py-2 text-[14px] font-semibold text-white active:scale-95 transition-transform"
        >
          Mở Quyền riêng tư
        </button>
        <button
          type="button"
          onClick={onAskGeneral}
          data-testid="consent-ask-general"
          className="shrink-0 rounded-full border border-[#0F9C6E]/40 bg-white/80 px-4 py-2 text-[14px] font-medium text-[#0F9C6E] active:scale-95 transition-transform"
        >
          Hỏi chung
        </button>
        <button
          type="button"
          onClick={onDismiss}
          data-testid="consent-dismiss"
          className="shrink-0 rounded-full border border-[#C8D8D4] bg-white/60 px-4 py-2 text-[14px] font-medium text-[#6B7E77] active:scale-95 transition-transform"
        >
          Để sau
        </button>
      </div>
    </div>
  )
}
