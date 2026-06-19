'use client'

import * as React from 'react'
import { Bot, Stethoscope, FlaskConical, Plus } from 'lucide-react'
import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  ErrorState,
  EmptyState,
  PageHeader,
  Spinner,
  Skeleton,
  SkeletonText,
  Modal,
  FormField,
  Input,
  Select,
} from '@/design-system'
import { useAuth } from '@/lib/auth/context'
import {
  getLabs,
  type LabResult,
} from '@/lib/api/patient'
import { api } from '@/lib/api/client'

// ── Helpers ────────────────────────────────────────────────────────────────────

function formatDate(iso: string): string {
  return new Intl.DateTimeFormat('vi-VN', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(iso))
}

// ── Status badge mapping ───────────────────────────────────────────────────────

type BadgeVariant = 'pending_review' | 'approved' | 'rejected' | 'request_info'

function getLabStatusConfig(status: string): { variant: BadgeVariant; label: string } {
  const map: Record<string, { variant: BadgeVariant; label: string }> = {
    pending_review: { variant: 'pending_review', label: 'Chờ duyệt' },
    uploaded:       { variant: 'pending_review', label: 'Chờ xử lý' },
    approved:       { variant: 'approved',       label: 'Đã duyệt' },
    rejected:       { variant: 'rejected',       label: 'Từ chối' },
    request_info:   { variant: 'request_info',   label: 'Cần bổ sung' },
  }
  return map[status] ?? { variant: 'pending_review', label: status }
}

// ── Lab result card ────────────────────────────────────────────────────────────

function LabResultCard({ lab, index }: { lab: LabResult; index: number }) {
  const { variant, label } = getLabStatusConfig(lab.status)
  const displayName = lab.file_name ?? `Xét nghiệm ${index + 1}`

  return (
    <Card variant="elevated" padding="none">
      <CardContent className="p-4 space-y-3">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2 min-w-0">
            <FlaskConical className="size-4 shrink-0 text-text-muted" aria-hidden="true" />
            <span className="text-body-sm font-medium text-text truncate">{displayName}</span>
          </div>
          <Badge variant={variant} dot size="sm">{label}</Badge>
        </div>

        <p className="text-body-xs text-text-muted">
          Tải lên: {formatDate(lab.uploaded_at ?? lab.created_at ?? new Date().toISOString())}
        </p>

        {(lab.status === 'pending_review' || lab.status === 'uploaded') && (
          <div className="flex items-center gap-2 text-body-xs text-amber-700">
            <Spinner size="sm" color="muted" />
            <span>Chờ bác sĩ xem xét</span>
          </div>
        )}

        {lab.status === 'approved' && lab.ai_explanation && (
          <div className="rounded-md bg-amber-50 border border-amber-200 p-3 space-y-2">
            <div className="flex items-center gap-2">
              <Bot className="size-4 shrink-0 text-amber-600" aria-hidden="true" />
              <span className="text-body-sm font-semibold text-amber-800">Giải thích từ AI</span>
            </div>
            <p className="text-body-sm text-amber-900">{lab.ai_explanation}</p>
            <p className="text-body-xs text-amber-700 italic">
              Đây là giải thích từ AI, không phải chẩn đoán y tế.
            </p>
          </div>
        )}

        {lab.doctor_notes && lab.status === 'approved' && (
          <div className="rounded-md bg-green-50 border border-green-200 p-3 space-y-2">
            <div className="flex items-center gap-2">
              <Stethoscope className="size-4 shrink-0 text-green-700" aria-hidden="true" />
              <span className="text-body-sm font-semibold text-green-800">Ghi chú bác sĩ</span>
            </div>
            <p className="text-body-sm text-green-900">{lab.doctor_notes}</p>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ── Loading skeleton ───────────────────────────────────────────────────────────

function LabsSkeleton() {
  return (
    <div className="space-y-3">
      {[1, 2, 3].map((n) => (
        <Card key={n} variant="elevated" padding="none">
          <CardContent className="p-4 space-y-3">
            <div className="flex items-center justify-between">
              <Skeleton width="60%" height="1rem" />
              <Skeleton width="5rem" height="1.25rem" className="rounded-full" />
            </div>
            <Skeleton width="40%" height="0.75rem" />
            <SkeletonText lines={2} />
          </CardContent>
        </Card>
      ))}
    </div>
  )
}

// ── Add Lab Modal — simple form (backend accepts JSON, no binary upload in pilot) ──

const FILE_TYPE_OPTIONS = [
  { value: 'application/pdf', label: 'PDF' },
  { value: 'image/jpeg', label: 'Ảnh JPEG' },
  { value: 'image/png', label: 'Ảnh PNG' },
  { value: 'other', label: 'Khác' },
]

interface AddLabModalProps {
  open: boolean
  onClose: () => void
  onSuccess: (lab: LabResult) => void
  patientId: string
}

function AddLabModal({ open, onClose, onSuccess, patientId }: AddLabModalProps) {
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

  const handleClose = () => {
    reset()
    onClose()
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
      // Merge display-only fields absent from backend response
      onSuccess({
        ...result,
        file_name: labName.trim(),
        uploaded_at: new Date().toISOString(),
      })
      reset()
      onClose()
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : 'Gửi thất bại. Vui lòng thử lại.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      open={open}
      onOpenChange={(o) => !o && handleClose()}
      title="Thêm hồ sơ xét nghiệm"
      footer={
        <>
          <Button variant="outline" size="sm" onClick={handleClose} disabled={submitting}>
            Hủy
          </Button>
          <Button
            variant="primary"
            size="sm"
            type="submit"
            form="add-lab-form"
            loading={submitting}
          >
            Gửi
          </Button>
        </>
      }
    >
      <form id="add-lab-form" onSubmit={handleSubmit} className="space-y-4">
        {err && <Alert variant="danger" title={err} />}

        <Alert variant="info" title="Lưu ý">
          Trong phiên bản pilot, bác sĩ sẽ nhận hồ sơ và liên hệ bạn để xác nhận tài liệu.
          Tính năng upload trực tiếp sẽ có trong phiên bản tiếp theo.
        </Alert>

        <FormField label="Tên xét nghiệm" required>
          <Input
            value={labName}
            onChange={(e) => setLabName(e.target.value)}
            placeholder="VD: Xét nghiệm máu tổng quát"
            fullWidth
            required
          />
        </FormField>

        <FormField label="Loại tài liệu">
          <Select
            value={fileType}
            onValueChange={setFileType}
            options={FILE_TYPE_OPTIONS}
            fullWidth
          />
        </FormField>

        <FormField label="Ghi chú (tuỳ chọn)">
          <Input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Thông tin thêm cho bác sĩ"
            fullWidth
          />
        </FormField>
      </form>
    </Modal>
  )
}

// ── Page ───────────────────────────────────────────────────────────────────────

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
          <Button
            variant="primary"
            size="sm"
            onClick={() => setModalOpen(true)}
            leftIcon={<Plus className="size-4" aria-hidden="true" />}
          >
            Thêm mới
          </Button>
        }
      />

      {successMsg && (
        <Alert
          variant="success"
          title="Đã gửi thành công"
          dismissible
          onDismiss={() => setSuccessMsg(null)}
        >
          {successMsg}
        </Alert>
      )}

      {error && !loading && (
        <ErrorState variant="inline" title="Lỗi" message={error} onRetry={fetchLabs} />
      )}

      {loading && <LabsSkeleton />}

      {!loading && !error && labs.length === 0 && (
        <EmptyState
          icon={<FlaskConical />}
          title="Chưa có kết quả xét nghiệm"
          description="Gửi thông tin xét nghiệm để bác sĩ xem xét."
          action={{ label: 'Thêm ngay', onClick: () => setModalOpen(true) }}
        />
      )}

      {!loading && labs.length > 0 && (
        <div className="space-y-3">
          {labs.map((lab, index) => (
            <LabResultCard key={lab.id} lab={lab} index={index} />
          ))}
        </div>
      )}

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
