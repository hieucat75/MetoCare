'use client'

import * as React from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { ShieldCheck } from 'lucide-react'
import { getDataSharingPolicy, type DataSharingConsentPolicy } from '@/lib/api/consultations'

/**
 * Blocking data-sharing consent for a doctor consultation.
 *
 * The consent act IS the primary button. There is no pre-ticked checkbox and no
 * default-on state to leave alone — nothing is granted until the patient presses
 * "Đồng ý và tiếp tục", and every other way out of this dialog (the decline
 * button, Escape, the backdrop) resolves to no consent and no booking.
 *
 * The two actions carry equal visual weight. Making "Không chia sẻ" quiet or
 * hard to find would be the dark pattern this screen exists to avoid.
 *
 * Copy is fetched from the server so the words the patient reads are the words
 * recorded against their grant. The accept button stays disabled until they
 * arrive: a consent screen that falls back to its own hardcoded text is a
 * consent screen that can disagree with what gets stored.
 */
export function DataSharingConsentModal({
  open,
  onOpenChange,
  onAccept,
  submitting,
  error,
  doctorName,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Called with the granted category keys + the versions actually rendered. */
  onAccept: (grant: {
    categories: string[]
    consentVersion: string
    policyVersion: string
  }) => void
  submitting: boolean
  error: string | null
  doctorName?: string | null
}) {
  const [policy, setPolicy] = React.useState<DataSharingConsentPolicy | null>(null)
  const [policyError, setPolicyError] = React.useState<string | null>(null)
  const [loadingPolicy, setLoadingPolicy] = React.useState(false)

  const loadPolicy = React.useCallback(() => {
    setLoadingPolicy(true)
    setPolicyError(null)
    getDataSharingPolicy()
      .then(setPolicy)
      .catch(() => setPolicyError('Không tải được nội dung chia sẻ dữ liệu. Vui lòng thử lại.'))
      .finally(() => setLoadingPolicy(false))
  }, [])

  React.useEffect(() => {
    if (open && policy === null && !loadingPolicy && policyError === null) loadPolicy()
  }, [open, policy, loadingPolicy, policyError, loadPolicy])

  const handleAccept = () => {
    if (!policy || submitting) return
    onAccept({
      categories: policy.categories.map((c) => c.key),
      consentVersion: policy.consent_version,
      policyVersion: policy.policy_version,
    })
  }

  // A submit in flight must not be cancellable by Escape or a backdrop click:
  // the booking may already exist server-side, and closing here would leave the
  // patient with no idea whether it went through.
  const handleOpenChange = (next: boolean) => {
    if (!next && submitting) return
    onOpenChange(next)
  }

  const paragraphs = policy ? policy.body.split('\n\n') : []

  return (
    <Dialog.Root open={open} onOpenChange={handleOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-[rgba(14,42,51,0.5)] backdrop-blur-[3px]" />
        <Dialog.Content
          // This Radix version does not emit aria-modal itself; without it a
          // screen reader is never told the rest of the page is inert.
          aria-modal="true"
          className="patient-app fixed left-1/2 top-1/2 z-50 w-[calc(100vw-32px)] max-w-[430px] -translate-x-1/2 -translate-y-1/2 rounded-[24px] border border-white/85 bg-[rgba(248,251,249,0.96)] p-5 shadow-[0_20px_60px_-20px_rgba(16,48,44,0.55)]"
          onEscapeKeyDown={(e) => {
            if (submitting) e.preventDefault()
          }}
          onInteractOutside={(e) => {
            if (submitting) e.preventDefault()
          }}
        >
          <div className="flex items-start gap-3">
            <span
              className="grid size-11 shrink-0 place-items-center rounded-full bg-[rgba(13,155,110,0.12)]"
              aria-hidden="true"
            >
              <ShieldCheck className="size-6 text-neu-green" />
            </span>
            <div className="min-w-0 flex-1">
              <Dialog.Title className="text-[19px] font-extrabold leading-snug text-[#0e2a33]">
                {policy?.title ?? 'Chia sẻ thông tin sức khỏe với bác sĩ?'}
              </Dialog.Title>
              {doctorName && (
                <p className="mt-0.5 text-[14px] font-semibold text-neu-green">{doctorName}</p>
              )}
            </div>
          </div>

          <div className="mt-4 max-h-[45vh] overflow-y-auto">
            {loadingPolicy && !policy && (
              <p className="text-[15px] text-[#365651]" role="status">
                Đang tải nội dung…
              </p>
            )}

            {policyError && !policy && (
              <div>
                <p className="text-[15px] text-[#D92D20]" role="alert">
                  {policyError}
                </p>
                <button type="button" onClick={loadPolicy} className="neu-btn-secondary mt-3 w-full">
                  Thử lại
                </button>
              </div>
            )}

            {policy && (
              <>
                {/* Radix owns the id + aria-describedby wiring here, so the
                    whole body is what a screen reader reads as the description. */}
                <Dialog.Description asChild>
                  <div className="space-y-3">
                    {paragraphs.map((paragraph, i) => (
                      <p key={i} className="text-[15px] leading-relaxed text-[#365651]">
                        {paragraph}
                      </p>
                    ))}
                  </div>
                </Dialog.Description>

                <ul className="mt-4 space-y-1.5 rounded-[16px] bg-white/70 p-3.5">
                  {policy.categories.map((category) => (
                    <li
                      key={category.key}
                      className="flex items-start gap-2 text-[14px] text-[#0e2a33]"
                    >
                      <span
                        className="mt-[7px] size-1.5 shrink-0 rounded-full bg-neu-green"
                        aria-hidden="true"
                      />
                      {category.label}
                    </li>
                  ))}
                </ul>
              </>
            )}
          </div>

          {error && (
            <p
              role="alert"
              className="mt-4 rounded-[12px] bg-[rgba(217,45,32,0.08)] px-3.5 py-2.5 text-[14px] font-semibold text-[#D92D20]"
            >
              {error}
            </p>
          )}

          <div className="mt-5 flex flex-col-reverse gap-2.5 sm:flex-row">
            <Dialog.Close asChild>
              <button
                type="button"
                disabled={submitting}
                className="neu-btn-secondary w-full disabled:opacity-50 sm:flex-1"
              >
                {policy?.decline_label ?? 'Không chia sẻ'}
              </button>
            </Dialog.Close>
            <button
              type="button"
              onClick={handleAccept}
              disabled={submitting || !policy}
              className="neu-btn-primary w-full disabled:opacity-50 sm:flex-1"
            >
              {submitting ? 'Đang xử lý…' : (policy?.accept_label ?? 'Đồng ý và tiếp tục')}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
