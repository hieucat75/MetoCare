'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import { CalendarDays, FlaskConical, Plus, Upload } from 'lucide-react'
import { ErrorState } from '@/design-system'
import { GlassCard, SectionHeader, PatientEmptyState, LabEntryModal } from '@/components/patient'
import { useAuth } from '@/lib/auth/context'
import { getLabResults, type LabResultEntry } from '@/lib/api/patient'
import { useFeatureFlags } from '@/lib/api/features'
import { formatDate } from '@/lib/utils'

// ─── Result card ──────────────────────────────────────────────────────────────
// Decision-first: exam date leads (the real test date), test name + value scan
// in one glance, reference range and upload provenance sit beneath, muted.

function ResultCard({ r }: { r: LabResultEntry }) {
  const valueStr = r.value != null ? `${r.value}${r.unit ? ` ${r.unit}` : ''}` : '—'
  return (
    <GlassCard>
      {/* Exam date — prominent (the real test date, not the upload date). */}
      <div className="flex items-center gap-1.5 text-[15px] font-semibold text-[#0D815A]">
        <CalendarDays className="size-4 shrink-0" aria-hidden="true" />
        {r.test_date ? formatDate(r.test_date) : 'Chưa có ngày xét nghiệm'}
      </div>

      <div className="mt-2 flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-mint-50 text-mint-600">
            <FlaskConical className="size-[18px]" aria-hidden="true" />
          </span>
          <span className="truncate text-[17px] font-semibold text-text">{r.test_name}</span>
        </div>
        <span className="shrink-0 text-[20px] font-bold leading-tight text-text">{valueStr}</span>
      </div>

      <div className="mt-2 flex items-center justify-between gap-3 pl-11">
        <span className="min-w-0 truncate text-[14px] text-text-muted">
          {r.reference_range ? `Tham chiếu: ${r.reference_range}` : ''}
        </span>
        {/* Upload date — muted, clearly distinct from the exam date. */}
        <span className="shrink-0 text-[13px] text-text-subtle">
          Tải lên {formatDate(r.created_at)}
        </span>
      </div>

      {r.verified_by_user && (
        <div className="mt-2 pl-11">
          <span className="inline-flex items-center rounded-full bg-[#DCFCE7] px-2.5 py-0.5 text-[12px] font-semibold text-[#0E5B2F]">
            Tự nhập
          </span>
        </div>
      )}
    </GlassCard>
  )
}

// ─── Loading skeleton ─────────────────────────────────────────────────────────

function LabsSkeleton() {
  return (
    <div className="space-y-3" aria-hidden="true">
      {[1, 2, 3].map((n) => (
        <GlassCard key={n}>
          <div className="mc-pulse h-3.5 w-2/5 rounded-md bg-mint-100/70" />
          <div className="mt-3 flex items-center justify-between gap-3">
            <div className="mc-pulse h-4 w-1/2 rounded-md bg-mint-100/70" />
            <div className="mc-pulse h-5 w-16 rounded-md bg-mint-100/70" />
          </div>
        </GlassCard>
      ))}
    </div>
  )
}

// ─── Upload CTA (OCR flag on) / coming-soon hint (flag off) ────────────────────

function UploadCta({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex w-full items-center justify-between gap-3 rounded-3xl bg-gradient-to-br from-mint-400 to-mint-600 px-5 py-4 text-left text-white shadow-glow-mint transition-transform active:scale-[0.99]"
    >
      <span className="flex min-w-0 items-center gap-3">
        <span className="grid size-12 shrink-0 place-items-center rounded-2xl bg-white/20">
          <Upload className="size-6" aria-hidden="true" />
        </span>
        <span className="min-w-0">
          <span className="block text-[17px] font-bold">Tải lên kết quả xét nghiệm</span>
          <span className="block text-[14px] leading-snug text-white/90">
            Chụp ảnh, tải tệp hoặc dán link — tự động đọc
          </span>
        </span>
      </span>
      <span aria-hidden="true" className="shrink-0 text-[22px] font-bold">
        →
      </span>
    </button>
  )
}

function UploadComingSoon() {
  return (
    <GlassCard className="flex items-center justify-between gap-3">
      <span className="flex min-w-0 items-center gap-3 text-text-muted">
        <span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-mint-50 text-mint-600">
          <Upload className="size-5" aria-hidden="true" />
        </span>
        <span className="min-w-0 text-[16px] leading-snug">Tải ảnh/PDF và tự động đọc kết quả</span>
      </span>
      <span className="shrink-0 rounded-full bg-[#FEF3C7] px-3 py-1 text-[13px] font-semibold text-[#78350F]">
        Sắp ra mắt
      </span>
    </GlassCard>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function LabsPage() {
  const router = useRouter()
  const { user } = useAuth()
  const patientId = user?.patient_profile_id
  const flags = useFeatureFlags()

  const [results, setResults] = React.useState<LabResultEntry[]>([])
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)
  const [modalOpen, setModalOpen] = React.useState(false)

  const load = React.useCallback(() => {
    if (!patientId) {
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    getLabResults(patientId, { limit: 100 })
      .then((res) => setResults(res.items))
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [patientId])

  React.useEffect(() => {
    load()
  }, [load])

  if (!user) return null

  if (!patientId) {
    return (
      <div className="mx-auto mt-10 max-w-md p-4">
        <GlassCard>
          <h2 className="text-[18px] font-semibold text-text">Chưa có hồ sơ bệnh nhân</h2>
          <p className="mt-1 text-[15px] text-text-muted">
            Tài khoản của bạn chưa được liên kết với hồ sơ bệnh nhân. Vui lòng liên hệ hỗ trợ.
          </p>
        </GlassCard>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-md space-y-5 p-4 pb-28 lg:max-w-2xl lg:p-6">
      {/* 1 — Header with primary "manual entry" action */}
      <SectionHeader
        title="Kết quả xét nghiệm"
        subtitle="Theo dõi các chỉ số xét nghiệm theo thời gian"
        action={
          <button
            type="button"
            onClick={() => setModalOpen(true)}
            className="inline-flex h-12 items-center gap-1.5 rounded-2xl bg-[#0D815A] px-4 text-[15px] font-bold text-white shadow-glass transition-transform active:scale-[0.97]"
          >
            <Plus className="size-4" aria-hidden="true" /> Nhập kết quả
          </button>
        }
      />

      {/* 2 — OCR upload — real CTA when the flag is on; otherwise a "coming soon" hint. */}
      {flags && flags.ocr && <UploadCta onClick={() => router.push('/labs/upload')} />}
      {flags && !flags.ocr && <UploadComingSoon />}

      {/* 3 — Content states */}
      {loading && <LabsSkeleton />}

      {!loading && error && (
        <ErrorState title="Không thể tải kết quả" message={error} onRetry={load} />
      )}

      {!loading && !error && results.length === 0 && (
        <GlassCard className="border-[1.5px] border-dashed border-mint-300 bg-white/60">
          <PatientEmptyState
            icon={<FlaskConical />}
            title="Chưa có kết quả xét nghiệm"
            description="Nhập kết quả xét nghiệm của bạn để theo dõi các chỉ số theo thời gian."
            cta={{ label: 'Nhập kết quả đầu tiên', onClick: () => setModalOpen(true) }}
          />
        </GlassCard>
      )}

      {!loading && !error && results.length > 0 && (
        <section aria-label="Danh sách kết quả xét nghiệm" className="space-y-3">
          {results.map((r) => (
            <ResultCard key={r.id} r={r} />
          ))}
        </section>
      )}

      <LabEntryModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onSaved={load}
        patientId={patientId}
      />
    </div>
  )
}
