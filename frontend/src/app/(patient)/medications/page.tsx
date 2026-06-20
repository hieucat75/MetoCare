'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import { Pill, Plus, Pencil, Trash2 } from 'lucide-react'
import {
  Alert,
  Button,
  Card,
  CardContent,
  EmptyState,
  ErrorState,
  FormField,
  Input,
  Modal,
  PageHeader,
  Skeleton,
  SkeletonText,
  Textarea,
} from '@/design-system'
import { useAuth } from '@/lib/auth/context'
import {
  getMedications,
  addMedication,
  updateMedication,
  deleteMedication,
  type Medication,
  type MedicationInput,
} from '@/lib/api/patient'
import { formatDate } from '@/lib/utils'

// ── Loading skeleton ───────────────────────────────────────────────────────────

function MedicationsSkeleton() {
  return (
    <div className="space-y-3">
      {[1, 2, 3].map((n) => (
        <Card key={n} variant="glass" padding="none">
          <CardContent className="p-4 space-y-3">
            <Skeleton width="55%" height="1rem" />
            <Skeleton width="40%" height="0.75rem" />
            <SkeletonText lines={1} />
          </CardContent>
        </Card>
      ))}
    </div>
  )
}

// ── Honest medication card — real fields only ──────────────────────────────────

function MedRow({
  med,
  onEdit,
  onDelete,
  onView,
}: {
  med: Medication
  onEdit: () => void
  onDelete: () => void
  onView: () => void
}) {
  const meta = [med.dose, med.frequency].filter(Boolean).join(' · ')
  return (
    <Card variant="glass" padding="none">
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-3">
          <button type="button" onClick={onView} className="min-w-0 text-left flex items-start gap-3 flex-1">
            <span className="flex items-center justify-center w-9 h-9 rounded-lg bg-mint-50 shrink-0">
              <Pill className="size-4 text-mint-600" aria-hidden="true" />
            </span>
            <span className="min-w-0">
              <span className="block text-body-md font-medium text-text truncate">{med.name}</span>
              {meta && <span className="block text-body-sm text-text-muted mt-0.5">{meta}</span>}
              {med.note && <span className="block text-body-sm text-text-muted mt-0.5 truncate">{med.note}</span>}
              <span className="block text-body-sm text-text-subtle mt-0.5">Thêm ngày {formatDate(med.created_at)}</span>
            </span>
          </button>
          <div className="flex items-center gap-1 shrink-0">
            <button
              type="button"
              onClick={onEdit}
              aria-label="Sửa thuốc"
              className="p-2 rounded-md text-text-muted hover:text-text hover:bg-secondary-50 transition-colors"
            >
              <Pencil className="size-4" />
            </button>
            <button
              type="button"
              onClick={onDelete}
              aria-label="Xoá thuốc"
              className="p-2 rounded-md text-danger hover:bg-danger-light transition-colors"
            >
              <Trash2 className="size-4" />
            </button>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

// ── Add / edit modal ───────────────────────────────────────────────────────────

interface MedModalProps {
  open: boolean
  onClose: () => void
  onSaved: () => void
  patientId: string
  editing: Medication | null
}

function MedModal({ open, onClose, onSaved, patientId, editing }: MedModalProps) {
  const [name, setName] = React.useState('')
  const [dose, setDose] = React.useState('')
  const [frequency, setFrequency] = React.useState('')
  const [note, setNote] = React.useState('')
  const [submitting, setSubmitting] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  // Sync form when the target medication changes / modal opens.
  React.useEffect(() => {
    if (open) {
      setName(editing?.name ?? '')
      setDose(editing?.dose ?? '')
      setFrequency(editing?.frequency ?? '')
      setNote(editing?.note ?? '')
      setError(null)
    }
  }, [open, editing])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim()) {
      setError('Vui lòng nhập tên thuốc.')
      return
    }
    setSubmitting(true)
    setError(null)
    const payload: MedicationInput = {
      name: name.trim(),
      dose: dose.trim() || null,
      frequency: frequency.trim() || null,
      note: note.trim() || null,
    }
    try {
      if (editing) {
        await updateMedication(patientId, editing.id, payload)
      } else {
        await addMedication(patientId, payload)
      }
      onSaved()
      onClose()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Lưu thất bại. Vui lòng thử lại.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      open={open}
      onOpenChange={(o) => !o && onClose()}
      title={editing ? 'Sửa thông tin thuốc' : 'Thêm thuốc'}
      footer={
        <>
          <Button variant="outline" size="sm" onClick={onClose} disabled={submitting}>
            Hủy
          </Button>
          <Button variant="mint" size="sm" type="submit" form="med-form" loading={submitting}>
            {editing ? 'Lưu' : 'Thêm'}
          </Button>
        </>
      }
    >
      <form id="med-form" onSubmit={handleSubmit} className="space-y-4">
        {error && <Alert variant="danger" title={error} />}
        <FormField label="Tên thuốc" required>
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="VD: Metformin" fullWidth required />
        </FormField>
        <FormField label="Liều dùng">
          <Input value={dose} onChange={(e) => setDose(e.target.value)} placeholder="VD: 500mg" fullWidth />
        </FormField>
        <FormField label="Tần suất">
          <Input value={frequency} onChange={(e) => setFrequency(e.target.value)} placeholder="VD: 2 lần/ngày, sáng & tối" fullWidth />
        </FormField>
        <FormField label="Ghi chú">
          <Textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="VD: Uống sau ăn" rows={2} />
        </FormField>
      </form>
    </Modal>
  )
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function MedicationsPage() {
  const router = useRouter()
  const { user } = useAuth()
  const patientId = user?.patient_profile_id

  const [meds, setMeds] = React.useState<Medication[]>([])
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)

  const [modalOpen, setModalOpen] = React.useState(false)
  const [editing, setEditing] = React.useState<Medication | null>(null)
  const [deleteTarget, setDeleteTarget] = React.useState<Medication | null>(null)
  const [deleting, setDeleting] = React.useState(false)

  const load = React.useCallback(() => {
    if (!patientId) {
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    getMedications(patientId, { limit: 50 })
      .then((res) => setMeds(res.items))
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [patientId])

  React.useEffect(() => {
    load()
  }, [load])

  async function confirmDelete() {
    if (!patientId || !deleteTarget) return
    setDeleting(true)
    try {
      await deleteMedication(patientId, deleteTarget.id)
      setDeleteTarget(null)
      load()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Xoá thất bại.')
    } finally {
      setDeleting(false)
    }
  }

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
        title="Thuốc & Điều trị"
        actions={
          <Button
            size="sm"
            variant="mint"
            onClick={() => {
              setEditing(null)
              setModalOpen(true)
            }}
          >
            <Plus className="size-4 mr-1" aria-hidden="true" /> Thêm thuốc
          </Button>
        }
      />

      {loading && <MedicationsSkeleton />}

      {!loading && error && (
        <ErrorState variant="inline" title="Không tải được danh sách thuốc" message={error} onRetry={load} />
      )}

      {!loading && !error && meds.length === 0 && (
        <EmptyState
          icon={<Pill />}
          title="Chưa có thuốc nào"
          description="Thêm thuốc bạn đang dùng để theo dõi, hoặc bác sĩ sẽ kê đơn khi cần."
        />
      )}

      {!loading && !error && meds.length > 0 && (
        <div className="space-y-3">
          {meds.map((med) => (
            <MedRow
              key={med.id}
              med={med}
              onView={() => router.push(`/medications/${med.id}`)}
              onEdit={() => {
                setEditing(med)
                setModalOpen(true)
              }}
              onDelete={() => setDeleteTarget(med)}
            />
          ))}
        </div>
      )}

      <MedModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onSaved={load}
        patientId={patientId}
        editing={editing}
      />

      {/* Delete confirm */}
      <Modal
        open={!!deleteTarget}
        onOpenChange={(o) => !o && setDeleteTarget(null)}
        title="Xoá thuốc?"
        footer={
          <>
            <Button variant="outline" size="sm" onClick={() => setDeleteTarget(null)} disabled={deleting}>
              Hủy
            </Button>
            <Button variant="danger" size="sm" onClick={confirmDelete} loading={deleting}>
              Xoá
            </Button>
          </>
        }
      >
        <p className="text-body-md text-text-muted">
          Bạn có chắc muốn xoá <span className="font-medium text-text">{deleteTarget?.name}</span> khỏi danh sách thuốc?
        </p>
      </Modal>
    </div>
  )
}
