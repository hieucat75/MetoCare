'use client'

import * as React from 'react'
import { cn } from '@/lib/utils'
import {
  PageHeader,
  Table,
  Alert,
  Button,
  Input,
  Select,
  EmptyState,
  ErrorState,
  CardSkeleton,
} from '@/design-system'
import type { Column } from '@/design-system'
import { getAuditLogs, type AuditLog } from '@/lib/api/admin'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDateTime(iso: string): string {
  try {
    return new Intl.DateTimeFormat('vi-VN', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    }).format(new Date(iso))
  } catch {
    return iso
  }
}

// ---------------------------------------------------------------------------
// Resource type filter options
// ---------------------------------------------------------------------------

const RESOURCE_TYPE_OPTIONS = [
  { value: '', label: 'Tất cả loại tài nguyên' },
  { value: 'user', label: 'Người dùng' },
  { value: 'patient_profile', label: 'Hồ sơ bệnh nhân' },
  { value: 'ai_session', label: 'Phiên AI' },
  { value: 'audit_log', label: 'Nhật ký' },
  { value: 'feature_flag', label: 'Feature Flag' },
  { value: 'clinic', label: 'Phòng khám' },
]

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const PAGE_SIZE = 50

export default function AuditLogsPage() {
  const [logs, setLogs] = React.useState<AuditLog[]>([])
  const [total, setTotal] = React.useState(0)
  const [offset, setOffset] = React.useState(0)
  const [loading, setLoading] = React.useState(true)
  const [loadingMore, setLoadingMore] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  const [resourceTypeFilter, setResourceTypeFilter] = React.useState<string>('')
  const [actionFilter, setActionFilter] = React.useState<string>('')
  const [appliedAction, setAppliedAction] = React.useState<string>('')
  const [appliedResourceType, setAppliedResourceType] = React.useState<string>('')

  const loadLogs = React.useCallback(
    async (currentOffset: number, append: boolean) => {
      if (append) {
        setLoadingMore(true)
      } else {
        setLoading(true)
      }
      setError(null)
      try {
        const params: Parameters<typeof getAuditLogs>[0] = {
          limit: PAGE_SIZE,
          offset: currentOffset,
        }
        if (appliedResourceType) params.resource_type = appliedResourceType
        if (appliedAction) params.action = appliedAction
        const res = await getAuditLogs(params)
        setTotal(res.total)
        if (append) {
          setLogs((prev) => [...prev, ...res.items])
        } else {
          setLogs(res.items)
        }
      } catch {
        setError('Không thể tải nhật ký kiểm tra. Vui lòng thử lại.')
      } finally {
        setLoading(false)
        setLoadingMore(false)
      }
    },
    [appliedResourceType, appliedAction]
  )

  // Initial load and reload when applied filters change
  React.useEffect(() => {
    setOffset(0)
    loadLogs(0, false)
  }, [loadLogs])

  const handleSearch = () => {
    setAppliedAction(actionFilter)
    setAppliedResourceType(resourceTypeFilter)
    // useEffect will re-run because appliedAction / appliedResourceType changed
  }

  const handleLoadMore = () => {
    const nextOffset = offset + PAGE_SIZE
    setOffset(nextOffset)
    loadLogs(nextOffset, true)
  }

  const hasMore = logs.length < total

  // ---------------------------------------------------------------------------
  // Table columns
  // ---------------------------------------------------------------------------

  const columns: Column<AuditLog>[] = React.useMemo(
    () => [
      {
        key: 'occurred_at',
        header: 'Thời gian',
        cell: (row) => (
          <span className="text-body-sm text-text-muted whitespace-nowrap">
            {row.occurred_at ? formatDateTime(row.occurred_at) : '—'}
          </span>
        ),
        width: '170px',
      },
      {
        key: 'actor_id',
        header: 'Người thực hiện',
        cell: (row) => (
          <span className="text-body-sm text-text">
            {row.actor_type}
            {row.actor_id ? ` · ${row.actor_id.slice(0, 8)}` : ''}
          </span>
        ),
        width: '200px',
      },
      {
        key: 'action',
        header: 'Hành động',
        cell: (row) => (
          <span
            className={cn(
              'font-mono text-body-xs bg-secondary-100 px-2 py-0.5 rounded',
              'text-text whitespace-nowrap'
            )}
          >
            {row.action}
          </span>
        ),
        width: '180px',
      },
      {
        key: 'resource_type',
        header: 'Tài nguyên',
        cell: (row) => (
          <span className="text-body-sm text-text-muted">
            {row.resource_type}
            {row.resource_id ? `#${row.resource_id.slice(0, 8)}` : ''}
          </span>
        ),
        width: '180px',
      },
      {
        key: 'outcome',
        header: 'Kết quả',
        cell: (row) => (
          <span className="text-body-sm text-text-muted font-mono">{row.outcome ?? '—'}</span>
        ),
        width: '130px',
      },
    ],
    []
  )

  return (
    <div className="px-6 py-6">
      <PageHeader title="Nhật ký kiểm tra" />

      {/* Info alert */}
      <Alert variant="info" className="mb-6">
        Nhật ký kiểm tra chỉ hiển thị 90 ngày gần nhất.
      </Alert>

      {/* Filter row */}
      <div className="flex flex-col sm:flex-row gap-3 mb-6">
        <div className="w-full sm:w-56">
          <Select
            options={RESOURCE_TYPE_OPTIONS}
            value={resourceTypeFilter}
            onValueChange={setResourceTypeFilter}
            placeholder="Loại tài nguyên"
            fullWidth
          />
        </div>
        <div className="flex-1">
          <Input
            placeholder="Tìm kiếm theo hành động (vd: user.login)..."
            value={actionFilter}
            onChange={(e) => setActionFilter(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleSearch()
            }}
            fullWidth
          />
        </div>
        <Button variant="primary" size="md" onClick={handleSearch}>
          Tìm kiếm
        </Button>
      </div>

      {/* Content */}
      {loading ? (
        <div className="flex flex-col gap-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <CardSkeleton key={i} lines={1} />
          ))}
        </div>
      ) : error ? (
        <ErrorState variant="inline" title={error} onRetry={() => loadLogs(0, false)} />
      ) : logs.length === 0 ? (
        <EmptyState
          title="Không có nhật ký nào"
          description="Thử thay đổi bộ lọc hoặc từ khóa tìm kiếm."
          size="md"
        />
      ) : (
        <>
          <Table<AuditLog>
            columns={columns}
            data={logs}
            rowKey="id"
            stickyHeader
            striped
            emptyMessage="Không có nhật ký nào."
          />

          {/* Load more */}
          {hasMore && (
            <div className="mt-4 flex justify-center">
              <Button variant="outline" size="sm" loading={loadingMore} onClick={handleLoadMore}>
                Tải thêm ({total - logs.length} còn lại)
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
