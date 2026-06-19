'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import { Search, Users, FlaskConical, ClipboardList, Clock } from 'lucide-react'
import { cn } from '@/lib/utils'
import { formatRelativeTime } from '@/lib/utils'
import {
  PageHeader,
  Card,
  Badge,
  EmptyState,
  CardSkeleton,
  ErrorState,
  RiskLevelBadge,
} from '@/design-system'
import type { RiskLevel } from '@/design-system'
import { getDoctorPatients, type DoctorPatient } from '@/lib/api/doctor'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

type RiskSegment = DoctorPatient['risk_segment']
type FilterSegment = 'all' | 'low' | 'medium' | 'high'

interface SegmentFilter {
  key: FilterSegment
  label: string
}

const SEGMENT_FILTERS: SegmentFilter[] = [
  { key: 'all', label: 'Tất cả' },
  { key: 'low', label: 'Nguy cơ thấp' },
  { key: 'medium', label: 'Nguy cơ trung bình' },
  { key: 'high', label: 'Nguy cơ cao' },
]

function toRiskLevel(segment: RiskSegment): RiskLevel {
  if (!segment) return 'unknown'
  if (segment === 'very_high') return 'high'
  return segment as RiskLevel
}

function matchesSegmentFilter(patient: DoctorPatient, filter: FilterSegment): boolean {
  if (filter === 'all') return true
  if (filter === 'high') {
    return patient.risk_segment === 'high' || patient.risk_segment === 'very_high'
  }
  return patient.risk_segment === filter
}

// ---------------------------------------------------------------------------
// Patient card
// ---------------------------------------------------------------------------

interface PatientCardProps {
  patient: DoctorPatient
  onClick: () => void
}

function PatientCard({ patient, onClick }: PatientCardProps) {
  const displayName = patient.full_name ?? patient.email

  return (
    <Card
      variant="default"
      padding="md"
      interactive
      className="cursor-pointer hover:border-primary/40 transition-colors"
    >
      <button
        type="button"
        onClick={onClick}
        className="w-full text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-inset rounded-md"
        aria-label={`Xem hồ sơ bệnh nhân ${displayName}`}
      >
        {/* Name + risk */}
        <div className="flex items-start justify-between gap-2 mb-2">
          <div className="min-w-0">
            <p className="text-body-sm font-semibold text-text truncate">
              {displayName}
            </p>
            {patient.full_name && (
              <p className="text-body-xs text-text-muted truncate">{patient.email}</p>
            )}
          </div>
          <RiskLevelBadge
            level={toRiskLevel(patient.risk_segment)}
            size="sm"
          />
        </div>

        {/* Stats row */}
        <div className="flex items-center gap-4 mb-2">
          <span
            className={cn(
              'inline-flex items-center gap-1 text-body-xs',
              patient.pending_labs > 0 ? 'text-amber-700' : 'text-text-muted',
            )}
          >
            <FlaskConical className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            {patient.pending_labs} xét nghiệm chờ duyệt
          </span>
          <span className="inline-flex items-center gap-1 text-body-xs text-text-muted">
            <ClipboardList className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            {patient.active_care_plans} kế hoạch
          </span>
        </div>

        {/* Footer row */}
        <div className="flex items-center justify-between">
          <span className="inline-flex items-center gap-1 text-body-xs text-text-muted">
            <Clock className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            {patient.last_metric_at
              ? formatRelativeTime(patient.last_metric_at)
              : 'Chưa có dữ liệu'}
          </span>
          {patient.consented ? (
            <Badge variant="success" size="sm">
              Đã đồng ý
            </Badge>
          ) : (
            <Badge variant="warning" size="sm">
              Chưa đồng ý
            </Badge>
          )}
        </div>
      </button>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function DoctorPatientsPage() {
  const router = useRouter()

  const [allPatients, setAllPatients] = React.useState<DoctorPatient[]>([])
  const [patients, setPatients] = React.useState<DoctorPatient[]>([])
  const [total, setTotal] = React.useState(0)
  const [loading, setLoading] = React.useState(true)
  const [searchLoading, setSearchLoading] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  const [searchQuery, setSearchQuery] = React.useState('')
  const [segmentFilter, setSegmentFilter] = React.useState<FilterSegment>('all')

  const debounceRef = React.useRef<ReturnType<typeof setTimeout> | null>(null)

  const loadPatients = React.useCallback(async (search?: string) => {
    if (search !== undefined) {
      setSearchLoading(true)
    } else {
      setLoading(true)
    }
    setError(null)
    try {
      const data = await getDoctorPatients({ limit: 50, search: search || undefined })
      if (!search) {
        setAllPatients(data.items)
      }
      setPatients(data.items)
      setTotal(data.total)
    } catch {
      setError('Không thể tải danh sách bệnh nhân. Vui lòng thử lại.')
    } finally {
      setLoading(false)
      setSearchLoading(false)
    }
  }, [])

  React.useEffect(() => {
    loadPatients()
  }, [loadPatients])

  const handleSearchChange = React.useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const value = e.target.value
      setSearchQuery(value)
      if (debounceRef.current) clearTimeout(debounceRef.current)
      debounceRef.current = setTimeout(() => {
        loadPatients(value)
      }, 300)
    },
    [loadPatients],
  )

  React.useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [])

  // Apply segment filter on the current patient list
  const displayedPatients = React.useMemo<DoctorPatient[]>(() => {
    return patients.filter((p) => matchesSegmentFilter(p, segmentFilter))
  }, [patients, segmentFilter])

  const isSearching = searchQuery.length > 0

  return (
    <div className="px-6 py-6">
      <PageHeader
        title="Danh sách bệnh nhân"
        actions={
          !loading && (
            <Badge variant="default" size="md">
              {total} bệnh nhân
            </Badge>
          )
        }
      />

      {/* Search + filters */}
      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center">
        {/* Search input */}
        <div className="relative flex-1 max-w-sm">
          <Search
            className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-text-muted pointer-events-none"
            aria-hidden="true"
          />
          <input
            type="search"
            placeholder="Tìm kiếm bệnh nhân..."
            value={searchQuery}
            onChange={handleSearchChange}
            aria-label="Tìm kiếm bệnh nhân"
            className={cn(
              'w-full rounded-lg border border-border bg-surface py-2 pl-9 pr-4 text-body-sm text-text',
              'placeholder:text-text-muted',
              'focus:outline-none focus:ring-2 focus:ring-primary focus:border-primary transition-colors',
            )}
          />
          {searchLoading && (
            <div
              className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 animate-spin rounded-full border-2 border-secondary-200 border-t-primary"
              aria-hidden="true"
            />
          )}
        </div>

        {/* Segment filter buttons */}
        <div className="flex gap-1 flex-wrap">
          {SEGMENT_FILTERS.map((opt) => (
            <button
              key={opt.key}
              type="button"
              onClick={() => setSegmentFilter(opt.key)}
              className={cn(
                'rounded-full px-3 py-1 text-body-xs font-medium transition-colors whitespace-nowrap',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-1',
                segmentFilter === opt.key
                  ? 'bg-primary text-white'
                  : 'bg-secondary-100 text-secondary-700 hover:bg-secondary-200',
              )}
              aria-pressed={segmentFilter === opt.key}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      {loading ? (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <CardSkeleton key={i} lines={3} />
          ))}
        </div>
      ) : error ? (
        <ErrorState
          variant="card"
          title={error}
          onRetry={() => loadPatients()}
        />
      ) : displayedPatients.length === 0 ? (
        <EmptyState
          icon={<Users />}
          title={isSearching ? 'Không tìm thấy kết quả' : 'Chưa có bệnh nhân'}
          description={
            isSearching
              ? `Không có bệnh nhân nào khớp với "${searchQuery}".`
              : 'Danh sách bệnh nhân của bạn chưa có dữ liệu.'
          }
          {...(isSearching
            ? {
                action: {
                  label: 'Xóa tìm kiếm',
                  onClick: () => {
                    setSearchQuery('')
                    loadPatients()
                  },
                },
              }
            : {})}
          size="md"
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {displayedPatients.map((patient) => (
            <PatientCard
              key={patient.id}
              patient={patient}
              onClick={() => router.push(`/doctor/patients/${patient.id}`)}
            />
          ))}
        </div>
      )}

      {/* Show "no results for filter" when filtered list is empty but full list isn't */}
      {!loading && !error && displayedPatients.length === 0 && allPatients.length > 0 && segmentFilter !== 'all' && (
        <div className="mt-4 text-center">
          <button
            type="button"
            onClick={() => setSegmentFilter('all')}
            className="text-body-sm text-primary hover:underline underline-offset-2"
          >
            Xem tất cả bệnh nhân
          </button>
        </div>
      )}
    </div>
  )
}
