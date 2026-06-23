'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import { Pill, Plus, Pencil, Trash2, Check, Sunrise, Sun, Moon, Clock } from 'lucide-react'
import { Alert, Button, ErrorState, FormField, Input, Modal, Textarea } from '@/design-system'
import { GlassCard, PatientEmptyState, SectionHeader, MintButton } from '@/components/patient'
import { useAuth } from '@/lib/auth/context'
import {
  getMedications,
  addMedication,
  updateMedication,
  deleteMedication,
  type Medication,
  type MedicationInput,
} from '@/lib/api/patient'
import { cn, formatDate } from '@/lib/utils'

// ─── Time-of-day grouping (visual schedule, derived from free-text frequency) ──
// The backend has NO structured schedule field — we infer a time-of-day bucket
// from the Vietnamese `frequency`/`note` text purely for visual grouping. This
// is presentation only; it never changes or persists any data.

type SlotKey = 'morning' | 'noon' | 'evening' | 'anytime'

interface Slot {
  key: SlotKey
  label: string
  hint: string
  icon: React.ReactNode
}

const SLOTS: Slot[] = [
  {
    key: 'morning',
    label: 'Buổi sáng',
    hint: 'Sau khi thức dậy / sau ăn sáng',
    icon: <Sunrise className="size-5" aria-hidden="true" />,
  },
  {
    key: 'noon',
    label: 'Buổi trưa',
    hint: 'Sau ăn trưa',
    icon: <Sun className="size-5" aria-hidden="true" />,
  },
  {
    key: 'evening',
    label: 'Buổi tối',
    hint: 'Sau ăn tối / trước khi ngủ',
    icon: <Moon className="size-5" aria-hidden="true" />,
  },
  {
    key: 'anytime',
    label: 'Khác / theo chỉ định',
    hint: 'Theo hướng dẫn của bác sĩ',
    icon: <Clock className="size-5" aria-hidden="true" />,
  },
]

const SLOT_BY_KEY: Record<SlotKey, Slot> = SLOTS.reduce(
  (acc, s) => ({ ...acc, [s.key]: s }),
  {} as Record<SlotKey, Slot>
)

/** Infer a visual time-of-day slot from free-text frequency/note (best-effort).
 *  Only commit to a specific slot when EXACTLY ONE time-of-day term is present.
 *  Multi-dose text ("sáng & tối", "sáng, chiều") or no match → "anytime", so a
 *  twice-daily med is never mislabeled as morning-only. Presentation only. */
function inferSlot(med: Medication): SlotKey {
  const text = `${med.frequency ?? ''} ${med.note ?? ''}`.toLowerCase()
  const matches: SlotKey[] = []
  if (/sáng|buổi sáng|morning/.test(text)) matches.push('morning')
  if (/trưa|buổi trưa|noon/.test(text)) matches.push('noon')
  if (/tối|chiều|đêm|buổi tối|trước khi ngủ|evening|night/.test(text)) matches.push('evening')
  return matches.length === 1 ? matches[0] : 'anytime'
}

// ─── Loading skeleton ──────────────────────────────────────────────────────────

function MedicationsSkeleton() {
  return (
    <div className="space-y-3">
      {[1, 2, 3].map((n) => (
        <GlassCard key={n}>
          <div className="flex items-center gap-3">
            <div className="size-11 shrink-0 animate-pulse rounded-2xl bg-mint-100/70" />
            <div className="flex-1 space-y-2">
              <div className="h-4 w-1/2 animate-pulse rounded bg-mint-100/70" />
              <div className="h-3 w-1/3 animate-pulse rounded bg-mint-100/60" />
            </div>
          </div>
        </GlassCard>
      ))}
    </div>
  )
}

// ─── Medication row — real fields only, decision-first ─────────────────────────

function MedRow({
  med,
  taken,
  onToggleTaken,
  onView,
}: {
  med: Medication
  taken: boolean
  onToggleTaken: () => void
  onView: () => void
}) {
  const meta = [med.dose, med.frequency].filter(Boolean).join(' · ')
  return (
    <div
      className={cn(
        'flex items-center gap-3 rounded-3xl border border-white/70 bg-white/85 p-3.5 shadow-glass ring-1 ring-mint-100/50 backdrop-blur-xl transition-colors',
        taken && 'bg-mint-50/70'
      )}
    >
      <button
        type="button"
        onClick={onView}
        className="flex min-w-0 flex-1 items-center gap-3 text-left"
        aria-label={`Xem chi tiết ${med.name}`}
      >
        <span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-mint-50 text-mint-600">
          <Pill className="size-5" aria-hidden="true" />
        </span>
        <span className="min-w-0 flex-1">
          <span
            className={cn(
              'block truncate text-[17px] font-medium text-text',
              taken && 'text-text-muted line-through'
            )}
          >
            {med.name}
          </span>
          {meta && <span className="block truncate text-[14px] text-text-muted">{meta}</span>}
          {med.note && (
            <span className="block truncate text-[14px] text-text-subtle">{med.note}</span>
          )}
        </span>
      </button>

      {/* Local-only "Đã uống" affordance. NO adherence persistence exists.
          TODO(backend): adherence API to persist mark-taken per dose/day. */}
      <button
        type="button"
        onClick={onToggleTaken}
        aria-pressed={taken}
        aria-label={taken ? `Bỏ đánh dấu đã uống ${med.name}` : `Đánh dấu đã uống ${med.name}`}
        className={cn(
          'grid size-12 shrink-0 place-items-center rounded-full border transition-transform active:scale-95',
          taken
            ? 'border-mint-400 bg-mint-500 text-white shadow-glow-mint'
            : 'border-mint-300 bg-white/70 text-mint-600'
        )}
      >
        <Check className="size-5" aria-hidden="true" />
      </button>
    </div>
  )
}

// ─── Schedule slot group ───────────────────────────────────────────────────────

function SlotGroup({
  slot,
  meds,
  takenSet,
  onToggleTaken,
  onEdit,
  onDelete,
  onView,
}: {
  slot: Slot
  meds: Medication[]
  takenSet: Set<string>
  onToggleTaken: (id: string) => void
  onEdit: (med: Medication) => void
  onDelete: (med: Medication) => void
  onView: (id: string) => void
}) {
  if (meds.length === 0) return null
  const takenCount = meds.filter((m) => takenSet.has(m.id)).length
  return (
    <section aria-label={slot.label}>
      <div className="mb-2 flex items-center gap-2.5 px-1">
        <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-mint-50 text-mint-600">
          {slot.icon}
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="text-[18px] font-bold leading-tight text-text">{slot.label}</h2>
          <p className="text-[13px] text-text-muted">{slot.hint}</p>
        </div>
        <span className="shrink-0 text-[13px] font-medium text-mint-700">
          {takenCount}/{meds.length}
        </span>
      </div>
      <div className="space-y-2.5">
        {meds.map((med) => (
          <div key={med.id} className="group">
            <MedRow
              med={med}
              taken={takenSet.has(med.id)}
              onToggleTaken={() => onToggleTaken(med.id)}
              onView={() => onView(med.id)}
            />
            {/* Inline edit/delete row — large targets, always visible (no hover dependency). */}
            <div className="mt-1 flex items-center justify-end gap-1 px-1">
              <button
                type="button"
                onClick={() => onEdit(med)}
                aria-label={`Sửa ${med.name}`}
                className="flex h-12 min-w-12 items-center gap-1 rounded-full px-3 text-[13px] font-medium text-text-muted transition-colors hover:bg-mint-50 hover:text-mint-700"
              >
                <Pencil className="size-4" aria-hidden="true" /> Sửa
              </button>
              <button
                type="button"
                onClick={() => onDelete(med)}
                aria-label={`Xoá ${med.name}`}
                className="flex h-12 min-w-12 items-center gap-1 rounded-full px-3 text-[13px] font-medium text-danger transition-colors hover:bg-danger-light"
              >
                <Trash2 className="size-4" aria-hidden="true" /> Xoá
              </button>
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}

// ─── Add / edit modal — preserves the exact form + API contract ────────────────

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
          <Button variant="mint-soft" size="lg" onClick={onClose} disabled={submitting}>
            Hủy
          </Button>
          <Button variant="mint" size="lg" type="submit" form="med-form" loading={submitting}>
            {editing ? 'Lưu' : 'Thêm thuốc'}
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
            placeholder="VD: 500mg, 1 viên"
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

// ─── Page ──────────────────────────────────────────────────────────────────────

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

  // Local-only "đã uống" check-off. NOT persisted — resets on reload / route
  // change. There is no adherence backend. TODO(backend): adherence API.
  const [takenSet, setTakenSet] = React.useState<Set<string>>(new Set())

  const toggleTaken = React.useCallback((id: string) => {
    setTakenSet((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

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

  // Group meds into visual time-of-day slots (presentation only).
  const grouped = React.useMemo(() => {
    const map: Record<SlotKey, Medication[]> = {
      morning: [],
      noon: [],
      evening: [],
      anytime: [],
    }
    for (const m of meds) map[inferSlot(m)].push(m)
    return map
  }, [meds])

  const takenCount = meds.filter((m) => takenSet.has(m.id)).length
  const todayStr = formatDate(new Date())

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

  if (loading) {
    return (
      <div className="mx-auto max-w-md space-y-5 p-4 pb-28 lg:max-w-2xl lg:p-6">
        <SectionHeader title="Thuốc & Điều trị" subtitle={todayStr} />
        <MedicationsSkeleton />
      </div>
    )
  }

  if (error && meds.length === 0) {
    return <ErrorState title="Không tải được danh sách thuốc" message={error} onRetry={load} />
  }

  const addButton = (
    <Button
      size="md"
      variant="mint"
      onClick={() => {
        setEditing(null)
        setModalOpen(true)
      }}
    >
      <Plus className="mr-1 size-4" aria-hidden="true" /> Thêm
    </Button>
  )

  return (
    <div className="mx-auto max-w-md space-y-5 p-4 pb-28 lg:max-w-2xl lg:p-6">
      {/* 1 — Header */}
      <SectionHeader title="Thuốc & Điều trị" subtitle={todayStr} action={addButton} />

      {/* Non-fatal error banner (e.g. delete failed) while list still shows */}
      {error && meds.length > 0 && <Alert variant="danger" title={error} />}

      {meds.length === 0 ? (
        // Empty state — spec §9 (frosted glass, friendly, single primary action)
        <GlassCard className="border border-dashed border-mint-300/80">
          <PatientEmptyState
            icon={<Pill aria-hidden="true" />}
            title="Chưa có thuốc nào"
            description="Thêm thuốc bạn đang dùng để theo dõi hằng ngày, hoặc bác sĩ sẽ kê đơn khi cần."
            cta={{
              label: 'Thêm thuốc đầu tiên',
              onClick: () => {
                setEditing(null)
                setModalOpen(true)
              },
            }}
          />
        </GlassCard>
      ) : (
        <>
          {/* 2 — Daily progress card (local-only check-off, clearly flagged) */}
          <GlassCard className="relative overflow-hidden glow-mint-soft">
            <div
              className="absolute -right-10 -top-10 size-40 rounded-full bg-gradient-to-br from-mint-300 to-mint-500 opacity-20 blur-2xl"
              aria-hidden="true"
            />
            <div className="relative flex items-center justify-between gap-4">
              <div className="min-w-0">
                <p className="text-[14px] font-medium text-text-muted">Đã đánh dấu hôm nay</p>
                <p className="mt-1 flex items-baseline gap-1">
                  <span className="text-[40px] font-bold leading-none tracking-tight text-brand-gradient">
                    {takenCount}
                  </span>
                  <span className="text-[18px] font-medium text-text-muted">
                    /{meds.length} thuốc
                  </span>
                </p>
                <p className="mt-2 text-[13px] leading-relaxed text-text-subtle">
                  Đánh dấu chỉ để nhắc bạn trong phiên này — chưa được lưu lại.
                </p>
              </div>
              <span className="grid size-14 shrink-0 place-items-center rounded-full bg-mint-50 text-mint-600">
                <Pill className="size-7" aria-hidden="true" />
              </span>
            </div>
          </GlassCard>

          {/* 3 — Schedule grouped by time of day */}
          <div className="space-y-6">
            {SLOTS.map((slot) => (
              <SlotGroup
                key={slot.key}
                slot={SLOT_BY_KEY[slot.key]}
                meds={grouped[slot.key]}
                takenSet={takenSet}
                onToggleTaken={toggleTaken}
                onEdit={(med) => {
                  setEditing(med)
                  setModalOpen(true)
                }}
                onDelete={(med) => setDeleteTarget(med)}
                onView={(id) => router.push(`/medications/${id}`)}
              />
            ))}
          </div>

          {/* 4 — Add another */}
          <MintButton
            variant="secondary"
            fullWidth
            onClick={() => {
              setEditing(null)
              setModalOpen(true)
            }}
          >
            <Plus className="mr-1.5 size-5" aria-hidden="true" /> Thêm thuốc khác
          </MintButton>
        </>
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
            <Button
              variant="mint-soft"
              size="lg"
              onClick={() => setDeleteTarget(null)}
              disabled={deleting}
            >
              Hủy
            </Button>
            <Button variant="danger" size="lg" onClick={confirmDelete} loading={deleting}>
              Xoá
            </Button>
          </>
        }
      >
        <p className="text-[17px] leading-relaxed text-text-muted">
          Bạn có chắc muốn xoá <span className="font-medium text-text">{deleteTarget?.name}</span>{' '}
          khỏi danh sách thuốc?
        </p>
      </Modal>
    </div>
  )
}
