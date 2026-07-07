'use client'

import { AlertCircle } from 'lucide-react'
import type { ConfidenceLevel } from '@/lib/api/clinicalCopilot'

type Props = {
  confidence: ConfidenceLevel
  note?: string | null
}

/**
 * Shared confidence disclosure for clinical-copilot cards.
 *
 * - `low` + a note: prominent warning-toned inline banner, near the top of
 *   the card — a different signal than the urgent-priority banner (which
 *   flags clinical risk, not analysis confidence), so it renders with a
 *   visually distinct style even though both can appear together.
 * - `medium` + a note: small muted inline text — present but not alarming.
 * - `high`, or no note: renders nothing.
 */
export function ConfidenceNote({ confidence, note }: Props) {
  if (!note) return null

  if (confidence === 'low') {
    return (
      <div
        role="status"
        data-testid="low-confidence-banner"
        className="mb-3 flex items-start gap-2 rounded-md border border-warning bg-warning-light px-3 py-2.5"
      >
        <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-warning" aria-hidden="true" />
        <div>
          <p className="text-body-sm font-bold text-amber-900">Độ tin cậy thấp</p>
          <p className="text-body-xs text-amber-800">{note}</p>
        </div>
      </div>
    )
  }

  if (confidence === 'medium') {
    return <p className="mb-2 text-body-xs text-text-subtle">{note}</p>
  }

  return null
}
