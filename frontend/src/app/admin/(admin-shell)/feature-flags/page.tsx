'use client'

import * as React from 'react'
import { ToggleLeft } from 'lucide-react'
import {
  PageHeader,
  Alert,
  EmptyState,
  Card,
  CardHeader,
  CardTitle,
  CardContent,
  CardSkeleton,
  Switch,
  Badge,
} from '@/design-system'
import { getFeatureFlags, updateFeatureFlag, type FeatureFlag } from '@/lib/api/admin'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString('vi-VN', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

// ---------------------------------------------------------------------------
// Feature Flag Card
// ---------------------------------------------------------------------------

interface FeatureFlagCardProps {
  flag: FeatureFlag
  onToggle: (key: string) => Promise<void>
  isUpdating: boolean
}

function FeatureFlagCard({ flag, onToggle, isUpdating }: FeatureFlagCardProps) {
  const showPartialRollout = flag.enabled && flag.rollout_pct < 100

  return (
    <Card className={flag.enabled ? undefined : 'opacity-60'}>
      <CardHeader>
        <CardTitle>{flag.label}</CardTitle>
        <Switch
          checked={flag.enabled}
          onCheckedChange={() => onToggle(flag.key)}
          disabled={isUpdating}
          aria-label={`Bật/tắt ${flag.label}`}
        />
      </CardHeader>

      <CardContent className="flex flex-col gap-2">
        {/* Flag key */}
        <p className="font-mono text-body-xs text-text-muted">{flag.key}</p>

        {/* Description */}
        <p className="text-body-sm text-text-muted">{flag.description}</p>

        {/* Rollout info */}
        <div className="flex items-center gap-3 flex-wrap">
          <p className="text-body-xs text-text-muted">
            {flag.rollout_pct}% người dùng
          </p>

          {showPartialRollout && (
            <Badge variant="warning" size="sm">
              Triển khai từng phần ({flag.rollout_pct}%)
            </Badge>
          )}
        </div>

        {/* Last updated */}
        <p className="text-body-xs text-text-muted">
          Cập nhật lần cuối: {formatDate(flag.updated_at)} bởi{' '}
          <span className="font-medium text-text">{flag.updated_by ?? 'Hệ thống'}</span>
        </p>
      </CardContent>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function FeatureFlagsPage() {
  const [flags, setFlags] = React.useState<FeatureFlag[]>([])
  const [isLoading, setIsLoading] = React.useState(true)
  const [updatingKeys, setUpdatingKeys] = React.useState<Set<string>>(new Set())
  const [error, setError] = React.useState<string | null>(null)

  React.useEffect(() => {
    let cancelled = false

    async function load() {
      try {
        const data = await getFeatureFlags()
        if (!cancelled) setFlags(data)
      } catch {
        if (!cancelled) setError('Không thể tải danh sách feature flags. Vui lòng thử lại.')
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    }

    void load()
    return () => { cancelled = true }
  }, [])

  async function handleToggle(key: string) {
    const flag = flags.find((f) => f.key === key)
    if (!flag) return

    setUpdatingKeys((prev) => new Set(prev).add(key))
    try {
      const updated = await updateFeatureFlag(key, { enabled: !flag.enabled })
      setFlags((prev) => prev.map((f) => (f.key === key ? updated : f)))
    } catch {
      // Silently fail — flag reverts to previous state since we didn't optimistically update
    } finally {
      setUpdatingKeys((prev) => {
        const next = new Set(prev)
        next.delete(key)
        return next
      })
    }
  }

  return (
    <div className="p-6">
      <PageHeader
        title="Feature Flags"
        subtitle="Kiểm soát tính năng triển khai theo từng nhóm người dùng"
      />

      {/* Safety warning */}
      <Alert variant="warning" title="Lưu ý quan trọng" className="mb-6">
        Thay đổi Feature Flags ảnh hưởng trực tiếp đến người dùng trong hệ thống. Chỉ thực hiện
        khi được ủy quyền.
      </Alert>

      {/* Error state */}
      {error && (
        <Alert variant="danger" className="mb-6">
          {error}
        </Alert>
      )}

      {/* Loading skeleton */}
      {isLoading && (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <CardSkeleton key={i} lines={3} />
          ))}
        </div>
      )}

      {/* Empty state */}
      {!isLoading && !error && flags.length === 0 && (
        <>
          <Alert variant="neutral" className="mb-6">
            Chưa có feature flags nào được cấu hình
          </Alert>
          <EmptyState
            icon={<ToggleLeft />}
            title="Không có feature flags"
            description="Hệ thống chưa có feature flags nào. Liên hệ kỹ thuật để thiết lập."
            size="lg"
          />
        </>
      )}

      {/* Flag cards grid */}
      {!isLoading && flags.length > 0 && (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {flags.map((flag) => (
            <FeatureFlagCard
              key={flag.key}
              flag={flag}
              onToggle={handleToggle}
              isUpdating={updatingKeys.has(flag.key)}
            />
          ))}
        </div>
      )}
    </div>
  )
}
