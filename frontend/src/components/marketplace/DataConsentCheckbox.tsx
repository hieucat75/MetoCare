import * as React from 'react'
import { Check } from 'lucide-react'
import { cn } from '@/lib/utils'

/**
 * Required data-sharing consent checkbox for booking. The patient must tick this
 * before a consultation can be created (the API rejects consent=false with 422).
 * Large touch target, clear VN wording, no overwhelming legal text.
 */
export function DataConsentCheckbox({
  checked,
  onChange,
  className,
}: {
  checked: boolean
  onChange: (next: boolean) => void
  className?: string
}) {
  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className={cn(
        'flex w-full items-start gap-3 rounded-[16px] border px-4 py-3.5 text-left transition-colors',
        checked
          ? 'border-[rgba(13,155,110,0.5)] bg-[rgba(227,244,234,0.6)]'
          : 'border-[rgba(16,48,44,0.12)] bg-white',
        className,
      )}
    >
      <span
        className={cn(
          'mt-0.5 grid size-6 shrink-0 place-items-center rounded-[8px] border-2 transition-colors',
          checked
            ? 'border-[#0B7F5B] bg-[#0B7F5B] text-white'
            : 'border-[rgba(16,48,44,0.25)] bg-white',
        )}
        aria-hidden="true"
      >
        {checked && <Check className="size-4" strokeWidth={3} />}
      </span>
      <span className="flex-1">
        <span className="block text-[15px] font-semibold text-neu-text">
          Tôi đồng ý chia sẻ dữ liệu sức khoẻ của mình với bác sĩ
        </span>
        <span className="mt-0.5 block text-[13px] leading-relaxed text-neu-muted">
          Bác sĩ sẽ xem chỉ số, xét nghiệm và hồ sơ liên quan để tư vấn cho bạn. Bạn có thể huỷ bất
          cứ lúc nào.
        </span>
      </span>
    </button>
  )
}
