'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import { ArrowLeft } from 'lucide-react'
import { cn } from '@/lib/utils'

/** Sub-screen header: glass back button + title (and optional subtitle / action). */
export function PatientScreenHeader({
  title,
  subtitle,
  onBack,
  action,
  className,
}: {
  title: string
  subtitle?: string
  onBack?: () => void
  action?: React.ReactNode
  className?: string
}) {
  const router = useRouter()
  return (
    <div className={cn('flex items-center gap-3 pb-1 pt-1.5', className)}>
      <button
        type="button"
        aria-label="Quay lại"
        onClick={onBack ?? (() => router.back())}
        className="grid size-12 shrink-0 place-items-center rounded-full border border-white/85 bg-white/60 backdrop-blur-md"
      >
        <ArrowLeft className="size-5 text-[#0e2a33]" aria-hidden="true" />
      </button>
      <div className="min-w-0 flex-1">
        <h1 className="truncate text-[19px] font-bold leading-tight text-[#0e2a33]">{title}</h1>
        {subtitle && <p className="truncate text-[13px] text-[#365651]">{subtitle}</p>}
      </div>
      {action}
    </div>
  )
}
