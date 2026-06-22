'use client'

import * as React from 'react'

export interface SegTab {
  value: string
  label: string
  badge?: number
}

/** Glass segmented control — horizontal-scroll pill tabs in the mint language. */
export function SegmentedTabs({
  tabs,
  value,
  onChange,
}: {
  tabs: SegTab[]
  value: string
  onChange: (v: string) => void
}) {
  return (
    <div className="mc-glass scrollbar-hide flex gap-1 overflow-x-auto rounded-2xl p-1">
      {tabs.map((t) => {
        const active = t.value === value
        return (
          <button
            key={t.value}
            type="button"
            onClick={() => onChange(t.value)}
            aria-pressed={active}
            className="flex min-h-[40px] shrink-0 items-center gap-1.5 rounded-[14px] px-3.5 text-[14px] font-semibold transition-colors"
            style={
              active
                ? {
                    background: 'linear-gradient(150deg,#1BB082,#0B7F5B)',
                    color: '#fff',
                    boxShadow: '0 8px 18px -10px rgba(16,140,99,0.8)',
                  }
                : { color: '#365651' }
            }
          >
            {t.label}
            {t.badge != null && t.badge > 0 && (
              <span
                className="grid min-w-[18px] place-items-center rounded-full px-1 text-[11px] font-bold"
                style={{
                  background: active ? 'rgba(255,255,255,0.25)' : 'rgba(16,140,99,0.12)',
                  color: active ? '#fff' : '#0b7f5b',
                }}
              >
                {t.badge}
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}
