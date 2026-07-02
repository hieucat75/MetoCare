'use client'

import * as React from 'react'
import { useParams, useRouter } from 'next/navigation'
import { ArrowLeft, CheckCircle2, CreditCard, MessageSquare, Video, MapPin } from 'lucide-react'
import { NeuCard } from '@/components/patient/neu'
import { PatientErrorState, PatientSkeleton } from '@/components/patient/states'
import {
  formatVnd,
  MarketplaceDisclaimer,
  DataConsentCheckbox,
} from '@/components/marketplace'
import { ApiError } from '@/lib/api/client'
import { getDoctorDetail, type DoctorDetailOut, type ConsultationType } from '@/lib/api/marketplace'
import {
  createConsultation,
  payConsultation,
  type ConsultationOut,
} from '@/lib/api/consultations'

type Step = 'form' | 'pay' | 'done'

const TYPE_OPTIONS: { key: ConsultationType; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
  { key: 'CHAT', label: 'Nhắn tin', icon: MessageSquare },
  { key: 'VIDEO', label: 'Gọi video', icon: Video },
  { key: 'IN_PERSON', label: 'Khám trực tiếp', icon: MapPin },
]

const MAX_COMPLAINT = 2000

export default function BookConsultationPage() {
  const router = useRouter()
  const params = useParams<{ doctorId: string }>()
  const doctorId = params.doctorId

  const [doctor, setDoctor] = React.useState<DoctorDetailOut | null>(null)
  const [loadingDoctor, setLoadingDoctor] = React.useState(true)
  const [loadError, setLoadError] = React.useState<string | null>(null)

  const [step, setStep] = React.useState<Step>('form')
  const [consultationType, setConsultationType] = React.useState<ConsultationType>('CHAT')
  const [consent, setConsent] = React.useState(false)
  const [chiefComplaint, setChiefComplaint] = React.useState('')

  const [consultation, setConsultation] = React.useState<ConsultationOut | null>(null)
  const [submitting, setSubmitting] = React.useState(false)
  const [actionError, setActionError] = React.useState<string | null>(null)

  const loadDoctor = React.useCallback(() => {
    setLoadingDoctor(true)
    setLoadError(null)
    getDoctorDetail(doctorId)
      .then((d) => setDoctor(d))
      .catch((err: Error) => setLoadError(err.message))
      .finally(() => setLoadingDoctor(false))
  }, [doctorId])

  React.useEffect(() => {
    loadDoctor()
  }, [loadDoctor])

  const handleCreate = async () => {
    if (!consent) {
      setActionError('Bạn cần đồng ý chia sẻ dữ liệu để đặt tư vấn.')
      return
    }
    setSubmitting(true)
    setActionError(null)
    try {
      const created = await createConsultation({
        doctor_id: doctorId,
        consultation_type: consultationType,
        data_consent_accepted: true,
        chief_complaint: chiefComplaint.trim() || undefined,
      })
      setConsultation(created)
      setStep('pay')
    } catch (err) {
      setActionError(friendlyError(err))
    } finally {
      setSubmitting(false)
    }
  }

  const handlePay = async () => {
    if (!consultation) return
    setSubmitting(true)
    setActionError(null)
    try {
      await payConsultation(consultation.id)
      setStep('done')
    } catch (err) {
      setActionError(friendlyError(err))
    } finally {
      setSubmitting(false)
    }
  }

  const price = doctor?.consultation_fee ?? consultation?.consultation_price ?? null

  return (
    <div className="p-4 max-w-md mx-auto pb-28 space-y-4">
      {/* ── Header ── */}
      <header className="flex items-center gap-3">
        <button
          type="button"
          aria-label="Quay lại"
          onClick={() => (step === 'form' ? router.back() : undefined)}
          disabled={step !== 'form'}
          className="neu-icon-btn !w-11 !h-11 !rounded-full text-neu-text disabled:opacity-40"
        >
          <ArrowLeft className="size-5" />
        </button>
        <h1 className="text-[20px] font-extrabold tracking-[-0.02em] text-neu-text">
          {step === 'done' ? 'Đặt tư vấn thành công' : 'Đặt tư vấn'}
        </h1>
      </header>

      {loadingDoctor ? (
        <PatientSkeleton />
      ) : loadError ? (
        <PatientErrorState title="Không thể tải hồ sơ bác sĩ" message={loadError} onRetry={loadDoctor} />
      ) : doctor ? (
        <>
          {/* Doctor summary strip (always visible) */}
          <NeuCard className="!p-4">
            <p className="text-[16px] font-bold text-neu-text">{doctor.full_name}</p>
            {doctor.specialty && (
              <p className="text-[14px] font-semibold text-neu-green">{doctor.specialty}</p>
            )}
          </NeuCard>

          {step === 'form' && (
            <BookingForm
              consultationType={consultationType}
              onType={setConsultationType}
              consent={consent}
              onConsent={setConsent}
              chiefComplaint={chiefComplaint}
              onChiefComplaint={setChiefComplaint}
              price={price}
              submitting={submitting}
              error={actionError}
              onSubmit={handleCreate}
            />
          )}

          {step === 'pay' && consultation && (
            <PaymentStep
              consultation={consultation}
              price={consultation.consultation_price}
              submitting={submitting}
              error={actionError}
              onPay={handlePay}
            />
          )}

          {step === 'done' && consultation && (
            <SuccessStep
              onViewConsultations={() => router.push(`/consultations/${consultation.id}`)}
              onBackToMarketplace={() => router.push('/marketplace')}
            />
          )}
        </>
      ) : null}
    </div>
  )
}

// ── Step 1: form ──────────────────────────────────────────────────────────────

function BookingForm({
  consultationType,
  onType,
  consent,
  onConsent,
  chiefComplaint,
  onChiefComplaint,
  price,
  submitting,
  error,
  onSubmit,
}: {
  consultationType: ConsultationType
  onType: (t: ConsultationType) => void
  consent: boolean
  onConsent: (b: boolean) => void
  chiefComplaint: string
  onChiefComplaint: (s: string) => void
  price: number | null
  submitting: boolean
  error: string | null
  onSubmit: () => void
}) {
  return (
    <>
      {/* Consultation type */}
      <section>
        <p className="mb-2 px-1 text-[15px] font-bold text-neu-text">Hình thức tư vấn</p>
        <div className="grid grid-cols-3 gap-2.5">
          {TYPE_OPTIONS.map((opt) => {
            const active = consultationType === opt.key
            const Icon = opt.icon
            return (
              <button
                key={opt.key}
                type="button"
                onClick={() => onType(opt.key)}
                className={
                  active
                    ? 'flex flex-col items-center gap-1.5 rounded-[16px] border-2 border-[#0B7F5B] bg-[rgba(227,244,234,0.6)] px-2 py-3.5'
                    : 'flex flex-col items-center gap-1.5 rounded-[16px] border-2 border-[rgba(16,48,44,0.1)] bg-white px-2 py-3.5'
                }
              >
                <Icon className={active ? 'size-6 text-neu-green' : 'size-6 text-neu-muted'} />
                <span
                  className={
                    active
                      ? 'text-[13px] font-bold text-neu-green'
                      : 'text-[13px] font-semibold text-neu-muted'
                  }
                >
                  {opt.label}
                </span>
              </button>
            )
          })}
        </div>
      </section>

      {/* Chief complaint (optional) */}
      <section>
        <label className="mb-2 block px-1 text-[15px] font-bold text-neu-text">
          Lý do tư vấn <span className="font-normal text-neu-muted">(không bắt buộc)</span>
        </label>
        <textarea
          value={chiefComplaint}
          onChange={(e) => onChiefComplaint(e.target.value.slice(0, MAX_COMPLAINT))}
          rows={3}
          placeholder="Mô tả ngắn gọn triệu chứng hoặc điều bạn muốn hỏi bác sĩ…"
          className="w-full rounded-[16px] bg-white px-4 py-3 text-[16px] text-neu-text outline-none neu-card !shadow-none border border-[rgba(16,48,44,0.08)] placeholder:text-neu-muted resize-none"
        />
        <p className="mt-1 px-1 text-right text-[12px] text-neu-muted">
          {chiefComplaint.length}/{MAX_COMPLAINT}
        </p>
      </section>

      {/* Data consent (required) */}
      <DataConsentCheckbox checked={consent} onChange={onConsent} />

      <MarketplaceDisclaimer />

      {/* Price confirm */}
      <NeuCard className="!p-4">
        <div className="flex items-center justify-between">
          <span className="text-[15px] text-neu-muted">Tổng thanh toán</span>
          <span className="text-[22px] font-extrabold text-neu-text">{formatVnd(price)}</span>
        </div>
      </NeuCard>

      {error && (
        <p className="rounded-[12px] bg-[rgba(217,45,32,0.08)] px-3.5 py-2.5 text-[14px] font-semibold text-[#D92D20]">
          {error}
        </p>
      )}

      <button
        type="button"
        onClick={onSubmit}
        disabled={!consent || submitting}
        className="neu-btn-primary w-full disabled:opacity-50"
      >
        {submitting ? 'Đang xử lý…' : 'Xác nhận đặt tư vấn'}
      </button>
    </>
  )
}

// ── Step 2: mock payment ──────────────────────────────────────────────────────

function PaymentStep({
  consultation,
  price,
  submitting,
  error,
  onPay,
}: {
  consultation: ConsultationOut
  price: number
  submitting: boolean
  error: string | null
  onPay: () => void
}) {
  return (
    <>
      <NeuCard className="!p-5 text-center">
        <span className="mx-auto grid size-14 place-items-center rounded-full bg-[rgba(13,155,110,0.12)]">
          <CreditCard className="size-7 text-neu-green" aria-hidden="true" />
        </span>
        <h2 className="mt-3 text-[18px] font-bold text-neu-text">Thanh toán tư vấn</h2>
        <p className="mt-1 text-[14px] text-neu-muted">
          Yêu cầu tư vấn đã được tạo. Hoàn tất thanh toán để bác sĩ bắt đầu.
        </p>
        <p className="mt-4 text-[32px] font-extrabold text-neu-text">{formatVnd(price)}</p>
        <p className="text-[13px] text-neu-muted">Mã tư vấn: {shortId(consultation.id)}</p>
      </NeuCard>

      <MarketplaceDisclaimer />

      {error && (
        <p className="rounded-[12px] bg-[rgba(217,45,32,0.08)] px-3.5 py-2.5 text-[14px] font-semibold text-[#D92D20]">
          {error}
        </p>
      )}

      <button
        type="button"
        onClick={onPay}
        disabled={submitting}
        className="neu-btn-primary w-full disabled:opacity-50"
      >
        {submitting ? 'Đang xử lý…' : 'Thanh toán thử'}
      </button>
      <p className="text-center text-[12px] text-neu-muted">
        Đây là thanh toán mô phỏng — không có giao dịch thật.
      </p>
    </>
  )
}

// ── Step 3: success ───────────────────────────────────────────────────────────

function SuccessStep({
  onViewConsultations,
  onBackToMarketplace,
}: {
  onViewConsultations: () => void
  onBackToMarketplace: () => void
}) {
  return (
    <>
      <NeuCard className="!p-6 text-center">
        <span className="mx-auto grid size-16 place-items-center rounded-full bg-[rgba(21,145,90,0.12)]">
          <CheckCircle2 className="size-9 text-neu-green" aria-hidden="true" />
        </span>
        <h2 className="mt-4 text-[20px] font-extrabold text-neu-text">Đã thanh toán thành công</h2>
        <p className="mt-1.5 text-[15px] leading-relaxed text-neu-muted">
          Bác sĩ sẽ xác nhận và bắt đầu tư vấn sớm. Bạn có thể theo dõi trạng thái trong mục tư vấn
          của mình.
        </p>
      </NeuCard>

      <button type="button" onClick={onViewConsultations} className="neu-btn-primary w-full">
        Xem tư vấn của tôi
      </button>
      <button type="button" onClick={onBackToMarketplace} className="neu-btn-secondary w-full">
        Về danh sách bác sĩ
      </button>
    </>
  )
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function friendlyError(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 422) {
      return 'Bạn cần đồng ý chia sẻ dữ liệu để đặt tư vấn.'
    }
    if (err.status === 402 || err.status === 409) {
      return err.detail || 'Không thể hoàn tất thanh toán. Vui lòng thử lại.'
    }
    return err.detail || 'Đã có lỗi xảy ra. Vui lòng thử lại.'
  }
  return 'Đã có lỗi xảy ra. Vui lòng thử lại.'
}

function shortId(id: string): string {
  return id.slice(0, 8).toUpperCase()
}
