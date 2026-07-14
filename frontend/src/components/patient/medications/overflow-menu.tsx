'use client'

import * as React from 'react'
import { PauseCircle, PlayCircle, XCircle, Pencil, Trash2 } from 'lucide-react'
import { NeuCard } from '@/components/patient/neu'
import type { Medication } from '@/lib/api/patient'

// ── Medication overflow action sheet (M2) ──────────────────────────────────────
//
// A bottom sheet, not a small floating dropdown — matches this app's existing
// action-sheet pattern (MedModal, DiscontinueModal) and gives large,
// thumb-reachable tap targets rather than a fine-motor-precision target next
// to the ⋯ trigger. Explicit M2 accessibility requirement: must stay easy to
// reach for elderly users.

export type MedicationOverflowMenuProps = {
  open: boolean
  onClose: () => void
  med: Medication
  busy: boolean
  onTogglePause: () => void
  onDiscontinue: () => void
  onEdit: () => void
  onDelete: () => void
}

export function MedicationOverflowMenu({
  open,
  onClose,
  med,
  busy,
  onTogglePause,
  onDiscontinue,
  onEdit,
  onDelete,
}: MedicationOverflowMenuProps) {
  const titleId = React.useId()
  const sheetRef = React.useRef<HTMLDivElement>(null)
  const previouslyFocusedRef = React.useRef<HTMLElement | null>(null)
  const isActive = med.lifecycle_status === 'active'
  const isPaused = med.lifecycle_status === 'paused'

  // Escape closes (a11y) — same pattern as DiscontinueModal/MedModal.
  React.useEffect(() => {
    if (!open) return
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  // Focus management: move focus into the sheet on open, restore it to
  // whatever triggered the sheet (the ⋯ button) on close.
  React.useEffect(() => {
    if (!open) return
    previouslyFocusedRef.current = document.activeElement as HTMLElement | null
    sheetRef.current?.querySelector('button')?.focus()
    return () => {
      previouslyFocusedRef.current?.focus?.()
    }
  }, [open])

  // Focus trap: aria-modal="true" promises keyboard focus can't leave the
  // sheet — Tab/Shift+Tab wrap within it instead of reaching controls behind
  // the overlay.
  React.useEffect(() => {
    if (!open) return
    function onKeyDown(e: KeyboardEvent) {
      if (e.key !== 'Tab') return
      const focusable =
        sheetRef.current?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)')
      if (!focusable || focusable.length === 0) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault()
        first.focus()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [open])

  if (!open) return null

  type Item = {
    key: string
    label: string
    icon: React.ReactNode
    onClick: () => void
    danger?: boolean
  }
  const items: Item[] = []
  if (isActive) {
    items.push({
      key: 'pause',
      label: 'Tạm ngưng',
      icon: <PauseCircle className="size-5" aria-hidden="true" />,
      onClick: onTogglePause,
    })
  } else if (isPaused) {
    items.push({
      key: 'resume',
      label: 'Tiếp tục uống',
      icon: <PlayCircle className="size-5" aria-hidden="true" />,
      onClick: onTogglePause,
    })
  }
  if (isActive || isPaused) {
    items.push(
      {
        key: 'discontinue',
        label: 'Ngừng thuốc',
        icon: <XCircle className="size-5" aria-hidden="true" />,
        onClick: onDiscontinue,
      },
      {
        key: 'edit',
        label: 'Sửa',
        icon: <Pencil className="size-5" aria-hidden="true" />,
        onClick: onEdit,
      },
      {
        key: 'delete',
        label: 'Xoá',
        icon: <Trash2 className="size-5" aria-hidden="true" />,
        onClick: onDelete,
        danger: true,
      }
    )
  }

  return (
    <div className="fixed inset-0 z-40 flex items-end bg-black/30" onClick={onClose}>
      <div
        ref={sheetRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="w-full max-w-md mx-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <NeuCard className="!rounded-b-none !p-3">
          <h2 id={titleId} className="sr-only">
            Tuỳ chọn thuốc
          </h2>
          <div className="space-y-1">
            {items.map((item) => (
              <button
                key={item.key}
                type="button"
                disabled={busy}
                onClick={() => {
                  onClose()
                  item.onClick()
                }}
                className={`flex w-full items-center gap-3 rounded-[12px] px-4 py-3.5 text-[16px] font-semibold transition-transform active:scale-[0.98] disabled:opacity-50 ${
                  item.danger ? 'text-[#D92D20]' : 'text-neu-text'
                }`}
              >
                {item.icon}
                {item.label}
              </button>
            ))}
            <button
              type="button"
              onClick={onClose}
              className="mt-1 flex w-full items-center justify-center rounded-[12px] px-4 py-3.5 text-[16px] font-semibold text-neu-muted"
            >
              Đóng
            </button>
          </div>
        </NeuCard>
      </div>
    </div>
  )
}
