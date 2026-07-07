'use client'

import * as React from 'react'
import { X } from 'lucide-react'
import { cn } from '@/lib/utils'

type Props = {
  open: boolean
  onClose: () => void
  children: React.ReactNode
  /** Accessible label for the dialog (announced by screen readers). */
  label?: string
  className?: string
}

/**
 * BottomSheet — generic full-screen-on-mobile overlay + slide-up sheet.
 *
 * Extracted mechanic (backdrop + fixed rounded-top sheet + safe-area-aware
 * bottom padding) from the patient-facing `ChatSheet`
 * (`frontend/src/components/patient/meto/ChatSheet.tsx`). This primitive is
 * content-agnostic — it owns only the open/close shell, not chat behavior —
 * so `ChatSheet` itself is left untouched.
 */
export function BottomSheet({ open, onClose, children, label, className }: Props) {
  if (!open) return null

  return (
    <>
      {/* Overlay */}
      <div
        className="fixed inset-0 z-50 bg-black/40 backdrop-blur-[2px]"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Sheet */}
      <div
        className={cn(
          'fixed bottom-0 left-0 right-0 z-[60] flex flex-col rounded-t-2xl bg-surface shadow-xl',
          className
        )}
        style={{
          maxHeight: '88vh',
          paddingBottom: 'env(safe-area-inset-bottom)',
        }}
        role="dialog"
        aria-modal="true"
        aria-label={label}
      >
        <div className="flex shrink-0 justify-end px-3 pt-3">
          <button
            type="button"
            onClick={onClose}
            aria-label="Đóng"
            className="flex h-8 w-8 items-center justify-center rounded-full text-text-muted transition-colors hover:bg-secondary-100"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-4 pb-4">{children}</div>
      </div>
    </>
  )
}
