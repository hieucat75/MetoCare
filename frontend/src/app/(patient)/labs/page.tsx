'use client'

import { PatientEmptyState } from '@/components/patient'
import * as React from 'react'
import { FlaskConical, Plus, Trash2, Upload } from 'lucide-react'
import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  ErrorState,
  PageHeader,
  Skeleton,
  SkeletonText,
  Modal,
  FormField,
  Input,
} from '@/design-system'
import { useAuth } from '@/lib/auth/context'
import {
  getLabResults,
  createManualLabResults,
  type LabResultEntry,
  type ManualLabItem,
} from '@/lib/api/patient'
import { useFeatureFlags } from '@/lib/api/features'
import { formatDate } from '@/lib/utils'

// ── Result card ────────────────────────────────────────────────────────────────

function ResultCard({ r }: { r: LabResultEntry }) {
  const valueStr =
    r.value != null ? `${r.value}${r.unit ? ` ${r.unit}` : ''}` : '—'
  return (
    <Card variant="glass" padding="none">
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2 min-w-0">
            <FlaskConical className="size-4 shrink-0 text-text-muted" aria-hidden="true" />
            <span className="text-body-md font-medium text-text truncate">{r.test_name}</span>
          </div>
          <span className="text-heading-md font-bold text-text shrink-0">{valueStr}</span>
        </div>
        <div className="flex items-center justify-between mt-1 pl-6">
          <span className="text-body-sm text-text-muted">
            {r.reference_range ? `Tham chiếu: ${r.reference_range}` : ''}
          </span>
          <span className="text-body-sm text-text-subtle">
            {r.test_date ? formatDate(r.test_date) : formatDate(r.created_at)}
          </span>
        </div>
        {r.verified_by_user && (
          <div className="mt-2 pl-6">
            <Badge variant="default" size="sm">Tự nhập</Badge>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function LabsSkeleton() {
  return (
    <div className="space-y-3">
      {[1, 2, 3].map((n) => (
        <Card key={n} variant="glass" padding="none">
          <CardContent className="p-4 space-y-3">
            <Skeleton width="50%" height="1rem" />
            <SkeletonText lines={1} />
          </CardContent>
        </Card>
      ))}
    </div>
  )
}

// ── Manual entry modal (structured rows) ───────────────────────────────────────

interface RowState {
  test_name: string
  value: string
  unit: string
  reference_range: string
}

const EMPTY_ROW: RowState = { test_name: '', value: '', unit: '', reference_range: '' }

function ManualEntryModal({
  open,
  onClose,
  onSaved,
  patientId,
}: {
  open: boolean
  onClose: () => void
  onSaved: () => void
  patientId: string
}) {
  const [labName, setLabName] = React.useState('')
  const [testDate, setTestDate] = React.useState('')
  const [rows, setRows] = React.useState<RowState[]>([{ ...EMPTY_ROW }])
  const [submitting, setSubmitting] = React.useState(false)
  const [err, setErr] = React.useState<string | null>(null)

  React.useEffect(() => {
    if (open) {
      setLabName('')
      setTestDate('')
      setRows([{ ...EMPTY_ROW }])
      setErr(null)
    }
  }, [open])

  function setRow(i: number, patch: Partial<RowState>) {
    setRows((rs) => rs.map((r, idx) => (idx === i ? { ...r, ...patch } : r)))
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const named = rows.filter((r) => r.test_name.trim())
    if (named.length === 0) {
      setErr('Vui lòng nhập ít nhất một chỉ số xét nghiệm.')
      return
    }
    const results: ManualLabItem[] = named.map((r) => ({
      test_name: r.test_name.trim(),
      value: r.value.trim() ? parseFloat(r.value) : null,
      unit: r.unit.trim() || null,
      reference_range: r.reference_range.trim() || null,
    }))
    if (results.some((r) => r.value != null && isNaN(r.value))) {
      setErr('Giá trị phải là số.')
      return
    }
    setSubmitting(true)
    setErr(null)
    try {
      await createManualLabResults(patientId, {
        lab_name: labName.trim() || null,
        test_date: testDate || null,
        results,
      })
      onSaved()
      onClose()
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : 'Lưu thất bại. Vui lòng thử lại.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      open={open}
      onOpenChange={(o) => !o && onClose()}
      title="Nhập kết quả xét nghiệm"
      footer={
        <>
          <Button variant="outline" size="sm" onClick={onClose} disabled={submitting}>
            Hủy
          </Button>
          <Button variant="mint" size="sm" type="submit" form="manual-lab-form" loading={submitting}>
            Lưu
          </Button>
        </>
      }
    >
      <form id="manual-lab-form" onSubmit={handleSubmit} className="space-y-4">
        {err && <Alert variant="danger" title={err} />}

        <div className="grid grid-cols-2 gap-3">
          <FormField label="Tên xét nghiệm">
            <Input value={labName} onChange={(e) => setLabName(e.target.value)} placeholder="VD: Máu tổng quát" fullWidth />
          </FormField>
          <FormField label="Ngày xét nghiệm">
            <Input type="date" value={testDate} onChange={(e) => setTestDate(e.target.value)} fullWidth />
          </FormField>
        </div>

        <div className="space-y-3">
          <p className="text-label-lg font-medium text-text-muted">Chỉ số</p>
          {rows.map((row, i) => (
            <div key={i} className="rounded-lg border border-border p-3 space-y-2">
              <div className="flex items-center gap-2">
                <Input
                  value={row.test_name}
                  onChange={(e) => setRow(i, { test_name: e.target.value })}
                  placeholder="Tên chỉ số (VD: Glucose)"
                  fullWidth
                />
                {rows.length > 1 && (
                  <button
                    type="button"
                    onClick={() => setRows((rs) => rs.filter((_, idx) => idx !== i))}
                    aria-label="Xoá chỉ số"
                    className="p-2 text-danger hover:bg-danger-light rounded-md shrink-0"
                  >
                    <Trash2 className="size-4" />
                  </button>
                )}
              </div>
              <div className="grid grid-cols-3 gap-2">
                <Input type="number" step="any" value={row.value} onChange={(e) => setRow(i, { value: e.target.value })} placeholder="Giá trị" fullWidth />
                <Input value={row.unit} onChange={(e) => setRow(i, { unit: e.target.value })} placeholder="Đơn vị" fullWidth />
                <Input value={row.reference_range} onChange={(e) => setRow(i, { reference_range: e.target.value })} placeholder="Tham chiếu" fullWidth />
              </div>
            </div>
          ))}
          <Button type="button" variant="outline" size="sm" onClick={() => setRows((rs) => [...rs, { ...EMPTY_ROW }])}>
            <Plus className="size-4 mr-1" aria-hidden="true" /> Thêm chỉ số
          </Button>
        </div>
      </form>
    </Modal>
  )
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function LabsPage() {
  const { user } = useAuth()
  const patientId = user?.patient_profile_id
  const flags = useFeatureFlags()

  const [results, setResults] = React.useState<LabResultEntry[]>([])
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)
  const [modalOpen, setModalOpen] = React.useState(false)

  const load = React.useCallback(() => {
    if (!patientId) {
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    getLabResults(patientId, { limit: 100 })
      .then((res) => setResults(res.items))
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [patientId])

  React.useEffect(() => {
    load()
  }, [load])

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
    <div className="p-4 lg:p-6 space-y-4 max-w-2xl mx-auto pb-24">
      <PageHeader
        title="Kết quả xét nghiệm"
        actions={
          <Button variant="mint" size="sm" onClick={() => setModalOpen(true)}>
            <Plus className="size-4 mr-1" aria-hidden="true" /> Nhập kết quả
          </Button>
        }
      />

      {/* OCR upload — Phase 2 stub. Only shown as enabled if the OCR flag is on
          (object-storage + auto-read deferred); otherwise a disabled hint. */}
      {flags && (
        <Card variant="glass" padding="md">
          <CardContent className="flex items-center justify-between gap-3 py-1">
            <div className="flex items-center gap-2 text-text-muted">
              <Upload className="size-4" aria-hidden="true" />
              <span className="text-body-md">Tải ảnh/PDF và tự động đọc kết quả</span>
            </div>
            <Badge variant="default" size="sm">{flags.ocr ? 'Sắp có' : 'Phase 2'}</Badge>
          </CardContent>
        </Card>
      )}

      {error && !loading && (
        <ErrorState variant="inline" title="Lỗi" message={error} onRetry={load} />
      )}

      {loading && <LabsSkeleton />}

      {!loading && !error && results.length === 0 && (
        <PatientEmptyState
          icon={<FlaskConical />}
          title="Chưa có kết quả xét nghiệm"
          description="Nhập kết quả xét nghiệm của bạn để theo dõi theo thời gian."
          cta={{ label: 'Nhập kết quả', onClick: () => setModalOpen(true) }}
        />
      )}

      {!loading && !error && results.length > 0 && (
        <div className="space-y-3">
          {results.map((r) => (
            <ResultCard key={r.id} r={r} />
          ))}
        </div>
      )}

      <ManualEntryModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onSaved={load}
        patientId={patientId}
      />
    </div>
  )
}
