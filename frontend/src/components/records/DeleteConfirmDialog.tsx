'use client'

/**
 * DeleteConfirmDialog — modal that asks the user to confirm a destructive action.
 *
 * Uses @radix-ui/react-dialog (already installed) as a base.
 *
 * Default Vietnamese text:
 *   Title:       "Xóa bản ghi sức khỏe này?"
 *   Description: "Thao tác này không thể hoàn tác."
 *
 * Props let callers override title / description for different resource types
 * (metrics, lab results, etc.).
 */

import * as React from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { cn } from '@/lib/utils'

export interface DeleteConfirmDialogProps {
  isOpen: boolean
  onConfirm: () => void
  onCancel: () => void
  title?: string
  description?: string
  /** Show a loading spinner on the Confirm button while the delete is in-flight. */
  loading?: boolean
}

export function DeleteConfirmDialog({
  isOpen,
  onConfirm,
  onCancel,
  title = 'Xóa bản ghi sức khỏe này?',
  description = 'Thao tác này không thể hoàn tác.',
  loading = false,
}: DeleteConfirmDialogProps) {
  return (
    <Dialog.Root
      open={isOpen}
      onOpenChange={(open) => {
        if (!open) onCancel()
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay
          className={cn(
            'fixed inset-0 z-50 bg-[rgba(14,42,51,0.45)] backdrop-blur-[3px]',
            'data-[state=open]:animate-in data-[state=closed]:animate-out',
            'data-[state=open]:fade-in data-[state=closed]:fade-out',
          )}
        />
        <Dialog.Content
          className={cn(
            'fixed left-1/2 top-1/2 z-50 w-[calc(100%-2rem)] max-w-[360px]',
            '-translate-x-1/2 -translate-y-1/2 rounded-[20px] p-6',
            'border border-[rgba(16,48,44,0.08)]',
            'data-[state=open]:animate-in data-[state=closed]:animate-out',
            'data-[state=open]:fade-in-0 data-[state=closed]:fade-out-0',
            'data-[state=open]:zoom-in-95 data-[state=closed]:zoom-out-95',
          )}
          style={{
            background: 'rgba(248,251,249,0.96)',
            backdropFilter: 'blur(24px) saturate(160%)',
            boxShadow: '0 20px 50px -16px rgba(16,48,44,0.35)',
          }}
        >
          {/* Trash icon */}
          <div className="mb-4 flex justify-center">
            <span className="grid size-12 place-items-center rounded-full bg-[rgba(217,45,32,0.1)]">
              <svg
                xmlns="http://www.w3.org/2000/svg"
                className="size-6 text-[#D92D20]"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth={2}
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <polyline points="3 6 5 6 21 6" />
                <path d="M19 6l-1 14H6L5 6" />
                <path d="M10 11v6M14 11v6" />
                <path d="M9 6V4h6v2" />
              </svg>
            </span>
          </div>

          <Dialog.Title className="mb-1 text-center text-[18px] font-extrabold text-neu-text">
            {title}
          </Dialog.Title>

          <Dialog.Description className="mb-6 text-center text-[14px] text-neu-muted">
            {description}
          </Dialog.Description>

          <div className="flex flex-col gap-2.5">
            {/* Confirm (danger) */}
            <button
              type="button"
              onClick={onConfirm}
              disabled={loading}
              className={cn(
                'flex w-full items-center justify-center rounded-[14px] py-3',
                'text-[15px] font-bold text-white',
                'bg-[#D92D20] active:bg-[#B91C1C]',
                'transition-colors disabled:opacity-60',
              )}
            >
              {loading ? (
                <span className="inline-block size-4 animate-spin rounded-full border-2 border-white/40 border-t-white" />
              ) : (
                'Xóa'
              )}
            </button>

            {/* Cancel — Dialog.Close triggers onOpenChange(false) which calls onCancel */}
            <Dialog.Close asChild>
              <button
                type="button"
                disabled={loading}
                className={cn(
                  'w-full rounded-[14px] py-3',
                  'text-[15px] font-semibold text-neu-text',
                  'bg-[rgba(16,48,44,0.06)] active:bg-[rgba(16,48,44,0.1)]',
                  'transition-colors disabled:opacity-60',
                )}
              >
                Huỷ
              </button>
            </Dialog.Close>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
