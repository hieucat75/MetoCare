'use client'

import { LabEntryModal } from '@/components/patient'
import * as React from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import {
  BarChart2,
  CalendarDays,
  ChevronDown,
  ChevronUp,
  FlaskConical,
  Plus,
  Trash2,
  Upload,
} from 'lucide-react'
import { PatientErrorState } from '@/components/patient/states'
import { NeuCard, NeuBadge, NeuButton } from '@/components/patient/neu'
import { useAuth } from '@/lib/auth/context'
import {
  deleteLabBatch,
  getBatchResults,
  getLabBatches,
  type LabUploadBatch,
  type LabResultEntry,
} from '@/lib/api/patient'
import { formatDate } from '@/lib/utils'
import { LabResultRow } from '@/components/patient/LabResultRow'

const HERO_GRADIENT = 'linear-gradient(160deg,#17AE7B,#0B6B4D)'

// ── Batch card ─────────────────────────────────────────────────────────────────

function BatchCard({
  batch,
  patientId,
  onDelete,
  isExpanded,
  onToggleExpand,
}: {
  batch: LabUploadBatch
  patientId: string
  onDelete: (id: string) => void
  isExpanded: boolean
  onToggleExpand: (id: string) => void
}) {
  const router = useRouter()

  // Per-batch results state — fetched lazily on first expand
  const [results, setResults] = React.useState<LabResultEntry[] | null>(null)
  const [resultsLoading, setResultsLoading] = React.useState(false)
  const [resultsError, setResultsError] = React.useState<string | null>(null)

  const loadResults = React.useCallback(() => {
    setResultsLoading(true)
    setResultsError(null)
    getBatchResults(patientId, batch.id)
      .then((res) => setResults(res.items))
      .catch((err: Error) => setResultsError(err.message ?? 'Lỗi tải chỉ số'))
      .finally(() => setResultsLoading(false))
  }, [patientId, batch.id])

  // Fetch on first expand
  React.useEffect(() => {
    if (isExpanded && results === null && !resultsLoading) {
      loadResults()
    }
  }, [isExpanded, results, resultsLoading, loadResults])

  return (
    <NeuCard className="!p-0 overflow-hidden">
      {/* Card header */}
      <div className="p-4">
        <div className="flex items-start gap-3">
          <span
            className="grid size-11 shrink-0 place-items-center rounded-[12px] text-white"
            style={{ background: HERO_GRADIENT }}
            aria-hidden="true"
          >
            <FlaskConical className="size-5" />
          </span>

          <div className="flex-1 min-w-0">
            {/* Hospital name — large */}
            <p
              className="font-bold text-neu-text leading-snug"
              style={{ fontSize: '18px' }}
            >
              {batch.lab_name ?? 'Phòng xét nghiệm'}
            </p>
            {/* Test date — large, green */}
            {batch.test_date && (
              <div
                className="mt-1 flex items-center gap-1.5 text-neu-green font-medium"
                style={{ fontSize: '16px' }}
              >
                <CalendarDays className="size-4 shrink-0" aria-hidden="true" />
                {formatDate(batch.test_date)}
              </div>
            )}
            {/* Upload date + count — smaller, muted */}
            <div className="mt-1 flex items-center gap-2">
              <NeuBadge tone="ok" className="!text-[12px]">
                {batch.result_count} chỉ số
              </NeuBadge>
              <p className="text-[12px] text-neu-muted">
                Tải lên {formatDate(batch.created_at)}
              </p>
            </div>
          </div>

          {/* Action buttons */}
          <div className="flex flex-col items-end gap-2 shrink-0">
            {/* Delete */}
            <button
              type="button"
              aria-label="Xoá phiếu xét nghiệm"
              onClick={() => onDelete(batch.id)}
              className="rounded-md p-1.5 text-[#D92D20] hover:bg-[rgba(217,45,32,0.1)]"
            >
              <Trash2 className="size-4" />
            </button>
            {/* Expand/collapse */}
            <button
              type="button"
              aria-label={isExpanded ? 'Thu gọn chỉ số' : 'Xem chỉ số'}
              aria-expanded={isExpanded}
              onClick={() => onToggleExpand(batch.id)}
              className="flex items-center gap-1 rounded-[10px] bg-[rgba(11,127,91,0.1)] px-2.5 py-1.5 text-[12px] font-semibold text-neu-green"
            >
              {isExpanded ? (
                <ChevronUp className="size-4" aria-hidden="true" />
              ) : (
                <ChevronDown className="size-4" aria-hidden="true" />
              )}
            </button>
          </div>
        </div>

      </div>

      {/* Expanded biomarker rows */}
      {isExpanded && (
        <div className="border-t border-black/[0.06]">
          {resultsLoading && (
            <p className="px-4 py-4 text-[15px] text-neu-muted text-center" aria-live="polite">
              Đang tải chỉ số...
            </p>
          )}
          {!resultsLoading && resultsError && (
            <div className="px-4 py-4 text-center space-y-2">
              <p className="text-[14px] text-[#D92D20]">{resultsError}</p>
              <button
                type="button"
                onClick={loadResults}
                className="text-[13px] font-semibold text-neu-green underline"
              >
                Thử lại
              </button>
            </div>
          )}
          {!resultsLoading && !resultsError && results !== null && results.length === 0 && (
            <p className="px-4 py-4 text-[15px] text-neu-muted text-center">
              Không có kết quả
            </p>
          )}
          {!resultsLoading && !resultsError && results !== null && results.length > 0 && (
            <div className="divide-y divide-black/[0.05]">
              {results.map((r) => (
                <LabResultRow
                  key={r.id}
                  result={r}
                  batchId={batch.id}
                  onNavigate={(bId, rId) => router.push(`/labs/${bId}/results/${rId}`)}
                />
              ))}
            </div>
          )}
          {/* AI insight CTA — secondary outline button at bottom of batch */}
          <div className="px-4 pb-4 pt-3 border-t border-black/[0.05]">
            <button
              type="button"
              onClick={() => router.push(`/labs/${batch.id}/insight`)}
              className="flex w-full items-center justify-center gap-2 rounded-[12px] border-2 border-neu-green bg-transparent py-3 text-[15px] font-semibold text-neu-green hover:bg-[rgba(11,107,77,0.06)] transition-colors"
              aria-label="Xem AI nhận định tổng thể cho phiếu này"
            >
              <BarChart2 className="size-4" aria-hidden="true" />
              Xem AI nhận định tổng thể →
            </button>
          </div>
        </div>
      )}
    </NeuCard>
  )
}

// ── Skeleton ───────────────────────────────────────────────────────────────────

function LabsSkeleton() {
  return (
    <div className="space-y-3">
      {[1, 2, 3].map((n) => (
        <div key={n} className="neu-card mc-pulse p-4">
          <div className="h-4 w-2/5 rounded-full bg-black/5" />
          <div className="mt-3 h-5 w-3/5 rounded-full bg-black/5" />
          <div className="mt-2 h-3 w-1/3 rounded-full bg-black/5" />
        </div>
      ))}
    </div>
  )
}

// ── Delete confirm modal ───────────────────────────────────────────────────────

function DeleteBatchModal({
  onConfirm,
  onCancel,
  deleting,
}: {
  onConfirm: () => void
  onCancel: () => void
  deleting: boolean
}) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Xác nhận xoá phiếu"
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 px-4 pb-8"
    >
      <div className="w-full max-w-md rounded-[20px] bg-white p-6 space-y-4 shadow-2xl">
        <div>
          <p className="text-[18px] font-extrabold text-neu-text">Xoá phiếu xét nghiệm?</p>
          <p className="mt-1.5 text-[15px] text-neu-muted">
            Xóa phiếu xét nghiệm này sẽ xóa các chỉ số sức khỏe được tạo từ phiếu này. Bạn có
            chắc không?
          </p>
        </div>
        <div className="flex gap-2.5">
          <NeuButton variant="secondary" onClick={onCancel} disabled={deleting} className="flex-1">
            Huỷ
          </NeuButton>
          <button
            type="button"
            onClick={onConfirm}
            disabled={deleting}
            className="flex-1 rounded-[14px] bg-[#D92D20] py-3 text-[15px] font-bold text-white disabled:opacity-50"
          >
            {deleting ? 'Đang xoá...' : 'Xoá'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function LabsPage() {
  const router = useRouter()
  const { user } = useAuth()
  const patientId = user?.patient_profile_id
  const [batches, setBatches] = React.useState<LabUploadBatch[]>([])
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)
  const [modalOpen, setModalOpen] = React.useState(false)
  const [confirmDeleteId, setConfirmDeleteId] = React.useState<string | null>(null)
  const [deleting, setDeleting] = React.useState(false)
  const [expandedBatchId, setExpandedBatchId] = React.useState<string | null>(null)

  function handleToggleExpand(batchId: string) {
    setExpandedBatchId((prev) => (prev === batchId ? null : batchId))
  }

  const load = React.useCallback(() => {
    if (!patientId) {
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    getLabBatches(patientId, { limit: 100 })
      .then((batchRes) => {
        setBatches(batchRes.items)
        // Auto-expand the latest batch (first item, sorted descending by backend)
        if (batchRes.items.length > 0) {
          setExpandedBatchId((prev) => prev ?? batchRes.items[0].id)
        }
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [patientId])

  React.useEffect(() => {
    load()
  }, [load])

  async function handleDeleteConfirm() {
    if (!patientId || !confirmDeleteId) return
    setDeleting(true)
    try {
      await deleteLabBatch(patientId, confirmDeleteId)
      setConfirmDeleteId(null)
      if (expandedBatchId === confirmDeleteId) setExpandedBatchId(null)
      load()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Xoá thất bại. Vui lòng thử lại.')
      setConfirmDeleteId(null)
    } finally {
      setDeleting(false)
    }
  }

  if (!patientId) {
    return (
      <div className="p-4 lg:p-6 max-w-md mx-auto mt-10">
        <div role="alert" className="rounded-[14px] bg-[#FEF9EC] border border-[#E0A92E]/30 p-4">
          <p className="text-[16px] font-bold text-[#8B6400]">Chưa có hồ sơ bệnh nhân</p>
          <p className="text-[14px] text-[#8B6400]/80 mt-1">
            Tài khoản của bạn chưa được liên kết với hồ sơ bệnh nhân. Vui lòng liên hệ hỗ trợ.
          </p>
        </div>
      </div>
    )
  }

  return (
    <>
      {confirmDeleteId && (
        <DeleteBatchModal
          onConfirm={handleDeleteConfirm}
          onCancel={() => setConfirmDeleteId(null)}
          deleting={deleting}
        />
      )}

      <div className="p-4 space-y-4 max-w-md mx-auto pb-28">
        <h1 className="px-1 text-[24px] font-extrabold tracking-[-0.02em] text-neu-text">
          Xét nghiệm
        </h1>

        {/* OCR upload — primary entry point, always available. */}
        <button
          type="button"
          onClick={() => router.push('/labs/upload')}
          className="flex w-full items-center justify-between gap-3 rounded-[20px] px-5 py-4 text-left text-white"
          style={{
            background: HERO_GRADIENT,
            boxShadow: '0 14px 26px -12px rgba(11,107,77,0.6)',
          }}
        >
          <div className="flex min-w-0 items-center gap-3">
            <span className="grid size-11 shrink-0 place-items-center rounded-[14px] bg-white/20">
              <Upload className="size-5" aria-hidden="true" />
            </span>
            <div className="min-w-0">
              <span className="block text-[17px] font-bold">Đọc kết quả xét nghiệm bằng AI</span>
              <span className="block text-[13px] text-white/80 mt-0.5">
                Chụp ảnh · Tải ảnh/PDF · Dán link kết quả
              </span>
            </div>
          </div>
          <span aria-hidden="true" className="text-[20px] shrink-0">
            →
          </span>
        </button>

        {error && !loading && (
          <PatientErrorState title="Lỗi tải xét nghiệm" message={error} onRetry={load} />
        )}

        {loading && <LabsSkeleton />}

        {!loading && !error && batches.length === 0 && (
          <div className="space-y-2.5">
            <NeuCard className="!p-5 text-center">
              <div className="mx-auto mb-3 grid size-[52px] place-items-center rounded-[16px] bg-[rgba(23,174,123,0.1)]">
                <FlaskConical className="size-6 text-neu-green" aria-hidden="true" />
              </div>
              <p className="text-[16px] font-bold text-neu-text">Chưa có kết quả xét nghiệm</p>
              <p className="mt-1.5 text-[14px] text-neu-muted leading-relaxed">
                Dùng AI để tự động đọc phiếu xét nghiệm, hoặc nhập tay từng chỉ số.
              </p>
              <button
                type="button"
                onClick={() => router.push('/labs/upload')}
                className="mt-4 flex w-full items-center justify-center gap-2 rounded-[14px] py-3 text-[15px] font-bold text-white"
                style={{ background: HERO_GRADIENT }}
              >
                <Upload className="size-4" aria-hidden="true" />
                Đọc kết quả xét nghiệm bằng AI
              </button>
              <button
                type="button"
                onClick={() => setModalOpen(true)}
                className="mt-2.5 flex w-full items-center justify-center gap-2 rounded-[14px] border border-[rgba(16,48,44,0.12)] py-3 text-[14px] font-semibold text-neu-text hover:bg-gray-50 transition-colors"
              >
                <Plus className="size-4 text-neu-green" aria-hidden="true" />
                Nhập thủ công
              </button>
            </NeuCard>
          </div>
        )}

        {!loading && !error && batches.length > 0 && (
          <div className="space-y-3">
            {batches.map((b) => (
              <BatchCard
                key={b.id}
                batch={b}
                patientId={patientId}
                onDelete={setConfirmDeleteId}
                isExpanded={expandedBatchId === b.id}
                onToggleExpand={handleToggleExpand}
              />
            ))}
          </div>
        )}

        {/* Health Timeline entry point */}
        <Link href="/health-story/timeline" className="block">
          <NeuCard className="!p-4 hover:opacity-90 transition-opacity">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <span
                  className="grid size-11 shrink-0 place-items-center rounded-[14px] text-[22px]"
                  style={{ background: 'rgba(23,174,123,0.12)' }}
                  aria-hidden="true"
                >
                  📅
                </span>
                <div>
                  <p className="text-[15px] font-bold text-neu-text">Lịch sử sức khỏe của tôi</p>
                  <p className="text-[13px] text-neu-muted">
                    Xem toàn bộ diễn biến sức khỏe theo thời gian
                  </p>
                </div>
              </div>
              <span className="text-[18px] text-neu-muted" aria-hidden="true">
                →
              </span>
            </div>
          </NeuCard>
        </Link>

        {/* Manual entry — FAB */}
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
    </>
  )
}
