'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import {
  AlertTriangle,
  ArrowLeft,
  Camera,
  CalendarDays,
  CheckCircle2,
  Link2,
  Plus,
  Trash2,
  Upload,
} from 'lucide-react'
import { PatientErrorState } from '@/components/patient/states'
import { PatientInput } from '@/components/patient'
import { NeuCard, NeuButton, NeuBadge } from '@/components/patient/neu'
import type { NeuTone } from '@/components/patient/metrics/metricVisuals'
import { useAuth } from '@/lib/auth/context'
import { useFeatureFlags } from '@/lib/api/features'
import {
  createManualLabResults,
  uploadLabDraft,
  type LabUploadDraft,
  type ManualLabItem,
} from '@/lib/api/patient'
import {
  displayDateToIso,
  formatDateInput,
  isOldLabDate,
  isoToDisplayDate,
  validateExamDate,
} from '@/lib/utils'

const MAX_MB = 10
const ACCEPT = ['image/jpeg', 'image/png', 'application/pdf']
const HERO_GRADIENT = 'linear-gradient(160deg,#17AE7B,#0B6B4D)'

type Mode = 'camera' | 'file' | 'url'

interface EditRow {
  test_name: string
  value: string
  unit: string
  reference_range: string
  confidence: number | null // null = manually added row
  needs_verification: boolean
  status: string | null
  confidence_reasons: string[]
  // As-printed values (read-only display).
  original_value: number | null
  original_unit: string | null
  // Vietnamese display label and exact OCR'd label.
  display_name_vi: string
  original_test_name: string
  // Canonical SI values — for the save path (health metrics).
  canonical_value: number | null
  canonical_unit: string | null
  // Reference range in the same display unit as value/unit.
  display_reference_range: string | null
}

const STATUS_LABEL: Record<string, string> = {
  normal: 'Bình thường',
  low: 'Thấp',
  high: 'Cao',
  critical: 'Cần lưu ý',
}

function confidenceBadge(c: number | null): { label: string; tone: NeuTone } {
  if (c == null) return { label: 'Tự nhập', tone: 'ok' }
  if (c >= 0.85) return { label: 'Độ tin cậy cao', tone: 'ok' }
  if (c >= 0.6) return { label: 'Cần kiểm tra', tone: 'watch' }
  return { label: 'Tin cậy thấp', tone: 'alert' }
}

function ConfidenceBadge({
  confidence,
  needsVerification,
  reasons,
}: {
  confidence: number | null
  needsVerification: boolean
  reasons?: string[]
}) {
  const showReasons = reasons && reasons.length > 0 && confidence !== null && confidence < 0.85

  let badge: React.ReactNode = null
  if (confidence === 0) {
    badge = (
      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-red-50 border border-red-200 text-red-700 ml-2">
        Giá trị không hợp lệ — cần kiểm tra lại
      </span>
    )
  } else if (confidence !== null && confidence < 0.75) {
    badge = (
      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-amber-50 border border-amber-200 text-amber-700 ml-2">
        Độ tin cậy thấp — nên xác nhận
      </span>
    )
  } else if (needsVerification) {
    badge = (
      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-blue-50 border border-blue-200 text-blue-700 ml-2">
        Cần xác nhận
      </span>
    )
  }

  if (!badge && !showReasons) return null

  return (
    <div className="mt-1">
      {badge}
      {showReasons && (
        <ul className="mt-1 ml-2 space-y-0.5">
          {reasons!.map((r, i) => (
            <li
              key={i}
              className={`text-xs ${r.startsWith('⚠') ? 'text-amber-700' : 'text-green-700'}`}
            >
              {r}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

// ── Mode picker ────────────────────────────────────────────────────────────────

function ModeTabs({ mode, onChange }: { mode: Mode; onChange: (m: Mode) => void }) {
  const tabs: { key: Mode; label: string; icon: React.ReactNode }[] = [
    { key: 'camera', label: 'Chụp ảnh', icon: <Camera className="size-5" /> },
    { key: 'file', label: 'Tải tệp', icon: <Upload className="size-5" /> },
    { key: 'url', label: 'Dán link', icon: <Link2 className="size-5" /> },
  ]
  return (
    <div role="tablist" aria-label="Cách tải kết quả" className="grid grid-cols-3 gap-2.5">
      {tabs.map((t) => {
        const active = mode === t.key
        return (
          <button
            key={t.key}
            role="tab"
            aria-selected={active}
            onClick={() => onChange(t.key)}
            className={
              active
                ? 'flex flex-col items-center gap-1.5 rounded-[16px] py-4 text-white'
                : 'neu-raised flex flex-col items-center gap-1.5 rounded-[16px] py-4 text-neu-muted'
            }
            style={
              active
                ? { background: HERO_GRADIENT, boxShadow: '0 10px 20px -10px rgba(11,107,77,0.6)' }
                : undefined
            }
          >
            {t.icon}
            <span className="text-[14px] font-semibold">{t.label}</span>
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
  const [testDate, setTestDate] = React.useState('') // display DD/MM/YYYY
  const [testDateAuto, setTestDateAuto] = React.useState(false) // detected by OCR
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
      const input = mode === 'url' ? { url: url.trim() } : file ? { file } : null
      if (!input || (mode === 'url' && !url.trim())) {
        setError(mode === 'url' ? 'Vui lòng dán đường link.' : 'Vui lòng chọn tệp.')
        setSubmitting(false)
        return
      }
      const d = await uploadLabDraft(input)
      setDraft(d)
      // Pre-fill the exam date from OCR if detected; else leave empty (the patient
      // MUST choose it — never silently default to today).
      setTestDate(isoToDisplayDate(d.extracted_test_date))
      setTestDateAuto(Boolean(d.extracted_test_date))
      const mapped: EditRow[] = d.parsed_values.map((v) => ({
        test_name: v.test_name,
        value: String(v.value),
        unit: v.unit ?? '',
        reference_range: v.display_reference_range ?? v.reference_range ?? '',
        confidence: v.confidence,
        needs_verification: v.needs_verification,
        status: v.status,
        confidence_reasons: v.confidence_reasons ?? [],
        original_value: v.original_value ?? null,
        original_unit: v.original_unit ?? null,
        display_name_vi: v.display_name_vi ?? '',
        original_test_name: v.original_test_name ?? '',
        canonical_value: v.canonical_value ?? null,
        canonical_unit: v.canonical_unit ?? null,
        display_reference_range: v.display_reference_range ?? null,
      }))
      // Always give the patient at least one editable row (manual fallback).
      setRows(
        mapped.length
          ? mapped
          : [
              {
                test_name: '',
                value: '',
                unit: '',
                reference_range: '',
                confidence: null,
                needs_verification: false,
                status: null,
                confidence_reasons: [],
                original_value: null,
                original_unit: null,
                display_name_vi: '',
                original_test_name: '',
                canonical_value: null,
                canonical_unit: null,
                display_reference_range: null,
              },
            ]
      )
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
    const dateErr = validateExamDate(testDate)
    if (dateErr) {
      setError(dateErr)
      return
    }
    const named = rows.filter((r) => r.test_name.trim())
    if (named.length === 0) {
      setError('Vui lòng nhập ít nhất một chỉ số.')
      return
    }
    const results: ManualLabItem[] = named.map((r) => ({
      test_name: r.test_name.trim(),
      value:
        r.canonical_value != null ? r.canonical_value : r.value.trim() ? parseFloat(r.value) : null,
      unit: r.canonical_unit || r.unit.trim() || null,
      reference_range: r.display_reference_range ?? (r.reference_range.trim() || null),
      original_value: r.original_value,
      original_unit: r.original_unit,
      original_reference_range: r.display_reference_range,
      original_test_name: r.original_test_name || null,
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
        test_date: displayDateToIso(testDate),
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
      <div className="p-4 max-w-md mx-auto mt-10">
        <div role="alert" className="rounded-[14px] bg-[#FEF9EC] border border-[#E0A92E]/30 p-4">
          <p className="text-[14px] font-bold text-[#8B6400]">Chưa có hồ sơ bệnh nhân</p>
          <p className="text-[13px] text-[#8B6400]/80 mt-1">
            Tài khoản chưa được liên kết với hồ sơ bệnh nhân. Vui lòng liên hệ hỗ trợ.
          </p>
        </div>
      </div>
    )
  }

  // Feature flag off → tell the patient it is coming soon (route may be opened directly).
  if (flags && !flags.ocr) {
    return (
      <div className="p-4 max-w-md mx-auto space-y-4">
        <PageHeaderNeu title="Tải lên kết quả" onBack={() => router.push('/labs')} />
        <div className="rounded-[14px] bg-[#EEF4FB] border border-[#2563EB]/20 p-4">
          <p className="text-[14px] font-bold text-[#1E4DA1]">Sắp ra mắt</p>
          <p className="text-[13px] text-[#1E4DA1]/80 mt-1">
            Tính năng tự động đọc kết quả xét nghiệm đang được hoàn thiện. Bạn có thể nhập tay kết
            quả ở trang Xét nghiệm.
          </p>
        </div>
        <NeuButton variant="secondary" onClick={() => router.push('/labs')}>
          Về trang xét nghiệm
        </NeuButton>
      </div>
    )
  }

  return (
    <div className="p-4 max-w-md mx-auto space-y-4 pb-28">
      <PageHeaderNeu
        title={step === 'input' ? 'Tải lên kết quả' : 'Kiểm tra & xác nhận'}
        onBack={() => (step === 'review' ? (setDraft(null), setError(null)) : router.push('/labs'))}
      />

      {error && <PatientErrorState title="Lỗi" message={error} onRetry={() => setError(null)} />}

      {step === 'input' && (
        <>
          <ModeTabs
            mode={mode}
            onChange={(m) => {
              setMode(m)
              setError(null)
            }}
          />

          <NeuCard>
            {mode === 'camera' && (
              <FilePicker
                accept="image/*"
                capture="environment"
                file={file}
                onPick={pickFile}
                hint="Chụp ảnh phiếu kết quả xét nghiệm bằng camera."
                icon={<Camera className="size-7 text-neu-green" />}
              />
            )}
            {mode === 'file' && (
              <FilePicker
                accept="image/jpeg,image/png,application/pdf"
                file={file}
                onPick={pickFile}
                hint="Chọn ảnh JPG/PNG hoặc tệp PDF (tối đa 10MB)."
                icon={<Upload className="size-7 text-neu-green" />}
              />
            )}
            {mode === 'url' && (
              <div className="space-y-3">
                <p className="text-[15px] text-neu-muted">
                  Dán đường link tới ảnh/PDF kết quả xét nghiệm.
                </p>
                <PatientInput
                  type="url"
                  inputMode="url"
                  placeholder="https://..."
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  leftIcon={<Link2 className="size-5" />}
                />
                <p className="text-[13px] text-neu-subtle">
                  Chỉ chấp nhận đường link công khai (http/https).
                </p>
              </div>
            )}
          </NeuCard>

          <NeuButton
            disabled={submitting || (mode === 'url' ? !url.trim() : !file)}
            onClick={submitForDraft}
          >
            {submitting ? 'Đang xử lý...' : 'Tải lên & đọc kết quả'}
          </NeuButton>
        </>
      )}

      {step === 'review' && draft && (
        <>
          {draft.manual_fallback ? (
            <div className="rounded-[14px] bg-[#EEF4FB] border border-[#2563EB]/20 p-4">
              <p className="text-[14px] font-bold text-[#1E4DA1]">Chưa nhận diện được chỉ số</p>
              <p className="text-[13px] text-[#1E4DA1]/80 mt-1">
                Bạn có thể nhập tay kết quả xét nghiệm bên dưới rồi lưu.
              </p>
            </div>
          ) : draft.low_confidence ? (
            <div
              role="alert"
              className="rounded-[14px] bg-[#FEF9EC] border border-[#E0A92E]/30 p-4"
            >
              <p className="text-[14px] font-bold text-[#8B6400]">
                Một số chỉ số có độ tin cậy thấp
              </p>
              <p className="text-[13px] text-[#8B6400]/80 mt-1">
                Vui lòng kiểm tra lại các giá trị được tô màu vàng/đỏ trước khi lưu.
              </p>
            </div>
          ) : (
            <div className="flex items-center gap-2 text-[15px] text-neu-green">
              <CheckCircle2 className="size-5" /> Đã đọc {draft.parsed_values.length} chỉ số. Hãy
              kiểm tra lại trước khi lưu.
            </div>
          )}

          {/* Persistent review reminder — always shown on all review states */}
          <div
            role="note"
            className="rounded-[14px] bg-[#FEF9EC] border border-[#E0A92E]/30 px-4 py-3"
          >
            <p className="text-[13px] font-semibold text-[#8B6400]">
              Vui lòng kiểm tra lại trước khi lưu
            </p>
          </div>

          {/* Backend warnings: no-date detected, cloud-fallback used, OCR issues */}
          {draft.warnings.length > 0 && (
            <div className="space-y-1.5">
              {draft.warnings.map((w, i) => (
                <div
                  key={i}
                  role="alert"
                  className="flex items-start gap-2 rounded-[12px] bg-[#FEF9EC] border border-[#E0A92E]/30 px-3 py-2.5"
                >
                  <AlertTriangle className="size-4 mt-0.5 shrink-0 text-[#E0A92E]" />
                  <p className="text-[13px] text-[#8B6400]">{w}</p>
                </div>
              ))}
            </div>
          )}

          {/* Exam date — prominent, required, at the TOP of the review form. */}
          <NeuCard>
            <div className="mb-1.5 flex items-center justify-between">
              <label className="flex items-center gap-1.5 text-[15px] font-semibold text-neu-green">
                <CalendarDays className="size-5" /> Ngày xét nghiệm
              </label>
              {testDateAuto && (
                <NeuBadge tone="ok" className="!text-[11px] !px-2.5 !py-0.5 before:!hidden">
                  Tự động phát hiện
                </NeuBadge>
              )}
            </div>
            <PatientInput
              aria-label="Ngày xét nghiệm"
              inputMode="numeric"
              placeholder="DD/MM/YYYY"
              value={testDate}
              invalid={Boolean(testDate) && validateExamDate(testDate) !== null}
              onChange={(e) => {
                setTestDate(formatDateInput(e.target.value))
                setTestDateAuto(false)
              }}
            />
            <p className="mt-1.5 text-[13px] text-neu-subtle">
              Ngày khám/lấy mẫu thật trên phiếu — không phải ngày tải lên.
            </p>
          </NeuCard>

          {testDate && isOldLabDate(testDate) && (
            <div
              role="note"
              className="rounded-[14px] bg-[#EEF4FB] border border-[#2563EB]/20 px-4 py-3"
            >
              <p className="text-[13px] text-[#1E4DA1]">
                Kết quả này đã cũ hơn 12 tháng — chỉ dùng để tham khảo lịch sử. Bạn vẫn có thể lưu.
              </p>
            </div>
          )}

          <NeuCard>
            <label className="mb-1.5 block text-[14px] font-semibold text-neu-green">
              Tên phòng khám / xét nghiệm (tuỳ chọn)
            </label>
            <PatientInput
              placeholder="VD: Phòng khám Đa khoa..."
              value={labName}
              onChange={(e) => setLabName(e.target.value)}
            />
          </NeuCard>

          <div className="space-y-3">
            {rows.map((row, i) => {
              const badge = confidenceBadge(row.confidence)
              const lowConf = row.confidence != null && row.confidence < 0.6
              return (
                <NeuCard key={i}>
                  <div className="mb-2 flex items-start justify-between gap-2">
                    <div className="flex items-center flex-wrap gap-1">
                      <NeuBadge
                        tone={badge.tone}
                        className="!text-[11px] !px-2.5 !py-0.5 before:!hidden"
                      >
                        {badge.label}
                      </NeuBadge>
                      <ConfidenceBadge
                        confidence={row.confidence}
                        needsVerification={row.needs_verification}
                        reasons={row.confidence_reasons}
                      />
                    </div>
                    <div className="flex items-center gap-2">
                      {row.status && STATUS_LABEL[row.status] && (
                        <span className="text-[13px] text-neu-subtle">
                          {STATUS_LABEL[row.status]}
                        </span>
                      )}
                      <button
                        type="button"
                        onClick={() => setRows((rs) => rs.filter((_, idx) => idx !== i))}
                        aria-label="Xoá chỉ số"
                        className="rounded-md p-1.5 text-[#D92D20] hover:bg-[#f6dede]"
                      >
                        <Trash2 className="size-4" />
                      </button>
                    </div>
                  </div>
                  {/* Vietnamese display label — not editable, from OCR + catalog */}
                  <div className="text-[15px] font-semibold text-neu-text">
                    {row.display_name_vi || row.test_name}
                  </div>
                  {row.original_test_name && row.original_test_name !== row.test_name && (
                    <div className="text-[11px] text-neu-subtle font-mono">
                      {row.original_test_name}
                    </div>
                  )}
                  <div className="mt-2 grid grid-cols-3 gap-2">
                    <PatientInput
                      aria-label="Giá trị"
                      type="number"
                      step="any"
                      inputMode="decimal"
                      placeholder="Giá trị"
                      value={row.value}
                      invalid={lowConf}
                      onChange={(e) => setRow(i, { value: e.target.value })}
                    />
                    <PatientInput
                      aria-label="Đơn vị"
                      placeholder="Đơn vị"
                      value={row.unit}
                      onChange={(e) => setRow(i, { unit: e.target.value })}
                    />
                    <PatientInput
                      aria-label="Tham chiếu"
                      placeholder="Tham chiếu"
                      value={row.reference_range}
                      onChange={(e) => setRow(i, { reference_range: e.target.value })}
                    />
                  </div>
                  {lowConf && (
                    <p className="mt-2 flex items-center gap-1 text-[13px] text-[#D92D20]">
                      <AlertTriangle className="size-4" /> Cần kiểm tra lại số liệu này.
                    </p>
                  )}
                  {row.canonical_value != null &&
                    row.canonical_unit &&
                    row.canonical_unit !== row.unit && (
                      <p className="mt-1 text-[11px] text-neu-subtle">
                        Chuẩn hóa: {row.canonical_value.toFixed(4)} {row.canonical_unit}
                      </p>
                    )}
                </NeuCard>
              )
            })}

            <NeuButton
              variant="secondary"
              onClick={() =>
                setRows((rs) => [
                  ...rs,
                  {
                    test_name: '',
                    value: '',
                    unit: '',
                    reference_range: '',
                    confidence: null,
                    needs_verification: false,
                    status: null,
                    confidence_reasons: [],
                    original_value: null,
                    original_unit: null,
                    display_name_vi: '',
                    original_test_name: '',
                    canonical_value: null,
                    canonical_unit: null,
                    display_reference_range: null,
                  },
                ])
              }
            >
              <Plus className="size-4" /> Thêm chỉ số
            </NeuButton>
          </div>

          <NeuButton disabled={saving} onClick={confirmSave}>
            {saving ? 'Đang lưu...' : 'Xác nhận & lưu vào hồ sơ'}
          </NeuButton>
          <p className="text-center text-[13px] text-neu-subtle">
            Kết quả chỉ được lưu sau khi bạn xác nhận.
          </p>
        </>
      )}
    </div>
  )
}

// ── Neu header (back + title) ────────────────────────────────────────────────────

function PageHeaderNeu({ title, onBack }: { title: string; onBack: () => void }) {
  return (
    <header className="flex items-center gap-3">
      <button
        type="button"
        aria-label="Quay lại"
        onClick={onBack}
        className="neu-icon-btn !h-11 !w-11 !rounded-full text-neu-text"
      >
        <ArrowLeft className="size-5" />
      </button>
      <h1 className="text-[20px] font-extrabold tracking-[-0.02em] text-neu-text">{title}</h1>
    </header>
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
        className="flex w-full flex-col items-center gap-3 rounded-[18px] border-2 border-dashed border-[#bcd2cb] bg-[#eef3f1] py-8 transition-colors hover:bg-[#e6ece9]"
      >
        <span className="neu-pressed flex size-16 items-center justify-center rounded-full">
          {icon}
        </span>
        <span className="text-[15px] font-semibold text-neu-text">
          {file ? file.name : 'Chạm để chọn'}
        </span>
        <span className="px-6 text-center text-[13px] text-neu-subtle">{hint}</span>
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
