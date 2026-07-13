'use client'

import * as React from 'react'
import { useParams, useRouter } from 'next/navigation'
import {
  ArrowLeft,
  Pill,
  Layers,
  Clock,
  FileText,
  Activity,
  CheckCircle2,
  XCircle,
  Lock,
  PauseCircle,
  PlayCircle,
} from 'lucide-react'
import { useAuth } from '@/lib/auth/context'
import {
  LifecycleBadges,
  DiscontinueModal,
} from '@/components/patient/medications/lifecycle'
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
  const [adherenceRate, setAdherenceRate] = React.useState<number>(0)
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)
  const [logging, setLogging] = React.useState(false)
  const [actionError, setActionError] = React.useState<string | null>(null)
  const [discontinueOpen, setDiscontinueOpen] = React.useState(false)

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
      const rate = safeHistory.length > 0 ? takenCount / safeHistory.length : 0
      setAdherenceRate(rate)

      const today = summaryRes.today_medications.find((m) => m.medication_id === id) ?? null
      setTodayStatus(today)
    } catch {
      setError('Không thể tải thông tin thuốc. Vui lòng thử lại.')
    } finally {
      setLoading(false)
    }
  }, [patientId, id])

  React.useEffect(() => {
    load()
  }, [load])

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

  return (
    <div className="p-4 max-w-md mx-auto pb-28 space-y-4">
      {/* Header: back + title */}
      <header className="flex items-center gap-3">
        <button
          type="button"
          aria-label="Quay lại"
          onClick={() => router.back()}
          className="neu-icon-btn !h-11 !w-11 !rounded-full text-neu-text"
        >
          <ArrowLeft className="size-5" />
        </button>
        <h1 className="text-[20px] font-extrabold tracking-[-0.02em] text-neu-text">
          Chi tiết thuốc
        </h1>
      </header>

      {/* Hero — name + dose/frequency */}
      <NeuCard className="!p-5">
        <div className="flex items-center gap-4">
          <span
            className="grid size-16 shrink-0 place-items-center rounded-[16px] text-white"
            style={{ background: PILL_GRADIENT, boxShadow: '0 10px 20px -8px rgba(37,99,235,0.5)' }}
            aria-hidden="true"
          >
            <Pill className="size-8" />
          </span>
          <div className="min-w-0">
            <p className="text-[21px] font-extrabold tracking-[-0.01em] text-neu-text">
              {medication.name}
            </p>
            {subtitle && <p className="mt-1 text-[13.5px] text-neu-secondary">{subtitle}</p>}
            <LifecycleBadges med={medication} />
          </div>
        </div>
        {medication.status_reason && !isActiveMed && (
          <p className="mt-3 rounded-[12px] bg-[#F4F7F5] px-3 py-2 text-[13px] text-neu-secondary">
            Lý do: {medication.status_reason}
          </p>
        )}
      </NeuCard>

      {actionError && (
        <p role="alert" className="px-1 text-[13px] font-semibold text-[#D92D20]">
          {actionError}
        </p>
      )}

      {/* Lifecycle controls */}
      {isActiveMed && (
        <div className="flex gap-2">
          <button
            type="button"
            onClick={async () => {
              if (logging) return
              setLogging(true)
              setActionError(null)
              try {
                await updateMedicationLifecycle(patientId, id, 'paused')
                await load()
              } catch (err: unknown) {
                setActionError(
                  err instanceof Error ? err.message : 'Không cập nhật được trạng thái.'
                )
              } finally {
                setLogging(false)
              }
            }}
            disabled={logging}
            className="flex flex-1 items-center justify-center gap-1.5 rounded-[12px] bg-[#FEF6E7] py-2.5 text-[13px] font-semibold text-[#8B6400] transition-transform active:scale-95 disabled:opacity-50"
          >
            <PauseCircle className="size-4" aria-hidden="true" />
            Tạm ngưng
          </button>
          <button
            type="button"
            onClick={() => setDiscontinueOpen(true)}
            disabled={logging}
            className="flex flex-1 items-center justify-center gap-1.5 rounded-[12px] bg-[#F4F4F4] py-2.5 text-[13px] font-semibold text-neu-muted transition-transform active:scale-95 disabled:opacity-50"
          >
            <XCircle className="size-4" aria-hidden="true" />
            Ngừng thuốc
          </button>
        </div>
      )}
      {isPausedMed && (
        <div className="flex gap-2">
        <button
          type="button"
          onClick={async () => {
            if (logging) return
            setLogging(true)
            setActionError(null)
            try {
              await updateMedicationLifecycle(patientId, id, 'active')
              await load()
            } catch (err: unknown) {
              setActionError(
                err instanceof Error ? err.message : 'Không cập nhật được trạng thái.'
              )
            } finally {
              setLogging(false)
            }
          }}
          disabled={logging}
          className="flex w-full items-center justify-center gap-1.5 rounded-[12px] bg-[#E8F7F2] py-2.5 text-[13px] font-semibold text-[#0F9C6E] transition-transform active:scale-95 disabled:opacity-50"
        >
          <PlayCircle className="size-4" aria-hidden="true" />
          {logging ? 'Đang lưu…' : 'Tiếp tục uống'}
        </button>
        <button
          type="button"
          onClick={() => setDiscontinueOpen(true)}
          disabled={logging}
          className="flex flex-1 items-center justify-center gap-1.5 rounded-[12px] bg-[#F4F4F4] py-2.5 text-[13px] font-semibold text-neu-muted transition-transform active:scale-95 disabled:opacity-50"
        >
          <XCircle className="size-4" aria-hidden="true" />
          Ngừng thuốc
        </button>
        </div>
      )}

      {/* on_hold clinical lock notice */}
      {medication.lifecycle_status === 'on_hold' && (
        <p className="flex items-start gap-2 rounded-[14px] bg-[#EFF4FF] px-4 py-3 text-[13.5px] font-medium text-[#2563EB]">
          <Lock className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          Bác sĩ yêu cầu tạm ngừng thuốc này. Không tự ý dùng lại — liên hệ bác sĩ nếu có thắc mắc.
        </p>
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

      {/* Adherence stats — 2×2 grid */}
      <div>
        <div className="mb-2 flex items-center gap-2">
          <Activity className="size-4 text-neu-green" aria-hidden="true" />
          <p className="text-[13px] font-bold text-neu-text">Tuân thủ điều trị</p>
        </div>
        <div className="grid grid-cols-2 gap-2.5">
          <StatChip
            label="Tuân thủ (30 ngày)"
            value={`${Math.round(adherenceRate * 100)}%`}
            color="#0F9C6E"
          />
          <StatChip label="Hôm nay" value={todayChipValue} color={todayChipColor} />
          <StatChip label="Lần cuối uống" value={lastTakenStr} color="#2563EB" />
          <StatChip label="Số lần đã ghi" value={String(history.length)} color="#8B6400" />
        </div>
      </div>

      {/* Quick-log section — active medications only (backend enforces too) */}
      {isActiveMed &&
        (takenToday ? (
        <NeuCard className="!p-4">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="size-5 text-[#0F9C6E]" aria-hidden="true" />
            <p className="text-[14px] font-bold text-[#0F9C6E]">Đã uống hôm nay</p>
          </div>
        </NeuCard>
      ) : (
        <NeuCard className="!p-4">
          <p className="mb-3 text-[13px] font-bold text-neu-text">Ghi hôm nay</p>
          <div className="flex gap-2.5">
            <NeuButton
              variant="primary"
              className="flex-1 !text-[13px]"
              onClick={handleTaken}
              disabled={logging}
            >
              {logging ? 'Đang lưu…' : 'Đã uống'}
            </NeuButton>
            <NeuButton
              variant="secondary"
              className="flex-1 !text-[13px]"
              onClick={handleSkipped}
              disabled={logging}
            >
              Bỏ qua
            </NeuButton>
          </div>
        </NeuCard>
        ))}

      {/* Notes */}
      {medication.note && (
        <NeuCard className="!p-4">
          <div className="mb-2 flex items-center gap-2">
            <FileText className="size-4 text-neu-green" aria-hidden="true" />
            <p className="text-[13px] font-bold text-neu-text">Ghi chú</p>
          </div>
          <p className="text-[14px] leading-relaxed text-neu-secondary">{medication.note}</p>
        </NeuCard>
      )}

      {/* Adherence history list */}
      {history.length > 0 && <AdherenceHistoryList records={history} />}

      <p className="px-1 text-[12.5px] text-neu-subtle">
        Thêm ngày {formatDate(medication.created_at)}
      </p>

      <NeuButton variant="secondary" onClick={() => router.push('/medications')}>
        Xem tất cả thuốc
      </NeuButton>

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
