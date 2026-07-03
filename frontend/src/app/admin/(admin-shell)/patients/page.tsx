'use client'

import * as React from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { AlertTriangle, ShieldCheck, ShieldOff, Users as UsersIcon } from 'lucide-react'
import {
  PageHeader,
  Table,
  Badge,
  Switch,
  Modal,
  Button,
  Input,
  Select,
  EmptyState,
  ErrorState,
  CardSkeleton,
  Card,
} from '@/design-system'
import type { Column } from '@/design-system'
import { getPatients, updatePatientStatus, type AdminPatientListItem } from '@/lib/api/admin'
import { useAuth } from '@/lib/auth/context'

// ---------------------------------------------------------------------------
// Static option lists (Vietnamese labels)
// ---------------------------------------------------------------------------

const STATUS_OPTIONS = [
  { value: '', label: 'Tất cả trạng thái' },
  { value: 'active', label: 'Đang hoạt động' },
  { value: 'inactive', label: 'Đã khóa' },
]

const GENDER_OPTIONS = [
  { value: '', label: 'Tất cả giới tính' },
  { value: 'male', label: 'Nam' },
  { value: 'female', label: 'Nữ' },
  { value: 'other', label: 'Khác' },
]

const TRISTATE_OPTIONS = [
  { value: '', label: 'Tất cả' },
  { value: 'true', label: 'Có' },
  { value: 'false', label: 'Không' },
]

const AGE_GROUP_OPTIONS = [
  { value: '', label: 'Tất cả độ tuổi' },
  { value: 'under_18', label: 'Dưới 18' },
  { value: '18_34', label: '18–34' },
  { value: '35_54', label: '35–54' },
  { value: '55_69', label: '55–69' },
  { value: '70_plus', label: '70+' },
]

const CONSENT_LABEL: Record<string, { label: string; variant: 'success' | 'danger' | 'default' }> = {
  valid: { label: 'Đã đồng ý', variant: 'success' },
  revoked: { label: 'Đã thu hồi', variant: 'danger' },
  none: { label: 'Chưa đồng ý', variant: 'default' },
}

const PAGE_SIZE = 20

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  try {
    return new Intl.DateTimeFormat('vi-VN', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    }).format(new Date(iso))
  } catch {
    return iso
  }
}

function formatDateTime(iso: string | null): string {
  if (!iso) return 'Chưa có hoạt động'
  try {
    return new Intl.DateTimeFormat('vi-VN', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    }).format(new Date(iso))
  } catch {
    return iso
  }
}

function genderLabel(gender: string | null): string {
  if (gender === 'male') return 'Nam'
  if (gender === 'female') return 'Nữ'
  if (gender === 'other') return 'Khác'
  return '—'
}

interface Filters {
  search: string
  status: string
  gender: string
  hasLabs: string
  hasMeds: string
  hasConsent: string
  ageGroup: string
  createdFrom: string
  createdTo: string
  page: number
}

function filtersFromParams(params: URLSearchParams): Filters {
  return {
    search: params.get('q') ?? '',
    status: params.get('status') ?? '',
    gender: params.get('gender') ?? '',
    hasLabs: params.get('has_labs') ?? '',
    hasMeds: params.get('has_meds') ?? '',
    hasConsent: params.get('has_consent') ?? '',
    ageGroup: params.get('age_group') ?? '',
    createdFrom: params.get('created_from') ?? '',
    createdTo: params.get('created_to') ?? '',
    page: Math.max(1, Number(params.get('page') ?? '1') || 1),
  }
}

function paramsFromFilters(filters: Filters): string {
  const qs = new URLSearchParams()
  if (filters.search) qs.set('q', filters.search)
  if (filters.status) qs.set('status', filters.status)
  if (filters.gender) qs.set('gender', filters.gender)
  if (filters.hasLabs) qs.set('has_labs', filters.hasLabs)
  if (filters.hasMeds) qs.set('has_meds', filters.hasMeds)
  if (filters.hasConsent) qs.set('has_consent', filters.hasConsent)
  if (filters.ageGroup) qs.set('age_group', filters.ageGroup)
  if (filters.createdFrom) qs.set('created_from', filters.createdFrom)
  if (filters.createdTo) qs.set('created_to', filters.createdTo)
  if (filters.page > 1) qs.set('page', String(filters.page))
  return qs.toString()
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function AdminPatientsPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { user: authUser } = useAuth()
  const isSuperAdmin = authUser?.role === 'super_admin'

  const urlFilters = React.useMemo(() => filtersFromParams(searchParams), [searchParams])
  const [searchInput, setSearchInput] = React.useState(urlFilters.search)

  const [items, setItems] = React.useState<AdminPatientListItem[]>([])
  const [total, setTotal] = React.useState(0)
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)

  const [pendingBlock, setPendingBlock] = React.useState<AdminPatientListItem | null>(null)
  const [toggling, setToggling] = React.useState(false)

  // Keep the search box in sync when navigation (back/forward) changes the URL.
  React.useEffect(() => {
    setSearchInput(urlFilters.search)
  }, [urlFilters.search])

  const updateFilters = React.useCallback(
    (patch: Partial<Filters>, opts?: { resetPage?: boolean }) => {
      const next: Filters = {
        ...urlFilters,
        ...patch,
        page: opts?.resetPage === false ? (patch.page ?? urlFilters.page) : 1,
      }
      const qs = paramsFromFilters(next)
      router.replace(`/admin/patients${qs ? `?${qs}` : ''}`)
    },
    [router, urlFilters],
  )

  // Debounce the free-text search box into the URL (300ms).
  React.useEffect(() => {
    if (searchInput === urlFilters.search) return
    const timer = setTimeout(() => {
      updateFilters({ search: searchInput })
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, 300)
    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchInput])

  const loadPatients = React.useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await getPatients({
        search: urlFilters.search || undefined,
        status: (urlFilters.status || undefined) as 'active' | 'inactive' | undefined,
        gender: urlFilters.gender || undefined,
        hasLabs: urlFilters.hasLabs ? urlFilters.hasLabs === 'true' : undefined,
        hasMeds: urlFilters.hasMeds ? urlFilters.hasMeds === 'true' : undefined,
        hasConsent: urlFilters.hasConsent ? urlFilters.hasConsent === 'true' : undefined,
        ageGroup: urlFilters.ageGroup || undefined,
        createdFrom: urlFilters.createdFrom || undefined,
        createdTo: urlFilters.createdTo || undefined,
        limit: PAGE_SIZE,
        offset: (urlFilters.page - 1) * PAGE_SIZE,
      })
      setItems(res.items)
      setTotal(res.total)
    } catch {
      setError('Không thể tải danh sách bệnh nhân. Vui lòng thử lại.')
    } finally {
      setLoading(false)
    }
  }, [urlFilters])

  React.useEffect(() => {
    loadPatients()
  }, [loadPatients])

  const applyStatus = React.useCallback(async (patient: AdminPatientListItem, isActive: boolean) => {
    setToggling(true)
    try {
      const updated = await updatePatientStatus(patient.id, isActive)
      setItems((prev) => prev.map((p) => (p.id === updated.id ? updated : p)))
    } catch {
      // silently ignore; row state remains unchanged, admin can retry
    } finally {
      setToggling(false)
      setPendingBlock(null)
    }
  }, [])

  const handleSwitchChange = React.useCallback(
    (patient: AdminPatientListItem, next: boolean) => {
      if (!next) {
        setPendingBlock(patient)
      } else {
        void applyStatus(patient, true)
      }
    },
    [applyStatus],
  )

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  // ---------------------------------------------------------------------------
  // Table columns (desktop)
  // ---------------------------------------------------------------------------

  const columns: Column<AdminPatientListItem>[] = React.useMemo(
    () => [
      {
        key: 'full_name',
        header: 'Họ tên',
        cell: (row) => (
          <div className="flex flex-col">
            <span className="text-base font-medium text-text">{row.full_name ?? '—'}</span>
            <span className="text-sm text-text-muted">{row.phone ?? '—'}</span>
          </div>
        ),
        width: '220px',
      },
      {
        key: 'gender',
        header: 'Giới tính',
        cell: (row) => <span className="text-base text-text">{genderLabel(row.gender)}</span>,
        width: '100px',
      },
      {
        key: 'age',
        header: 'Tuổi / Năm sinh',
        cell: (row) => (
          <span className="text-base text-text-muted whitespace-nowrap">
            {row.age != null ? `${row.age} tuổi` : '—'}
            {row.birth_year ? ` (${row.birth_year})` : ''}
          </span>
        ),
        width: '150px',
      },
      {
        key: 'is_active',
        header: 'Trạng thái',
        cell: (row) => (
          <div className="flex items-center gap-2">
            <Switch
              size="sm"
              checked={row.is_active}
              disabled={!isSuperAdmin || toggling}
              onCheckedChange={(checked) => handleSwitchChange(row, checked)}
            />
            <span className="text-base text-text-muted">
              {row.is_active ? 'Hoạt động' : 'Đã khóa'}
            </span>
          </div>
        ),
        width: '160px',
      },
      {
        key: 'lab_result_count',
        header: 'Hồ sơ',
        cell: (row) => (
          <span className="text-base text-text-muted whitespace-nowrap">
            {row.lab_result_count} XN · {row.medication_count} thuốc
            {row.has_data_quality_flag && (
              <AlertTriangle
                className="ml-1 inline h-4 w-4 text-warning"
                aria-label="Có cảnh báo dữ liệu"
              />
            )}
          </span>
        ),
        width: '160px',
      },
      {
        key: 'created_at',
        header: 'Ngày tạo',
        cell: (row) => (
          <span className="text-base text-text-muted whitespace-nowrap">
            {formatDate(row.created_at)}
          </span>
        ),
        width: '120px',
      },
      {
        key: 'last_activity_at',
        header: 'Hoạt động gần nhất',
        cell: (row) => (
          <span className="text-base text-text-muted whitespace-nowrap">
            {formatDateTime(row.last_activity_at)}
          </span>
        ),
        width: '180px',
      },
      {
        key: 'consent_status',
        header: 'Consent',
        cell: (row) => {
          const meta = CONSENT_LABEL[row.consent_status] ?? CONSENT_LABEL.none
          return (
            <Badge variant={meta.variant} size="sm">
              {meta.label}
            </Badge>
          )
        },
        width: '130px',
      },
      {
        key: 'id',
        header: 'Hành động',
        cell: (row) => (
          <Button
            variant="outline"
            size="sm"
            className="min-h-11"
            onClick={(e) => {
              e.stopPropagation()
              router.push(`/admin/patients/${row.id}`)
            }}
          >
            Xem chi tiết
          </Button>
        ),
        width: '140px',
      },
    ],
    [isSuperAdmin, toggling, handleSwitchChange, router],
  )

  return (
    <div className="px-6 py-6">
      <PageHeader
        title="Quản lý bệnh nhân"
        subtitle="Xem, tìm kiếm và quản lý hồ sơ bệnh nhân toàn hệ thống"
        actions={
          <Badge variant="default" size="md">
            {total} bệnh nhân
          </Badge>
        }
      />

      {/* Filter row */}
      <div className="flex flex-col gap-3 mb-6">
        <Input
          placeholder="Tìm theo tên, số điện thoại, email hoặc mã bệnh nhân..."
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          fullWidth
          className="text-base"
        />
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          <Select
            options={STATUS_OPTIONS}
            value={urlFilters.status}
            onValueChange={(v) => updateFilters({ status: v })}
            placeholder="Trạng thái"
            fullWidth
          />
          <Select
            options={GENDER_OPTIONS}
            value={urlFilters.gender}
            onValueChange={(v) => updateFilters({ gender: v })}
            placeholder="Giới tính"
            fullWidth
          />
          <Select
            options={AGE_GROUP_OPTIONS}
            value={urlFilters.ageGroup}
            onValueChange={(v) => updateFilters({ ageGroup: v })}
            placeholder="Độ tuổi"
            fullWidth
          />
          <Select
            options={[{ value: '', label: 'Xét nghiệm' }, ...TRISTATE_OPTIONS.slice(1)]}
            value={urlFilters.hasLabs}
            onValueChange={(v) => updateFilters({ hasLabs: v })}
            placeholder="Có xét nghiệm"
            fullWidth
          />
          <Select
            options={[{ value: '', label: 'Thuốc' }, ...TRISTATE_OPTIONS.slice(1)]}
            value={urlFilters.hasMeds}
            onValueChange={(v) => updateFilters({ hasMeds: v })}
            placeholder="Có medication"
            fullWidth
          />
          <Select
            options={[{ value: '', label: 'Consent' }, ...TRISTATE_OPTIONS.slice(1)]}
            value={urlFilters.hasConsent}
            onValueChange={(v) => updateFilters({ hasConsent: v })}
            placeholder="Có consent"
            fullWidth
          />
        </div>
        <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center">
          <label className="text-base text-text-muted flex items-center gap-2">
            Ngày tạo từ
            <input
              type="date"
              value={urlFilters.createdFrom}
              onChange={(e) => updateFilters({ createdFrom: e.target.value })}
              className="min-h-11 rounded-md border border-border px-3 text-base"
            />
          </label>
          <label className="text-base text-text-muted flex items-center gap-2">
            đến
            <input
              type="date"
              value={urlFilters.createdTo}
              onChange={(e) => updateFilters({ createdTo: e.target.value })}
              className="min-h-11 rounded-md border border-border px-3 text-base"
            />
          </label>
        </div>
      </div>

      {/* Content */}
      {loading ? (
        <div className="flex flex-col gap-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <CardSkeleton key={i} lines={1} />
          ))}
        </div>
      ) : error ? (
        <ErrorState variant="inline" title={error} onRetry={loadPatients} />
      ) : items.length === 0 ? (
        <EmptyState
          icon={<UsersIcon />}
          title="Không tìm thấy bệnh nhân"
          description="Chưa có bệnh nhân nào khớp với bộ lọc hiện tại. Thử thay đổi tìm kiếm hoặc bộ lọc."
          size="md"
        />
      ) : (
        <>
          {/* Desktop table */}
          <div className="hidden md:block">
            <Table<AdminPatientListItem>
              columns={columns}
              data={items}
              rowKey="id"
              stickyHeader
              striped
              onRowClick={(row) => router.push(`/admin/patients/${row.id}`)}
              emptyMessage="Không có bệnh nhân nào."
            />
          </div>

          {/* Mobile cards */}
          <div className="flex flex-col gap-3 md:hidden">
            {items.map((row) => {
              const meta = CONSENT_LABEL[row.consent_status] ?? CONSENT_LABEL.none
              return (
                <div
                  key={row.id}
                  role="button"
                  tabIndex={0}
                  onClick={() => router.push(`/admin/patients/${row.id}`)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      router.push(`/admin/patients/${row.id}`)
                    }
                  }}
                >
                  <Card padding="sm" interactive>
                  <div className="flex justify-between items-start gap-2 mb-2">
                    <div>
                      <p className="text-base font-medium text-text">{row.full_name ?? '—'}</p>
                      <p className="text-sm text-text-muted">{row.phone ?? '—'}</p>
                    </div>
                    <Badge variant={row.is_active ? 'success' : 'danger'} size="sm">
                      {row.is_active ? 'Hoạt động' : 'Đã khóa'}
                    </Badge>
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-sm text-text-muted mb-2">
                    <span>
                      {genderLabel(row.gender)}
                      {row.age != null ? ` · ${row.age} tuổi` : ''}
                    </span>
                    <span>
                      {row.lab_result_count} XN · {row.medication_count} thuốc
                      {row.has_data_quality_flag && (
                        <AlertTriangle
                          className="ml-1 inline h-3.5 w-3.5 text-warning"
                          aria-label="Có cảnh báo dữ liệu"
                        />
                      )}
                    </span>
                    <span>Tạo: {formatDate(row.created_at)}</span>
                    <span>HĐ: {formatDateTime(row.last_activity_at)}</span>
                  </div>
                  <Badge variant={meta.variant} size="sm">
                    {meta.label}
                  </Badge>
                  </Card>
                </div>
              )
            })}
          </div>

          {/* Pagination */}
          <div className="flex items-center justify-between mt-6">
            <span className="text-base text-text-muted">
              Trang {urlFilters.page} / {totalPages} ({total} bệnh nhân)
            </span>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                className="min-h-11"
                disabled={urlFilters.page <= 1}
                onClick={() => updateFilters({ page: urlFilters.page - 1 }, { resetPage: false })}
              >
                Trước
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="min-h-11"
                disabled={urlFilters.page >= totalPages}
                onClick={() => updateFilters({ page: urlFilters.page + 1 }, { resetPage: false })}
              >
                Sau
              </Button>
            </div>
          </div>
        </>
      )}

      {/* Block confirmation modal */}
      <Modal
        open={pendingBlock !== null}
        onOpenChange={(open) => {
          if (!open) setPendingBlock(null)
        }}
        title="Xác nhận khóa tài khoản"
        footer={
          <>
            <Button
              variant="outline"
              size="sm"
              className="min-h-11"
              onClick={() => setPendingBlock(null)}
              disabled={toggling}
            >
              Hủy
            </Button>
            <Button
              variant="danger"
              size="sm"
              className="min-h-11"
              loading={toggling}
              onClick={() => {
                if (pendingBlock) void applyStatus(pendingBlock, false)
              }}
            >
              <ShieldOff className="h-4 w-4 mr-1" aria-hidden />
              Khóa tài khoản
            </Button>
          </>
        }
      >
        <p className="text-base text-text">
          Bạn có chắc muốn khóa tài khoản của bệnh nhân này? Bệnh nhân sẽ không thể đăng nhập cho
          đến khi được mở khóa lại.
        </p>
        {pendingBlock && (
          <p className="mt-2 text-base font-medium text-text-muted flex items-center gap-2">
            <ShieldCheck className="h-4 w-4" aria-hidden />
            {pendingBlock.full_name ?? pendingBlock.phone}
          </p>
        )}
      </Modal>
    </div>
  )
}
