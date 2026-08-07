'use client'

import * as React from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { ShieldCheck, ShieldOff } from 'lucide-react'
import { NeuCard } from '@/components/patient/neu'
import { ApiError } from '@/lib/api/client'
import {
  getDataSharingConsent,
  getDataSharingPolicy,
  revokeDataSharingConsent,
  restoreDataSharingConsent,
  type DataSharingConsent,
  type DataSharingConsentPolicy,
} from '@/lib/api/consultations'
import { formatDateTime } from './format'
import { DataSharingConsentModal } from './DataSharingConsentModal'

/** Statuses where the doctor still holds an access grant, so sharing is live. */
const LIVE_STATUSES = new Set(['PAID', 'IN_PROGRESS'])

/**
 * "Chia sẻ dữ liệu với bác sĩ" — the control the booking consent copy promises.
 *
 * Three things this screen is careful about:
 *
 * 1. It never claims a sharing state that is not true. The doctor's access ends
 *    when the consultation does, so on a finished consultation the card says the
 *    session ended rather than showing a green "Đang chia sẻ" for access nobody
 *    has — and it does not offer a re-share that would reopen nothing.
 * 2. Re-sharing goes through the same consent dialog as booking, showing the
 *    server's current terms. Re-granting is a consent decision, and recording
 *    one against copy the patient never saw is exactly what the version stamps
 *    exist to prevent.
 * 3. It never renders a status it is not sure of. If the state cannot be
 *    re-read after an action, the card drops to its error/retry state instead of
 *    leaving a stale "Đang chia sẻ" on screen.
 *
 * Category labels come from the policy endpoint, not a second hardcoded copy —
 * the patient revokes against the same words they consented to.
 */
export function ConsultationSharingCard({
  consultationId,
  consultationStatus,
  doctorName,
  consultationDate,
}: {
  consultationId: string
  consultationStatus?: string | null
  doctorName?: string | null
  consultationDate?: string | null
}) {
  const [consent, setConsent] = React.useState<DataSharingConsent | null>(null)
  const [policy, setPolicy] = React.useState<DataSharingConsentPolicy | null>(null)
  const [loading, setLoading] = React.useState(true)
  const [absent, setAbsent] = React.useState(false)
  const [loadError, setLoadError] = React.useState<string | null>(null)

  const [confirmOpen, setConfirmOpen] = React.useState(false)
  const [reshareOpen, setReshareOpen] = React.useState(false)
  const [busy, setBusy] = React.useState(false)
  const [actionError, setActionError] = React.useState<string | null>(null)
  const [announcement, setAnnouncement] = React.useState<string | null>(null)
  // Synchronous lock: setBusy lands after the stack unwinds, so a double-press
  // could otherwise fire two revokes before it takes effect.
  const inFlightRef = React.useRef(false)
  const reshareButtonRef = React.useRef<HTMLButtonElement>(null)
  const revokeButtonRef = React.useRef<HTMLButtonElement>(null)
  // Where to put focus once the action's dialog unmounts — otherwise Radix
  // restores focus to a node that no longer exists and it lands on <body>.
  const focusAfterRef = React.useRef<'revoke' | 'reshare' | null>(null)

  const load = React.useCallback(() => {
    setLoading(true)
    setLoadError(null)
    Promise.all([
      getDataSharingConsent(consultationId),
      getDataSharingPolicy().catch(() => null),
    ])
      .then(([data, loadedPolicy]) => {
        setConsent(data)
        setPolicy(loadedPolicy)
        setAbsent(false)
      })
      .catch((err: unknown) => {
        // 404 = booked before this feature existed. Not an error to show.
        if (err instanceof ApiError && err.status === 404) setAbsent(true)
        else setLoadError('Không tải được trạng thái chia sẻ dữ liệu.')
      })
      .finally(() => setLoading(false))
  }, [consultationId])

  React.useEffect(() => {
    load()
  }, [load])

  React.useEffect(() => {
    if (busy || !focusAfterRef.current) return
    const target = focusAfterRef.current
    focusAfterRef.current = null
    // Next frame: the dialog has to finish unmounting first.
    const id = requestAnimationFrame(() => {
      const el = target === 'reshare' ? reshareButtonRef.current : revokeButtonRef.current
      el?.focus()
    })
    return () => cancelAnimationFrame(id)
  }, [busy, consent])

  const run = async (
    action: () => Promise<unknown>,
    { onDone, announce }: { onDone: 'revoke' | 'reshare'; announce: string },
  ) => {
    if (inFlightRef.current) return
    inFlightRef.current = true
    setBusy(true)
    setActionError(null)
    try {
      await action()
    } catch (err) {
      setActionError(
        err instanceof ApiError && err.detail
          ? err.detail
          : 'Không thực hiện được. Vui lòng thử lại.',
      )
      inFlightRef.current = false
      setBusy(false)
      return
    }
    // The mutation landed. Re-read separately: a failure HERE must not be
    // reported as "the action failed", and must never leave the old status on
    // screen — a card claiming "Đã thu hồi" while the doctor can read is worse
    // than a card that admits it does not know.
    try {
      setConsent(await getDataSharingConsent(consultationId))
      setConfirmOpen(false)
      setReshareOpen(false)
      setAnnouncement(announce)
      focusAfterRef.current = onDone
    } catch {
      setConsent(null)
      setConfirmOpen(false)
      setReshareOpen(false)
      setLoadError('Không tải lại được trạng thái chia sẻ. Vui lòng thử lại.')
    } finally {
      inFlightRef.current = false
      setBusy(false)
    }
  }

  if (absent) return null

  if (loading) {
    return (
      <NeuCard className="!p-4">
        <p className="text-[15px] text-neu-muted" role="status">
          Đang tải trạng thái chia sẻ…
        </p>
      </NeuCard>
    )
  }

  if (loadError || !consent) {
    return (
      <NeuCard className="!p-4">
        <p className="text-[15px] text-[#D92D20]" role="alert">
          {loadError ?? 'Không tải được trạng thái chia sẻ dữ liệu.'}
        </p>
        <button type="button" onClick={load} className="neu-btn-secondary mt-3 w-full">
          Thử lại
        </button>
      </NeuCard>
    )
  }

  // The consultation must still be live for sharing to mean anything: the
  // doctor's access grant is closed when it completes or is cancelled.
  const sessionLive = consultationStatus == null || LIVE_STATUSES.has(consultationStatus)
  const granted = consent.is_active
  const active = granted && sessionLive
  const labelFor = (key: string) =>
    policy?.categories.find((c) => c.key === key)?.label ?? key

  const statusText = !sessionLive
    ? 'Đã kết thúc chia sẻ (buổi tư vấn đã xong)'
    : granted
      ? 'Đang chia sẻ'
      : 'Đã thu hồi'

  return (
    <NeuCard className="!p-4" data-testid="sharing-card">
      <div className="flex items-start gap-3">
        <span
          className={
            active
              ? 'grid size-10 shrink-0 place-items-center rounded-full bg-[rgba(13,155,110,0.12)]'
              : 'grid size-10 shrink-0 place-items-center rounded-full bg-[rgba(16,48,44,0.08)]'
          }
          aria-hidden="true"
        >
          {active ? (
            <ShieldCheck className="size-5 text-neu-green" />
          ) : (
            <ShieldOff className="size-5 text-neu-muted" />
          )}
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="text-[16px] font-bold text-neu-text">Chia sẻ dữ liệu với bác sĩ</h2>
          <p
            role="status"
            aria-live="polite"
            className={
              active
                ? 'mt-0.5 text-[14px] font-semibold text-neu-green'
                : 'mt-0.5 text-[14px] font-semibold text-neu-muted'
            }
            data-testid="sharing-status"
          >
            {announcement ?? statusText}
          </p>
        </div>
      </div>

      <dl className="mt-3 space-y-1 text-[14px]">
        {doctorName && (
          <div className="flex justify-between gap-3">
            <dt className="text-neu-muted">Bác sĩ</dt>
            <dd className="text-right font-semibold text-neu-text">{doctorName}</dd>
          </div>
        )}
        <div className="flex justify-between gap-3">
          <dt className="text-neu-muted">Mã tư vấn</dt>
          <dd className="text-right font-semibold text-neu-text">
            {consultationId.slice(0, 8).toUpperCase()}
          </dd>
        </div>
        {consultationDate && (
          <div className="flex justify-between gap-3">
            <dt className="text-neu-muted">Ngày tư vấn</dt>
            <dd className="text-right font-semibold text-neu-text">
              {formatDateTime(consultationDate)}
            </dd>
          </div>
        )}
      </dl>

      <p className="mt-3 text-[13px] font-semibold text-neu-muted">
        {active ? 'Thông tin đang chia sẻ' : 'Thông tin đã từng chia sẻ'}
      </p>
      <ul className="mt-1 space-y-1" data-testid="sharing-categories">
        {consent.categories.map((key) => (
          <li
            key={key}
            className={
              active
                ? 'flex items-start gap-2 text-[14px] text-neu-text'
                : 'flex items-start gap-2 text-[14px] text-neu-muted'
            }
          >
            <span
              className={
                active
                  ? 'mt-[7px] size-1.5 shrink-0 rounded-full bg-neu-green'
                  : 'mt-[7px] size-1.5 shrink-0 rounded-full bg-[rgba(16,48,44,0.25)]'
              }
              aria-hidden="true"
            />
            {labelFor(key)}
          </li>
        ))}
      </ul>

      {actionError && !confirmOpen && !reshareOpen && (
        <p
          role="alert"
          className="mt-3 rounded-[12px] bg-[rgba(217,45,32,0.08)] px-3.5 py-2.5 text-[14px] font-semibold text-[#D92D20]"
        >
          {actionError}
        </p>
      )}

      {!sessionLive ? (
        <p className="mt-4 text-[13px] leading-relaxed text-neu-muted" data-testid="session-ended">
          Buổi tư vấn đã kết thúc nên bác sĩ không còn xem được dữ liệu của bạn.
        </p>
      ) : granted ? (
        <>
          <button
            ref={revokeButtonRef}
            type="button"
            onClick={() => {
              setActionError(null)
              setConfirmOpen(true)
            }}
            disabled={busy}
            className="neu-btn-secondary mt-4 w-full disabled:opacity-50"
            data-testid="revoke-button"
          >
            Thu hồi quyền chia sẻ
          </button>
          <RevokeConfirmDialog
            open={confirmOpen}
            onOpenChange={(next) => {
              if (!next && busy) return
              setConfirmOpen(next)
              if (!next) setActionError(null)
            }}
            busy={busy}
            error={actionError}
            doctorName={doctorName}
            onConfirm={() =>
              void run(() => revokeDataSharingConsent(consultationId), {
                onDone: 'reshare',
                announce: 'Đã thu hồi quyền chia sẻ.',
              })
            }
          />
        </>
      ) : (
        <>
          <button
            ref={reshareButtonRef}
            type="button"
            onClick={() => {
              setActionError(null)
              setReshareOpen(true)
            }}
            disabled={busy}
            className="neu-btn-primary mt-4 w-full disabled:opacity-50"
            data-testid="reshare-button"
          >
            Chia sẻ lại
          </button>
          {/* Re-granting shows the same terms as booking. A one-tap re-share
              would record a consent decision against copy never displayed. */}
          <DataSharingConsentModal
            open={reshareOpen}
            onOpenChange={(next) => {
              if (!next && busy) return
              setReshareOpen(next)
              if (!next) setActionError(null)
            }}
            onAccept={(grant) =>
              void run(
                () =>
                  restoreDataSharingConsent(consultationId, {
                    accepted: true,
                    categories: grant.categories,
                    consent_version: grant.consentVersion,
                    policy_version: grant.policyVersion,
                  }),
                { onDone: 'revoke', announce: 'Đã chia sẻ lại dữ liệu với bác sĩ.' },
              )
            }
            submitting={busy}
            error={actionError}
            doctorName={doctorName}
            restrictToCategories={consent.categories}
            titleOverride="Chia sẻ lại dữ liệu với bác sĩ?"
          />
        </>
      )}
    </NeuCard>
  )
}

/**
 * Revoking cuts the doctor off mid-consultation, so it is confirmed — and the
 * confirmation states the consequences a patient could otherwise get wrong:
 * that the session continues and is not refunded, that the doctor loses the
 * clinical detail immediately, and that this can be undone.
 */
function RevokeConfirmDialog({
  open,
  onOpenChange,
  busy,
  error,
  doctorName,
  onConfirm,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  busy: boolean
  error: string | null
  doctorName?: string | null
  onConfirm: () => void
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-[rgba(14,42,51,0.5)] backdrop-blur-[3px]" />
        <Dialog.Content
          aria-modal="true"
          className="patient-app fixed left-1/2 top-1/2 z-50 flex max-h-[calc(100dvh-32px)] w-[calc(100vw-32px)] max-w-[400px] -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-[24px] border border-white/85 bg-[rgba(248,251,249,0.96)] p-5 shadow-[0_20px_60px_-20px_rgba(16,48,44,0.55)]"
          onEscapeKeyDown={(e) => {
            if (busy) e.preventDefault()
          }}
          onInteractOutside={(e) => {
            if (busy) e.preventDefault()
          }}
        >
          <Dialog.Title className="text-[19px] font-extrabold text-[#0e2a33]">
            Thu hồi quyền chia sẻ?
          </Dialog.Title>
          <Dialog.Description className="mt-3 min-h-0 flex-1 space-y-3 overflow-y-auto text-[15px] leading-relaxed text-[#365651]">
            <span className="block">
              Sau khi thu hồi, {doctorName ? `bác sĩ ${doctorName}` : 'bác sĩ'} sẽ không thể
              tiếp tục xem các thông tin sức khỏe được chia sẻ cho phiên tư vấn này — bao gồm
              danh sách thuốc và kết quả xét nghiệm — ngay lập tức.
            </span>
            <span className="block">
              Buổi tư vấn vẫn tiếp tục và không được hoàn tiền. Thông tin về phiên tư vấn và
              các hồ sơ cần lưu theo quy định vẫn được giữ lại.
            </span>
            <span className="block">Bạn có thể chia sẻ lại bất cứ lúc nào.</span>
          </Dialog.Description>

          {error && (
            <p
              role="alert"
              className="mt-4 rounded-[12px] bg-[rgba(217,45,32,0.08)] px-3.5 py-2.5 text-[14px] font-semibold text-[#D92D20]"
            >
              {error}
            </p>
          )}

          {/* Safe option first, and the destructive one is styled as destructive
              rather than as the endorsed brand action. */}
          <div className="mt-5 flex shrink-0 flex-col gap-2.5 sm:flex-row">
            <Dialog.Close asChild>
              <button
                type="button"
                disabled={busy}
                className="neu-btn-secondary w-full disabled:opacity-50 sm:flex-1"
                data-testid="revoke-cancel"
              >
                Giữ quyền chia sẻ
              </button>
            </Dialog.Close>
            <button
              type="button"
              onClick={onConfirm}
              disabled={busy}
              className="w-full rounded-[999px] bg-[#D92D20] px-5 py-4 text-[18px] font-bold text-white shadow-[0_10px_24px_-12px_rgba(217,45,32,0.7)] disabled:opacity-50 sm:flex-1"
              data-testid="revoke-confirm"
            >
              {busy ? 'Đang xử lý…' : 'Thu hồi'}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
