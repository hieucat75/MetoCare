import * as React from 'react'
import { ShieldAlert } from 'lucide-react'
import { cn } from '@/lib/utils'
import { MARKETPLACE_DISCLAIMER } from '@/lib/api/marketplace'

/**
 * Safety disclaimer banner shown on booking, doctor detail, and consultation
 * screens. Renders the exact VN string from the marketplace contract.
 */
export function MarketplaceDisclaimer({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        'flex items-start gap-2.5 rounded-[14px] border border-[rgba(245,166,35,0.35)] bg-[rgba(252,239,201,0.5)] px-3.5 py-3',
        className,
      )}
      role="note"
    >
      <ShieldAlert className="mt-0.5 size-[18px] shrink-0 text-[#B8740A]" aria-hidden="true" />
      <p className="text-[13px] leading-relaxed text-[#7A5410]">{MARKETPLACE_DISCLAIMER}</p>
    </div>
  )
}
