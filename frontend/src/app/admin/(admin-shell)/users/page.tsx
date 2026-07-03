'use client'

import * as React from 'react'
import { CheckCircle, X } from 'lucide-react'
import { cn } from '@/lib/utils'
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
} from '@/design-system'
import type { Column } from '@/design-system'
import { getUsers, toggleUserActive, type AdminUser, type AdminUserRole } from '@/lib/api/admin'
import { useAuth } from '@/lib/auth/context'

// ---------------------------------------------------------------------------
// Role labels
// ---------------------------------------------------------------------------

const ROLE_LABEL: Record<AdminUserRole, string> = {
  patient: 'Bệnh nhân',
  doctor: 'Bác sĩ',
  medical_reviewer: 'Chuyên gia duyệt',
  internal_admin: 'Admin nội bộ',
  super_admin: 'Super Admin',
  clinic_admin: 'Quản trị phòng khám',
  ai_service: 'Dịch vụ AI',
}

const ROLE_BADGE_VARIANT: Record<
  AdminUserRole,
  'default' | 'primary' | 'info' | 'warning' | 'danger' | 'success'
> = {
  patient: 'default',
  doctor: 'info',
  medical_reviewer: 'warning',
  internal_admin: 'primary',
  super_admin: 'danger',
  clinic_admin: 'success',
  ai_service: 'default',
}

// ---------------------------------------------------------------------------
// Date formatter
// ---------------------------------------------------------------------------

function formatDate(iso: string): string {
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

// ---------------------------------------------------------------------------
// Role filter options
// ---------------------------------------------------------------------------

const ROLE_OPTIONS = [
  { value: '', label: 'Tất cả' },
  { value: 'patient', label: 'Bệnh nhân' },
  { value: 'doctor', label: 'Bác sĩ' },
  { value: 'medical_reviewer', label: 'Chuyên gia duyệt' },
  { value: 'internal_admin', label: 'Admin nội bộ' },
  { value: 'super_admin', label: 'Super Admin' },
  { value: 'clinic_admin', label: 'Quản trị phòng khám' },
]

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function AdminUsersPage() {
  const { user: authUser } = useAuth()

  const [users, setUsers] = React.useState<AdminUser[]>([])
  const [total, setTotal] = React.useState(0)
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)

  const [roleFilter, setRoleFilter] = React.useState<string>('')
  const [searchQuery, setSearchQuery] = React.useState<string>('')
  const [debouncedSearch, setDebouncedSearch] = React.useState<string>('')

  // Confirmation modal
  const [pendingToggle, setPendingToggle] = React.useState<AdminUser | null>(null)
  const [toggling, setToggling] = React.useState(false)

  // Debounce search
  React.useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchQuery)
    }, 300)
    return () => clearTimeout(timer)
  }, [searchQuery])

  const loadUsers = React.useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params: Parameters<typeof getUsers>[0] = { limit: 50 }
      if (roleFilter) params.role = roleFilter as AdminUserRole
      if (debouncedSearch) params.search = debouncedSearch
      const res = await getUsers(params)
      setUsers(res.items)
      setTotal(res.total)
    } catch {
      setError('Không thể tải danh sách người dùng. Vui lòng thử lại.')
    } finally {
      setLoading(false)
    }
  }, [roleFilter, debouncedSearch])

  React.useEffect(() => {
    loadUsers()
  }, [loadUsers])

  const isSuperAdmin = authUser?.role === 'super_admin'

  // Handle switch click — open confirm modal for deactivation, toggle directly for activation
  const handleSwitchChange = React.useCallback(
    (user: AdminUser, newValue: boolean) => {
      if (!newValue) {
        // Deactivating — show confirmation
        setPendingToggle(user)
      } else {
        // Activating directly
        void handleConfirmToggle(user, true)
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []
  )

  const handleConfirmToggle = React.useCallback(async (user: AdminUser, isActive: boolean) => {
    setToggling(true)
    try {
      const updated = await toggleUserActive(user.id, isActive)
      setUsers((prev) => prev.map((u) => (u.id === updated.id ? updated : u)))
    } catch {
      // silently ignore; user list state remains unchanged
    } finally {
      setToggling(false)
      setPendingToggle(null)
    }
  }, [])

  // ---------------------------------------------------------------------------
  // Table columns
  // ---------------------------------------------------------------------------

  const columns: Column<AdminUser>[] = React.useMemo(
    () => [
      {
        key: 'full_name',
        header: 'Tên',
        cell: (row) => (
          <span className="text-body-sm font-medium text-text">
            {row.full_name ?? row.email ?? row.phone ?? '—'}
          </span>
        ),
        width: '200px',
      },
      {
        key: 'email',
        header: 'Email',
        cell: (row) => (
          <span className="text-body-sm text-text-muted">{row.email ?? row.phone ?? '—'}</span>
        ),
        width: '220px',
      },
      {
        key: 'role',
        header: 'Vai trò',
        cell: (row) => (
          <Badge variant={ROLE_BADGE_VARIANT[row.role]} size="sm">
            {ROLE_LABEL[row.role]}
          </Badge>
        ),
        width: '160px',
      },
      {
        key: 'mfa_enabled',
        header: 'MFA',
        align: 'center',
        cell: (row) =>
          row.mfa_enabled ? (
            <CheckCircle className="h-4 w-4 text-success mx-auto" aria-label="MFA đã bật" />
          ) : (
            <X className="h-4 w-4 text-secondary-400 mx-auto" aria-label="MFA chưa bật" />
          ),
        width: '80px',
      },
      {
        key: 'is_active',
        header: 'Trạng thái',
        cell: (row) => (
          <Switch
            size="sm"
            checked={row.is_active}
            disabled={!isSuperAdmin || toggling}
            onCheckedChange={(checked) => handleSwitchChange(row, checked)}
          />
        ),
        width: '100px',
      },
      {
        key: 'created_at',
        header: 'Ngày tạo',
        cell: (row) => (
          <span className="text-body-sm text-text-muted whitespace-nowrap">
            {formatDate(row.created_at)}
          </span>
        ),
        width: '120px',
      },
    ],
    [isSuperAdmin, toggling, handleSwitchChange]
  )

  return (
    <div className="px-6 py-6">
      <PageHeader
        title="Quản lý người dùng"
        actions={
          <Badge variant="default" size="md">
            {total} người dùng
          </Badge>
        }
      />

      {/* Filter row */}
      <div className="flex flex-col sm:flex-row gap-3 mb-6">
        <div className="w-full sm:w-48">
          <Select
            options={ROLE_OPTIONS}
            value={roleFilter}
            onValueChange={setRoleFilter}
            placeholder="Vai trò"
            fullWidth
          />
        </div>
        <div className="flex-1">
          <Input
            placeholder="Tìm kiếm theo tên hoặc email..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            fullWidth
          />
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
        <ErrorState variant="inline" title={error} onRetry={loadUsers} />
      ) : users.length === 0 ? (
        <EmptyState
          title="Không tìm thấy người dùng"
          description="Thử thay đổi bộ lọc hoặc từ khóa tìm kiếm."
          size="md"
        />
      ) : (
        <Table<AdminUser>
          columns={columns}
          data={users}
          rowKey="id"
          stickyHeader
          striped
          emptyMessage="Không có người dùng nào."
        />
      )}

      {/* Confirmation modal */}
      <Modal
        open={pendingToggle !== null}
        onOpenChange={(open) => {
          if (!open) setPendingToggle(null)
        }}
        title="Xác nhận vô hiệu hóa"
        footer={
          <>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPendingToggle(null)}
              disabled={toggling}
            >
              Hủy
            </Button>
            <Button
              variant="danger"
              size="sm"
              loading={toggling}
              onClick={() => {
                if (pendingToggle) {
                  void handleConfirmToggle(pendingToggle, false)
                }
              }}
            >
              Vô hiệu hóa
            </Button>
          </>
        }
      >
        <p className="text-body-sm text-text">Bạn có chắc muốn vô hiệu hóa tài khoản này?</p>
        {pendingToggle && (
          <p className={cn('mt-2 text-body-sm font-medium text-text-muted')}>
            {pendingToggle.full_name ?? pendingToggle.email}
          </p>
        )}
      </Modal>
    </div>
  )
}
