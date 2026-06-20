'use client'

import { PatientEmptyState, LabEntryModal } from '@/components/patient'
import * as React from 'react'
import { useRouter } from 'next/navigation'
import { CalendarDays, FlaskConical, Plus, Upload } from 'lucide-react'
import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  ErrorState,
  PageHeader,
  Skeleton,
  SkeletonText,
} from '@/design-system'
import { useAuth } from '@/lib/auth/context'
import { getLabResults, type LabResultEntry } from '@/lib/api/patient'
import { useFeatureFlags } from '@/lib/api/features'
import { formatDate } from '@/lib/utils'

// ── Result card ────────────────────────────────────────────────────────────────

function ResultCard({ r }: { r: LabResultEntry }) {
  const valueStr =
    r.value != null ? `${r.value}${r.unit ? ` ${r.unit}` : ''}` : '—'
  return (
    <Card variant="glass" padding="none">
      <CardContent className="p-4">
        {/* Exam date — prominent (the real test date, not the upload date). */}
        <div className="flex items-center gap-1.5 text-[15px] font-semibold text-mint-700 mb-1.5">
          <CalendarDays className="size-4 shrink-0" aria-hidden="true" />
          {r.test_date ? formatDate(r.test_date) : 'Chưa có ngày xét nghiệm'}
        </div>
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2 min-w-0">
            <FlaskConical className="size-4 shrink-0 text-text-muted" aria-hidden="true" />
            <span className="text-[17px] font-medium text-text truncate">{r.test_name}</span>
          </div>
          <span className="text-[18px] font-bold text-text shrink-0">{valueStr}</span>
        </div>
        <div className="flex items-center justify-between mt-1 pl-6">
          <span className="text-[15px] text-text-muted">
            {r.reference_range ? `Tham chiếu: ${r.reference_range}` : ''}
          </span>
          {/* Upload date — muted, clearly distinct from the exam date. */}
          <span className="text-[13px] text-text-subtle">Tải lên {formatDate(r.created_at)}</span>
        </div>
        {r.verified_by_user && (
          <div className="mt-2 pl-6">
            <Badge variant="default" size="sm">Tự nhập</Badge>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function LabsSkeleton() {
  return (
    <div className="space-y-3">
      {[1, 2, 3].map((n) => (
        <Card key={n} variant="glass" padding="none">
          <CardContent className="p-4 space-y-3">
            <Skeleton width="50%" height="1rem" />
            <SkeletonText lines={1} />
          </CardContent>
        </Card>
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
      <div className="p-4 lg:p-6 max-w-2xl mx-auto">
        <Alert variant="warning" title="Chưa có hồ sơ bệnh nhân">
          Tài khoản của bạn chưa được liên kết với hồ sơ bệnh nhân. Vui lòng liên hệ hỗ trợ.
        </Alert>
      </div>
    )
  }

  return (
    <div className="p-4 lg:p-6 space-y-4 max-w-2xl mx-auto pb-24">
      <PageHeader
        title="Kết quả xét nghiệm"
        actions={
          <Button variant="mint" size="sm" onClick={() => setModalOpen(true)}>
            <Plus className="size-4 mr-1" aria-hidden="true" /> Nhập kết quả
          </Button>
        }
      />

      {/* OCR upload — real CTA when the OCR flag is on; otherwise a "coming soon" hint. */}
      {flags && flags.ocr && (
        <button
          type="button"
          onClick={() => router.push('/labs/upload')}
          className="w-full text-left rounded-2xl bg-mint-500 text-white px-4 py-4 shadow-glow-mint hover:bg-mint-600 transition-colors flex items-center justify-between gap-3"
        >
          <div className="flex items-center gap-3 min-w-0">
            <span className="flex items-center justify-center size-11 rounded-xl bg-white/20 shrink-0">
              <Upload className="size-5" aria-hidden="true" />
            </span>
            <div className="min-w-0">
              <span className="block text-[17px] font-semibold">Tải lên kết quả xét nghiệm</span>
              <span className="block text-[14px] text-white/85">Chụp ảnh, tải tệp hoặc dán link — tự động đọc</span>
            </div>
          </div>
          <span aria-hidden="true" className="text-[20px]">→</span>
        </button>
      )}
      {flags && !flags.ocr && (
        <Card variant="glass" padding="md">
          <CardContent className="flex items-center justify-between gap-3 py-1">
            <div className="flex items-center gap-2 text-text-muted">
              <Upload className="size-4" aria-hidden="true" />
              <span className="text-[17px]">Tải ảnh/PDF và tự động đọc kết quả</span>
            </div>
            <Badge variant="default" size="sm">Sắp ra mắt</Badge>
          </CardContent>
        </Card>
      )}

      {error && !loading && (
        <ErrorState variant="inline" title="Lỗi" message={error} onRetry={load} />
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

      <LabEntryModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onSaved={load}
        patientId={patientId}
      />
    </div>
  )
}
