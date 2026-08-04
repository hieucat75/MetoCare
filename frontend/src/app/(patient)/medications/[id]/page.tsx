'use client'

import * as React from 'react'
import { useParams, useRouter } from 'next/navigation'
import {
  ArrowLeft,
  Pill,
  Layers,
  Clock,
  Activity,
  CheckCircle2,
  XCircle,
  Lock,
  MoreVertical,
} from 'lucide-react'
import { useAuth } from '@/lib/auth/context'
import { LifecycleBadges, DiscontinueModal } from '@/components/patient/medications/lifecycle'
import { AdherenceStatusBadge } from '@/components/patient/medications/today-status'
import { MedModal } from '@/components/patient/medications/med-modal'
import { MedicationOverflowMenu } from '@/components/patient/medications/overflow-menu'
import { UsageInstructionsCard } from '@/components/patient/medications/usage-instructions'
import { InteractionsCard } from '@/components/patient/medications/interactions-card'
import { SideEffectsCard } from '@/components/patient/medications/side-effects-card'
import { MedicationScheduleCard } from '@/components/patient/medications/schedule-card'
import { MedicationSourceCard } from '@/components/patient/medications/source-card'
import { useMedicationSchedule } from '@/components/patient/medications/use-medication-schedule'
import { ApiError } from '@/lib/api/client'
import {
  getMedications,
  updateMedicationLifecycle,
  getAdherenceHistory,
  getAdherenceSummary,
  logAdherence,
  type Medication,
  type MedicationAdherence,
  type TodayMedication,
} from '@/lib/api/patient'
import { PatientErrorState, PatientSkeleton } from '@/components/patient/states'
import { NeuCard, NeuButton } from '@/components/patient/neu'

const PILL_GRADIENT = 'linear-gradient(160deg,#5B8DEF,#2563EB)'

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatDate(dateStr: string): string {
  try {
    return new Date(dateStr).toLocaleDateString('vi-VN', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    })
  } catch {
    return dateStr
  }
}

function formatTime(dateStr: string): string {
  try {
    return new Date(dateStr).toLocaleTimeString('vi-VN', {
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return dateStr
  }
}

/** Returns a short Vietnamese date header for a given ISO date string. */
function dateHeader(isoDate: string): string {
  try {
    const d = new Date(isoDate)
    const today = new Date()
    const yesterday = new Date(today)
    yesterday.setDate(yesterday.getDate() - 1)

    const sameDay = (a: Date, b: Date) =>
      a.getFullYear() === b.getFullYear() &&
      a.getMonth() === b.getMonth() &&
      a.getDate() === b.getDate()

    if (sameDay(d, today)) return 'Hôm nay'
    if (sameDay(d, yesterday)) return 'Hôm qua'

    return d.toLocaleDateString('vi-VN', { weekday: 'short', day: '2-digit', month: 'numeric' })
  } catch {
    return isoDate.slice(0, 10)
  }
}

/** ISO date string (YYYY-MM-DD) for a record, using taken_at or created_at. */
function recordDate(r: MedicationAdherence): string {
  const ts = r.taken_at ?? r.created_at
  try {
    return new Date(ts).toISOString().slice(0, 10)
  } catch {
    return ts.slice(0, 10)
  }
}

// ── StatChip ──────────────────────────────────────────────────────────────────

type StatChipProps = {
  label: string
  value: string
  color: string
}

function StatChip({ label, value, color }: StatChipProps) {
  return (
    <div className="neu-raised rounded-[14px] p-3.5" style={{ backgroundColor: `${color}18` }}>
      <p className="text-[11.5px] font-semibold" style={{ color }}>
        {label}
      </p>
      <p className="mt-1.5 text-[15px] font-extrabold text-neu-text leading-tight">{value}</p>
    </div>
  )
}

// ── AdherenceHistoryList ──────────────────────────────────────────────────────

type AdherenceHistoryListProps = {
  records: MedicationAdherence[]
}

function AdherenceHistoryList({ records }: AdherenceHistoryListProps) {
  const visible = records.slice(0, 14)

  // Group by calendar date
  const groups: { date: string; items: MedicationAdherence[] }[] = []
  for (const r of visible) {
    const d = recordDate(r)
    const last = groups[groups.length - 1]
    if (last && last.date === d) {
      last.items.push(r)
    } else {
      groups.push({ date: d, items: [r] })
    }
  }

  return (
    <NeuCard className="!p-4">
      <div className="mb-3 flex items-center gap-2">
        <Clock className="size-4 text-neu-green" aria-hidden="true" />
        <p className="text-[13px] font-bold text-neu-text">Lịch sử ({records.length} lần)</p>
      </div>

      {groups.length === 0 ? (
        <p className="text-[13px] text-neu-secondary">Chưa có dữ liệu ghi nhận.</p>
      ) : (
        <div className="space-y-3">
          {groups.map((group) => (
            <div key={group.date}>
              <p className="mb-1.5 text-[11px] font-bold uppercase tracking-wide text-neu-muted">
                {dateHeader(group.date)}
              </p>
              <div className="space-y-1.5">
                {group.items.map((r) => {
                  const ts = r.taken_at ?? r.created_at
                  if (r.taken_at !== null) {
                    return (
                      <div key={r.id} className="flex items-center gap-2.5">
                        <CheckCircle2
                          className="size-4 shrink-0 text-[#0F9C6E]"
                          aria-hidden="true"
                        />
                        <span className="text-[13px] text-neu-text">{formatTime(ts)}</span>
                        {r.note && (
                          <span className="text-[12px] text-neu-secondary">· {r.note}</span>
                        )}
                      </div>
                    )
                  }
                  if (r.skipped) {
                    return (
                      <div key={r.id} className="flex items-center gap-2.5">
                        <XCircle className="size-4 shrink-0 text-neu-muted" aria-hidden="true" />
                        <span className="text-[13px] text-neu-secondary">Bỏ qua</span>
                        {r.note && <span className="text-[12px] text-neu-subtle">· {r.note}</span>}
                      </div>
                    )
                  }
                  return (
                    <div key={r.id} className="flex items-center gap-2.5">
                      <span className="size-4 shrink-0 flex items-center justify-center">
                        <span className="size-2 rounded-full bg-neu-muted/50" />
                      </span>
                      <span className="text-[13px] text-neu-subtle">Không rõ</span>
                    </div>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </NeuCard>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function MedicationDetailPage() {
  const { id } = useParams<{ id: string }>()
  const router = useRouter()
  const { user } = useAuth()
  const patientId = user?.patient_profile_id

  const [medication, setMedication] = React.useState<Medication | null>(null)
  const [history, setHistory] = React.useState<MedicationAdherence[]>([])
  const [todayStatus, setTodayStatus] = React.useState<TodayMedication | null>(null)
  // Nullable on purpose: with no self-reported entry there is no rate, and a green
  // 0% next to a schedule card saying "chưa đủ dữ liệu" is the false claim the
  // schedule card exists to avoid.
  const [adherenceRate, setAdherenceRate] = React.useState<number | null>(null)
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)
  const [logging, setLogging] = React.useState(false)
  const [actionError, setActionError] = React.useState<string | null>(null)
  const [discontinueOpen, setDiscontinueOpen] = React.useState(false)
  const [menuOpen, setMenuOpen] = React.useState(false)
  const [medModalOpen, setMedModalOpen] = React.useState(false)
  const [medModalDeleteMode, setMedModalDeleteMode] = React.useState(false)

  const load = React.useCallback(async () => {
    if (!patientId) return
    setLoading(true)
    setError(null)
    try {
      const [medsRes, historyRes, summaryRes] = await Promise.all([
        // include_completed: detail must resolve history records too
        getMedications(patientId, { limit: 100, include_completed: true }),
        getAdherenceHistory(patientId, id, 30),
        getAdherenceSummary(patientId),
      ])

      let found = medsRes.items.find((m) => m.id === id)
      if (!found) {
        // Expired records live outside include_completed — dedicated lookup
        const expiredRes = await getMedications(patientId, {
          limit: 100,
          lifecycle_status: 'expired',
        }).catch(() => null)
        found = expiredRes?.items.find((m) => m.id === id)
      }
      if (!found) {
        setError('Không tìm thấy thông tin thuốc.')
        return
      }
      setMedication(found)

      const safeHistory = Array.isArray(historyRes) ? historyRes : []
      setHistory(safeHistory)

      const takenCount = safeHistory.filter((r) => r.taken_at !== null).length
      setAdherenceRate(safeHistory.length > 0 ? takenCount / safeHistory.length : null)

      const today = summaryRes.today_medications.find((m) => m.medication_id === id) ?? null
      setTodayStatus(today)
    } catch (err: unknown) {
      // Distinct states, not one generic failure: a 403 is an access decision the
      // patient can act on, a 404 means the record is gone, and only the rest is a
      // "try again" situation. Collapsing them told every patient to retry a
      // request that could never succeed.
      if (err instanceof ApiError) {
        if (err.status === 403) setError('Bạn không có quyền xem thông tin thuốc này.')
        else if (err.status === 404) setError('Không tìm thấy thông tin thuốc.')
        else if (err.status >= 500) setError('Hệ thống đang bận. Vui lòng thử lại sau.')
        else setError(err.detail || 'Không thể tải thông tin thuốc. Vui lòng thử lại.')
      } else {
        setError('Không thể tải thông tin thuốc. Vui lòng kiểm tra kết nối và thử lại.')
      }
    } finally {
      setLoading(false)
    }
  }, [patientId, id])

  React.useEffect(() => {
    load()
  }, [load])

  // Journey-3 structured schedule / due doses / dose-occurrence adherence. Loaded
  // independently of the record above so a schedule failure never blanks the page,
  // and vice versa.
  const schedule = useMedicationSchedule(patientId, id)

  const handleTaken = React.useCallback(async () => {
    if (!patientId || logging) return
    setLogging(true)
    setActionError(null)
    try {
      await logAdherence(patientId, id, { taken_at: new Date().toISOString() })
      await load()
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : 'Không ghi được liều. Vui lòng thử lại.')
    } finally {
      setLogging(false)
    }
  }, [patientId, id, logging, load])

  const handleSkipped = React.useCallback(async () => {
    if (!patientId || logging) return
    setLogging(true)
    setActionError(null)
    try {
      await logAdherence(patientId, id, { skipped: true })
      await load()
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : 'Không ghi được liều. Vui lòng thử lại.')
    } finally {
      setLogging(false)
    }
  }, [patientId, id, logging, load])

  const handleTogglePause = React.useCallback(async () => {
    if (!patientId || !medication || logging) return
    const target = medication.lifecycle_status === 'active' ? 'paused' : 'active'
    setLogging(true)
    setActionError(null)
    try {
      await updateMedicationLifecycle(patientId, id, target)
      await load()
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : 'Không cập nhật được trạng thái.')
    } finally {
      setLogging(false)
    }
  }, [patientId, id, medication, logging, load])

  if (!patientId) {
    return (
      <div className="p-4 max-w-md mx-auto mt-10">
        <div
          role="alert"
          className="rounded-[14px] bg-[#FEF9EC] border border-[#E0A92E]/30 p-4 text-[14px]"
        >
          <p className="font-bold text-[#8B6400] mb-0.5">Chưa có hồ sơ</p>
          <p className="text-[#8B6400]/80 text-[13px]">
            Chưa có hồ sơ bệnh nhân. Vui lòng liên hệ hỗ trợ.
          </p>
        </div>
      </div>
    )
  }

  if (loading)
    return (
      <div className="p-4 space-y-3 max-w-md mx-auto">
        <PatientSkeleton />
      </div>
    )
  if (error) return <PatientErrorState message={error} onRetry={load} />
  if (!medication) return null

  const subtitle = [medication.dose, medication.frequency].filter(Boolean).join(' · ')

  const takenToday = todayStatus?.taken_today ?? false
  const skippedToday = todayStatus?.skipped_today ?? false
  const lastTakenAt =
    todayStatus?.last_taken_at ?? history.find((r) => r.taken_at !== null)?.taken_at ?? null
  const lastTakenStr = lastTakenAt
    ? new Date(lastTakenAt).toLocaleDateString('vi-VN', { day: '2-digit', month: '2-digit' })
    : '—'

  const todayChipValue = takenToday ? 'Đã uống' : skippedToday ? 'Đã bỏ qua' : 'Chưa uống'
  const todayChipColor = takenToday ? '#0F9C6E' : skippedToday ? '#6B7280' : '#C77A06'

  const isActiveMed = medication.lifecycle_status === 'active'
  const isPausedMed = medication.lifecycle_status === 'paused'
  const canManage = isActiveMed || isPausedMed

  // When a structured schedule exists, dose occurrences are the authoritative
  // record and the schedule card owns "Đã uống" / "Bỏ qua". Showing the legacy
  // free-floating adherence buttons alongside would give the patient two buttons
  // writing to two different models with no way to tell which one counted.
  //
  // `schedules` is [] until the schedule fetch resolves, and that fetch is slower
  // than the record fetch above (two sequential rounds vs one). So this must gate
  // on the load having COMPLETED, not merely on the array being empty — otherwise
  // a scheduled medication shows the legacy buttons during the loading window and
  // a tap writes to the wrong model.
  const isScheduleResolved = schedule.phase === 'ready'
  const hasStructuredSchedule = schedule.schedules.length > 0
  const showsLegacyAdherence = isScheduleResolved && !hasStructuredSchedule

  return (
    <div className="p-4 pb-28 mx-auto max-w-md lg:max-w-5xl">
      {/* Header: back + title */}
      <header className="flex items-center gap-3">
        <button
          type="button"
          aria-label="Quay lại"
          onClick={() => router.back()}
          className="neu-icon-btn !h-11 !w-11 !rounded-full text-neu-text"
        >
          <ArrowLeft className="size-5" aria-hidden="true" />
        </button>
        <h1 className="text-[20px] font-extrabold tracking-[-0.02em] text-neu-text">
          Chi tiết thuốc
        </h1>
      </header>

      {/* Two columns from `lg` up: "what do I do now" on the left, reference and
          provenance on the right. Below `lg` it collapses to the original single
          mobile-web column, so the phone layout is unchanged. */}
      <div className="mt-4 grid gap-4 lg:grid-cols-2 lg:items-start">
        <div className="space-y-4">
      {/* Hero — consolidated identity + adherence status + today's dose + primary
          action + overflow (M2: answers "thuốc gì / đúng không / bấm gì" in one
          card, replacing the old 4-side-by-side-button layout). */}
      <NeuCard className="!p-5">
        <div className="flex items-start gap-4">
          <span
            className="grid size-16 shrink-0 place-items-center rounded-[16px] text-white"
            style={{ background: PILL_GRADIENT, boxShadow: '0 10px 20px -8px rgba(37,99,235,0.5)' }}
            aria-hidden="true"
          >
            <Pill className="size-8" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-[21px] font-extrabold tracking-[-0.01em] text-neu-text break-words">
              {medication.name}
            </p>
            {subtitle && <p className="mt-1 text-[13.5px] text-neu-secondary">{subtitle}</p>}
            <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
              <LifecycleBadges med={medication} />
              {/* The badge reads the LEGACY medication_adherence rollup. Once a
                  medication is schedule-tracked, its doses are recorded as
                  DoseOccurrences and `last_taken_at` stays null forever, so
                  computeAdherenceStatus would drift to the red "Chưa ghi nhận liều
                  gần đây" tier and sit there contradicting the 100% adherence shown
                  in the schedule card below. Same gate as the legacy buttons. */}
              {isActiveMed && showsLegacyAdherence && (
                <AdherenceStatusBadge med={medication} today={todayStatus ?? undefined} />
              )}
            </div>
          </div>
          {canManage && (
            <button
              type="button"
              aria-label="Thêm tuỳ chọn"
              aria-haspopup="dialog"
              aria-expanded={menuOpen}
              onClick={() => setMenuOpen(true)}
              className="neu-icon-btn !h-11 !w-11 shrink-0 !rounded-full text-neu-muted"
            >
              <MoreVertical className="size-5" aria-hidden="true" />
            </button>
          )}
        </div>

        {medication.status_reason && !isActiveMed && (
          <p className="mt-3 rounded-[12px] bg-[#F4F7F5] px-3 py-2 text-[13px] text-neu-secondary">
            Lý do: {medication.status_reason}
          </p>
        )}

        {medication.lifecycle_status === 'on_hold' && (
          <p className="mt-3 flex items-start gap-2 rounded-[14px] bg-[#EFF4FF] px-4 py-3 text-[13.5px] font-medium text-[#2563EB]">
            <Lock className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
            Bác sĩ yêu cầu tạm ngừng thuốc này. Không tự ý dùng lại — liên hệ bác sĩ nếu có thắc
            mắc.
          </p>
        )}

        {actionError && (
          <p role="alert" className="mt-3 text-[13px] font-semibold text-[#D92D20]">
            {actionError}
          </p>
        )}

        {/* Today's dose status + primary/secondary action — active only.
            taken_today/skipped_today are mutually exclusive by backend design
            (last-action-wins on today's most-recent record) — see the note
            on computeAdherenceStatus in today-status.tsx for the disclosed
            limitation this implies. */}
        {isActiveMed && showsLegacyAdherence && (
          <div className="mt-4 border-t border-[#E8F0ED] pt-4">
            {takenToday ? (
              <div className="flex items-center gap-2">
                <CheckCircle2 className="size-5 text-[#0F9C6E]" aria-hidden="true" />
                <p className="text-[14px] font-bold text-[#0F9C6E]">Đã uống hôm nay</p>
              </div>
            ) : (
              <>
                {skippedToday && (
                  <p className="mb-2 text-[13px] font-semibold text-neu-muted">
                    Hôm nay: đã bỏ qua
                  </p>
                )}
                <div className="flex items-center gap-3">
                  <NeuButton
                    variant="primary"
                    className="flex-[2] !text-[15px]"
                    onClick={handleTaken}
                    disabled={logging}
                  >
                    {logging ? 'Đang lưu…' : 'Đã uống'}
                  </NeuButton>
                  <button
                    type="button"
                    onClick={handleSkipped}
                    disabled={logging}
                    className="flex-1 py-3 text-center text-[14px] font-semibold text-neu-muted underline underline-offset-2 disabled:opacity-50"
                  >
                    Bỏ qua
                  </button>
                </div>
              </>
            )}
          </div>
        )}
      </NeuCard>

      {/* Journey 3 — structured schedule, next due dose, dose-level taken/skipped
          (with a reason) and DoseOccurrence-based adherence. */}
      {schedule.phase === 'loading' ? (
        <NeuCard className="!p-4">
          <p className="text-[13px] text-neu-secondary">Đang tải lịch uống thuốc…</p>
        </NeuCard>
      ) : schedule.phase === 'error' ? (
        <NeuCard className="!p-4">
          <p role="alert" className="text-[13px] text-neu-secondary">
            {schedule.errorMessage}
          </p>
          <button
            type="button"
            onClick={() => void schedule.reload()}
            className="mt-1 text-[13px] font-semibold text-neu-green underline underline-offset-2"
          >
            Thử lại
          </button>
        </NeuCard>
      ) : (
        <MedicationScheduleCard
          schedules={schedule.schedules}
          dueDoses={schedule.dueDoses}
          nextDue={schedule.nextDue}
          adherence={schedule.adherence}
          isAdherencePartial={schedule.isAdherencePartial}
          adherenceSince={schedule.adherenceSince}
          isSubmitting={schedule.isSubmitting}
          actionError={schedule.actionError}
          onMarkTaken={(doseId) => void schedule.markTaken(doseId)}
          onMarkSkipped={(doseId, reason) => schedule.markSkipped(doseId, reason)}
          onRequestDiscontinue={canManage ? () => setDiscontinueOpen(true) : undefined}
        />
      )}

      {/* Dose / timing chips */}
      {(medication.dose || medication.frequency) && (
        <div className="grid grid-cols-2 gap-2.5">
          {medication.dose && (
            <div className="neu-raised rounded-[14px] p-3.5" style={{ backgroundColor: '#E9F2ED' }}>
              <div className="flex items-center gap-1.5 text-neu-muted">
                <Layers className="size-4 text-neu-green" aria-hidden="true" />
                <span className="text-[11.5px] font-semibold">Liều dùng</span>
              </div>
              <p className="mt-2 text-[16px] font-extrabold text-neu-text">{medication.dose}</p>
            </div>
          )}
          {medication.frequency && (
            <div className="neu-raised rounded-[14px] p-3.5" style={{ backgroundColor: '#F7EFDF' }}>
              <div className="flex items-center gap-1.5 text-[#8a6a25]">
                <Clock className="size-4 text-[#C77A06]" aria-hidden="true" />
                <span className="text-[11.5px] font-semibold">Tần suất</span>
              </div>
              <p className="mt-2 text-[16px] font-extrabold text-neu-text">
                {medication.frequency}
              </p>
            </div>
          )}
        </div>
      )}
        </div>

        <div className="space-y-4">
      {/* Cách sử dụng — M3: user note vs professional guidance, kept apart */}
      <UsageInstructionsCard note={medication.note} />

      {/* Tương tác thuốc + Tác dụng phụ — M4: structure/empty-state only, no
          interaction/side-effect engine exists yet. Always called with empty
          arrays today — the data contract exists so Gate 2 can wire a real
          source without touching these components. */}
      <InteractionsCard medicationName={medication.name} interactions={[]} />
      <SideEffectsCard groups={[]} />

      {/* Nguồn thông tin — BRD §F provenance (document + OCR origin). */}
      <MedicationSourceCard
        patientId={patientId}
        medicationId={id}
        fallbackSourceType={medication.source_type}
        fallbackVerificationStatus={medication.verification_status}
      />

      {/* Legacy self-reported log. Kept because it is real history the patient
          entered before schedules existed — but once the medication is
          schedule-tracked this figure is frozen (dose writes go to DoseOccurrence,
          not here) and would sit on screen contradicting the live one. Two
          different adherence percentages for one drug is exactly the kind of thing
          a patient shows a clinician, so the stale one is collapsed away rather
          than shown side by side. */}
      <details open={!hasStructuredSchedule}>
        <summary className="mb-2 flex cursor-pointer items-center gap-2">
          <Activity className="size-4 text-neu-green" aria-hidden="true" />
          <span className="text-[13px] font-bold text-neu-text">
            {hasStructuredSchedule ? 'Nhật ký tự ghi nhận (trước khi có lịch)' : 'Tự ghi nhận'}
          </span>
        </summary>
        {hasStructuredSchedule && (
          <p className="mb-2 text-[12.5px] text-neu-secondary">
            Đây là nhật ký cũ do bạn tự ghi. Từ khi có lịch uống, các liều được tính ở mục
            “Tuân thủ theo lịch” phía trên.
          </p>
        )}
        <div className="grid grid-cols-2 gap-2.5">
          {/* "30 ngày" was wrong: getAdherenceHistory's third argument is a row
              LIMIT, not a day window (lib/api/patient.ts). Thirty entries can span
              months, so the label now states what is actually measured. */}
          <StatChip
            label="Tuân thủ (30 lần ghi gần nhất)"
            value={adherenceRate === null ? 'Chưa có' : `${Math.round(adherenceRate * 100)}%`}
            color="#0F9C6E"
          />
          <StatChip label="Hôm nay" value={todayChipValue} color={todayChipColor} />
          <StatChip label="Lần cuối uống" value={lastTakenStr} color="#2563EB" />
          <StatChip label="Số lần đã ghi" value={String(history.length)} color="#8B6400" />
        </div>

        {/* Adherence history list */}
        <div className="mt-3">
          {history.length > 0 ? (
            <AdherenceHistoryList records={history} />
          ) : (
            <NeuCard className="!p-4">
              <p className="text-[13px] text-neu-secondary">
                Bạn chưa tự ghi nhận lần uống nào cho thuốc này.
              </p>
            </NeuCard>
          )}
        </div>
      </details>
        </div>
      </div>

      <p className="mt-4 px-1 text-[12.5px] text-neu-subtle">
        Thêm ngày {formatDate(medication.created_at)}
      </p>

      <NeuButton
        variant="secondary"
        className="mt-3"
        onClick={() => router.push('/medications')}
      >
        Xem tất cả thuốc
      </NeuButton>

      <MedicationOverflowMenu
        open={menuOpen}
        onClose={() => setMenuOpen(false)}
        med={medication}
        busy={logging}
        onTogglePause={handleTogglePause}
        onDiscontinue={() => setDiscontinueOpen(true)}
        onEdit={() => {
          setMedModalDeleteMode(false)
          setMedModalOpen(true)
        }}
        onDelete={() => {
          setMedModalDeleteMode(true)
          setMedModalOpen(true)
        }}
      />

      <MedModal
        open={medModalOpen}
        onClose={() => setMedModalOpen(false)}
        onSaved={load}
        onDeleted={() => router.push('/medications')}
        patientId={patientId}
        editing={medication}
        deleteMode={medModalDeleteMode}
      />

      <DiscontinueModal
        open={discontinueOpen}
        onClose={() => setDiscontinueOpen(false)}
        onSaved={load}
        patientId={patientId}
        med={medication}
      />
    </div>
  )
}
