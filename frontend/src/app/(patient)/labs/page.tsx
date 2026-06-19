'use client'

import * as React from 'react'
import { Sparkles, Stethoscope, FlaskConical, Plus, Clock } from 'lucide-react'
import { GlassCard } from '@/components/patient/glass'
import { PatientScreenHeader } from '@/components/patient/header'
import { PatientEmptyState, PatientErrorState, PatientSkeleton, DoctorApprovedBadge } from '@/components/patient/states'
import { GlassModal } from '@/components/patient/modal'
import { Field, MintFab } from '@/components/patient/forms'
import { useAuth } from '@/lib/auth/context'
import { getLabs, type LabResult } from '@/lib/api/patient'
import { api } from '@/lib/api/client'

function formatDate(iso: string): string {
  return new Intl.DateTimeFormat('vi-VN', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(iso))
}

const STATUS_CONFIG: Record<string, { color: string; bg: string; label: string }> = {
  pending_review: { color: '#c77a06', bg: 'rgba(252,239,201,0.9)', label: 'Chờ duyệt' },
  uploaded: { color: '#c77a06', bg: 'rgba(252,239,201,0.9)', label: 'Chờ xử lý' },
  approved: { color: '#15915a', bg: 'rgba(227,244,234,0.9)', label: 'Đã duyệt' },
  rejected: { color: '#d92d20', bg: 'rgba(251,231,229,0.9)', label: 'Từ chối' },
  request_info: { color: '#2563eb', bg: 'rgba(229,237,251,0.9)', label: 'Cần bổ sung' },
}

function LabResultCard({ lab, index }: { lab: LabResult; index: number }) {
  const cfg = STATUS_CONFIG[lab.status] ?? { color: '#c77a06', bg: 'rgba(252,239,201,0.9)', label: lab.status }
  const displayName = lab.file_name ?? `Xét nghiệm ${index + 1}`
  return (
    <GlassCard className="p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <FlaskConical className="size-4 shrink-0 text-[#566e66]" aria-hidden="true" />
          <span className="truncate text-[14px] font-semibold text-[#0e2a33]">{displayName}</span>
        </div>
        <span
          className="inline-flex shrink-0 items-center gap-1.5 rounded-md px-2 py-1 text-[11px] font-semibold"
          style={{ color: cfg.color, background: cfg.bg }}
        >
          <span className="size-1.5 rounded-full" style={{ background: cfg.color }} />
          {cfg.label}
        </span>
      </div>

      <p className="mt-2 text-[12px] text-[#566e66]">
        Tải lên: {formatDate(lab.uploaded_at ?? lab.created_at ?? new Date().toISOString())}
      </p>

      {(lab.status === 'pending_review' || lab.status === 'uploaded') && (
        <div className="mt-2 flex items-center gap-2 text-[12px] font-medium text-[#c77a06]">
          <Clock className="size-4" aria-hidden="true" />
          Chờ bác sĩ xem xét
        </div>
      )}

      {lab.status === 'approved' && lab.ai_explanation && (
        <div
          className="mt-3 rounded-[12px] border border-[rgba(216,201,246,0.7)] bg-[rgba(243,238,251,0.6)] p-3"
          style={{ borderLeft: '3px solid rgba(109,63,190,0.5)' }}
        >
          <div className="mb-1.5 flex items-center gap-2">
            <Sparkles className="size-4 shrink-0 text-[#6d3fbe]" aria-hidden="true" />
            <span className="text-[13px] font-bold text-[#6d3fbe]">Giải thích từ AI</span>
          </div>
          <p className="text-[13px] leading-relaxed text-[#244744]">{lab.ai_explanation}</p>
          <p className="mt-1.5 text-[11.5px] italic text-[#6d3fbe]">Đây là giải thích từ AI, không phải chẩn đoán y tế.</p>
        </div>
      )}

      {lab.doctor_notes && lab.status === 'approved' && (
        <div className="mt-3 rounded-[12px] border border-[rgba(134,242,204,0.7)] bg-[rgba(227,244,234,0.6)] p-3">
          <div className="mb-1.5 flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <Stethoscope className="size-4 shrink-0 text-[#15915a]" aria-hidden="true" />
              <span className="text-[13px] font-bold text-[#15915a]">Ghi chú bác sĩ</span>
            </div>
            <DoctorApprovedBadge />
          </div>
          <p className="text-[13px] leading-relaxed text-[#244744]">{lab.doctor_notes}</p>
        </div>
      )}
    </GlassCard>
  )
}

const FILE_TYPE_OPTIONS = [
  { value: 'application/pdf', label: 'PDF' },
  { value: 'image/jpeg', label: 'Ảnh JPEG' },
  { value: 'image/png', label: 'Ảnh PNG' },
  { value: 'other', label: 'Khác' },
]

function AddLabModal({
  open,
  onClose,
  onSuccess,
  patientId,
}: {
  open: boolean
  onClose: () => void
  onSuccess: (lab: LabResult) => void
  patientId: string
}) {
  const [labName, setLabName] = React.useState('')
  const [fileType, setFileType] = React.useState('application/pdf')
  const [note, setNote] = React.useState('')
  const [submitting, setSubmitting] = React.useState(false)
  const [err, setErr] = React.useState<string | null>(null)

  const reset = () => {
    setLabName('')
    setFileType('application/pdf')
    setNote('')
    setErr(null)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!labName.trim()) {
      setErr('Vui lòng nhập tên xét nghiệm')
      return
    }
    setSubmitting(true)
    setErr(null)
    try {
      const storageKey = `pilot/manual/${Date.now()}_${labName.trim().replace(/\s+/g, '_')}`
      const result = await api.post<LabResult>(`/patients/${patientId}/lab-documents`, {
        storage_key: storageKey,
        file_type: fileType,
        lab_name: labName.trim(),
        ...(note.trim() ? { note: note.trim() } : {}),
      })
      onSuccess({ ...result, file_name: labName.trim(), uploaded_at: new Date().toISOString() })
      reset()
      onClose()
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : 'Gửi thất bại. Vui lòng thử lại.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <GlassModal
      open={open}
      onOpenChange={(o) => {
        if (!o) {
          reset()
          onClose()
        }
      }}
      title="Thêm hồ sơ xét nghiệm"
      footer={
        <>
          <button
            type="button"
            className="mc-btn-glass flex-1"
            onClick={() => {
              reset()
              onClose()
            }}
            disabled={submitting}
          >
            Huỷ
          </button>
          <button type="submit" form="add-lab-form" className="mc-btn flex-1" disabled={submitting}>
            {submitting ? 'Đang gửi…' : 'Gửi'}
          </button>
        </>
      }
    >
      <form id="add-lab-form" onSubmit={handleSubmit} className="space-y-4">
        {err && (
          <p className="rounded-xl bg-[rgba(251,231,229,0.8)] px-4 py-3 text-[14px] font-medium text-[#b3261e]">{err}</p>
        )}
        <p className="rounded-xl border border-[rgba(37,99,235,0.2)] bg-[rgba(229,237,251,0.6)] px-4 py-3 text-[13px] leading-relaxed text-[#2563eb]">
          Trong bản thử nghiệm, bác sĩ sẽ nhận hồ sơ và liên hệ bạn để xác nhận tài liệu. Tính năng tải file trực tiếp sẽ có ở phiên bản tiếp theo.
        </p>
        <Field label="Tên xét nghiệm">
          <input className="mc-input" value={labName} onChange={(e) => setLabName(e.target.value)} placeholder="VD: Xét nghiệm máu tổng quát" required />
        </Field>
        <Field label="Loại tài liệu">
          <select className="mc-input" value={fileType} onChange={(e) => setFileType(e.target.value)}>
            {FILE_TYPE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Ghi chú (tuỳ chọn)">
          <input className="mc-input" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Thông tin thêm cho bác sĩ" />
        </Field>
      </form>
    </GlassModal>
  )
}

export default function LabsPage() {
  const { user } = useAuth()
  const patientId = user?.patient_profile_id

  const [labs, setLabs] = React.useState<LabResult[]>([])
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)
  const [modalOpen, setModalOpen] = React.useState(false)
  const [successMsg, setSuccessMsg] = React.useState<string | null>(null)

  const fetchLabs = React.useCallback(async () => {
    if (!patientId) return
    setLoading(true)
    setError(null)
    try {
      const res = await getLabs(patientId, { limit: 20 })
      setLabs(res.items)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không tải được kết quả xét nghiệm.')
    } finally {
      setLoading(false)
    }
  }, [patientId])

  React.useEffect(() => {
    fetchLabs()
  }, [fetchLabs])

  if (!patientId) {
    return (
      <div className="pt-2">
        <PatientScreenHeader title="Kết quả xét nghiệm" />
        <PatientEmptyState icon={FlaskConical} title="Chưa có hồ sơ bệnh nhân" description="Vui lòng liên hệ hỗ trợ." className="mt-3" />
      </div>
    )
  }

  return (
    <div className="pt-2">
      <PatientScreenHeader
        title="Kết quả xét nghiệm"
        subtitle="Gửi & xem kết quả đã duyệt"
        action={
          <MintFab label="Thêm hồ sơ xét nghiệm" onClick={() => setModalOpen(true)}>
            <Plus className="size-5 text-white" aria-hidden="true" />
          </MintFab>
        }
      />

      <div className="mt-3 space-y-3">
        {successMsg && (
          <div className="rounded-xl border border-[rgba(21,145,90,0.25)] bg-[rgba(227,244,234,0.7)] px-4 py-3 text-[14px] font-medium text-[#15915a]">
            {successMsg}
          </div>
        )}

        {loading && (
          <>
            <PatientSkeleton />
            <PatientSkeleton />
          </>
        )}

        {!loading && error && <PatientErrorState title="Không tải được xét nghiệm" message={error} onRetry={fetchLabs} />}

        {!loading && !error && labs.length === 0 && (
          <PatientEmptyState
            icon={FlaskConical}
            title="Chưa có kết quả xét nghiệm"
            description="Gửi thông tin xét nghiệm để bác sĩ xem xét."
            actionLabel="Thêm ngay"
            onAction={() => setModalOpen(true)}
          />
        )}

        {!loading && labs.map((lab, index) => <LabResultCard key={lab.id} lab={lab} index={index} />)}
      </div>

      <AddLabModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onSuccess={(lab) => {
          setLabs((prev) => [lab, ...prev])
          setSuccessMsg(`Đã gửi "${lab.file_name ?? 'xét nghiệm'}". Bác sĩ sẽ xem xét sớm.`)
        }}
        patientId={patientId}
      />
    </div>
  )
}
