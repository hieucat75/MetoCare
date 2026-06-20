'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import {
  AlertTriangle,
  ArrowLeft,
  Camera,
  CheckCircle2,
  Link2,
  Plus,
  Trash2,
  Upload,
} from 'lucide-react'
import { Alert, Badge, Button, PageHeader } from '@/design-system'
import { GlassCard, MintButton, PatientInput } from '@/components/patient'
import { useAuth } from '@/lib/auth/context'
import { useFeatureFlags } from '@/lib/api/features'
import {
  createManualLabResults,
  uploadLabDraft,
  type LabUploadDraft,
  type ManualLabItem,
} from '@/lib/api/patient'

const MAX_MB = 10
const ACCEPT = ['image/jpeg', 'image/png', 'application/pdf']

type Mode = 'camera' | 'file' | 'url'

interface EditRow {
  test_name: string
  value: string
  unit: string
  reference_range: string
  confidence: number | null   // null = manually added row
  status: string | null
}

const STATUS_LABEL: Record<string, string> = {
  normal: 'Bình thường',
  low: 'Thấp',
  high: 'Cao',
  critical: 'Cần lưu ý',
}

function confidenceBadge(c: number | null): { label: string; variant: 'mint' | 'warning' | 'danger' } {
  if (c == null) return { label: 'Tự nhập', variant: 'mint' }
  if (c >= 0.85) return { label: `Độ tin cậy cao`, variant: 'mint' }
  if (c >= 0.6) return { label: `Cần kiểm tra`, variant: 'warning' }
  return { label: `Tin cậy thấp`, variant: 'danger' }
}

// ── Mode picker ────────────────────────────────────────────────────────────────

function ModeTabs({ mode, onChange }: { mode: Mode; onChange: (m: Mode) => void }) {
  const tabs: { key: Mode; label: string; icon: React.ReactNode }[] = [
    { key: 'camera', label: 'Chụp ảnh', icon: <Camera className="size-5" /> },
    { key: 'file', label: 'Tải tệp', icon: <Upload className="size-5" /> },
    { key: 'url', label: 'Dán link', icon: <Link2 className="size-5" /> },
  ]
  return (
    <div role="tablist" aria-label="Cách tải kết quả" className="grid grid-cols-3 gap-2">
      {tabs.map((t) => {
        const active = mode === t.key
        return (
          <button
            key={t.key}
            role="tab"
            aria-selected={active}
            onClick={() => onChange(t.key)}
            className={[
              'flex flex-col items-center gap-1.5 rounded-2xl py-4 transition-all',
              active
                ? 'bg-mint-500 text-white shadow-glow-mint scale-[1.02]'
                : 'bg-white/70 text-text-muted ring-1 ring-mint-100 hover:bg-white',
            ].join(' ')}
          >
            {t.icon}
            <span className="text-[15px] font-medium">{t.label}</span>
          </button>
        )
      })}
    </div>
  )
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function LabUploadPage() {
  const router = useRouter()
  const { user } = useAuth()
  const patientId = user?.patient_profile_id
  const flags = useFeatureFlags()

  const [mode, setMode] = React.useState<Mode>('camera')
  const [file, setFile] = React.useState<File | null>(null)
  const [url, setUrl] = React.useState('')
  const [submitting, setSubmitting] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  const [draft, setDraft] = React.useState<LabUploadDraft | null>(null)
  const [rows, setRows] = React.useState<EditRow[]>([])
  const [labName, setLabName] = React.useState('')
  const [saving, setSaving] = React.useState(false)

  const step: 'input' | 'review' = draft ? 'review' : 'input'

  function pickFile(f: File | null) {
    setError(null)
    if (!f) return
    if (!ACCEPT.includes(f.type)) {
      setError('Chỉ chấp nhận ảnh JPG/PNG hoặc tệp PDF.')
      return
    }
    if (f.size > MAX_MB * 1024 * 1024) {
      setError(`Tệp vượt quá ${MAX_MB}MB.`)
      return
    }
    setFile(f)
  }

  async function submitForDraft() {
    setError(null)
    setSubmitting(true)
    try {
      const input =
        mode === 'url' ? { url: url.trim() } : file ? { file } : null
      if (!input || (mode === 'url' && !url.trim())) {
        setError(mode === 'url' ? 'Vui lòng dán đường link.' : 'Vui lòng chọn tệp.')
        setSubmitting(false)
        return
      }
      const d = await uploadLabDraft(input)
      setDraft(d)
      const mapped: EditRow[] = d.parsed_values.map((v) => ({
        test_name: v.test_name,
        value: String(v.value),
        unit: v.unit ?? '',
        reference_range: v.reference_range ?? '',
        confidence: v.confidence,
        status: v.status,
      }))
      // Always give the patient at least one editable row (manual fallback).
      setRows(mapped.length ? mapped : [{ test_name: '', value: '', unit: '', reference_range: '', confidence: null, status: null }])
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Không xử lý được tệp. Vui lòng thử lại.')
    } finally {
      setSubmitting(false)
    }
  }

  function setRow(i: number, patch: Partial<EditRow>) {
    setRows((rs) => rs.map((r, idx) => (idx === i ? { ...r, ...patch } : r)))
  }

  async function confirmSave() {
    if (!patientId) return
    const named = rows.filter((r) => r.test_name.trim())
    if (named.length === 0) {
      setError('Vui lòng nhập ít nhất một chỉ số.')
      return
    }
    const results: ManualLabItem[] = named.map((r) => ({
      test_name: r.test_name.trim(),
      value: r.value.trim() ? parseFloat(r.value) : null,
      unit: r.unit.trim() || null,
      reference_range: r.reference_range.trim() || null,
    }))
    if (results.some((r) => r.value != null && Number.isNaN(r.value))) {
      setError('Giá trị phải là số.')
      return
    }
    setSaving(true)
    setError(null)
    try {
      await createManualLabResults(patientId, {
        lab_name: labName.trim() || null,
        results,
      })
      router.push('/labs')
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Lưu thất bại. Vui lòng thử lại.')
      setSaving(false)
    }
  }

  if (!patientId) {
    return (
      <div className="p-4 lg:p-6 max-w-2xl mx-auto">
        <Alert variant="warning" title="Chưa có hồ sơ bệnh nhân">
          Tài khoản chưa được liên kết với hồ sơ bệnh nhân. Vui lòng liên hệ hỗ trợ.
        </Alert>
      </div>
    )
  }

  // Feature flag off → tell the patient it is coming soon (route may be opened directly).
  if (flags && !flags.ocr) {
    return (
      <div className="p-4 lg:p-6 max-w-2xl mx-auto space-y-4">
        <PageHeader title="Tải lên kết quả" />
        <Alert variant="info" title="Sắp ra mắt">
          Tính năng tự động đọc kết quả xét nghiệm đang được hoàn thiện. Bạn có thể nhập tay kết quả ở
          trang Xét nghiệm.
        </Alert>
        <Button variant="outline" onClick={() => router.push('/labs')}>
          <ArrowLeft className="size-4 mr-1" /> Về trang xét nghiệm
        </Button>
      </div>
    )
  }

  return (
    <div className="p-4 lg:p-6 max-w-2xl mx-auto space-y-5 pb-28">
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => (step === 'review' ? (setDraft(null), setError(null)) : router.push('/labs'))}
          className="flex items-center gap-1.5 text-[16px] text-mint-600"
          aria-label="Quay lại"
        >
          <ArrowLeft className="size-5" /> Quay lại
        </button>
      </div>

      <PageHeader title={step === 'input' ? 'Tải lên kết quả xét nghiệm' : 'Kiểm tra & xác nhận'} />

      {error && <Alert variant="danger" title={error} />}

      {step === 'input' && (
        <>
          <ModeTabs mode={mode} onChange={(m) => { setMode(m); setError(null) }} />

          <GlassCard>
            {mode === 'camera' && (
              <FilePicker
                accept="image/*"
                capture="environment"
                file={file}
                onPick={pickFile}
                hint="Chụp ảnh phiếu kết quả xét nghiệm bằng camera."
                icon={<Camera className="size-7 text-mint-500" />}
              />
            )}
            {mode === 'file' && (
              <FilePicker
                accept="image/jpeg,image/png,application/pdf"
                file={file}
                onPick={pickFile}
                hint="Chọn ảnh JPG/PNG hoặc tệp PDF (tối đa 10MB)."
                icon={<Upload className="size-7 text-mint-500" />}
              />
            )}
            {mode === 'url' && (
              <div className="space-y-3">
                <p className="text-[16px] text-text-muted">Dán đường link tới ảnh/PDF kết quả xét nghiệm.</p>
                <PatientInput
                  type="url"
                  inputMode="url"
                  placeholder="https://..."
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  leftIcon={<Link2 className="size-5" />}
                />
                <p className="text-[14px] text-text-subtle">
                  Chỉ chấp nhận đường link công khai (http/https).
                </p>
              </div>
            )}
          </GlassCard>

          <MintButton
            fullWidth
            loading={submitting}
            disabled={mode === 'url' ? !url.trim() : !file}
            onClick={submitForDraft}
          >
            Tải lên & đọc kết quả
          </MintButton>
        </>
      )}

      {step === 'review' && draft && (
        <>
          {draft.manual_fallback ? (
            <Alert variant="info" title="Chưa nhận diện được chỉ số">
              Bạn có thể nhập tay kết quả xét nghiệm bên dưới rồi lưu.
            </Alert>
          ) : draft.low_confidence ? (
            <Alert variant="warning" title="Một số chỉ số có độ tin cậy thấp">
              Vui lòng kiểm tra lại các giá trị được tô màu vàng/đỏ trước khi lưu.
            </Alert>
          ) : (
            <div className="flex items-center gap-2 text-[15px] text-mint-700">
              <CheckCircle2 className="size-5" /> Đã đọc {draft.parsed_values.length} chỉ số. Hãy kiểm tra lại trước khi lưu.
            </div>
          )}

          <GlassCard>
            <label className="block text-[15px] font-medium text-mint-700 mb-1.5">Tên phòng khám / xét nghiệm (tuỳ chọn)</label>
            <PatientInput
              placeholder="VD: Phòng khám Đa khoa..."
              value={labName}
              onChange={(e) => setLabName(e.target.value)}
            />
          </GlassCard>

          <div className="space-y-3">
            {rows.map((row, i) => {
              const badge = confidenceBadge(row.confidence)
              const lowConf = row.confidence != null && row.confidence < 0.6
              return (
                <GlassCard key={i}>
                  <div className="flex items-start justify-between gap-2 mb-2">
                    <Badge variant={badge.variant} size="sm">{badge.label}</Badge>
                    <div className="flex items-center gap-2">
                      {row.status && STATUS_LABEL[row.status] && (
                        <span className="text-[14px] text-text-subtle">{STATUS_LABEL[row.status]}</span>
                      )}
                      <button
                        type="button"
                        onClick={() => setRows((rs) => rs.filter((_, idx) => idx !== i))}
                        aria-label="Xoá chỉ số"
                        className="p-1.5 text-danger hover:bg-danger-light rounded-md"
                      >
                        <Trash2 className="size-4" />
                      </button>
                    </div>
                  </div>
                  <PatientInput
                    aria-label="Tên chỉ số"
                    placeholder="Tên chỉ số"
                    value={row.test_name}
                    invalid={lowConf}
                    onChange={(e) => setRow(i, { test_name: e.target.value })}
                  />
                  <div className="grid grid-cols-3 gap-2 mt-2">
                    <PatientInput aria-label="Giá trị" type="number" step="any" inputMode="decimal" placeholder="Giá trị" value={row.value} invalid={lowConf} onChange={(e) => setRow(i, { value: e.target.value })} />
                    <PatientInput aria-label="Đơn vị" placeholder="Đơn vị" value={row.unit} onChange={(e) => setRow(i, { unit: e.target.value })} />
                    <PatientInput aria-label="Tham chiếu" placeholder="Tham chiếu" value={row.reference_range} onChange={(e) => setRow(i, { reference_range: e.target.value })} />
                  </div>
                  {lowConf && (
                    <p className="mt-2 flex items-center gap-1 text-[14px] text-danger">
                      <AlertTriangle className="size-4" /> Cần kiểm tra lại số liệu này.
                    </p>
                  )}
                </GlassCard>
              )
            })}

            <Button
              type="button"
              variant="outline"
              onClick={() => setRows((rs) => [...rs, { test_name: '', value: '', unit: '', reference_range: '', confidence: null, status: null }])}
            >
              <Plus className="size-4 mr-1" /> Thêm chỉ số
            </Button>
          </div>

          <MintButton fullWidth loading={saving} onClick={confirmSave}>
            Xác nhận & lưu vào hồ sơ
          </MintButton>
          <p className="text-center text-[14px] text-text-subtle">
            Kết quả chỉ được lưu sau khi bạn xác nhận.
          </p>
        </>
      )}
    </div>
  )
}

// ── File picker (camera/file) ───────────────────────────────────────────────────

function FilePicker({
  accept,
  capture,
  file,
  onPick,
  hint,
  icon,
}: {
  accept: string
  capture?: 'environment' | 'user'
  file: File | null
  onPick: (f: File | null) => void
  hint: string
  icon: React.ReactNode
}) {
  const inputRef = React.useRef<HTMLInputElement>(null)
  return (
    <div className="space-y-3">
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        className="w-full flex flex-col items-center gap-3 rounded-2xl border-2 border-dashed border-mint-200 bg-white/50 py-8 hover:bg-white/80 transition-colors"
      >
        <span className="flex items-center justify-center size-16 rounded-full bg-mint-50">{icon}</span>
        <span className="text-[16px] font-medium text-text">
          {file ? file.name : 'Chạm để chọn'}
        </span>
        <span className="text-[14px] text-text-subtle px-6 text-center">{hint}</span>
      </button>
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        capture={capture}
        className="hidden"
        onChange={(e) => onPick(e.target.files?.[0] ?? null)}
      />
    </div>
  )
}
