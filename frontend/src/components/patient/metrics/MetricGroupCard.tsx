'use client'

import * as React from 'react'
import type { CategoryBucket } from '@/lib/metrics/kpi'
import { MetricRowItem } from './MetricRowItem'

type Props = {
  bucket: CategoryBucket
}

export function MetricGroupCard({ bucket }: Props) {
  const { theme, series } = bucket
  const [expandedType, setExpandedType] = React.useState<string | null>(null)

  function handleToggle(metricType: string) {
    setExpandedType((prev) => (prev === metricType ? null : metricType))
  }

  const abnormalCount = series.filter((s) => {
    if (!s.unit) {
      return s.latest.status === 'abnormal' || s.latest.status === 'critical'
    }
    return false
  }).length

  return (
    <div
      className="flex flex-col"
      style={{
        borderRadius: '24px',
        background: 'rgba(255,255,255,0.66)',
        backdropFilter: 'blur(16px)',
        WebkitBackdropFilter: 'blur(16px)',
        border: '1px solid rgba(255,255,255,0.85)',
        boxShadow: '0 20px 44px -28px rgba(16,48,44,0.5), inset 0 1px 0 rgba(255,255,255,0.9)',
      }}
      aria-label={`Nhóm ${theme.label}`}
    >
      {/* Category header */}
      <div className="flex items-center gap-[10px] px-[18px] pt-[16px] pb-[12px]">
        <span
          className="size-[10px] shrink-0 rounded-full"
          style={{ background: theme.accent }}
          aria-hidden="true"
        />
        <h2 className="flex-1 text-[14px] font-bold text-[#0E2A33] leading-snug">{theme.label}</h2>
        {abnormalCount > 0 && (
          <span
            className="text-[11px] font-bold px-[8px] py-[3px] rounded-full"
            style={{
              background: 'rgba(253,230,228,0.95)',
              color: '#B0231A',
              border: '1px solid rgba(217,45,32,0.25)',
            }}
            aria-label={`${abnormalCount} chỉ số bất thường`}
          >
            {abnormalCount} bất thường
          </span>
        )}
      </div>

      {/* Metric rows */}
      <div className="flex flex-col gap-[8px] px-[10px] pb-[12px]">
        {series.map((s) => (
          <MetricRowItem
            key={s.metricType}
            series={s}
            expanded={expandedType === s.metricType}
            onToggle={() => handleToggle(s.metricType)}
          />
        ))}
      </div>
    </div>
  )
}
