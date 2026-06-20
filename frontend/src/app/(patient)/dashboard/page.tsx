'use client'

import { PatientEmptyState } from '@/components/patient'
import * as React from 'react'
import { useRouter } from 'next/navigation'
import { Bot, Pill, ClipboardList, ChevronRight } from 'lucide-react'
import {
  PageLoading,
  ErrorState,
  Alert,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Button,
  Badge,
  EmptyState,
  PatientMetricCard,
  RiskLevelBadge,
} from '@/design-system'
import type { RiskLevel } from '@/design-system'
import { useAuth } from '@/lib/auth/context'
import {
  getLatestMetabolicScore,
  getMedications,
  getMetrics,
  getCarePlans,
  getNotifications,
  getLabs,
  getPatientProfile,
  isProfileComplete,
  metricLabel,
  metricUnit,
} from '@/lib/api/patient'
import { useFeatureFlags } from '@/lib/api/features'
import type {
  MetabolicScore,
  Medication,
  HealthMetric,
  CarePlan,
  MetricType,
} from '@/lib/api/patient'
import { formatDate } from '@/lib/utils'

// ─── Helpers ─────────────────────────────────────────────────────────────────

function toMetricStatus(
  status: HealthMetric['status'],
): 'normal' | 'warning' | 'danger' | 'unknown' {
  if (status === 'normal') return 'normal'
  if (status === 'borderline') return 'warning'
  if (status === 'abnormal' || status === 'critical') return 'danger'
  return 'unknown'
}

function toRiskLevel(level: MetabolicScore['risk_level'] | null | undefined): RiskLevel {
  if (!level) return 'unknown'
  if (level === 'very_high') return 'high'
  return level as RiskLevel
}

function toMetricKey(type: MetricType): string {
  const map: Partial<Record<MetricType, string>> = {
    fasting_glucose: 'glucose',
    weight: 'weight',
    blood_pressure_systolic: 'blood_pressure',
    blood_pressure_diastolic: 'blood_pressure',
    heart_rate: 'heart_rate',
  }
  return map[type] ?? type
}

// ─── Dashboard state ──────────────────────────────────────────────────────────

interface DashboardData {
  metabolicScore: MetabolicScore | null
  medications: Medication[]
  metrics: HealthMetric[]
  carePlans: CarePlan[]
  unreadCount: number
  hasPendingLabs: boolean
  profileComplete: boolean
}

// ─── Dashboard page ───────────────────────────────────────────────────────────

export default function PatientDashboardPage() {
  const router = useRouter()
  const { user } = useAuth()
  const patientId = user?.patient_profile_id
  const flags = useFeatureFlags()

  const [data, setData] = React.useState<DashboardData | null>(null)
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)

  const load = React.useCallback(() => {
    if (!patientId) {
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)

    const metricTypes: MetricType[] = ['fasting_glucose', 'weight', 'blood_pressure_systolic']

    Promise.all([
      getLatestMetabolicScore(patientId),
      getMedications(patientId, { limit: 3 }),
      ...metricTypes.map((t) =>
        getMetrics(patientId, { metric_type: t, limit: 1 }).catch(() => ({
          items: [] as HealthMetric[],
          patient_id: patientId,
          total: 0,
        })),
      ),
      getCarePlans(patientId).catch(() => [] as CarePlan[]),
      getNotifications(patientId, { limit: 1 }).catch(() => [] as import('@/lib/api/patient').Notification[]),
      getLabs(patientId, { limit: 20 }).catch(() => ({
        items: [],
        patient_id: patientId,
        total: 0,
      })),
      getPatientProfile(patientId).catch(() => null),
    ])
      .then((results) => {
        const score = results[0] as MetabolicScore | null
        const medsResp = results[1] as { items?: Medication[] } | Medication[]
        const m0 = results[2] as { items?: HealthMetric[] }
        const m1 = results[3] as { items?: HealthMetric[] }
        const m2 = results[4] as { items?: HealthMetric[] }
        const carePlansRaw = results[5] as CarePlan[] | { items?: CarePlan[] }
        const notificationsRaw = results[6] as import('@/lib/api/patient').Notification[] | { items?: import('@/lib/api/patient').Notification[] }
        const labsRaw = results[7] as { items?: Array<{ status: string }> } | Array<{ status: string }>
        const profile = results[8] as import('@/lib/api/patient').PatientProfile | null

        // Safely extract arrays regardless of whether backend returns plain array or {items:[]}
        function safeItems<T>(v: T[] | { items?: T[] }): T[] {
          return Array.isArray(v) ? v : (v as { items?: T[] }).items ?? []
        }

        const latestMetrics: HealthMetric[] = [
          ...(m0.items ?? []).slice(0, 1),
          ...(m1.items ?? []).slice(0, 1),
          ...(m2.items ?? []).slice(0, 1),
        ]

        const meds = safeItems(medsResp)
        const plans = safeItems(carePlansRaw)
        const notifs = safeItems(notificationsRaw)
        const labItems = safeItems(labsRaw)

        setData({
          metabolicScore: score,
          medications: meds,
          metrics: latestMetrics,
          carePlans: plans.filter((p) => p.status === 'ACTIVE'),
          unreadCount: notifs.filter((n) => !n.is_read).length,
          hasPendingLabs: labItems.some((l) => l.status === 'pending_review'),
          profileComplete: isProfileComplete(profile),
        })
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [patientId])

  React.useEffect(() => {
    load()
  }, [load])

  if (!user) return null

  if (!patientId) {
    return (
      <div className="p-4 max-w-md mx-auto mt-10">
        <Alert variant="warning" title="Chưa có hồ sơ bệnh nhân">
          Tài khoản của bạn chưa được liên kết với hồ sơ bệnh nhân. Vui lòng liên hệ hỗ trợ để được trợ giúp.
        </Alert>
      </div>
    )
  }

  if (loading) {
    return <PageLoading label="Đang tải..." />
  }

  if (error || !data) {
    return (
      <ErrorState
        title="Không thể tải dữ liệu"
        message={error ?? 'Đã xảy ra lỗi không xác định'}
        onRetry={load}
      />
    )
  }

  const { metabolicScore, medications, metrics, carePlans, hasPendingLabs, profileComplete } = data
  const todayStr = formatDate(new Date())
  const activePlan = carePlans[0] ?? null
  // CarePlan.items[] removed — backend uses content:string, no task checklist

  return (
    <div className="p-4 lg:p-6 space-y-5 max-w-md mx-auto lg:max-w-2xl">

      {/* Greeting */}
      <div>
        <h1 className="text-heading-xl font-bold text-text">
          Xin chào, {user.full_name ?? user.email}!
        </h1>
        <p className="text-body-md text-text-muted mt-0.5">{todayStr}</p>
      </div>

      {/* Profile completion nudge (PR-A) */}
      {!profileComplete && (
        <Alert variant="mint" title="Hoàn thiện hồ sơ của bạn">
          <div className="flex flex-col gap-2">
            <span>Bổ sung ngày sinh, giới tính, chiều cao và cân nặng để cá nhân hoá theo dõi sức khỏe.</span>
            <div>
              <Button size="sm" variant="mint" onClick={() => router.push('/onboarding')}>
                Hoàn thiện ngay
              </Button>
            </div>
          </div>
        </Alert>
      )}

      {/* Pending lab alert */}
      {hasPendingLabs && (
        <Alert variant="warning" title="Xét nghiệm đang chờ bác sĩ duyệt">
          Bạn có xét nghiệm đang chờ bác sĩ xem xét. Kết quả sẽ sớm có.
        </Alert>
      )}

      {/* Risk / Metabolic score */}
      <Card variant="glass" padding="md">
        <CardContent>
          {metabolicScore ? (
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="text-body-md text-text-muted mb-1">Đánh giá sức khỏe</p>
                <p className="text-body-md font-medium text-text">
                  Điểm chuyển hóa:{' '}
                  <span className="font-bold">{metabolicScore.score}/100</span>
                </p>
              </div>
              <RiskLevelBadge
                level={toRiskLevel(metabolicScore.risk_level)}
                score={metabolicScore.score}
                showScore
                size="lg"
              />
            </div>
          ) : (
            <EmptyState
              size="sm"
              title="Chưa có điểm chuyển hóa"
              description="Điểm sẽ được tính sau khi bạn ghi đủ chỉ số sức khỏe."
            />
          )}
        </CardContent>
      </Card>

      {/* Health metrics grid */}
      <section aria-label="Chỉ số sức khỏe gần đây">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-heading-md font-semibold text-text">Chỉ số sức khỏe</h2>
          <Button variant="ghost" size="sm" onClick={() => router.push('/metrics')}>
            Xem tất cả
          </Button>
        </div>
        {metrics.length === 0 ? (
          <PatientEmptyState
            title="Chưa có chỉ số nào"
            description="Bắt đầu theo dõi sức khỏe bằng cách ghi chỉ số đầu tiên."
            cta={{ label: 'Ghi chỉ số', onClick: () => router.push('/metrics') }}
          />
        ) : (
          <div className="grid grid-cols-2 gap-3">
            {metrics.map((m) => (
              <PatientMetricCard
                key={m.id}
                metric={toMetricKey(m.metric_type)}
                label={metricLabel(m.metric_type)}
                value={m.value}
                unit={m.unit || metricUnit(m.metric_type)}
                status={toMetricStatus(m.status)}
                lastUpdated={m.measured_at ?? m.recorded_at}
                compact
                onClick={() => router.push(`/metrics?type=${m.metric_type}`)}
              />
            ))}
          </div>
        )}
      </section>

      {/* Medication reminder */}
      <section aria-label="Nhắc nhở thuốc">
        <Card variant="glass" padding="none">
          <CardHeader className="px-4 pt-4 pb-2">
            <div className="flex items-center gap-2">
              <Pill className="size-4 text-mint-600" aria-hidden="true" />
              <CardTitle className="text-heading-md font-semibold">Nhắc nhở thuốc</CardTitle>
            </div>
          </CardHeader>
          <CardContent className="px-4 pb-4">
            {medications.length === 0 ? (
              <EmptyState
                size="sm"
                title="Không có thuốc đang dùng"
                description="Bạn chưa có đơn thuốc nào đang hoạt động."
              />
            ) : (
              <div className="space-y-3">
                {medications.map((med) => (
                    <div
                      key={med.id}
                      className="flex items-start justify-between gap-3 rounded-lg p-3 bg-secondary-50"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="text-body-md font-medium text-text truncate">
                          {med.name}
                        </p>
                        {med.dose && (
                          <p className="text-body-sm text-text-muted mt-0.5">{med.dose}</p>
                        )}
                      </div>
                    </div>
                  ))}
                <button
                  type="button"
                  onClick={() => router.push('/medications')}
                  className="flex items-center gap-1 text-body-md text-mint-600 hover:underline mt-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mint-400/30 rounded"
                >
                  Xem tất cả
                  <ChevronRight className="size-4" aria-hidden="true" />
                </button>
              </div>
            )}
          </CardContent>
        </Card>
      </section>

      {/* Care plan */}
      <section aria-label="Kế hoạch điều trị">
        <Card variant="glass" padding="none">
          <CardHeader className="px-4 pt-4 pb-2">
            <div className="flex items-center gap-2">
              <ClipboardList className="size-4 text-mint-600" aria-hidden="true" />
              <CardTitle className="text-heading-md font-semibold">Kế hoạch điều trị</CardTitle>
            </div>
          </CardHeader>
          <CardContent className="px-4 pb-4">
            {!activePlan ? (
              <EmptyState
                size="sm"
                title="Chưa có kế hoạch điều trị"
                description="Bác sĩ của bạn chưa tạo kế hoạch điều trị."
              />
            ) : (
              <div className="space-y-3">
                <p className="text-body-md font-medium text-text">{activePlan.title}</p>
                {activePlan.content && (
                  <p className="text-body-sm text-text-muted line-clamp-2">{activePlan.content}</p>
                )}
                <button
                  type="button"
                  onClick={() => router.push('/care-plan')}
                  className="flex items-center gap-1 text-body-md text-mint-600 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mint-400/30 rounded"
                >
                  Xem kế hoạch
                  <ChevronRight className="size-4" aria-hidden="true" />
                </button>
              </div>
            )}
          </CardContent>
        </Card>
      </section>

      {/* AI Assistant entry — only when the AI feature flag is on (MVP: OFF) */}
      {flags?.ai_assistant && (
      <section aria-label="Trợ lý AI">
        <Card variant="glass" padding="none" className="border-amber-200 bg-amber-50">
          <CardContent className="px-4 py-4">
            <div className="flex items-start gap-3">
              <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-amber-100 shrink-0">
                <Bot className="size-5 text-amber-700" aria-hidden="true" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-0.5">
                  <p className="text-body-md font-semibold text-text">Trợ lý AI MetoCare</p>
                  <Badge variant="warning" size="sm">AI</Badge>
                </div>
                <p className="text-body-sm text-text-muted mb-2">
                  Đặt câu hỏi về sức khỏe của bạn
                </p>
                <p className="text-body-sm text-amber-700 mb-3">
                  Thông tin từ AI, không thay thế tư vấn bác sĩ
                </p>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => router.push('/ai-assistant')}
                  className="border-amber-300 text-amber-800 hover:bg-amber-100"
                >
                  Bắt đầu hỏi
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      </section>
      )}

    </div>
  )
}
