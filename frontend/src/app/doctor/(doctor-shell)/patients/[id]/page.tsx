'use client'

import * as React from 'react'
import { useParams, useRouter } from 'next/navigation'
import { FileText, Microscope, Activity } from 'lucide-react'
import {
  PageHeader,
  PageLoading,
  ErrorState,
  EmptyState,
  Card,
  CardHeader,
  CardTitle,
  CardContent,
  Tabs,
  TabsContent,
  Badge,
} from '@/design-system'
import {
  PatientSummaryHeader,
  type PatientProfile as SummaryPatientProfile,
} from '@/design-system/components/healthcare/PatientSummaryHeader'
import { TimelineItem } from '@/design-system/components/healthcare/TimelineItem'
import type { TimelineEvent as DSTimelineEvent } from '@/design-system/components/healthcare/TimelineItem'
import {
  getPatientProfile,
  getLatestMetabolicScore,
  getLabs,
  type PatientProfile,
  type MetabolicScore,
  type LabListResponse,
} from '@/lib/api/patient'
import {
  getPatientTimeline,
  type TimelineEvent,
  type TimelineEventType as APITimelineEventType,
} from '@/lib/api/doctor'
import { ApiError } from '@/lib/api/client'
import { formatRelativeTime } from '@/lib/utils'
import { DoctorAssistantPanel } from './DoctorAssistantPanel'

const NO_CONSENT_MESSAGE = 'Chưa có quyền xem hồ sơ bệnh nhân này (cần bệnh nhân cấp quyền).'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function mapRiskSegment(seg: PatientProfile['risk_segment']): SummaryPatientProfile['riskLevel'] {
  if (seg === 'very_high') return 'high'
  return (seg ?? 'unknown') as SummaryPatientProfile['riskLevel']
}

function mapApiEventType(eventType: APITimelineEventType): DSTimelineEvent['type'] {
  switch (eventType) {
    case 'lab_uploaded':
    case 'lab_approved':
      return 'lab_result'
    case 'ai_session':
      return 'ai_session'
    case 'care_plan_created':
    case 'care_plan_approved':
      return 'care_plan'
    case 'consent_granted':
    case 'consent_revoked':
      return 'consent'
    case 'metric_logged':
    default:
      return 'system'
  }
}

function mapEventTitle(eventType: APITimelineEventType): string {
  switch (eventType) {
    case 'lab_uploaded':
      return 'Tải lên xét nghiệm'
    case 'lab_approved':
      return 'Xét nghiệm được duyệt'
    case 'metric_logged':
      return 'Ghi nhận chỉ số'
    case 'care_plan_created':
      return 'Tạo kế hoạch điều trị'
    case 'care_plan_approved':
      return 'Kế hoạch điều trị được duyệt'
    case 'ai_session':
      return 'Phiên tư vấn AI'
    case 'consent_granted':
      return 'Cấp quyền đồng ý'
    case 'consent_revoked':
      return 'Thu hồi quyền đồng ý'
    default:
      return 'Sự kiện hệ thống'
  }
}

function mapApiEvent(event: TimelineEvent, isLast: boolean): DSTimelineEvent & { isLast: boolean } {
  return {
    id: event.id,
    date: event.occurred_at,
    type: mapApiEventType(event.event_type),
    title: mapEventTitle(event.event_type),
    description: event.description,
    actor: event.actor ?? undefined,
    isLast,
  }
}

const RISK_LABEL: Record<MetabolicScore['risk_level'], string> = {
  low: 'Thấp',
  medium: 'Trung bình',
  high: 'Cao',
  very_high: 'Rất cao',
}

const RISK_BADGE_VARIANT = {
  low: 'success',
  medium: 'warning',
  high: 'danger',
  very_high: 'danger',
} as const

const LAB_STATUS_LABEL: Record<string, string> = {
  pending_review: 'Chờ duyệt',
  approved: 'Đã duyệt',
  rejected: 'Từ chối',
  request_info: 'Yêu cầu thêm thông tin',
}

// ---------------------------------------------------------------------------
// PatientDetailPage
// ---------------------------------------------------------------------------

export default function PatientDetailPage() {
  const params = useParams<{ id: string }>()
  const patientId = params.id
  const router = useRouter()

  const [profile, setProfile] = React.useState<PatientProfile | null>(null)
  const [metabolicScore, setMetabolicScore] = React.useState<MetabolicScore | null>(null)
  const [labsResponse, setLabsResponse] = React.useState<LabListResponse | null>(null)
  const [timeline, setTimeline] = React.useState<TimelineEvent[]>([])
  const [timelineForbidden, setTimelineForbidden] = React.useState(false)
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)
  const [noConsent, setNoConsent] = React.useState(false)

  const load = React.useCallback(async () => {
    setLoading(true)
    setError(null)
    setNoConsent(false)
    setTimelineForbidden(false)

    // The profile load gates the whole screen: a 403 here means the doctor
    // lacks consent for this patient.
    let prof: PatientProfile
    try {
      prof = await getPatientProfile(patientId)
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        setNoConsent(true)
      } else {
        setError('Không thể tải thông tin bệnh nhân. Vui lòng thử lại.')
      }
      setLoading(false)
      return
    }
    setProfile(prof)

    // Secondary resources degrade gracefully — a 403 on any of them shows an
    // empty/no-access section rather than blocking the whole page.
    const [score, labs, tl] = await Promise.all([
      getLatestMetabolicScore(patientId).catch(() => null),
      getLabs(patientId, { limit: 5 }).catch(() => null),
      getPatientTimeline(patientId, { limit: 20 }).catch((err: unknown) => {
        if (err instanceof ApiError && err.status === 403) setTimelineForbidden(true)
        return [] as TimelineEvent[]
      }),
    ])
    setMetabolicScore(score)
    setLabsResponse(labs)
    setTimeline(tl)
    setLoading(false)
  }, [patientId])

  React.useEffect(() => {
    load()
  }, [load])

  if (loading) {
    return (
      <div className="p-6">
        <PageLoading label="Đang tải thông tin bệnh nhân..." />
      </div>
    )
  }

  if (noConsent) {
    return (
      <div className="p-6 space-y-4">
        <ErrorState title="Chưa có quyền truy cập" message={NO_CONSENT_MESSAGE} variant="page" />
        <div className="text-center">
          <button
            type="button"
            onClick={() => router.push('/doctor/patients')}
            className="text-body-sm text-primary hover:underline underline-offset-2"
          >
            Quay lại danh sách bệnh nhân
          </button>
        </div>
      </div>
    )
  }

  if (error || !profile) {
    return (
      <div className="p-6">
        <ErrorState
          title="Lỗi tải dữ liệu"
          message={error ?? 'Không tìm thấy bệnh nhân.'}
          onRetry={load}
          variant="page"
        />
      </div>
    )
  }

  // Build PatientSummaryHeader-compatible profile
  const summaryPatient: SummaryPatientProfile = {
    id: profile.id,
    fullName: profile.full_name ?? 'Không rõ tên',
    dateOfBirth: profile.dob,
    gender: profile.gender,
    phone: profile.phone ?? undefined,
    address: undefined,
    avatarUrl: undefined,
    riskLevel: mapRiskSegment(profile.risk_segment),
    riskScore: metabolicScore != null ? Math.round(metabolicScore.score) : undefined,
    primaryDiagnosis: profile.known_conditions ?? undefined,
    primaryDoctor: undefined,
    lastVisit: undefined,
    activePlanCount: 0,
    pendingReviewCount:
      labsResponse?.items.filter((l) => l.status === 'pending_review').length ?? 0,
  }

  const TABS = [
    { value: 'overview', label: 'Tổng quan', icon: <Activity className="h-4 w-4" /> },
    {
      value: 'labs',
      label: 'Xét nghiệm',
      icon: <Microscope className="h-4 w-4" />,
      badge: labsResponse?.total,
    },
    {
      value: 'timeline',
      label: 'Dòng thời gian',
      icon: <FileText className="h-4 w-4" />,
      badge: timeline.length,
    },
  ]

  return (
    <div className="flex flex-col">
      {/* Page header — title + back */}
      <div className="px-6 pt-6">
        <PageHeader
          title={profile.full_name ?? 'Chi tiết bệnh nhân'}
          breadcrumbs={[
            { label: 'Danh sách bệnh nhân', href: '/doctor/patients' },
            { label: profile.full_name ?? patientId },
          ]}
          actions={
            <button
              type="button"
              onClick={() => router.push('/doctor/patients')}
              className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-surface px-3 py-2 text-body-sm font-medium text-text hover:bg-secondary-50 transition-colors"
            >
              Quay lại
            </button>
          }
        />
      </div>

      {/* Patient summary header */}
      <PatientSummaryHeader
        patient={summaryPatient}
        onBack={() => router.push('/doctor/patients')}
        showBackButton={false}
      />

      {/* Tabs */}
      <div className="px-6 pb-6 mt-4">
        <Tabs defaultValue="overview" variant="line" tabs={TABS}>
          {/* ── Tổng quan ─────────────────────────────────────────────── */}
          <TabsContent value="overview">
            <div className="grid gap-4 lg:grid-cols-2">
              {/* Metabolic score card */}
              <Card>
                <CardHeader>
                  <CardTitle>Điểm chuyển hóa</CardTitle>
                </CardHeader>
                <CardContent>
                  {metabolicScore ? (
                    <div className="space-y-3">
                      <div className="flex items-center gap-3">
                        <span className="text-display-sm font-bold text-text">
                          {Math.round(metabolicScore.score)}
                        </span>
                        <Badge variant={RISK_BADGE_VARIANT[metabolicScore.risk_level]} size="md">
                          {RISK_LABEL[metabolicScore.risk_level]}
                        </Badge>
                      </div>
                      <p className="text-body-xs text-text-muted">
                        Tính toán lúc: {formatRelativeTime(metabolicScore.calculated_at)}
                      </p>
                      {metabolicScore.top_risks.length > 0 && (
                        <div>
                          <p className="text-body-sm font-medium text-text mb-1.5">
                            Yếu tố nguy cơ chính:
                          </p>
                          <ul className="flex flex-wrap gap-1.5">
                            {metabolicScore.top_risks.map((risk) => (
                              <li key={risk}>
                                <span className="inline-flex items-center rounded-full bg-danger-light border border-danger/20 px-2.5 py-0.5 text-body-xs text-danger font-medium">
                                  {risk}
                                </span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {metabolicScore.suggested_actions.length > 0 && (
                        <div>
                          <p className="text-body-sm font-medium text-text mb-1.5">Khuyến nghị:</p>
                          <ul className="space-y-1">
                            {metabolicScore.suggested_actions.map((action) => (
                              <li
                                key={action}
                                className="flex items-start gap-2 text-body-xs text-text-muted"
                              >
                                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
                                {action}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  ) : (
                    <EmptyState
                      title="Chưa có điểm chuyển hóa"
                      description="Bệnh nhân chưa có dữ liệu điểm chuyển hóa."
                      size="sm"
                    />
                  )}
                </CardContent>
              </Card>

              {/* Patient info card */}
              <Card>
                <CardHeader>
                  <CardTitle>Thông tin bệnh nhân</CardTitle>
                </CardHeader>
                <CardContent>
                  <dl className="space-y-3">
                    {[
                      {
                        label: 'Chiều cao',
                        value: profile.height_cm != null ? `${profile.height_cm} cm` : null,
                      },
                      {
                        label: 'Cân nặng',
                        value: profile.weight_kg != null ? `${profile.weight_kg} kg` : null,
                      },
                      {
                        label: 'Vòng eo',
                        value: profile.waist_cm != null ? `${profile.waist_cm} cm` : null,
                      },
                      { label: 'Bệnh lý đã biết', value: profile.known_conditions },
                      { label: 'Dị ứng', value: profile.allergies },
                    ].map(({ label, value }) =>
                      value ? (
                        <div key={label} className="flex items-start justify-between gap-4">
                          <dt className="text-body-sm text-text-muted shrink-0">{label}</dt>
                          <dd className="text-body-sm font-medium text-text text-right">{value}</dd>
                        </div>
                      ) : null
                    )}
                    {!profile.height_cm &&
                      !profile.weight_kg &&
                      !profile.known_conditions &&
                      !profile.allergies && (
                        <p className="text-body-sm text-text-muted">Chưa có thông tin bổ sung.</p>
                      )}
                  </dl>
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          {/* ── Xét nghiệm ────────────────────────────────────────────── */}
          <TabsContent value="labs">
            {labsResponse && labsResponse.items.length > 0 ? (
              <div className="space-y-4">
                {labsResponse.items.map((lab) => (
                  <Card key={lab.id}>
                    <CardHeader>
                      <div className="flex items-start justify-between gap-3 w-full">
                        <div className="min-w-0">
                          <CardTitle className="text-body-md">
                            {lab.file_name ?? 'Kết quả xét nghiệm'}
                          </CardTitle>
                          <p className="mt-0.5 text-body-xs text-text-muted">
                            {formatRelativeTime(lab.uploaded_at ?? lab.created_at ?? '')}
                          </p>
                        </div>
                        <Badge
                          variant={
                            lab.status === 'approved'
                              ? 'success'
                              : lab.status === 'rejected'
                                ? 'danger'
                                : lab.status === 'pending_review'
                                  ? 'warning'
                                  : 'default'
                          }
                          size="sm"
                        >
                          {LAB_STATUS_LABEL[lab.status] ?? lab.status}
                        </Badge>
                      </div>
                    </CardHeader>
                    <CardContent>
                      {/* AI explanation — amber panel */}
                      {lab.ai_explanation && (
                        <div className="mb-3 rounded-md bg-amber-50 border border-amber-200 p-3">
                          <p className="text-body-xs font-semibold text-amber-800 mb-1">
                            Giải thích AI
                          </p>
                          <p className="text-body-xs text-amber-700 leading-relaxed">
                            {lab.ai_explanation}
                          </p>
                        </div>
                      )}

                      {/* Doctor notes — green panel (only if approved) */}
                      {lab.doctor_notes && lab.status === 'approved' && (
                        <div className="rounded-md bg-green-50 border border-green-200 p-3">
                          <p className="text-body-xs font-semibold text-green-800 mb-1">
                            Ghi chú bác sĩ
                          </p>
                          <p className="text-body-xs text-green-700 leading-relaxed">
                            {lab.doctor_notes}
                          </p>
                        </div>
                      )}

                      {/* OCR text summary — field removed in backend schema update (PA-08) */}

                      {/* File link */}
                      {lab.file_url && (
                        <a
                          href={lab.file_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="mt-2 inline-flex items-center gap-1.5 text-body-xs text-primary hover:underline"
                        >
                          <Microscope className="h-3.5 w-3.5" aria-hidden="true" />
                          Xem file gốc
                        </a>
                      )}
                    </CardContent>
                  </Card>
                ))}
              </div>
            ) : (
              <Card>
                <EmptyState
                  icon={<Microscope />}
                  title="Chưa có kết quả xét nghiệm"
                  description="Bệnh nhân chưa tải lên kết quả xét nghiệm nào."
                  size="md"
                />
              </Card>
            )}
          </TabsContent>

          {/* ── Dòng thời gian ────────────────────────────────────────── */}
          <TabsContent value="timeline">
            {timelineForbidden ? (
              <Card>
                <EmptyState
                  icon={<Activity />}
                  title="Không có quyền xem dòng thời gian"
                  description="Cần bệnh nhân cấp quyền để xem lịch sử hoạt động."
                  size="md"
                />
              </Card>
            ) : timeline.length > 0 ? (
              <Card>
                <CardContent className="pt-5">
                  {timeline.map((event, idx) => {
                    const dsEvent = mapApiEvent(event, idx === timeline.length - 1)
                    return <TimelineItem key={dsEvent.id} event={dsEvent} isLast={dsEvent.isLast} />
                  })}
                </CardContent>
              </Card>
            ) : (
              <Card>
                <EmptyState
                  icon={<Activity />}
                  title="Chưa có hoạt động"
                  description="Bệnh nhân chưa có sự kiện nào được ghi lại."
                  size="md"
                />
              </Card>
            )}
          </TabsContent>
        </Tabs>

        {/* Patient-scoped AI assistant (collapsible; disabled shell in P0) */}
        <div className="mt-6">
          <DoctorAssistantPanel patientId={patientId} />
        </div>
      </div>
    </div>
  )
}
