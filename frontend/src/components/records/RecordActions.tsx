'use client'

/**
 * RecordActions — three-dot menu (⋯) for health record rows.
 *
 * Renders a small action menu with "Sửa" (edit) and "Xóa" (delete) options.
 * Uses a simple popover pattern (no external dep beyond what's already installed).
 *
 * Desktop: click the ⋯ button to open.
 * Mobile: also responds to long-press (onContextMenu) on the parent element.
 */

import * as React from 'react'
import { MoreHorizontal, Pencil, Trash2 } from 'lucide-react'
import { cn } from '@/lib/utils'

export interface RecordActionsProps {
  /** Called when the user chooses "Sửa" (edit). */
  onEdit: () => void
  /** Called when the user chooses "Xóa" (delete). */
  onDelete: () => void
  /** Accessible label suffix for the trigger button (e.g. metric name). */
  label?: string
  className?: string
}

export function RecordActions({ onEdit, onDelete, label, className }: RecordActionsProps) {
  const [open, setOpen] = React.useState(false)
  const containerRef = React.useRef<HTMLDivElement>(null)

  // Close on outside click
  React.useEffect(() => {
    if (!open) return
    const handle = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handle)
    return () => document.removeEventListener('mousedown', handle)
  }, [open])

  // Close on Escape
  React.useEffect(() => {
    if (!open) return
    const handle = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('keydown', handle)
    return () => document.removeEventListener('keydown', handle)
  }, [open])

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        aria-label={label ? `Tùy chọn cho ${label}` : 'Tùy chọn bản ghi'}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className={cn(
          'grid size-8 shrink-0 place-items-center rounded-full text-neu-muted',
          'hover:bg-[rgba(16,48,44,0.06)] active:bg-[rgba(16,48,44,0.1)]',
          'transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-neu-green/50',
          className
        )}
      >
        <MoreHorizontal className="size-4" aria-hidden="true" />
      </button>

      {open && (
        <div
          role="menu"
          className={cn(
            'absolute right-0 top-full z-50 mt-1 min-w-[140px] rounded-[14px]',
            'border border-[rgba(16,48,44,0.08)] bg-white/95 p-1',
            'shadow-[0_8px_28px_-8px_rgba(16,48,44,0.18)]',
          )}
          style={{ backdropFilter: 'blur(12px)' }}
        >
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false)
              onEdit()
            }}
            className={cn(
              'flex w-full cursor-pointer items-center gap-2.5 rounded-[10px] px-3 py-2',
              'text-left text-[14px] font-semibold text-neu-text',
              'hover:bg-[rgba(16,48,44,0.06)] focus:bg-[rgba(16,48,44,0.06)] focus:outline-none',
            )}
          >
            <Pencil className="size-4 text-neu-green" aria-hidden="true" />
            Sửa
          </button>

          <div className="my-1 h-px bg-[rgba(16,48,44,0.07)]" role="separator" />

          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false)
              onDelete()
            }}
            className={cn(
              'flex w-full cursor-pointer items-center gap-2.5 rounded-[10px] px-3 py-2',
              'text-left text-[14px] font-semibold text-[#D92D20]',
              'hover:bg-[rgba(217,45,32,0.06)] focus:bg-[rgba(217,45,32,0.06)] focus:outline-none',
            )}
          >
            <Trash2 className="size-4" aria-hidden="true" />
            Xóa
          </button>
        </div>
      )}
    </div>
  )
}
