'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import { Search, Users, FlaskConical, ClipboardList, Clock } from 'lucide-react'
import { cn } from '@/lib/utils'
import { formatRelativeTime } from '@/lib/utils'
import { toPageError, type PageError } from '@/lib/api/client'
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
import {
  getDoctorPatients,
  type DoctorPatient,
  type DoctorPatientRiskFilter,
  type DoctorPatientSort,
} from '@/lib/api/doctor'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

type RiskSegment = DoctorPatient['risk_segment']
type FilterSegment = 'all' | DoctorPatientRiskFilter

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

interface SortOption {
  key: DoctorPatientSort
  label: string
}

const SORT_OPTIONS: SortOption[] = [
  { key: 'risk', label: 'Nguy cơ' },
  { key: 'last_activity', label: 'Hoạt động gần đây' },
  { key: 'pending', label: 'Chờ xử lý' },
  { key: 'name', label: 'Tên' },
]

function toRiskLevel(segment: RiskSegment): RiskLevel {
  if (!segment) return 'unknown'
  if (segment === 'very_high') return 'high'
  return segment as RiskLevel
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
            <p className="text-body-sm font-semibold text-text truncate">{displayName}</p>
            {patient.full_name && (
              <p className="text-body-xs text-text-muted truncate">{patient.email}</p>
            )}
          </div>
          <RiskLevelBadge level={toRiskLevel(patient.risk_segment)} size="sm" />
        </div>

        {/* Stats row */}
        <div className="flex items-center gap-4 mb-2">
          <span
            className={cn(
              'inline-flex items-center gap-1 text-body-xs',
              patient.pending_labs > 0 ? 'text-amber-700' : 'text-text-muted'
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

  const [patients, setPatients] = React.useState<DoctorPatient[]>([])
  const [total, setTotal] = React.useState(0)
  const [loading, setLoading] = React.useState(true)
  const [searchLoading, setSearchLoading] = React.useState(false)
  const [error, setError] = React.useState<PageError | null>(null)

  const [searchQuery, setSearchQuery] = React.useState('')
  const [segmentFilter, setSegmentFilter] = React.useState<FilterSegment>('all')
  const [sort, setSort] = React.useState<DoctorPatientSort>('risk')

  const debounceRef = React.useRef<ReturnType<typeof setTimeout> | null>(null)

  // Server-side fetch. Search, risk segment, and sort are all query params —
  // the backend owns filtering/sorting so pagination stays correct (no
  // client-side hiding of rows that live on other pages).
  const loadPatients = React.useCallback(
    async (
      opts: {
        search?: string
        segment?: FilterSegment
        sort?: DoctorPatientSort
        isSearch?: boolean
      } = {}
    ) => {
      const search = opts.search ?? searchQuery
      const segment = opts.segment ?? segmentFilter
      const sortKey = opts.sort ?? sort

      if (opts.isSearch) setSearchLoading(true)
      else setLoading(true)
      setError(null)
      try {
        const data = await getDoctorPatients({
          limit: 50,
          search: search || undefined,
          risk: segment === 'all' ? undefined : segment,
          sort: sortKey,
        })
        setPatients(data.items)
        setTotal(data.total)
      } catch (err: unknown) {
        setError(toPageError(err))
      } finally {
        setLoading(false)
        setSearchLoading(false)
      }
    },
    [searchQuery, segmentFilter, sort]
  )

  React.useEffect(() => {
    void loadPatients()
    // Initial load only — subsequent loads are triggered explicitly by
    // search/filter/sort handlers to control the loading indicator.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleSearchChange = React.useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const value = e.target.value
      setSearchQuery(value)
      if (debounceRef.current) clearTimeout(debounceRef.current)
      debounceRef.current = setTimeout(() => {
        void loadPatients({ search: value, isSearch: true })
      }, 300)
    },
    [loadPatients]
  )

  const handleSegmentChange = React.useCallback(
    (segment: FilterSegment) => {
      setSegmentFilter(segment)
      void loadPatients({ segment })
    },
    [loadPatients]
  )

  const handleSortChange = React.useCallback(
    (nextSort: DoctorPatientSort) => {
      setSort(nextSort)
      void loadPatients({ sort: nextSort })
    },
    [loadPatients]
  )

  React.useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [])

  const displayedPatients = patients
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
              'focus:outline-none focus:ring-2 focus:ring-primary focus:border-primary transition-colors'
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
              onClick={() => handleSegmentChange(opt.key)}
              className={cn(
                'rounded-full px-3 py-1 text-body-xs font-medium transition-colors whitespace-nowrap',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-1',
                segmentFilter === opt.key
                  ? 'bg-primary text-white'
                  : 'bg-secondary-100 text-secondary-700 hover:bg-secondary-200'
              )}
              aria-pressed={segmentFilter === opt.key}
            >
              {opt.label}
            </button>
          ))}
        </div>

        {/* Sort control */}
        <div className="flex items-center gap-1.5 sm:ml-auto">
          <label htmlFor="patient-sort" className="text-body-xs text-text-muted whitespace-nowrap">
            Sắp xếp
          </label>
          <select
            id="patient-sort"
            value={sort}
            onChange={(e) => handleSortChange(e.target.value as DoctorPatientSort)}
            aria-label="Sắp xếp bệnh nhân"
            className={cn(
              'rounded-lg border border-border bg-surface py-1.5 pl-2.5 pr-7 text-body-xs text-text',
              'focus:outline-none focus:ring-2 focus:ring-primary focus:border-primary transition-colors'
            )}
          >
            {SORT_OPTIONS.map((opt) => (
              <option key={opt.key} value={opt.key}>
                {opt.label}
              </option>
            ))}
          </select>
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
          title={error.title}
          code={error.code}
          message={error.message}
          onRetry={() => void loadPatients()}
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
                    void loadPatients({ search: '' })
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
    </div>
  )
}
