import * as React from 'react'

type Props = {
  message: string
}

export function DangerAlertBanner({ message }: Props) {
  return (
    <div
      role="alert"
      className="rounded-[14px] px-4 py-3 flex items-start gap-3 text-white"
      style={{ background: 'linear-gradient(160deg, #E53E3E, #C53030)' }}
    >
      <span className="text-[18px] leading-none shrink-0 mt-0.5" aria-hidden="true">
        ⚠️
      </span>
      <div className="flex-1 min-w-0">
        {/* a11y: alert text — 18px (was 14px) */}
        <p className="text-[18px] font-semibold leading-snug">{message}</p>
        <a
          href="tel:1800599920"
          className="mt-1.5 inline-block text-[16px] font-bold underline underline-offset-2 opacity-90"
        >
          Liên hệ bác sĩ
        </a>
      </div>
    </div>
  )
}
