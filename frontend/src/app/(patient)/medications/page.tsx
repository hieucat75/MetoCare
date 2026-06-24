'use client'
import { PatientEmptyState } from '@/components/patient'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import { Pill, Plus, Pencil, Trash2 } from 'lucide-react'
import { Alert, Button, ErrorState, FormField, Input, Modal, Textarea } from '@/design-system'
import { useAuth } from '@/lib/auth/context'
import {
  getMedications,
  addMedication,
  updateMedication,
  deleteMedication,
  type Medication,
  type MedicationInput,
} from '@/lib/api/patient'

const PILL_GRADIENT = 'linear-gradient(160deg,#5B8DEF,#2563EB)'

// ── Loading skeleton ───────────────────────────────────────────────────────────

function MedicationsSkeleton() {
  return (
    <div className="space-y-3">
      {[1, 2, 3].map((n) => (
        <div key={n} className="neu-card mc-pulse p-4">
          <div className="flex gap-3">
            <div className="size-11 rounded-[13px] bg-black/5" />
            <div className="flex-1 space-y-2 pt-1">
              <div className="h-3.5 w-1/2 rounded-full bg-black/5" />
              <div className="h-3 w-1/3 rounded-full bg-black/5" />
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

// ── Honest medication card — real fields only (no faked adherence/schedule) ─────

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
    <div className="neu-card p-4">
      <div className="flex items-start gap-3">
        <button
          type="button"
          onClick={onView}
          className="flex min-w-0 flex-1 items-start gap-3 text-left"
        >
          <span
            className="grid size-11 shrink-0 place-items-center rounded-[13px] text-white"
            style={{ background: PILL_GRADIENT, boxShadow: '0 8px 16px -8px rgba(37,99,235,0.5)' }}
            aria-hidden="true"
          >
            <Pill className="size-5" />
          </span>
          <span className="min-w-0">
            <span className="block truncate text-[16px] font-bold text-neu-text">{med.name}</span>
            {meta && <span className="mt-0.5 block text-[13.5px] text-neu-muted">{meta}</span>}
            {med.note && (
              <span className="mt-0.5 block truncate text-[13px] text-neu-subtle">{med.note}</span>
            )}
          </span>
        </button>
        <div className="flex shrink-0 items-center gap-1">
          <button
            type="button"
            onClick={onEdit}
            aria-label="Sửa thuốc"
            className="rounded-[10px] p-2 text-neu-muted transition-transform active:scale-90"
          >
            <Pencil className="size-4" />
          </button>
          <button
            type="button"
            onClick={onDelete}
            aria-label="Xoá thuốc"
            className="rounded-[10px] p-2 text-[#D92D20] transition-transform active:scale-90"
          >
            <Trash2 className="size-4" />
          </button>
        </div>
      </div>
    </div>
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
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="VD: Metformin"
            fullWidth
            required
          />
        </FormField>
        <FormField label="Liều dùng">
          <Input
            value={dose}
            onChange={(e) => setDose(e.target.value)}
            placeholder="VD: 500mg"
            fullWidth
          />
        </FormField>
        <FormField label="Tần suất">
          <Input
            value={frequency}
            onChange={(e) => setFrequency(e.target.value)}
            placeholder="VD: 2 lần/ngày, sáng & tối"
            fullWidth
          />
        </FormField>
        <FormField label="Ghi chú">
          <Textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="VD: Uống sau ăn"
            rows={2}
          />
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
      <div className="p-4 max-w-md mx-auto mt-10">
        <Alert variant="warning" title="Chưa có hồ sơ bệnh nhân">
          Tài khoản của bạn chưa được liên kết với hồ sơ bệnh nhân. Vui lòng liên hệ hỗ trợ.
        </Alert>
      </div>
    )
  }

  return (
    <div className="p-4 space-y-4 max-w-md mx-auto pb-28">
      <h1 className="px-1 text-[21px] font-extrabold tracking-[-0.02em] text-neu-text">Thuốc</h1>

      {loading && <MedicationsSkeleton />}

      {!loading && error && (
        <ErrorState
          variant="inline"
          title="Không tải được danh sách thuốc"
          message={error}
          onRetry={load}
        />
      )}

      {!loading && !error && meds.length === 0 && (
        <PatientEmptyState
          icon={<Pill />}
          title="Chưa có thuốc nào"
          description="Thêm thuốc bạn đang dùng để theo dõi, hoặc bác sĩ sẽ kê đơn khi cần."
          cta={{
            label: 'Thêm thuốc',
            onClick: () => {
              setEditing(null)
              setModalOpen(true)
            },
          }}
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

      {/* Add medication — neu FAB */}
      <button
        type="button"
        aria-label="Thêm thuốc"
        onClick={() => {
          setEditing(null)
          setModalOpen(true)
        }}
        className="fixed bottom-28 right-5 z-30 flex size-14 items-center justify-center rounded-full text-white neu-btn-primary !min-h-0 !p-0"
      >
        <Plus className="size-7" aria-hidden="true" />
      </button>

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
            <Button
              variant="outline"
              size="sm"
              onClick={() => setDeleteTarget(null)}
              disabled={deleting}
            >
              Hủy
            </Button>
            <Button variant="danger" size="sm" onClick={confirmDelete} loading={deleting}>
              Xoá
            </Button>
          </>
        }
      >
        <p className="text-[16px] text-neu-muted">
          Bạn có chắc muốn xoá{' '}
          <span className="font-semibold text-neu-text">{deleteTarget?.name}</span> khỏi danh sách
          thuốc?
        </p>
      </Modal>
    </div>
  )
}
