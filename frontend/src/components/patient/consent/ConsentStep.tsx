'use client'

import * as React from 'react'
import Link from 'next/link'
import { Check, ChevronRight, Loader2, ShieldCheck } from 'lucide-react'
import { NeuButton } from '@/components/patient/neu'
import { CONSENT_SUMMARY } from '@/lib/legal'
import { cn } from '@/lib/utils'

type Props = {
  onAccept: () => void
  onBack: () => void
  isLoading?: boolean
  error?: string | null
}

/**
 * Final registration step: Terms of Use + Privacy Policy consent.
 * Large fonts / 48px targets for 45–70yo users, Soft Mint UI, dark-mode aware.
 */
export function ConsentStep({ onAccept, onBack, isLoading = false, error }: Props) {
  const [checked, setChecked] = React.useState(false)
  const canContinue = checked && !isLoading

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (canContinue) onAccept()
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="animate-in fade-in duration-300">
      {/* Header */}
      <div className="mb-5 text-center">
        <div className="mx-auto mb-3 flex h-14 w-14 items-center justify-center rounded-2xl bg-mint-100 dark:bg-mint-100/10">
          <ShieldCheck className="h-8 w-8 text-neu-green" aria-hidden="true" />
        </div>
        <h1 className="text-[24px] font-extrabold text-neu-text dark:text-white">
          Điều khoản sử dụng
        </h1>
        <p className="mx-auto mt-1.5 max-w-[340px] text-[16px] leading-relaxed text-text-muted dark:text-white/70">
          Để bảo vệ quyền lợi của bạn và đảm bảo MetoCare có thể hỗ trợ chăm sóc sức khỏe hiệu quả.
        </p>
      </div>

      {error && (
        <div
          role="alert"
          className="mb-4 rounded-[14px] border border-[#D92D20]/20 bg-[#FEF0F0] p-3 text-[15px] text-[#D92D20] dark:bg-[#D92D20]/10"
        >
          {error}
        </div>
      )}

      {/* Scrollable summary card */}
      <div
        className="max-h-[38vh] overflow-y-auto rounded-2xl border border-[rgba(16,48,44,0.10)] bg-white/70 p-4 dark:border-white/10 dark:bg-white/5"
        tabIndex={0}
        aria-label="Tóm tắt điều khoản"
      >
        <ul className="space-y-3">
          {CONSENT_SUMMARY.map((point) => (
            <li key={point} className="flex items-start gap-3">
              <span
                className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-mint-100 dark:bg-mint-100/15"
                aria-hidden="true"
              >
                <Check className="h-4 w-4 text-neu-green" />
              </span>
              <span className="text-[16px] leading-relaxed text-text dark:text-white/90">
                {point}
              </span>
            </li>
          ))}
        </ul>
      </div>

      {/* Full-document links */}
      <div className="mt-4 space-y-1">
        <LegalLink href="/terms">Xem đầy đủ Điều khoản sử dụng</LegalLink>
        <LegalLink href="/privacy">Xem Chính sách quyền riêng tư</LegalLink>
      </div>

      {/* Consent checkbox — large touch target */}
      <label
        htmlFor="consent-checkbox"
        className={cn(
          'mt-5 flex cursor-pointer items-start gap-3 rounded-2xl border p-4 transition-colors',
          'min-h-[48px]',
          checked
            ? 'border-neu-green bg-mint-100/50 dark:bg-mint-100/10'
            : 'border-[rgba(16,48,44,0.14)] bg-white/60 dark:border-white/12 dark:bg-white/5',
        )}
      >
        <input
          id="consent-checkbox"
          type="checkbox"
          checked={checked}
          onChange={(e) => setChecked(e.target.checked)}
          disabled={isLoading}
          className="mt-0.5 h-6 w-6 shrink-0 cursor-pointer rounded-md border-[rgba(16,48,44,0.3)] text-neu-green accent-neu-green focus:ring-2 focus:ring-neu-green/30"
        />
        <span className="text-[16px] leading-relaxed text-text dark:text-white/90">
          Tôi đã đọc, hiểu và đồng ý với Điều khoản sử dụng và Chính sách quyền riêng tư của MetoCare.
        </span>
      </label>

      {/* CTAs */}
      <div className="mt-6 space-y-3">
        <NeuButton
          type="submit"
          disabled={!canContinue}
          className="flex h-[52px] w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-b from-[#17AE7B] to-[#0B6B4D] text-[17px] font-semibold text-white shadow-[0_12px_24px_-8px_rgba(11,107,77,0.6)] hover:opacity-95 disabled:opacity-50"
        >
          {isLoading ? (
            <>
              <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
              Đang tạo tài khoản…
            </>
          ) : (
            'Đồng ý và tạo tài khoản'
          )}
        </NeuButton>

        <button
          type="button"
          onClick={onBack}
          disabled={isLoading}
          className="flex h-[52px] w-full items-center justify-center rounded-xl text-[17px] font-medium text-text-muted transition-colors hover:text-neu-green disabled:opacity-50 dark:text-white/70"
        >
          Quay lại
        </button>
      </div>
    </form>
  )
}

function LegalLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <Link
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="flex min-h-[48px] items-center justify-between rounded-xl px-1 text-[16px] font-semibold text-neu-green hover:underline underline-offset-2"
    >
      <span>{children}</span>
      <ChevronRight className="h-5 w-5" aria-hidden="true" />
    </Link>
  )
}
