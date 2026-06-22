'use client'

import * as React from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { X } from 'lucide-react'
import { cn } from '@/lib/utils'

/** Mint glass modal (Radix Dialog) — bottom-sheet feel on a mobile column. */
export function GlassModal({
  open,
  onOpenChange,
  title,
  description,
  children,
  footer,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description?: string
  children: React.ReactNode
  footer?: React.ReactNode
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-[rgba(14,42,51,0.45)] backdrop-blur-[3px] data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=open]:fade-in data-[state=closed]:fade-out" />
        <Dialog.Content
          className={cn(
            'patient-app fixed inset-x-0 bottom-0 z-50 mx-auto w-full max-w-[430px]',
            'rounded-t-[24px] border border-white/85 p-5 pb-[max(20px,env(safe-area-inset-bottom))]',
            'data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=open]:slide-in-from-bottom data-[state=closed]:slide-out-to-bottom',
          )}
          style={{
            background: 'rgba(248,251,249,0.9)',
            backdropFilter: 'blur(28px) saturate(180%)',
            boxShadow: '0 -18px 50px -20px rgba(16,48,44,0.5)',
          }}
        >
          <div className="mx-auto mb-3 h-1.5 w-10 rounded-full bg-[rgba(16,48,44,0.15)]" aria-hidden="true" />
          <div className="mb-4 flex items-start justify-between gap-3">
            <div>
              <Dialog.Title className="text-[19px] font-extrabold text-[#0e2a33]">{title}</Dialog.Title>
              {description && (
                <Dialog.Description className="mt-1 text-[13px] text-[#365651]">
                  {description}
                </Dialog.Description>
              )}
            </div>
            <Dialog.Close
              className="grid size-9 shrink-0 place-items-center rounded-full bg-white/70 text-[#365651]"
              aria-label="Đóng"
            >
              <X className="size-5" aria-hidden="true" />
            </Dialog.Close>
          </div>
          <div className="max-h-[70vh] overflow-y-auto">{children}</div>
          {footer && <div className="mt-5 flex gap-3">{footer}</div>}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
