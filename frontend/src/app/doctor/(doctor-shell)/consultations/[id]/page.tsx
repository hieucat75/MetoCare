'use client'

import * as React from 'react'
import { useParams, useRouter } from 'next/navigation'
import {
  ArrowLeft,
  CheckCircle2,
  PlayCircle,
  Flag,
  XCircle,
  Lock,
  FileText,
  Activity,
  FlaskConical,
  Pill,
  ClipboardList,
  Calendar,
  Utensils,
  Gauge,
} from 'lucide-react'
import {
  PageHeader,
  Card,
  Alert,
  Button,
  Textarea,
  Select,
  SkeletonText,
  PageLoading,
  ErrorState,
} from '@/design-system'
import {
  ConsultationStatusBadge,
  formatVnd,
  formatDateTime,
  MarketplaceDisclaimer,
} from '@/components/marketplace'
import { ApiError } from '@/lib/api/client'
import type { ConsultationStatus } from '@/lib/api/marketplace'
import {
  getConsultation,
  confirmConsultation,
  startConsultation,
  completeConsultation,
  cancelConsultation,
  getPatientSummary,
  listNotes,
  createNote,
  type ConsultationOut,
  type NoteOut,
  type PatientSummaryOut,
} from '@/lib/api/consultations'

const TYPE_LABELS: Record<string, string> = {
  CHAT: 'Nhắn tin',
  VIDEO: 'Gọi video',
  IN_PERSON: 'Khám trực tiếp',
}

// Patient summary access window: granted only while PAID or IN_PROGRESS.
const SUMMARY_ACCESS: ConsultationStatus[] = ['PAID', 'IN_PROGRESS']
// Statuses where the doctor may append notes.
const NOTE_WRITABLE: ConsultationStatus[] = ['PAID', 'IN_PROGRESS']
// Statuses where a consultation can still be cancelled.
const CANCELLABLE: ConsultationStatus[] = ['REQUESTED', 'CONFIRMED', 'PAID', 'IN_PROGRESS']

const NOTE_TYPE_OPTIONS = [
  { value: 'recommendation', label: 'Khuyến nghị' },
  { value: 'observation', label: 'Quan sát' },
  { value: 'follow_up', label: 'Theo dõi tiếp' },
]

function friendlyActionError(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 409)
      return 'Không thể thực hiện: trạng thái buổi tư vấn đã thay đổi. Vui lòng tải lại trang.'
    if (err.status === 403)
      return 'Bạn cần xác thực đa yếu tố (MFA) hoặc không có quyền thực hiện thao tác này.'
    return err.detail || 'Đã có lỗi xảy ra. Vui lòng thử lại.'
  }
  return 'Đã có lỗi xảy ra. Vui lòng thử lại.'
}

export default function DoctorConsultationDetailPage() {
  const router = useRouter()
  const params = useParams<{ id: string }>()
  const id = params.id

  const [consultation, setConsultation] = React.useState<ConsultationOut | null>(null)
  const [loading, setLoading] = React.useState(true)
  const [loadError, setLoadError] = React.useState<string | null>(null)

  const [busy, setBusy] = React.useState(false)
  const [actionError, setActionError] = React.useState<string | null>(null)

  const [showCancel, setShowCancel] = React.useState(false)
  const [cancelReason, setCancelReason] = React.useState('')

  const load = React.useCallback(() => {
    setLoading(true)
    setLoadError(null)
    getConsultation(id)
      .then(setConsultation)
      .catch((err: unknown) =>
        setLoadError(err instanceof Error ? err.message : 'Không tìm thấy buổi tư vấn')
      )
      .finally(() => setLoading(false))
  }, [id])

  React.useEffect(() => {
    load()
  }, [load])

  const runAction = async (fn: (id: string) => Promise<ConsultationOut>) => {
    setBusy(true)
    setActionError(null)
    try {
      const updated = await fn(id)
      setConsultation(updated)
    } catch (err) {
      setActionError(friendlyActionError(err))
    } finally {
      setBusy(false)
    }
  }

  const handleCancel = async () => {
    setBusy(true)
    setActionError(null)
    try {
      const updated = await cancelConsultation(id, cancelReason.trim() || undefined)
      setConsultation(updated)
      setShowCancel(false)
      setCancelReason('')
    } catch (err) {
      setActionError(friendlyActionError(err))
    } finally {
      setBusy(false)
    }
  }

  if (loading) {
    return (
      <div className="p-6">
        <PageLoading label="Đang tải buổi tư vấn..." />
      </div>
    )
  }

  if (loadError || !consultation) {
    return (
      <div className="p-6">
        <ErrorState
          title="Không thể tải buổi tư vấn"
          message={loadError ?? 'Không tìm thấy buổi tư vấn'}
          onRetry={load}
        />
      </div>
    )
  }

  const c = consultation
  const status = c.status
  const primaryAvailable = status === 'REQUESTED' || status === 'PAID' || status === 'IN_PROGRESS'
  const hasActions = primaryAvailable || CANCELLABLE.includes(status)

  const actionProps: StateActionsProps = {
    status,
    busy,
    showCancel,
    cancelReason,
    onSetShowCancel: setShowCancel,
    onSetCancelReason: setCancelReason,
    onRun: runAction,
    onCancel: handleCancel,
    actionError,
  }

  return (
    <div className="p-4 sm:p-6 pb-28 lg:pb-6">
      <div className="flex items-center gap-3">
        <button
          type="button"
          aria-label="Quay lại"
          onClick={() => router.push('/doctor/consultations')}
          className="flex h-9 w-9 items-center justify-center rounded-md border border-border text-text-muted hover:bg-secondary-100"
        >
          <ArrowLeft className="h-5 w-5" />
        </button>
        <PageHeader title="Chi tiết buổi tư vấn" />
      </div>

      {/* Responsive split: summary (left) + actions/notes (right) on lg; stacked on mobile. */}
      <div className="mt-6 lg:grid lg:grid-cols-[minmax(0,1fr)_360px] lg:items-start lg:gap-6">
        {/* Left column — consultation info + patient summary */}
        <div className="min-w-0 space-y-6">
          {/* ── Consultation info ── */}
          <Card padding="lg">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <ConsultationStatusBadge status={status} />
              <span className="text-body-sm text-text-muted">
                {TYPE_LABELS[c.consultation_type] ?? c.consultation_type}
              </span>
            </div>

            <p className="mt-3 text-heading-lg font-bold text-text">
              {formatVnd(c.consultation_price)}
            </p>

            <dl className="mt-4 grid grid-cols-1 gap-x-8 gap-y-2 text-body-sm sm:grid-cols-2">
              <InfoRow label="Mã tư vấn" value={c.id.slice(0, 8).toUpperCase()} />
              <InfoRow label="Tạo lúc" value={formatDateTime(c.created_at) ?? '—'} />
              {c.confirmed_at && (
                <InfoRow label="Xác nhận" value={formatDateTime(c.confirmed_at) ?? '—'} />
              )}
              {c.paid_at && <InfoRow label="Thanh toán" value={formatDateTime(c.paid_at) ?? '—'} />}
              {c.started_at && (
                <InfoRow label="Bắt đầu" value={formatDateTime(c.started_at) ?? '—'} />
              )}
              {c.completed_at && (
                <InfoRow label="Hoàn thành" value={formatDateTime(c.completed_at) ?? '—'} />
              )}
              {c.cancelled_at && (
                <InfoRow label="Huỷ lúc" value={formatDateTime(c.cancelled_at) ?? '—'} />
              )}
            </dl>

            {c.chief_complaint && (
              <div className="mt-4 rounded-lg bg-secondary-50 px-4 py-3">
                <p className="text-body-xs font-semibold text-text-muted">Lý do tư vấn</p>
                <p className="mt-0.5 whitespace-pre-line text-body-sm text-text">
                  {c.chief_complaint}
                </p>
              </div>
            )}
            {c.patient_note && (
              <div className="mt-3 rounded-lg bg-secondary-50 px-4 py-3">
                <p className="text-body-xs font-semibold text-text-muted">Ghi chú của bệnh nhân</p>
                <p className="mt-0.5 whitespace-pre-line text-body-sm text-text">
                  {c.patient_note}
                </p>
              </div>
            )}
            {c.cancel_reason && (
              <div className="mt-3 rounded-lg bg-danger-light px-4 py-3">
                <p className="text-body-xs font-semibold text-danger">Lý do huỷ</p>
                <p className="mt-0.5 text-body-sm text-text">{c.cancel_reason}</p>
              </div>
            )}

            {status === 'CONFIRMED' && (
              <p className="mt-4 text-body-sm text-text-muted">
                Đang chờ bệnh nhân thanh toán để bắt đầu buổi tư vấn.
              </p>
            )}
          </Card>

          {/* ── Patient summary ── */}
          <PatientSummaryPanel consultationId={id} status={status} />
        </div>

        {/* Right column — actions (desktop) + clinical notes */}
        <div className="mt-6 space-y-6 lg:mt-0 lg:sticky lg:top-6">
          {/* Desktop actions panel — the mobile equivalent is the sticky bar below. */}
          {hasActions && (
            <Card padding="md" className="hidden lg:block">
              <h2 className="mb-3 text-heading-sm font-semibold text-text">Thao tác</h2>
              <StateActions {...actionProps} variant="panel" />
            </Card>
          )}

          {/* ── Clinical notes (append-only) ── */}
          <NotesPanel consultationId={id} status={status} />
        </div>
      </div>

      <div className="mt-6">
        <MarketplaceDisclaimer />
      </div>

      {/* Mobile sticky quick-action bar — state-machine actions at the bottom. */}
      {hasActions && (
        <div className="fixed inset-x-0 bottom-0 z-30 border-t border-border bg-surface/95 px-4 py-3 backdrop-blur lg:hidden">
          <StateActions {...actionProps} variant="bar" />
        </div>
      )}
    </div>
  )
}

// ── State-machine actions (shared by desktop panel + mobile sticky bar) ───────

interface StateActionsProps {
  status: ConsultationStatus
  busy: boolean
  showCancel: boolean
  cancelReason: string
  actionError: string | null
  onSetShowCancel: (v: boolean) => void
  onSetCancelReason: (v: string) => void
  onRun: (fn: (id: string) => Promise<ConsultationOut>) => void
  onCancel: () => void
}

function StateActions({
  status,
  busy,
  showCancel,
  cancelReason,
  actionError,
  onSetShowCancel,
  onSetCancelReason,
  onRun,
  onCancel,
  variant,
}: StateActionsProps & { variant: 'panel' | 'bar' }) {
  const isBar = variant === 'bar'
  const canCancel = CANCELLABLE.includes(status)
  const primaryClass = isBar ? 'flex-1' : undefined

  return (
    <div>
      {actionError && (
        <div className="mb-3">
          <Alert variant="danger" title="Thao tác thất bại">
            {actionError}
          </Alert>
        </div>
      )}

      {showCancel ? (
        <div className={isBar ? undefined : 'rounded-lg border border-border p-4'}>
          <p className="text-body-sm font-medium text-text">Xác nhận huỷ buổi tư vấn?</p>
          <Textarea
            className="mt-2"
            placeholder="Lý do huỷ (không bắt buộc)…"
            rows={2}
            maxLength={255}
            showCount
            value={cancelReason}
            onChange={(e) => onSetCancelReason(e.target.value)}
            fullWidth
          />
          <div className="mt-3 flex gap-2">
            <Button type="button" variant="danger" loading={busy} onClick={onCancel}>
              Xác nhận huỷ
            </Button>
            <Button
              type="button"
              variant="ghost"
              disabled={busy}
              onClick={() => {
                onSetShowCancel(false)
                onSetCancelReason('')
              }}
            >
              Không
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex flex-wrap gap-2">
          {status === 'REQUESTED' && (
            <Button
              type="button"
              variant="primary"
              loading={busy}
              className={primaryClass}
              leftIcon={<CheckCircle2 className="h-4 w-4" />}
              onClick={() => onRun(confirmConsultation)}
            >
              Xác nhận
            </Button>
          )}
          {status === 'PAID' && (
            <Button
              type="button"
              variant="primary"
              loading={busy}
              className={primaryClass}
              leftIcon={<PlayCircle className="h-4 w-4" />}
              onClick={() => onRun(startConsultation)}
            >
              Bắt đầu tư vấn
            </Button>
          )}
          {status === 'IN_PROGRESS' && (
            <Button
              type="button"
              variant="primary"
              loading={busy}
              className={primaryClass}
              leftIcon={<Flag className="h-4 w-4" />}
              onClick={() => onRun(completeConsultation)}
            >
              Hoàn thành
            </Button>
          )}
          {canCancel && (
            <Button
              type="button"
              variant="outline"
              disabled={busy}
              leftIcon={<XCircle className="h-4 w-4" />}
              onClick={() => onSetShowCancel(true)}
            >
              Huỷ buổi tư vấn
            </Button>
          )}
        </div>
      )}
    </div>
  )
}

// ── Info row ──────────────────────────────────────────────────────────────────

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between border-b border-border/60 py-1 last:border-0">
      <dt className="text-text-muted">{label}</dt>
      <dd className="font-medium text-text">{value}</dd>
    </div>
  )
}

// ── Patient summary panel ─────────────────────────────────────────────────────

function PatientSummaryPanel({
  consultationId,
  status,
}: {
  consultationId: string
  status: ConsultationStatus
}) {
  const hasAccess = SUMMARY_ACCESS.includes(status)
  const [summary, setSummary] = React.useState<PatientSummaryOut | null>(null)
  const [loading, setLoading] = React.useState(hasAccess)
  const [forbidden, setForbidden] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  React.useEffect(() => {
    if (!hasAccess) {
      setLoading(false)
      return
    }
    let cancelled = false
    setLoading(true)
    setForbidden(false)
    setError(null)
    getPatientSummary(consultationId)
      .then((data) => {
        if (!cancelled) setSummary(data)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        if (err instanceof ApiError && err.status === 403) setForbidden(true)
        else setError(err instanceof Error ? err.message : 'Không thể tải hồ sơ bệnh nhân')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [consultationId, hasAccess])

  return (
    <section>
      <h2 className="mb-2 text-heading-sm font-semibold text-text">Hồ sơ bệnh nhân</h2>

      {!hasAccess || forbidden ? (
        <Card padding="lg">
          <div className="flex items-start gap-3">
            <Lock className="mt-0.5 h-5 w-5 shrink-0 text-text-subtle" aria-hidden="true" />
            <div>
              <p className="text-body-sm font-medium text-text">Chưa có quyền xem hồ sơ</p>
              <p className="mt-0.5 text-body-sm text-text-muted">
                Hồ sơ bệnh nhân chỉ hiển thị sau khi bệnh nhân thanh toán và trước khi buổi tư vấn
                kết thúc (chưa thanh toán / phiên đã kết thúc).
              </p>
            </div>
          </div>
        </Card>
      ) : loading ? (
        <Card padding="lg">
          <SkeletonText lines={4} lineWidths={['70%', '55%', '60%', '40%']} />
        </Card>
      ) : error ? (
        <Alert variant="danger" title={error} />
      ) : summary ? (
        <SummaryBody summary={summary} />
      ) : null}
    </section>
  )
}

function SummaryBody({ summary }: { summary: PatientSummaryOut }) {
  const score = summary.metabolic_score
  return (
    <div className="space-y-3">
      {/* Metabolic score */}
      <Card padding="md">
        <SummaryHeading icon={<Gauge className="h-4 w-4" />} title="Điểm chuyển hoá" />
        {score?.latest_score != null ? (
          <div className="mt-1 flex items-baseline gap-2">
            <span className="text-heading-md font-bold text-text">{score.latest_score}</span>
            {score.trend && (
              <span className="text-body-sm text-text-muted">Xu hướng: {score.trend}</span>
            )}
            {score.recorded_at && (
              <span className="text-body-xs text-text-subtle">
                {formatDateTime(score.recorded_at)}
              </span>
            )}
          </div>
        ) : (
          <EmptyLine />
        )}
      </Card>

      {/* Vitals */}
      <Card padding="md">
        <SummaryHeading icon={<Activity className="h-4 w-4" />} title="Chỉ số sinh tồn" />
        {summary.vitals?.latest?.length ? (
          <ul className="mt-1 space-y-1 text-body-sm">
            {summary.vitals.latest.map((v, i) => (
              <li key={i} className="flex items-center justify-between">
                <span className="text-text-muted">{v.metric_type ?? 'Chỉ số'}</span>
                <span className="font-medium text-text">
                  {v.value ?? '—'}
                  {v.unit ? ` ${v.unit}` : ''}
                  {v.measured_at ? ` · ${formatDateTime(v.measured_at)}` : ''}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyLine />
        )}
        {summary.vitals?.trend && (
          <p className="mt-1 text-body-xs text-text-subtle">Xu hướng: {summary.vitals.trend}</p>
        )}
      </Card>

      {/* Lab documents */}
      <Card padding="md">
        <SummaryHeading icon={<FlaskConical className="h-4 w-4" />} title="Kết quả xét nghiệm" />
        {summary.lab_documents?.length ? (
          <ul className="mt-1 space-y-1 text-body-sm">
            {summary.lab_documents.map((d, i) => (
              <li key={d.id ?? i} className="flex items-center justify-between">
                <span className="truncate text-text">{d.lab_name ?? 'Tài liệu'}</span>
                <span className="shrink-0 text-text-muted">
                  {formatDateTime(d.created_at) ?? d.status ?? '—'}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyLine />
        )}
      </Card>

      {/* Medications */}
      <Card padding="md">
        <SummaryHeading icon={<Pill className="h-4 w-4" />} title="Thuốc đang dùng" />
        {summary.medications?.length ? (
          <ul className="mt-1 space-y-1 text-body-sm">
            {summary.medications.map((m, i) => (
              <li key={m.id ?? i} className="flex items-center justify-between">
                <span className="text-text">{m.name ?? 'Thuốc'}</span>
                <span className="text-text-muted">
                  {[m.dose, m.note].filter(Boolean).join(' · ') || '—'}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyLine />
        )}
      </Card>

      {/* Symptoms */}
      <Card padding="md">
        <SummaryHeading icon={<Activity className="h-4 w-4" />} title="Triệu chứng" />
        {summary.symptoms?.length ? (
          <ul className="mt-1 space-y-1 text-body-sm">
            {summary.symptoms.map((s, i) => (
              <li key={s.id ?? i} className="flex items-center justify-between">
                <span className="text-text">{s.description ?? 'Triệu chứng'}</span>
                <span className="text-text-muted">
                  {[s.severity, s.reported_at ? formatDateTime(s.reported_at) : null]
                    .filter(Boolean)
                    .join(' · ') || '—'}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyLine />
        )}
      </Card>

      {/* Nutrition */}
      <Card padding="md">
        <SummaryHeading icon={<Utensils className="h-4 w-4" />} title="Dinh dưỡng" />
        {summary.nutrition?.length ? (
          <ul className="mt-1 space-y-1 text-body-sm">
            {summary.nutrition.map((n, i) => (
              <li key={n.id ?? i} className="flex items-center justify-between">
                <span className="text-text">{n.meal_type ?? 'Bữa ăn'}</span>
                <span className="truncate text-text-muted">
                  {n.description ?? (n.logged_at ? formatDateTime(n.logged_at) : '—')}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyLine />
        )}
      </Card>

      {/* Upcoming appointments */}
      <Card padding="md">
        <SummaryHeading icon={<Calendar className="h-4 w-4" />} title="Lịch hẹn sắp tới" />
        {summary.upcoming_appointments?.length ? (
          <ul className="mt-1 space-y-1 text-body-sm">
            {summary.upcoming_appointments.map((a, i) => (
              <li key={a.id ?? i} className="flex items-center justify-between">
                <span className="text-text">{a.notes ?? 'Lịch hẹn'}</span>
                <span className="text-text-muted">
                  {formatDateTime(a.slot_start) ?? a.status ?? '—'}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyLine />
        )}
      </Card>

      {/* Active care plans */}
      <Card padding="md">
        <SummaryHeading icon={<ClipboardList className="h-4 w-4" />} title="Kế hoạch điều trị" />
        {summary.active_care_plans?.length ? (
          <ul className="mt-1 space-y-1.5 text-body-sm">
            {summary.active_care_plans.map((p, i) => (
              <li key={p.id ?? i}>
                <p className="font-medium text-text">{p.title ?? 'Kế hoạch'}</p>
                {p.version != null && <p className="text-text-muted">Phiên bản {p.version}</p>}
              </li>
            ))}
          </ul>
        ) : (
          <EmptyLine />
        )}
      </Card>

      {summary.generated_at && (
        <p className="text-body-xs text-text-subtle">
          Tổng hợp lúc {formatDateTime(summary.generated_at)}
        </p>
      )}
    </div>
  )
}

function SummaryHeading({ icon, title }: { icon: React.ReactNode; title: string }) {
  return (
    <div className="flex items-center gap-2 text-body-sm font-semibold text-text">
      <span className="text-primary" aria-hidden="true">
        {icon}
      </span>
      {title}
    </div>
  )
}

function EmptyLine() {
  return <p className="mt-1 text-body-sm text-text-subtle">Không có dữ liệu.</p>
}

// ── Notes panel (append-only) ─────────────────────────────────────────────────

function NotesPanel({
  consultationId,
  status,
}: {
  consultationId: string
  status: ConsultationStatus
}) {
  const canWrite = NOTE_WRITABLE.includes(status)
  const [notes, setNotes] = React.useState<NoteOut[]>([])
  const [loading, setLoading] = React.useState(true)
  const [listError, setListError] = React.useState<string | null>(null)

  const [content, setContent] = React.useState('')
  const [noteType, setNoteType] = React.useState('recommendation')
  const [saving, setSaving] = React.useState(false)
  const [saveError, setSaveError] = React.useState<string | null>(null)

  const loadNotes = React.useCallback(() => {
    setLoading(true)
    setListError(null)
    listNotes(consultationId)
      .then((data) => setNotes([...data].sort(byNewest)))
      .catch((err: unknown) => {
        // 403 (e.g. outside access window / MFA) → treat as no notes visible.
        if (err instanceof ApiError && err.status === 403) setNotes([])
        else setListError(err instanceof Error ? err.message : 'Không thể tải ghi chú')
      })
      .finally(() => setLoading(false))
  }, [consultationId])

  React.useEffect(() => {
    loadNotes()
  }, [loadNotes])

  const handleSubmit = async () => {
    const trimmed = content.trim()
    if (trimmed.length < 1) {
      setSaveError('Vui lòng nhập nội dung ghi chú.')
      return
    }
    setSaving(true)
    setSaveError(null)
    try {
      const created = await createNote(consultationId, { content: trimmed, note_type: noteType })
      setNotes((prev) => [created, ...prev])
      setContent('')
      setNoteType('recommendation')
    } catch (err) {
      setSaveError(friendlyActionError(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <section>
      <div className="mb-2 flex items-center gap-2">
        <FileText className="h-5 w-5 text-text-muted" aria-hidden="true" />
        <h2 className="text-heading-sm font-semibold text-text">Ghi chú lâm sàng</h2>
      </div>

      {canWrite && (
        <Card padding="md" className="mb-3">
          <Alert variant="info" className="mb-3">
            Ghi chú không thể chỉnh sửa hay xoá sau khi lưu (append-only).
          </Alert>
          <div className="max-w-xs">
            <Select
              label="Loại ghi chú"
              options={NOTE_TYPE_OPTIONS}
              value={noteType}
              onValueChange={setNoteType}
            />
          </div>
          <Textarea
            className="mt-3"
            label="Nội dung"
            placeholder="Nhập khuyến nghị / quan sát lâm sàng…"
            rows={4}
            maxLength={8000}
            showCount
            value={content}
            onChange={(e) => setContent(e.target.value)}
            fullWidth
          />
          {saveError && <p className="mt-2 text-body-sm font-medium text-danger">{saveError}</p>}
          <div className="mt-3 flex justify-end">
            <Button type="button" variant="primary" loading={saving} onClick={handleSubmit}>
              Lưu ghi chú
            </Button>
          </div>
        </Card>
      )}

      {loading ? (
        <Card padding="md">
          <SkeletonText lines={2} lineWidths={['80%', '50%']} />
        </Card>
      ) : listError ? (
        <Alert variant="danger" title={listError} />
      ) : notes.length === 0 ? (
        <Card padding="md">
          <p className="text-body-sm text-text-muted">Chưa có ghi chú nào.</p>
        </Card>
      ) : (
        <div className="space-y-2.5">
          {notes.map((n) => (
            <Card key={n.id} padding="md">
              <div className="flex items-center justify-between">
                <span className="rounded-full bg-secondary-100 px-2 py-0.5 text-body-xs font-medium text-secondary-700">
                  {noteTypeLabel(n.note_type)}
                </span>
                {n.created_at && (
                  <span className="text-body-xs text-text-subtle">
                    {formatDateTime(n.created_at)}
                  </span>
                )}
              </div>
              <p className="mt-2 whitespace-pre-line text-body-sm text-text">{n.content}</p>
            </Card>
          ))}
        </div>
      )}
    </section>
  )
}

function byNewest(a: NoteOut, b: NoteOut): number {
  const ta = a.created_at ? new Date(a.created_at).getTime() : 0
  const tb = b.created_at ? new Date(b.created_at).getTime() : 0
  return tb - ta
}

function noteTypeLabel(type: string): string {
  const found = NOTE_TYPE_OPTIONS.find((o) => o.value === type)
  return found?.label ?? type
}
