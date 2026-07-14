'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import {
  Pill,
  Pencil,
  Trash2,
  CheckCircle2,
  XCircle,
  PauseCircle,
  PlayCircle,
  Lock,
} from 'lucide-react'
import { PatientPrimaryFab } from '@/components/patient/PatientPrimaryFab'
import { NeuCard } from '@/components/patient/neu'
import { PatientEmptyState } from '@/components/patient'
import { PatientErrorState, PatientSkeleton } from '@/components/patient/states'
import { useAuth } from '@/lib/auth/context'
import {
  getMedications,
  updateMedicationLifecycle,
  logAdherence,
  getAdherenceSummary,
  type Medication,
  type AdherenceSummary,
  type TodayMedication,
} from '@/lib/api/patient'
import {
  LifecycleBadges,
  DiscontinueModal,
} from '@/components/patient/medications/lifecycle'
import { TodayStatusCard, AdherenceStatusBadge } from '@/components/patient/medications/today-status'
import { MedModal } from '@/components/patient/medications/med-modal'
import {
  AdherenceSummaryCard,
  AdherenceSummarySkeleton,
  WeeklyAdherenceSection,
} from './adherence-widgets'

const PILL_GRADIENT = 'linear-gradient(160deg,#5B8DEF,#2563EB)'

// ── Medication card row ────────────────────────────────────────────────────────

type MedRowProps = {
  med: Medication
  todayStatus: TodayMedication | undefined
  /** False when the adherence-summary fetch hasn't succeeded — suppresses the
   *  adherence badge so it never fabricates "cần chú ý"/"đã bỏ lỡ" from a
   *  fetch failure rather than real absence of data. */
  adherenceLoaded: boolean
  onEdit: () => void
  onDelete: () => void
  onView: () => void
  onLogged: () => Promise<void> | void
  onDiscontinue: () => void
  patientId: string
}

function MedRow({
  med,
  todayStatus,
  adherenceLoaded,
  onEdit,
  onDelete,
  onView,
  onLogged,
  onDiscontinue,
  patientId,
}: MedRowProps) {
  const [logging, setLogging] = React.useState(false)
  const [rowError, setRowError] = React.useState<string | null>(null)
  const [reasserted, setReasserted] = React.useState(false)
  const meta = [med.dose, med.frequency].filter(Boolean).join(' · ')

  const isActive = med.lifecycle_status === 'active'
  const isPaused = med.lifecycle_status === 'paused'
  const isOnHold = med.lifecycle_status === 'on_hold'

  async function handleTaken() {
    if (logging) return
    setLogging(true)
    setRowError(null)
    try {
      await logAdherence(patientId, med.id, { taken_at: new Date().toISOString() })
      await onLogged()
    } catch (err: unknown) {
      setRowError(err instanceof Error ? err.message : 'Không ghi được liều. Vui lòng thử lại.')
    } finally {
      setLogging(false)
    }
  }

  async function handleSkipped() {
    if (logging) return
    setLogging(true)
    setRowError(null)
    try {
      await logAdherence(patientId, med.id, { skipped: true })
      await onLogged()
    } catch (err: unknown) {
      setRowError(err instanceof Error ? err.message : 'Không ghi được liều. Vui lòng thử lại.')
    } finally {
      setLogging(false)
    }
  }

  async function handleLifecycle(target: 'active' | 'paused') {
    if (logging) return
    setLogging(true)
    setRowError(null)
    try {
      await updateMedicationLifecycle(patientId, med.id, target)
      await onLogged()
    } catch (err: unknown) {
      setRowError(err instanceof Error ? err.message : 'Không cập nhật được trạng thái.')
    } finally {
      setLogging(false)
    }
  }

  async function handleReassert() {
    if (logging) return
    setLogging(true)
    setRowError(null)
    try {
      // Backend records a pending continued_use statement; the record stays
      // expired until reviewed (Q-OQ-1) — no direct reactivation.
      await updateMedicationLifecycle(patientId, med.id, 'active')
      setReasserted(true)
    } catch (err: unknown) {
      setRowError(err instanceof Error ? err.message : 'Không gửi được yêu cầu.')
    } finally {
      setLogging(false)
    }
  }

  const isTaken = todayStatus?.taken_today === true
  const isSkipped = todayStatus?.skipped_today === true

  return (
    <NeuCard className="p-4">
      <div className="flex items-start gap-3">
        <button
          type="button"
          onClick={onView}
          className="flex min-w-0 flex-1 items-start gap-3 text-left"
        >
          <span
            className="grid size-11 shrink-0 place-items-center rounded-[13px] text-white"
            style={{
              background: PILL_GRADIENT,
              boxShadow: '0 8px 16px -8px rgba(37,99,235,0.5)',
              opacity: isActive || isPaused || isOnHold ? 1 : 0.45,
            }}
            aria-hidden="true"
          >
            <Pill className="size-5" />
          </span>
          <span className="min-w-0">
            {/* a11y: med name — 18px (was 16px) */}
            <span className="block truncate text-[18px] font-bold text-neu-text">{med.name}</span>
            {/* a11y: meta — 16px (was 13.5px) */}
            {meta && <span className="mt-0.5 block text-[16px] text-neu-muted">{meta}</span>}
            {med.note && (
              <span className="mt-0.5 block truncate text-[15px] text-neu-subtle">{med.note}</span>
            )}
            <LifecycleBadges med={med} />
            {isActive && adherenceLoaded && (
              <span className="mt-1 flex flex-wrap items-center gap-1.5">
                <AdherenceStatusBadge med={med} today={todayStatus} />
              </span>
            )}
          </span>
        </button>
        {/* edit/delete only while the record is live (active/paused) —
            on_hold is doctor-controlled; terminal records are history */}
        {(isActive || isPaused) && (
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
        )}
      </div>

      {rowError && (
        <p role="alert" className="mt-2 text-[13px] font-semibold text-[#D92D20]">
          {rowError}
        </p>
      )}

      {/* on_hold: clinical lock notice — patient must not resume by themselves */}
      {isOnHold && (
        <div className="mt-3 border-t border-[#E8F0ED] pt-3">
          <p className="flex items-start gap-2 rounded-[12px] bg-[#EFF4FF] px-3 py-2 text-[13px] font-medium text-[#2563EB]">
            <Lock className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
            Bác sĩ yêu cầu tạm ngừng thuốc này. Không tự ý dùng lại — liên hệ bác sĩ nếu có thắc
            mắc.
          </p>
        </div>
      )}

      {/* paused: resume OR permanently discontinue */}
      {isPaused && (
        <div className="mt-3 flex gap-2 border-t border-[#E8F0ED] pt-3">
          <button
            type="button"
            onClick={() => handleLifecycle('active')}
            disabled={logging}
            className="flex flex-1 items-center justify-center gap-1.5 rounded-[12px] bg-[#E8F7F2] py-2 text-[13px] font-semibold text-[#0F9C6E] transition-transform active:scale-95 disabled:opacity-50"
          >
            <PlayCircle className="size-4" aria-hidden="true" />
            {logging ? 'Đang lưu…' : 'Tiếp tục uống'}
          </button>
          <button
            type="button"
            onClick={onDiscontinue}
            disabled={logging}
            className="flex flex-1 items-center justify-center gap-1.5 rounded-[12px] bg-[#F4F4F4] py-2 text-[13px] font-semibold text-neu-muted transition-transform active:scale-95 disabled:opacity-50"
          >
            <XCircle className="size-4" aria-hidden="true" />
            Ngừng thuốc
          </button>
        </div>
      )}

      {/* expired: Q-OQ-1 re-review — re-assert goes to review, no direct reactivation */}
      {med.lifecycle_status === 'expired' && (
        <div className="mt-3 border-t border-[#E8F0ED] pt-3">
          {reasserted ? (
            <p className="rounded-[12px] bg-[#E8F7F2] px-3 py-2 text-[13px] font-semibold text-[#0F9C6E]">
              Đã ghi nhận — thuốc sẽ được xem xét trước khi kích hoạt lại.
            </p>
          ) : (
            <button
              type="button"
              onClick={handleReassert}
              disabled={logging}
              className="flex w-full items-center justify-center gap-1.5 rounded-[12px] bg-[#FEF2F2] py-2 text-[13px] font-semibold text-[#D92D20] transition-transform active:scale-95 disabled:opacity-50"
            >
              <PlayCircle className="size-4" aria-hidden="true" />
              {logging ? 'Đang lưu…' : 'Tôi vẫn đang dùng thuốc này'}
            </button>
          )}
        </div>
      )}

      {/* Adherence quick-log — active medications only (backend enforces too) */}
      {isActive && (
      <div className="mt-3 border-t border-[#E8F0ED] pt-3">
        {isTaken ? (
          // Taken state: green badge + allow correcting to skipped
          <div className="flex items-center gap-2">
            <span
              className="flex flex-1 items-center gap-1.5 rounded-[12px] px-3 py-2 text-[13px] font-semibold"
              style={{ background: '#E8F7F2', color: '#0F9C6E' }}
            >
              <CheckCircle2 className="size-4 shrink-0" aria-hidden="true" />
              Đã uống hôm nay
            </span>
            <button
              type="button"
              onClick={handleSkipped}
              disabled={logging}
              aria-label="Đánh dấu bỏ qua"
              className="flex items-center justify-center gap-1.5 rounded-[12px] bg-[#F4F4F4] px-3 py-2 text-[13px] font-semibold text-neu-muted transition-transform active:scale-95 disabled:opacity-50"
            >
              <XCircle className="size-4" aria-hidden="true" />
              Bỏ qua
            </button>
          </div>
        ) : isSkipped ? (
          // Skipped state: gray badge + allow marking as taken
          <div className="flex items-center gap-2">
            <span className="flex flex-1 items-center gap-1.5 rounded-[12px] bg-[#F4F4F4] px-3 py-2 text-[13px] font-semibold text-neu-muted">
              <XCircle className="size-4 shrink-0" aria-hidden="true" />
              Đã bỏ qua hôm nay
            </span>
            <button
              type="button"
              onClick={handleTaken}
              disabled={logging}
              aria-label="Đánh dấu đã uống"
              className="flex items-center justify-center gap-1.5 rounded-[12px] bg-[#E8F7F2] px-3 py-2 text-[13px] font-semibold text-[#0F9C6E] transition-transform active:scale-95 disabled:opacity-50"
            >
              <CheckCircle2 className="size-4" aria-hidden="true" />
              Đã uống
            </button>
          </div>
        ) : (
          // Default state: two action buttons
          <div className="flex gap-2">
            <button
              type="button"
              onClick={handleTaken}
              disabled={logging}
              aria-label="Đánh dấu đã uống"
              className="flex flex-1 items-center justify-center gap-1.5 rounded-[12px] bg-[#E8F7F2] py-2 text-[13px] font-semibold text-[#0F9C6E] transition-transform active:scale-95 disabled:opacity-50"
            >
              <CheckCircle2 className="size-4" aria-hidden="true" />
              {logging ? 'Đang lưu…' : 'Đã uống'}
            </button>
            <button
              type="button"
              onClick={handleSkipped}
              disabled={logging}
              aria-label="Đánh dấu bỏ qua"
              className="flex flex-1 items-center justify-center gap-1.5 rounded-[12px] bg-[#F4F4F4] py-2 text-[13px] font-semibold text-neu-muted transition-transform active:scale-95 disabled:opacity-50"
            >
              <XCircle className="size-4" aria-hidden="true" />
              {logging ? 'Đang lưu…' : 'Bỏ qua'}
            </button>
          </div>
        )}
      </div>
      )}

      {/* Lifecycle actions — active medications only */}
      {isActive && (
        <div className="mt-2 flex gap-2">
          <button
            type="button"
            onClick={() => handleLifecycle('paused')}
            disabled={logging}
            className="flex flex-1 items-center justify-center gap-1.5 rounded-[12px] bg-[#FEF6E7] py-2 text-[13px] font-semibold text-[#8B6400] transition-transform active:scale-95 disabled:opacity-50"
          >
            <PauseCircle className="size-4" aria-hidden="true" />
            Tạm ngưng
          </button>
          <button
            type="button"
            onClick={onDiscontinue}
            disabled={logging}
            className="flex flex-1 items-center justify-center gap-1.5 rounded-[12px] bg-[#F4F4F4] py-2 text-[13px] font-semibold text-neu-muted transition-transform active:scale-95 disabled:opacity-50"
          >
            <XCircle className="size-4" aria-hidden="true" />
            Ngừng thuốc
          </button>
        </div>
      )}
    </NeuCard>
  )
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function MedicationsPage() {
  const router = useRouter()
  const { user } = useAuth()
  const patientId = user?.patient_profile_id

  const [meds, setMeds] = React.useState<Medication[]>([])
  const [adherence, setAdherence] = React.useState<Record<string, TodayMedication>>({})
  const [summary, setSummary] = React.useState<AdherenceSummary | null>(null)
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)

  const [modalOpen, setModalOpen] = React.useState(false)
  const [editing, setEditing] = React.useState<Medication | null>(null)
  const [deleteMode, setDeleteMode] = React.useState(false)
  const [discontinuing, setDiscontinuing] = React.useState<Medication | null>(null)
  const [showHistory, setShowHistory] = React.useState(false)

  // Reset state synchronously, during render, the moment `patientId` changes
  // — this is React's documented pattern for "resetting state when a prop
  // changes" (as opposed to resetting in an effect, which would commit one
  // paint of the OLD patient's meds/adherence under the NEW patientId before
  // `load()` gets a chance to run).
  const [loadedForPatientId, setLoadedForPatientId] = React.useState(patientId)
  if (patientId !== loadedForPatientId) {
    setLoadedForPatientId(patientId)
    setMeds([])
    setSummary(null)
    setAdherence({})
    setLoading(true)
    setError(null)
  }

  // Two separate epoch counters, not one shared counter: `loadEpochRef` gates
  // only `load()`'s own completion/loading-state, so a background adherence
  // refresh can never strand the page in its loading skeleton by invalidating
  // an in-flight `load()`. `adherenceEpochRef` gates the adherence snapshot
  // specifically (bumped by both the interval AND `load()`, since a full load
  // also produces a fresher snapshot that should supersede any in-flight
  // background refresh) — this still prevents an out-of-order interval
  // response from overwriting newer data.
  const loadEpochRef = React.useRef(0)
  const adherenceEpochRef = React.useRef(0)
  // Kept in sync every render (not in an effect, so it's current before any
  // effect or async callback can run) — an epoch match alone doesn't encode
  // *which patient* a response belongs to, so a stale response for a patient
  // this page no longer shows must still be rejected even if its epoch
  // happens to still be current.
  const patientIdRef = React.useRef(patientId)
  patientIdRef.current = patientId

  const load = React.useCallback(() => {
    if (!patientId) {
      setLoading(false)
      return Promise.resolve()
    }
    const loadEpoch = ++loadEpochRef.current
    // Independently bumped (not copied from loadEpoch) — it's the same
    // monotonic sequence the interval increments, so a full load correctly
    // supersedes an in-flight interval fetch, and `load()`'s own adherence
    // write is gated by this sequence rather than the unrelated load sequence.
    const adherenceEpoch = ++adherenceEpochRef.current
    setLoading(true)
    setError(null)
    return Promise.all([
      getMedications(patientId, { limit: 50, include_completed: showHistory }),
      // Q-OQ-1: expired records need review — always surfaced, own fetch
      getMedications(patientId, { limit: 50, lifecycle_status: 'expired' }).catch(() => null),
      getAdherenceSummary(patientId).catch(() => null),
    ])
      .then(([medsRes, expiredRes, summaryRes]) => {
        const stillCurrentPatient = patientId === patientIdRef.current
        if (loadEpoch === loadEpochRef.current && stillCurrentPatient) {
          setMeds([...(expiredRes?.items ?? []), ...medsRes.items])
        }
        // Always set (never leave a stale summary/adherence from a prior
        // successful load in place) — a failed refresh must show "no data"
        // rather than yesterday's now-inaccurate "hôm nay" snapshot.
        if (adherenceEpoch === adherenceEpochRef.current && stillCurrentPatient) {
          setSummary(summaryRes)
          const map: Record<string, TodayMedication> = {}
          if (summaryRes) {
            for (const m of summaryRes.today_medications) {
              map[m.medication_id] = m
            }
          }
          setAdherence(map)
        }
      })
      .catch((err: Error) => {
        if (loadEpoch !== loadEpochRef.current || patientId !== patientIdRef.current) return
        setError(err.message)
      })
      .finally(() => {
        if (loadEpoch === loadEpochRef.current && patientId === patientIdRef.current) {
          setLoading(false)
        }
      })
  }, [patientId, showHistory])

  React.useEffect(() => {
    load()
  }, [load])

  // Silently re-fetch just the time-sensitive adherence snapshot on an
  // interval — the "hôm nay" rollup and per-med badges are only accurate
  // as of the last fetch; without this a tab left open across the day
  // boundary keeps showing yesterday's "taken today" as current. Uses its
  // own request (not `load()`) so it never flips the page into the loading
  // skeleton for a background refresh.
  React.useEffect(() => {
    if (!patientId) return
    const ADHERENCE_REFRESH_INTERVAL_MS = 5 * 60 * 1000
    const id = setInterval(() => {
      const epoch = ++adherenceEpochRef.current
      getAdherenceSummary(patientId)
        .then((summaryRes) => {
          if (epoch !== adherenceEpochRef.current || patientId !== patientIdRef.current) return
          setSummary(summaryRes)
          const map: Record<string, TodayMedication> = {}
          for (const m of summaryRes.today_medications) {
            map[m.medication_id] = m
          }
          setAdherence(map)
        })
        .catch(() => {
          if (epoch !== adherenceEpochRef.current || patientId !== patientIdRef.current) return
          setSummary(null)
          setAdherence({})
        })
    }, ADHERENCE_REFRESH_INTERVAL_MS)
    return () => clearInterval(id)
  }, [patientId])

  if (!patientId) {
    return (
      <div className="p-4 max-w-md mx-auto mt-10">
        <div
          role="alert"
          className="rounded-[14px] bg-[#FEF9EC] border border-[#E0A92E]/30 p-4 text-[14px]"
        >
          <p className="font-bold text-[#8B6400] mb-0.5">Chưa có hồ sơ bệnh nhân</p>
          <p className="text-[#8B6400]/80 text-[13px]">
            Tài khoản của bạn chưa được liên kết với hồ sơ bệnh nhân. Vui lòng liên hệ hỗ trợ.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="p-4 space-y-4 max-w-md mx-auto pb-28">
      <h1 className="px-1 text-[21px] font-extrabold tracking-[-0.02em] text-neu-text">Thuốc</h1>

      {/* "Tình trạng hôm nay" — real-data-only today rollup, first thing patients see.
          Gated on `summary` (not just !error): getAdherenceSummary() swallows its own
          fetch failure via .catch(() => null), so a transient error must not render
          the card with an empty/stale adherence map — that would fabricate "chưa ghi
          nhận"/"bỏ lỡ" for medications we simply failed to check. */}
      {!loading && !error && summary && (
        <TodayStatusCard meds={meds} adherence={adherence} currentStreak={summary.current_streak} />
      )}

      {/* Adherence Summary Card */}
      {loading && <AdherenceSummarySkeleton />}
      {!loading && summary && summary.total_doses_logged > 0 && (
        <AdherenceSummaryCard summary={summary} />
      )}

      {loading && (
        <div className="p-4 space-y-3">
          <PatientSkeleton />
          <PatientSkeleton />
        </div>
      )}

      {!loading && error && (
        <PatientErrorState title="Không thể tải thuốc" message={error} onRetry={load} />
      )}

      {!loading && !error && meds.length === 0 && (
        <PatientEmptyState
          icon={<Pill />}
          title="Chưa có thuốc"
          description="Thêm thuốc để theo dõi lịch uống."
          cta={{
            label: 'Thêm thuốc',
            onClick: () => {
              setDeleteMode(false)
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
              todayStatus={adherence[med.id]}
              adherenceLoaded={summary !== null}
              patientId={patientId}
              onView={() => router.push(`/medications/${med.id}`)}
              onEdit={() => {
                setDeleteMode(false)
                setEditing(med)
                setModalOpen(true)
              }}
              onDelete={() => {
                setDeleteMode(true)
                setEditing(med)
                setModalOpen(true)
              }}
              onDiscontinue={() => setDiscontinuing(med)}
              onLogged={load}
            />
          ))}
        </div>
      )}

      {/* History toggle — completed + discontinued records (Plan §5.5) */}
      {!loading && !error && (
        <button
          type="button"
          onClick={() => setShowHistory((v) => !v)}
          className="w-full rounded-[12px] py-2 text-center text-[14px] font-semibold text-neu-muted transition-opacity active:opacity-70"
        >
          {showHistory ? 'Ẩn thuốc đã ngừng / hoàn tất' : 'Hiện thuốc đã ngừng / hoàn tất'}
        </button>
      )}

      {/* Adherence History Section */}
      {!loading && !error && summary && summary.total_doses_logged > 0 && (
        <WeeklyAdherenceSection summary={summary} />
      )}

      {/* FAB — add medication (keeps its own gradient skin via className="" + style) */}
      <PatientPrimaryFab
        ariaLabel="Thêm thuốc"
        onClick={() => {
          setDeleteMode(false)
          setEditing(null)
          setModalOpen(true)
        }}
        className=""
        style={{
          background: 'linear-gradient(160deg,#0F9C6E,#0a7a57)',
          boxShadow: '0 8px 20px -6px rgba(15,156,110,0.55)',
        }}
      />

      <MedModal
        open={modalOpen}
        onClose={() => {
          setModalOpen(false)
          setEditing(null)
          setDeleteMode(false)
        }}
        onSaved={load}
        patientId={patientId}
        editing={editing}
        deleteMode={deleteMode}
      />

      <DiscontinueModal
        open={discontinuing !== null}
        onClose={() => setDiscontinuing(null)}
        onSaved={load}
        patientId={patientId}
        med={discontinuing}
      />
    </div>
  )
}
