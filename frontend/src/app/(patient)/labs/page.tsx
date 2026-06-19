'use client'

import * as React from 'react'
import { Upload, Bot, Stethoscope, FlaskConical } from 'lucide-react'
import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  ErrorState,
  EmptyState,
  PageHeader,
  Spinner,
  Skeleton,
  SkeletonText,
} from '@/design-system'
import { useAuth } from '@/lib/auth/context'
import {
  getLabs,
  uploadLab,
  type LabResult,
  type LabStatus,
} from '@/lib/api/patient'

// ── Helpers ────────────────────────────────────────────────────────────────────

function formatDate(iso: string): string {
  return new Intl.DateTimeFormat('vi-VN', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(iso))
}

// ── Status badge mapping ───────────────────────────────────────────────────────

type BadgeVariant = 'pending_review' | 'approved' | 'rejected' | 'request_info'

const LAB_STATUS_CONFIG: Record<
  LabStatus,
  { variant: BadgeVariant; label: string }
> = {
  pending_review: { variant: 'pending_review', label: 'Chờ duyệt' },
  approved: { variant: 'approved', label: 'Đã duyệt' },
  rejected: { variant: 'rejected', label: 'Từ chối' },
  request_info: { variant: 'request_info', label: 'Cần bổ sung' },
}

// ── Lab result card ────────────────────────────────────────────────────────────

function LabResultCard({
  lab,
  index,
}: {
  lab: LabResult
  index: number
}) {
  const { variant, label } = LAB_STATUS_CONFIG[lab.status]
  const displayName = lab.file_name ?? `Xét nghiệm ${index + 1}`

  return (
    <Card variant="elevated" padding="none">
      <CardContent className="p-4 space-y-3">
        {/* Header row */}
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2 min-w-0">
            <FlaskConical
              className="size-4 shrink-0 text-text-muted"
              aria-hidden="true"
            />
            <span className="text-body-sm font-medium text-text truncate">
              {displayName}
            </span>
          </div>
          <Badge variant={variant} dot size="sm">
            {label}
          </Badge>
        </div>

        {/* Upload date */}
        <p className="text-body-xs text-text-muted">
          Tải lên: {formatDate(lab.uploaded_at)}
        </p>

        {/* Pending spinner */}
        {lab.status === 'pending_review' && (
          <div className="flex items-center gap-2 text-body-xs text-amber-700">
            <Spinner size="sm" color="muted" />
            <span>Chờ xử lý</span>
          </div>
        )}

        {/* AI explanation panel */}
        {lab.status === 'approved' && lab.ai_explanation && (
          <div className="rounded-md bg-amber-50 border border-amber-200 p-3 space-y-2">
            <div className="flex items-center gap-2">
              <Bot
                className="size-4 shrink-0 text-amber-600"
                aria-hidden="true"
              />
              <span className="text-body-sm font-semibold text-amber-800">
                Giải thích từ AI
              </span>
            </div>
            <p className="text-body-sm text-amber-900">{lab.ai_explanation}</p>
            <p className="text-body-xs text-amber-700 italic">
              Đây là giải thích từ AI, không phải chẩn đoán y tế.
            </p>
          </div>
        )}

        {/* Doctor notes panel */}
        {lab.doctor_notes && lab.status === 'approved' && (
          <div className="rounded-md bg-green-50 border border-green-200 p-3 space-y-2">
            <div className="flex items-center gap-2">
              <Stethoscope
                className="size-4 shrink-0 text-green-700"
                aria-hidden="true"
              />
              <span className="text-body-sm font-semibold text-green-800">
                Ghi chú bác sĩ
              </span>
              <span className="ml-auto text-body-xs text-green-700">
                Đã duyệt bởi bác sĩ
              </span>
            </div>
            <p className="text-body-sm text-green-900">{lab.doctor_notes}</p>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ── Loading skeleton ───────────────────────────────────────────────────────────

function LabsSkeleton() {
  return (
    <div className="space-y-3">
      {[1, 2, 3].map((n) => (
        <Card key={n} variant="elevated" padding="none">
          <CardContent className="p-4 space-y-3">
            <div className="flex items-center justify-between">
              <Skeleton width="60%" height="1rem" />
              <Skeleton width="5rem" height="1.25rem" className="rounded-full" />
            </div>
            <Skeleton width="40%" height="0.75rem" />
            <SkeletonText lines={2} />
          </CardContent>
        </Card>
      ))}
    </div>
  )
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function LabsPage() {
  const { user } = useAuth()
  const patientId = user?.patient_profile_id

  const [labs, setLabs] = React.useState<LabResult[]>([])
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)
  const [successMsg, setSuccessMsg] = React.useState<string | null>(null)
  const [uploading, setUploading] = React.useState(false)

  const fetchLabs = React.useCallback(async () => {
    if (!patientId) return
    setLoading(true)
    setError(null)
    try {
      const res = await getLabs(patientId, { limit: 20 })
      setLabs(res.items)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không tải được kết quả xét nghiệm.')
    } finally {
      setLoading(false)
    }
  }, [patientId])

  React.useEffect(() => {
    fetchLabs()
  }, [fetchLabs])

  async function handleFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file || !patientId) return

    setUploading(true)
    setSuccessMsg(null)
    try {
      const newLab = await uploadLab(patientId, file)
      setLabs((prev) => [newLab, ...prev])
      setSuccessMsg(`Đã tải lên "${file.name}" thành công. Đang chờ bác sĩ xét duyệt.`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Tải lên thất bại. Vui lòng thử lại.')
    } finally {
      setUploading(false)
      // Reset file input so the same file can be re-uploaded if needed
      e.target.value = ''
    }
  }

  if (!patientId) {
    return (
      <div className="p-4 lg:p-6 max-w-2xl mx-auto">
        <Alert variant="warning" title="Chưa có hồ sơ bệnh nhân">
          Tài khoản của bạn chưa được liên kết với hồ sơ bệnh nhân. Vui lòng liên hệ hỗ trợ.
        </Alert>
      </div>
    )
  }

  return (
    <div className="p-4 lg:p-6 space-y-4 max-w-2xl mx-auto">
      {/* Hidden file input */}
      <input
        type="file"
        id="lab-upload"
        accept="image/*,.pdf"
        onChange={handleFileUpload}
        className="hidden"
        aria-label="Tải lên kết quả xét nghiệm"
      />

      <PageHeader
        title="Kết quả xét nghiệm"
        actions={
          <Button
            variant="primary"
            size="sm"
            onClick={() => document.getElementById('lab-upload')?.click()}
            disabled={uploading}
            leftIcon={<Upload className="size-4" aria-hidden="true" />}
          >
            {uploading ? 'Đang tải...' : 'Tải lên'}
          </Button>
        }
      />

      {/* Success alert */}
      {successMsg && (
        <Alert
          variant="success"
          title="Tải lên thành công"
          dismissible
          onDismiss={() => setSuccessMsg(null)}
        >
          {successMsg}
        </Alert>
      )}

      {/* Error alert */}
      {error && !loading && (
        <ErrorState
          variant="inline"
          title="Lỗi"
          message={error}
          onRetry={fetchLabs}
        />
      )}

      {/* Loading skeleton */}
      {loading && <LabsSkeleton />}

      {/* Empty state */}
      {!loading && !error && labs.length === 0 && (
        <EmptyState
          icon={<FlaskConical />}
          title="Chưa có kết quả xét nghiệm"
          description="Tải lên kết quả xét nghiệm để bác sĩ xem xét và phân tích."
          action={{
            label: 'Tải lên ngay',
            onClick: () => document.getElementById('lab-upload')?.click(),
          }}
        />
      )}

      {/* Lab list */}
      {!loading && labs.length > 0 && (
        <div className="space-y-3">
          {labs.map((lab, index) => (
            <LabResultCard key={lab.id} lab={lab} index={index} />
          ))}
        </div>
      )}
    </div>
  )
}
