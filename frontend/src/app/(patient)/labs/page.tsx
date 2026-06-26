'use client'

import { PatientEmptyState, LabEntryModal } from '@/components/patient'
import * as React from 'react'
import { useRouter } from 'next/navigation'
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
import { deleteLabBatch, getLabBatches, type LabUploadBatch } from '@/lib/api/patient'
import { useFeatureFlags } from '@/lib/api/features'
import { formatDate } from '@/lib/utils'
import { LabInsightSection } from '@/components/patient/LabInsightCards'

const HERO_GRADIENT = 'linear-gradient(160deg,#17AE7B,#0B6B4D)'

// ── Batch card ─────────────────────────────────────────────────────────────────

function BatchCard({
  batch,
  onDelete,
  isSelected,
  onToggleInsight,
}: {
  batch: LabUploadBatch
  onDelete: (id: string) => void
  isSelected: boolean
  onToggleInsight: (id: string) => void
}) {
  return (
    <NeuCard className="!p-4">
      <div className="flex items-start gap-3">
        <span
          className="grid size-10 shrink-0 place-items-center rounded-[12px] text-white"
          style={{ background: HERO_GRADIENT }}
          aria-hidden="true"
        >
          <FlaskConical className="size-[18px]" />
        </span>
        <div className="flex-1 min-w-0">
          <p className="text-[15px] font-semibold text-neu-text truncate">
            {batch.lab_name ?? 'Phòng xét nghiệm'}
          </p>
          {batch.test_date && (
            <div className="mt-0.5 flex items-center gap-1 text-[13px] text-neu-green">
              <CalendarDays className="size-3.5 shrink-0" aria-hidden="true" />
              {formatDate(batch.test_date)}
            </div>
          )}
          <p className="mt-0.5 text-[12px] text-neu-subtle">
            {batch.result_count} chỉ số · Tải lên {formatDate(batch.created_at)}
          </p>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <button
            type="button"
            aria-label={isSelected ? 'Thu gọn phân tích' : 'Xem phân tích AI'}
            onClick={() => onToggleInsight(batch.id)}
            className="flex items-center gap-1 rounded-[10px] bg-[rgba(11,127,91,0.1)] px-2.5 py-1.5 text-[12px] font-semibold text-neu-green"
          >
            <BarChart2 className="size-3.5" aria-hidden="true" />
            {isSelected ? (
              <ChevronUp className="size-3" aria-hidden="true" />
            ) : (
              <ChevronDown className="size-3" aria-hidden="true" />
            )}
          </button>
          <button
            type="button"
            aria-label="Xoá phiếu xét nghiệm"
            onClick={() => onDelete(batch.id)}
            className="shrink-0 rounded-md p-1.5 text-[#D92D20] hover:bg-[#f6dede]"
          >
            <Trash2 className="size-4" />
          </button>
        </div>
      </div>
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
          <p className="text-[16px] font-extrabold text-neu-text">Xoá phiếu xét nghiệm?</p>
          <p className="mt-1.5 text-[14px] text-neu-muted">
            Xóa phiếu xét nghiệm này sẽ xóa các chỉ số sức khỏe được tạo từ phiếu này. Bạn có chắc
            không?
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
  const flags = useFeatureFlags()

  const [batches, setBatches] = React.useState<LabUploadBatch[]>([])
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)
  const [modalOpen, setModalOpen] = React.useState(false)
  const [confirmDeleteId, setConfirmDeleteId] = React.useState<string | null>(null)
  const [deleting, setDeleting] = React.useState(false)
  const [selectedBatchId, setSelectedBatchId] = React.useState<string | null>(null)

  function handleToggleInsight(batchId: string) {
    setSelectedBatchId((prev) => (prev === batchId ? null : batchId))
  }

  const load = React.useCallback(() => {
    if (!patientId) {
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    getLabBatches(patientId, { limit: 100 })
      .then((res) => setBatches(res.items))
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
          <p className="text-[14px] font-bold text-[#8B6400]">Chưa có hồ sơ bệnh nhân</p>
          <p className="text-[13px] text-[#8B6400]/80 mt-1">
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
        <h1 className="px-1 text-[21px] font-extrabold tracking-[-0.02em] text-neu-text">
          Xét nghiệm
        </h1>

        {/* OCR upload — real CTA when the OCR flag is on; otherwise a "coming soon" hint. */}
        {flags && flags.ocr && (
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

        {!loading && !error && batches.length === 0 && (
          <PatientEmptyState
            icon={<FlaskConical />}
            title="Chưa có kết quả xét nghiệm"
            description="Nhập kết quả xét nghiệm của bạn để theo dõi theo thời gian."
            cta={{ label: 'Nhập kết quả', onClick: () => setModalOpen(true) }}
          />
        )}

        {!loading && !error && batches.length > 0 && (
          <div className="space-y-3">
            {batches.map((b) => (
              <React.Fragment key={b.id}>
                <BatchCard
                  batch={b}
                  onDelete={setConfirmDeleteId}
                  isSelected={selectedBatchId === b.id}
                  onToggleInsight={handleToggleInsight}
                />
                {selectedBatchId === b.id && patientId && (
                  <LabInsightSection patientId={patientId} batchId={b.id} />
                )}
              </React.Fragment>
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
    </>
  )
}
