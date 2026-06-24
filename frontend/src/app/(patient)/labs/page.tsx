'use client'

import { PatientEmptyState, LabEntryModal } from '@/components/patient'
import * as React from 'react'
import { useRouter } from 'next/navigation'
import { CalendarDays, FlaskConical, Plus, Upload } from 'lucide-react'
import { PatientErrorState } from '@/components/patient/states'
import { NeuCard, NeuBadge } from '@/components/patient/neu'
import { useAuth } from '@/lib/auth/context'
import { getLabResults, type LabResultEntry } from '@/lib/api/patient'
import { useFeatureFlags } from '@/lib/api/features'
import { formatDate } from '@/lib/utils'

const HERO_GRADIENT = 'linear-gradient(160deg,#17AE7B,#0B6B4D)'

// ── Result card ────────────────────────────────────────────────────────────────

function ResultCard({ r }: { r: LabResultEntry }) {
  const valueStr = r.value != null ? `${r.value}${r.unit ? ` ${r.unit}` : ''}` : '—'
  return (
    <NeuCard className="!p-4">
      {/* Exam date — prominent (the real test date, not the upload date). */}
      <div className="mb-2 flex items-center gap-1.5 text-[13.5px] font-semibold text-neu-green">
        <CalendarDays className="size-4 shrink-0" aria-hidden="true" />
        {r.test_date ? formatDate(r.test_date) : 'Chưa có ngày xét nghiệm'}
      </div>
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2.5">
          <span
            className="grid size-9 shrink-0 place-items-center rounded-[12px] text-white"
            style={{ background: HERO_GRADIENT }}
            aria-hidden="true"
          >
            <FlaskConical className="size-[18px]" />
          </span>
          <span className="truncate text-[16px] font-semibold text-neu-text">{r.test_name}</span>
        </div>
        <span className="shrink-0 text-[18px] font-extrabold text-neu-text">{valueStr}</span>
      </div>
      <div className="mt-1.5 flex items-center justify-between pl-11">
        <span className="text-[13px] text-neu-muted">
          {r.reference_range ? `Tham chiếu: ${r.reference_range}` : ''}
        </span>
        <span className="text-[12px] text-neu-subtle">Tải lên {formatDate(r.created_at)}</span>
      </div>
      {r.verified_by_user && (
        <div className="mt-2 pl-11">
          <NeuBadge tone="ok" className="!text-[11px] !px-2.5 !py-0.5 before:!hidden">
            Tự nhập
          </NeuBadge>
        </div>
      )}
    </NeuCard>
  )
}

function LabsSkeleton() {
  return (
    <div className="space-y-3">
      {[1, 2, 3].map((n) => (
        <div key={n} className="neu-card mc-pulse p-4">
          <div className="h-3.5 w-2/5 rounded-full bg-black/5" />
          <div className="mt-3 h-4 w-3/5 rounded-full bg-black/5" />
        </div>
      ))}
    </div>
  )
}

// ── Page ───────────────────────────────────────────────────────────────────────

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

  if (!patientId) {
    return (
      <div className="p-4 lg:p-6 max-w-md mx-auto mt-10">
        <div role="alert" className="rounded-[14px] bg-[#FEF9EC] border border-[#E0A92E]/30 p-4">
          <p className="text-[14px] font-bold text-[#8B6400]">Chưa có hồ sơ bệnh nhân</p>
          <p className="text-[13px] text-[#8B6400]/80 mt-1">
            Tài khoản của bạn chưa được liên kết với hồ sơ bệnh nhân. Vui lòng liên hệ hỗ trợ.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="p-4 space-y-4 max-w-md mx-auto pb-28">
      <h1 className="px-1 text-[21px] font-extrabold tracking-[-0.02em] text-neu-text">
        Xét nghiệm
      </h1>

      {/* OCR upload — real CTA when the OCR flag is on; otherwise a "coming soon" hint. */}
      {flags && flags.ocr && (
        <button
          type="button"
          onClick={() => router.push('/labs/upload')}
          className="flex w-full items-center justify-between gap-3 rounded-[20px] px-5 py-4 text-left text-white"
          style={{ background: HERO_GRADIENT, boxShadow: '0 14px 26px -12px rgba(11,107,77,0.6)' }}
        >
          <div className="flex min-w-0 items-center gap-3">
            <span className="grid size-11 shrink-0 place-items-center rounded-[14px] bg-white/20">
              <Upload className="size-5" aria-hidden="true" />
            </span>
            <div className="min-w-0">
              <span className="block text-[16px] font-bold">Tải lên kết quả xét nghiệm</span>
              <span className="block text-[13px] text-white/85">
                Chụp ảnh, tải tệp hoặc dán link — tự động đọc
              </span>
            </div>
          </div>
          <span aria-hidden="true" className="text-[20px]">
            →
          </span>
        </button>
      )}
      {flags && !flags.ocr && (
        <NeuCard className="!p-4">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-neu-muted">
              <Upload className="size-4" aria-hidden="true" />
              <span className="text-[15px]">Tải ảnh/PDF và tự động đọc kết quả</span>
            </div>
            <NeuBadge tone="watch" className="!text-[11px] !px-2.5 !py-0.5 before:!hidden">
              Sắp ra mắt
            </NeuBadge>
          </div>
        </NeuCard>
      )}

      {error && !loading && (
        <PatientErrorState title="Lỗi tải xét nghiệm" message={error} onRetry={load} />
      )}

      {loading && <LabsSkeleton />}

      {!loading && !error && results.length === 0 && (
        <PatientEmptyState
          icon={<FlaskConical />}
          title="Chưa có kết quả xét nghiệm"
          description="Nhập kết quả xét nghiệm của bạn để theo dõi theo thời gian."
          cta={{ label: 'Nhập kết quả', onClick: () => setModalOpen(true) }}
        />
      )}

      {!loading && !error && results.length > 0 && (
        <div className="space-y-3">
          {results.map((r) => (
            <ResultCard key={r.id} r={r} />
          ))}
        </div>
      )}

      {/* Manual entry — neu FAB (OCR card above is the primary upload path). */}
      <button
        type="button"
        aria-label="Nhập kết quả thủ công"
        onClick={() => setModalOpen(true)}
        className="fixed bottom-28 right-5 z-30 flex size-14 items-center justify-center rounded-full text-white neu-btn-primary !min-h-0 !p-0"
      >
        <Plus className="size-7" aria-hidden="true" />
      </button>

      <LabEntryModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onSaved={load}
        patientId={patientId}
      />
    </div>
  )
}
