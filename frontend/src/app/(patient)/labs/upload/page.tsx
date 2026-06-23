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
import { GlassCard, MintButton, PatientInput, SectionHeader } from '@/components/patient'
import { PatientScreenHeader } from '@/components/patient/header'
import { useAuth } from '@/lib/auth/context'
import { useFeatureFlags } from '@/lib/api/features'
import {
  createManualLabResults,
  uploadLabDraft,
  type LabUploadDraft,
  type ManualLabItem,
} from '@/lib/api/patient'
import {
  cn,
  displayDateToIso,
  formatDateInput,
  isoToDisplayDate,
  validateExamDate,
} from '@/lib/utils'

const MAX_MB = 10
const ACCEPT = ['image/jpeg', 'image/png', 'application/pdf']

type Mode = 'camera' | 'file' | 'url'

interface EditRow {
  test_name: string
  value: string
  unit: string
  reference_range: string
  confidence: number | null // null = manually added row
  status: string | null
}

const STATUS_LABEL: Record<string, string> = {
  normal: 'Bình thường',
  low: 'Thấp',
  high: 'Cao',
  critical: 'Cần lưu ý',
}

// Confidence → light-mint tone (decision-first: green = trust, amber/red = check).
interface ConfTone {
  label: string
  pill: string
}

function confidenceTone(c: number | null): ConfTone {
  if (c == null) return { label: 'Tự nhập', pill: 'bg-[#DCFCE7] text-[#0E5B2F]' }
  if (c >= 0.85) return { label: 'Độ tin cậy cao', pill: 'bg-[#DCFCE7] text-[#0E5B2F]' }
  if (c >= 0.6) return { label: 'Cần kiểm tra', pill: 'bg-[#FEF3C7] text-[#78350F]' }
  return { label: 'Tin cậy thấp', pill: 'bg-[#FEE2E2] text-[#991B1B]' }
}

// ─── Mode picker ────────────────────────────────────────────────────────────────

function ModeTabs({ mode, onChange }: { mode: Mode; onChange: (m: Mode) => void }) {
  const tabs: { key: Mode; label: string; icon: React.ReactNode }[] = [
    { key: 'camera', label: 'Chụp ảnh', icon: <Camera className="size-6" aria-hidden="true" /> },
    { key: 'file', label: 'Tải tệp', icon: <Upload className="size-6" aria-hidden="true" /> },
    { key: 'url', label: 'Dán link', icon: <Link2 className="size-6" aria-hidden="true" /> },
  ]
  return (
    <div role="tablist" aria-label="Cách tải kết quả" className="grid grid-cols-3 gap-2.5">
      {tabs.map((t) => {
        const active = mode === t.key
        return (
          <button
            key={t.key}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(t.key)}
            className={cn(
              'flex h-[88px] flex-col items-center justify-center gap-1.5 rounded-3xl transition-all',
              active
                ? 'bg-gradient-to-br from-mint-400 to-mint-600 text-white shadow-glow-mint'
                : 'border border-white/70 bg-white/80 text-text-muted ring-1 ring-mint-100/50 backdrop-blur-xl shadow-glass active:scale-[0.98]'
            )}
          >
            {t.icon}
            <span className="text-[15px] font-semibold">{t.label}</span>
          </button>
        )
      })}
    </div>
  )
}

// ─── Inline alert (light-mint, never technical) ────────────────────────────────

type AlertTone = 'danger' | 'warning' | 'info'

const ALERT_TONE: Record<AlertTone, { wrap: string; title: string; body: string }> = {
  danger: {
    wrap: 'border-[1.5px] border-[#FCA5A5] bg-[#FEE2E2]/70',
    title: 'text-[#991B1B]',
    body: 'text-[#7F1D1D]',
  },
  warning: {
    wrap: 'border-[1.5px] border-[#FDE68A] bg-[#FEF3C7]/70',
    title: 'text-[#78350F]',
    body: 'text-[#713F12]',
  },
  info: {
    wrap: 'border-[1.5px] border-mint-200 bg-mint-50/70',
    title: 'text-[#0E5B2F]',
    body: 'text-[#1A4535]',
  },
}

function InlineAlert({
  tone,
  title,
  children,
}: {
  tone: AlertTone
  title: string
  children?: React.ReactNode
}) {
  const t = ALERT_TONE[tone]
  return (
    <div className={cn('rounded-3xl p-4 shadow-glass backdrop-blur-xl', t.wrap)} role="alert">
      <p className={cn('text-[16px] font-bold', t.title)}>{title}</p>
      {children && <p className={cn('mt-1 text-[15px] leading-relaxed', t.body)}>{children}</p>}
    </div>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

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
        reference_range: v.reference_range ?? '',
        confidence: v.confidence,
        status: v.status,
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
                status: null,
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
        test_date: displayDateToIso(testDate),
        results,
      })
      router.push('/labs')
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Lưu thất bại. Vui lòng thử lại.')
      setSaving(false)
    }
  }

  if (!user) return null

  if (!patientId) {
    return (
      <div className="mx-auto mt-10 max-w-md p-4">
        <GlassCard>
          <h2 className="text-[18px] font-semibold text-text">Chưa có hồ sơ bệnh nhân</h2>
          <p className="mt-1 text-[15px] text-text-muted">
            Tài khoản chưa được liên kết với hồ sơ bệnh nhân. Vui lòng liên hệ hỗ trợ.
          </p>
        </GlassCard>
      </div>
    )
  }

  // Feature flag off → tell the patient it is coming soon (route may be opened directly).
  if (flags && !flags.ocr) {
    return (
      <div className="mx-auto max-w-md space-y-5 p-4 pb-12 lg:max-w-2xl lg:p-6">
        <PatientScreenHeader
          title="Tải lên kết quả"
          subtitle="Tự động đọc kết quả xét nghiệm"
          onBack={() => router.push('/labs')}
        />
        <InlineAlert tone="info" title="Sắp ra mắt">
          Tính năng tự động đọc kết quả xét nghiệm đang được hoàn thiện. Bạn vẫn có thể nhập tay kết
          quả ở trang Xét nghiệm.
        </InlineAlert>
        <MintButton variant="secondary" fullWidth onClick={() => router.push('/labs')}>
          <ArrowLeft className="mr-1.5 size-5" aria-hidden="true" /> Về trang xét nghiệm
        </MintButton>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-md space-y-5 p-4 pb-28 lg:max-w-2xl lg:p-6">
      {/* Back + title. In review, back returns to the input step (not the route). */}
      <PatientScreenHeader
        title={step === 'input' ? 'Tải lên kết quả xét nghiệm' : 'Kiểm tra & xác nhận'}
        subtitle={
          step === 'input'
            ? 'Chụp ảnh, tải tệp hoặc dán link'
            : 'Đối chiếu với phiếu gốc trước khi lưu'
        }
        onBack={() => (step === 'review' ? (setDraft(null), setError(null)) : router.push('/labs'))}
      />

      {error && <InlineAlert tone="danger" title={error} />}

      {step === 'input' && (
        <>
          <ModeTabs
            mode={mode}
            onChange={(m) => {
              setMode(m)
              setError(null)
            }}
          />

          <GlassCard>
            {mode === 'camera' && (
              <FilePicker
                accept="image/*"
                capture="environment"
                file={file}
                onPick={pickFile}
                hint="Chụp ảnh phiếu kết quả xét nghiệm bằng camera."
                icon={<Camera className="size-8 text-mint-600" aria-hidden="true" />}
              />
            )}
            {mode === 'file' && (
              <FilePicker
                accept="image/jpeg,image/png,application/pdf"
                file={file}
                onPick={pickFile}
                hint="Chọn ảnh JPG/PNG hoặc tệp PDF (tối đa 10MB)."
                icon={<Upload className="size-8 text-mint-600" aria-hidden="true" />}
              />
            )}
            {mode === 'url' && (
              <div className="space-y-3">
                <p className="text-[16px] text-text-muted">
                  Dán đường link tới ảnh/PDF kết quả xét nghiệm.
                </p>
                <PatientInput
                  type="url"
                  inputMode="url"
                  placeholder="https://..."
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  leftIcon={<Link2 className="size-5" aria-hidden="true" />}
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
            <InlineAlert tone="info" title="Chưa nhận diện được chỉ số">
              Bạn có thể nhập tay kết quả xét nghiệm bên dưới rồi lưu.
            </InlineAlert>
          ) : draft.low_confidence ? (
            <InlineAlert tone="warning" title="Một số chỉ số có độ tin cậy thấp">
              Vui lòng kiểm tra lại các giá trị được tô màu vàng/đỏ trước khi lưu.
            </InlineAlert>
          ) : (
            <div className="flex items-center gap-2 rounded-3xl bg-[#DCFCE7] px-4 py-3 text-[15px] font-semibold text-[#0E5B2F]">
              <CheckCircle2 className="size-5 shrink-0" aria-hidden="true" />
              Đã đọc {draft.parsed_values.length} chỉ số. Hãy kiểm tra lại trước khi lưu.
            </div>
          )}

          {/* Exam date — prominent, required, at the TOP of the review form. */}
          <GlassCard>
            <div className="mb-2 flex items-center justify-between gap-2">
              <label className="flex items-center gap-1.5 text-[16px] font-bold text-[#0D815A]">
                <CalendarDays className="size-5" aria-hidden="true" /> Ngày xét nghiệm
              </label>
              {testDateAuto && (
                <span className="rounded-full bg-[#DCFCE7] px-2.5 py-0.5 text-[12px] font-semibold text-[#0E5B2F]">
                  Tự động phát hiện
                </span>
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
            <p className="mt-2 text-[14px] text-text-subtle">
              Ngày khám/lấy mẫu thật trên phiếu — không phải ngày tải lên.
            </p>
          </GlassCard>

          <GlassCard>
            <label className="mb-2 block text-[15px] font-semibold text-[#0D815A]">
              Tên phòng khám / xét nghiệm (tuỳ chọn)
            </label>
            <PatientInput
              placeholder="VD: Phòng khám Đa khoa..."
              value={labName}
              onChange={(e) => setLabName(e.target.value)}
            />
          </GlassCard>

          <section aria-label="Các chỉ số xét nghiệm" className="space-y-3">
            <SectionHeader title="Các chỉ số" />
            {rows.map((row, i) => {
              const tone = confidenceTone(row.confidence)
              const lowConf = row.confidence != null && row.confidence < 0.6
              return (
                <GlassCard key={i} className={cn(lowConf && 'border-[1.5px] border-[#FCA5A5]')}>
                  <div className="mb-3 flex items-start justify-between gap-2">
                    <span
                      className={cn('rounded-full px-3 py-1 text-[13px] font-semibold', tone.pill)}
                    >
                      {tone.label}
                    </span>
                    <div className="flex items-center gap-2">
                      {row.status && STATUS_LABEL[row.status] && (
                        <span className="text-[14px] text-text-muted">
                          {STATUS_LABEL[row.status]}
                        </span>
                      )}
                      <button
                        type="button"
                        onClick={() => setRows((rs) => rs.filter((_, idx) => idx !== i))}
                        aria-label="Xoá chỉ số"
                        className="grid size-12 place-items-center rounded-xl text-[#991B1B] transition-colors hover:bg-[#FEE2E2]"
                      >
                        <Trash2 className="size-[18px]" aria-hidden="true" />
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
                    <p className="mt-2 flex items-center gap-1.5 text-[14px] font-medium text-[#991B1B]">
                      <AlertTriangle className="size-4 shrink-0" aria-hidden="true" /> Cần kiểm tra
                      lại số liệu này.
                    </p>
                  )}
                </GlassCard>
              )
            })}

            <button
              type="button"
              onClick={() =>
                setRows((rs) => [
                  ...rs,
                  {
                    test_name: '',
                    value: '',
                    unit: '',
                    reference_range: '',
                    confidence: null,
                    status: null,
                  },
                ])
              }
              className="flex h-12 w-full items-center justify-center gap-1.5 rounded-2xl border-[1.5px] border-dashed border-mint-300 bg-white/60 text-[16px] font-semibold text-[#0D815A] transition-colors hover:bg-mint-50/70"
            >
              <Plus className="size-5" aria-hidden="true" /> Thêm chỉ số
            </button>
          </section>

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

// ─── File picker (camera/file) ──────────────────────────────────────────────────

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
        className="flex w-full flex-col items-center gap-3 rounded-3xl border-[1.5px] border-dashed border-mint-300 bg-white/55 py-9 transition-colors hover:bg-white/80 active:scale-[0.99]"
      >
        <span className="grid size-16 place-items-center rounded-full bg-mint-50 ring-1 ring-mint-200/60">
          {icon}
        </span>
        <span className="px-6 text-center text-[16px] font-semibold text-text">
          {file ? file.name : 'Chạm để chọn'}
        </span>
        <span className="px-6 text-center text-[14px] text-text-subtle">{hint}</span>
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
