'use client'

import * as React from 'react'
import { useParams, useRouter } from 'next/navigation'
import { ArrowLeft, FileText, Star, CreditCard, XCircle } from 'lucide-react'
import { NeuCard } from '@/components/patient/neu'
import { PatientErrorState, PatientSkeleton } from '@/components/patient/states'
import {
  ConsultationStatusBadge,
  formatVnd,
  formatDateTime,
  MarketplaceDisclaimer,
  ConsultationSharingCard,
} from '@/components/marketplace'
import { getDoctorDetail } from '@/lib/api/marketplace'
import { ApiError } from '@/lib/api/client'
import type { ConsultationStatus } from '@/lib/api/marketplace'
import {
  getConsultation,
  payConsultation,
  cancelConsultation,
  listNotes,
  createReview,
  type ConsultationOut,
  type NoteOut,
} from '@/lib/api/consultations'

const TYPE_LABELS: Record<string, string> = {
  CHAT: 'Nhắn tin',
  VIDEO: 'Gọi video',
  IN_PERSON: 'Khám trực tiếp',
}

// Statuses where the patient may still cancel.
const CANCELLABLE: ConsultationStatus[] = ['REQUESTED', 'CONFIRMED', 'PAID', 'IN_PROGRESS']

function isPaid(c: ConsultationOut): boolean {
  return (
    c.paid_at != null ||
    c.status === 'PAID' ||
    c.status === 'IN_PROGRESS' ||
    c.status === 'COMPLETED'
  )
}

export default function ConsultationDetailPage() {
  const router = useRouter()
  const params = useParams<{ id: string }>()
  const id = params.id

  const [consultation, setConsultation] = React.useState<ConsultationOut | null>(null)
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)
  const [actionError, setActionError] = React.useState<string | null>(null)
  const [busy, setBusy] = React.useState(false)

  const [notes, setNotes] = React.useState<NoteOut[]>([])
  const [notesError, setNotesError] = React.useState<string | null>(null)
  // The sharing section has to name the recipient — "you are sharing with
  // doctor 41de…" is not something a patient can make a decision about. Best
  // effort: a failed lookup degrades to omitting the name, never to blocking
  // the revoke control.
  const [doctorName, setDoctorName] = React.useState<string | null>(null)

  const load = React.useCallback(() => {
    setLoading(true)
    setError(null)
    getConsultation(id)
      .then((c) => setConsultation(c))
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [id])

  // Cosmetic, so it runs on its own: chaining it into `load` would let a slow
  // marketplace lookup hold the whole consultation screen on its spinner.
  React.useEffect(() => {
    const doctorId = consultation?.doctor_id
    if (!doctorId) return
    let cancelled = false
    getDoctorDetail(doctorId)
      .then((d) => {
        if (!cancelled) setDoctorName(d.full_name)
      })
      .catch(() => {
        if (!cancelled) setDoctorName(null)
      })
    return () => {
      cancelled = true
    }
  }, [consultation?.doctor_id])

  React.useEffect(() => {
    load()
  }, [load])

  // Notes are only readable AFTER COMPLETED — fetch then, handle 403/empty gracefully.
  React.useEffect(() => {
    if (consultation?.status !== 'COMPLETED') return
    let cancelled = false
    setNotesError(null)
    listNotes(id)
      .then((data) => {
        if (!cancelled) setNotes(data)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        // 403 before completion shouldn't happen here; treat any failure as "no notes yet".
        if (err instanceof ApiError && err.status === 403) {
          setNotes([])
        } else {
          setNotesError(err instanceof Error ? err.message : 'Không thể tải ghi chú')
        }
      })
    return () => {
      cancelled = true
    }
  }, [consultation?.status, id])

  const handlePay = async () => {
    setBusy(true)
    setActionError(null)
    try {
      await payConsultation(id)
      load()
    } catch (err) {
      setActionError(friendlyError(err))
    } finally {
      setBusy(false)
    }
  }

  const handleCancel = async () => {
    setBusy(true)
    setActionError(null)
    try {
      await cancelConsultation(id)
      load()
    } catch (err) {
      setActionError(friendlyError(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="p-4 max-w-md mx-auto pb-28 space-y-4">
      {/* ── Header ── */}
      <header className="flex items-center gap-3">
        <button
          type="button"
          aria-label="Quay lại"
          onClick={() => router.back()}
          className="neu-icon-btn !w-11 !h-11 !rounded-full text-neu-text"
        >
          <ArrowLeft className="size-5" />
        </button>
        <h1 className="text-[20px] font-extrabold tracking-[-0.02em] text-neu-text">Chi tiết tư vấn</h1>
      </header>

      {loading ? (
        <div className="space-y-3">
          <PatientSkeleton />
          <PatientSkeleton />
        </div>
      ) : error || !consultation ? (
        <PatientErrorState
          title="Không thể tải buổi tư vấn"
          message={error ?? 'Không tìm thấy buổi tư vấn'}
          onRetry={load}
        />
      ) : (
        <>
          {/* ── Info ── */}
          <NeuCard className="!p-5">
            <div className="flex items-center justify-between">
              <ConsultationStatusBadge status={consultation.status} />
              <span className="text-[13px] text-neu-muted">
                {TYPE_LABELS[consultation.consultation_type] ?? consultation.consultation_type}
              </span>
            </div>

            <p className="mt-3 text-[28px] font-extrabold text-neu-text">
              {formatVnd(consultation.consultation_price)}
            </p>

            <dl className="mt-3 space-y-1.5 text-[14px]">
              <InfoRow label="Mã tư vấn" value={consultation.id.slice(0, 8).toUpperCase()} />
              <InfoRow label="Tạo lúc" value={formatDateTime(consultation.created_at) ?? '—'} />
              {consultation.confirmed_at && (
                <InfoRow label="Xác nhận" value={formatDateTime(consultation.confirmed_at) ?? '—'} />
              )}
              {consultation.paid_at && (
                <InfoRow label="Thanh toán" value={formatDateTime(consultation.paid_at) ?? '—'} />
              )}
              {consultation.completed_at && (
                <InfoRow label="Hoàn thành" value={formatDateTime(consultation.completed_at) ?? '—'} />
              )}
              {consultation.cancelled_at && (
                <InfoRow label="Huỷ lúc" value={formatDateTime(consultation.cancelled_at) ?? '—'} />
              )}
            </dl>

            {consultation.chief_complaint && (
              <div className="mt-3 rounded-[12px] bg-[rgba(16,48,44,0.04)] px-3.5 py-2.5">
                <p className="text-[13px] font-semibold text-neu-muted">Lý do tư vấn</p>
                <p className="mt-0.5 text-[15px] text-neu-text whitespace-pre-line">
                  {consultation.chief_complaint}
                </p>
              </div>
            )}
            {consultation.cancel_reason && (
              <div className="mt-3 rounded-[12px] bg-[rgba(217,45,32,0.06)] px-3.5 py-2.5">
                <p className="text-[13px] font-semibold text-[#D92D20]">Lý do huỷ</p>
                <p className="mt-0.5 text-[15px] text-neu-text">{consultation.cancel_reason}</p>
              </div>
            )}
          </NeuCard>

          {actionError && (
            <p className="rounded-[12px] bg-[rgba(217,45,32,0.08)] px-3.5 py-2.5 text-[14px] font-semibold text-[#D92D20]">
              {actionError}
            </p>
          )}

          {/* ── Actions ── */}
          {!isPaid(consultation) && consultation.status !== 'CANCELLED' && (
            <button
              type="button"
              onClick={handlePay}
              disabled={busy}
              className="neu-btn-primary w-full disabled:opacity-50"
            >
              <span className="inline-flex items-center justify-center gap-2">
                <CreditCard className="size-5" aria-hidden="true" />
                {busy ? 'Đang xử lý…' : 'Thanh toán thử'}
              </span>
            </button>
          )}

          {CANCELLABLE.includes(consultation.status) && (
            <button
              type="button"
              onClick={handleCancel}
              disabled={busy}
              className="neu-btn-secondary w-full disabled:opacity-50"
            >
              <span className="inline-flex items-center justify-center gap-2 text-[#D92D20]">
                <XCircle className="size-5" aria-hidden="true" />
                Huỷ buổi tư vấn
              </span>
            </button>
          )}

          {/* ── Data sharing (the control the consent copy promises) ── */}
          <ConsultationSharingCard
            consultationId={id}
            consultationStatus={consultation.status}
            doctorName={doctorName}
            consultationDate={consultation.created_at}
          />

          {/* ── Doctor notes (after COMPLETED) ── */}
          {consultation.status === 'COMPLETED' && (
            <DoctorNotesSection notes={notes} error={notesError} />
          )}

          {/* ── Review (after COMPLETED) ── */}
          {consultation.status === 'COMPLETED' && <ReviewSection consultationId={id} />}

          <MarketplaceDisclaimer />
        </>
      )}
    </div>
  )
}

// ── Info row ──────────────────────────────────────────────────────────────────

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between">
      <dt className="text-neu-muted">{label}</dt>
      <dd className="font-semibold text-neu-text">{value}</dd>
    </div>
  )
}

// ── Doctor notes ──────────────────────────────────────────────────────────────

function DoctorNotesSection({ notes, error }: { notes: NoteOut[]; error: string | null }) {
  return (
    <section>
      <p className="mb-2 flex items-center gap-1.5 px-1 text-[15px] font-bold text-neu-text">
        <FileText className="size-4" aria-hidden="true" />
        Ghi chú của bác sĩ
      </p>
      {error ? (
        <NeuCard className="!p-4">
          <p className="text-[14px] text-neu-muted">{error}</p>
        </NeuCard>
      ) : notes.length === 0 ? (
        <NeuCard className="!p-4">
          <p className="text-[14px] text-neu-muted">Bác sĩ chưa để lại ghi chú nào.</p>
        </NeuCard>
      ) : (
        <div className="space-y-2.5">
          {notes.map((n) => (
            <NeuCard key={n.id} className="!p-4">
              <p className="text-[15px] leading-relaxed text-neu-text whitespace-pre-line">
                {n.content}
              </p>
              {n.created_at && (
                <p className="mt-2 text-[12px] text-neu-muted">{formatDateTime(n.created_at)}</p>
              )}
            </NeuCard>
          ))}
        </div>
      )}
    </section>
  )
}

// ── Review form ───────────────────────────────────────────────────────────────

function ReviewSection({ consultationId }: { consultationId: string }) {
  const [rating, setRating] = React.useState(0)
  const [feedback, setFeedback] = React.useState('')
  const [submitting, setSubmitting] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [done, setDone] = React.useState(false)

  const handleSubmit = async () => {
    if (rating < 1) {
      setError('Vui lòng chọn số sao đánh giá.')
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      await createReview(consultationId, {
        rating,
        feedback: feedback.trim() || undefined,
      })
      setDone(true)
    } catch (err) {
      setError(friendlyError(err))
    } finally {
      setSubmitting(false)
    }
  }

  if (done) {
    return (
      <NeuCard className="!p-5 text-center">
        <p className="text-[16px] font-bold text-neu-green">Cảm ơn bạn đã đánh giá! ✓</p>
        <p className="mt-1 text-[14px] text-neu-muted">Phản hồi của bạn giúp cải thiện dịch vụ.</p>
      </NeuCard>
    )
  }

  return (
    <NeuCard className="!p-5">
      <p className="text-[16px] font-bold text-neu-text">Đánh giá buổi tư vấn</p>
      <p className="mt-0.5 text-[14px] text-neu-muted">Trải nghiệm của bạn với bác sĩ thế nào?</p>

      {/* Star picker */}
      <div className="mt-3 flex items-center gap-1.5" role="radiogroup" aria-label="Số sao">
        {[1, 2, 3, 4, 5].map((n) => {
          const filled = n <= rating
          return (
            <button
              key={n}
              type="button"
              role="radio"
              aria-checked={rating === n}
              aria-label={`${n} sao`}
              onClick={() => setRating(n)}
              className="p-1"
            >
              <Star
                className={
                  filled ? 'size-8 fill-[#F5B547] text-[#F5B547]' : 'size-8 text-[rgba(16,48,44,0.2)]'
                }
              />
            </button>
          )
        })}
      </div>

      <textarea
        value={feedback}
        onChange={(e) => setFeedback(e.target.value.slice(0, 2000))}
        rows={3}
        placeholder="Chia sẻ thêm cảm nhận của bạn (không bắt buộc)…"
        className="mt-3 w-full rounded-[16px] bg-white px-4 py-3 text-[16px] text-neu-text outline-none neu-card !shadow-none border border-[rgba(16,48,44,0.08)] placeholder:text-neu-muted resize-none"
      />

      {error && (
        <p className="mt-2 text-[14px] font-semibold text-[#D92D20]">{error}</p>
      )}

      <button
        type="button"
        onClick={handleSubmit}
        disabled={submitting}
        className="neu-btn-primary mt-3 w-full disabled:opacity-50"
      >
        {submitting ? 'Đang gửi…' : 'Gửi đánh giá'}
      </button>
    </NeuCard>
  )
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function friendlyError(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 409) return err.detail || 'Bạn đã đánh giá buổi tư vấn này rồi.'
    if (err.status === 403) return 'Bạn không có quyền thực hiện thao tác này.'
    return err.detail || 'Đã có lỗi xảy ra. Vui lòng thử lại.'
  }
  return 'Đã có lỗi xảy ra. Vui lòng thử lại.'
}
