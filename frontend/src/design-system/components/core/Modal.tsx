'use client'

import * as React from 'react'
import * as DialogPrimitive from '@radix-ui/react-dialog'
import { X } from 'lucide-react'
import { cn } from '@/lib/utils'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type ModalSize = 'sm' | 'md' | 'lg' | 'xl' | 'full'

export interface ModalProps {
  /** Whether the modal is open. */
  open?: boolean
  /** Callback fired when the open state changes. */
  onOpenChange?: (open: boolean) => void
  /** Modal heading rendered in the header bar. */
  title?: string
  /** Supplemental description rendered below the title (visually hidden for a11y). */
  description?: string
  /** Modal body content. */
  children?: React.ReactNode
  /** Slot rendered inside the footer bar. */
  footer?: React.ReactNode
  /** Width/height preset. Defaults to 'md'. */
  size?: ModalSize
  /**
   * Whether clicking the overlay dismisses the modal.
   * Defaults to true.
   */
  closeOnOverlayClick?: boolean
}

// ---------------------------------------------------------------------------
// Size map
// ---------------------------------------------------------------------------

const sizeClasses: Record<ModalSize, string> = {
  sm: 'w-80',
  md: 'w-full max-w-md',
  lg: 'w-full max-w-lg',
  xl: 'w-full max-w-2xl',
  full: 'w-screen h-screen rounded-none',
}

// ---------------------------------------------------------------------------
// Modal
// ---------------------------------------------------------------------------

/**
 * Accessible modal dialog built on @radix-ui/react-dialog.
 *
 * @example
 * <Modal open={open} onOpenChange={setOpen} title="Confirm action" footer={<Button>OK</Button>}>
 *   <p>Are you sure?</p>
 * </Modal>
 */
export function Modal({
  open,
  onOpenChange,
  title,
  description,
  children,
  footer,
  size = 'md',
  closeOnOverlayClick = true,
}: ModalProps) {
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        {/* Overlay */}
        <DialogPrimitive.Overlay
          className={cn(
            'fixed inset-0 z-50 bg-black/50 backdrop-blur-sm',
            'data-[state=open]:animate-in data-[state=open]:fade-in',
            'data-[state=closed]:animate-out data-[state=closed]:fade-out',
          )}
          // Prevent overlay click from closing when closeOnOverlayClick=false
          onClick={closeOnOverlayClick ? undefined : (e) => e.stopPropagation()}
          onPointerDown={closeOnOverlayClick ? undefined : (e) => e.stopPropagation()}
        />

        {/* Content */}
        <DialogPrimitive.Content
          className={cn(
            // Position
            'fixed left-1/2 top-1/2 z-50',
            '-translate-x-1/2 -translate-y-1/2',
            // Appearance
            'bg-surface rounded-xl shadow-2xl',
            // Layout
            'flex flex-col',
            // Animation
            'data-[state=open]:animate-in data-[state=open]:fade-in data-[state=open]:zoom-in-95',
            'data-[state=closed]:animate-out data-[state=closed]:fade-out data-[state=closed]:zoom-out-95',
            // Size
            sizeClasses[size],
          )}
          // When closeOnOverlayClick is false, intercept the Radix outside-click event
          onInteractOutside={
            closeOnOverlayClick ? undefined : (e) => e.preventDefault()
          }
          // Always allow ESC key to close (standard accessible behaviour)
        >
          {/* Header */}
          {(title != null || description != null) && (
            <div className="flex items-center justify-between px-6 py-4 border-b border-border shrink-0">
              <div className="flex flex-col gap-0.5 min-w-0 pr-4">
                {title && (
                  <DialogPrimitive.Title className="text-heading-md font-semibold text-text truncate">
                    {title}
                  </DialogPrimitive.Title>
                )}
                {description && (
                  <DialogPrimitive.Description className="text-body-sm text-text-muted">
                    {description}
                  </DialogPrimitive.Description>
                )}
              </div>

              {/* Close button */}
              <DialogPrimitive.Close
                className={cn(
                  'shrink-0 rounded-lg p-1.5 text-text-muted',
                  'hover:bg-secondary-100 hover:text-text',
                  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50',
                  'transition-colors duration-150',
                )}
                aria-label="Đóng"
              >
                <X className="h-4 w-4" aria-hidden />
              </DialogPrimitive.Close>
            </div>
          )}

          {/* Body */}
          <div className="flex-1 overflow-auto px-6 py-4">{children}</div>

          {/* Footer */}
          {footer && (
            <div className="shrink-0 px-6 py-4 border-t border-border flex justify-end gap-3">
              {footer}
            </div>
          )}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}

// ---------------------------------------------------------------------------
// useModal hook
// ---------------------------------------------------------------------------

export interface UseModalReturn {
  /** Whether the modal is currently open. */
  open: boolean
  /** Setter / toggle passed directly to Modal's onOpenChange. */
  onOpenChange: (open: boolean) => void
  /** Spread onto any trigger element to open the modal on click. */
  triggerProps: {
    onClick: () => void
    'aria-haspopup': 'dialog'
    'aria-expanded': boolean
  }
  /** Spread onto <Modal> to wire up open + onOpenChange automatically. */
  modalProps: {
    open: boolean
    onOpenChange: (open: boolean) => void
  }
}

/**
 * Convenience hook that manages open state and returns ready-made prop bags for
 * both the trigger element and the <Modal> component.
 *
 * @example
 * const { triggerProps, modalProps } = useModal()
 * return (
 *   <>
 *     <button {...triggerProps}>Open</button>
 *     <Modal {...modalProps} title="Hello">…</Modal>
 *   </>
 * )
 */
export function useModal(initialOpen = false): UseModalReturn {
  const [open, setOpen] = React.useState(initialOpen)

  const onOpenChange = React.useCallback((next: boolean) => {
    setOpen(next)
  }, [])

  const triggerProps = React.useMemo(
    () => ({
      onClick: () => setOpen(true),
      'aria-haspopup': 'dialog' as const,
      'aria-expanded': open,
    }),
    [open],
  )

  const modalProps = React.useMemo(
    () => ({ open, onOpenChange }),
    [open, onOpenChange],
  )

  return { open, onOpenChange, triggerProps, modalProps }
}
