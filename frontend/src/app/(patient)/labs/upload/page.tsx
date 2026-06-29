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
  Upload,
} from 'lucide-react'
import { PatientErrorState } from '@/components/patient/states'
import { PatientInput } from '@/components/patient'
import { NeuCard, NeuButton, NeuBadge } from '@/components/patient/neu'
import { useAuth } from '@/lib/auth/context'
import {
  checkDuplicate,
  createManualLabResults,
  uploadLabDraft,
  type DuplicateCheckResponse,
  type LabUploadDraft,
  type ManualLabItem,
} from '@/lib/api/patient'
import { ApiError } from '@/lib/api/client'
import { useLabReference, formatRefRange } from '@/lib/api/labReference'
import { OcrReviewCard, buildOcrRow, makeEmptyOcrRow, type OcrRow } from './OcrReviewCard'
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

// ── OCR error card ─────────────────────────────────────────────────────────────

function OcrErrorCard({
  onRetry,
  onManualEntry,
}: {
  onRetry: () => void
  onManualEntry: () => void
}) {
  return (
    <div
      role="alert"
      className="rounded-[14px] bg-[#FEF9EC] border border-[#E0A92E]/30 p-4 space-y-3"
    >
      <p className="text-[14px] font-bold text-[#8B6400]">Chưa đọc được ảnh xét nghiệm</p>
      <p className="text-[13px] text-[#8B6400]/80">
        Hiện chưa thể đọc ảnh xét nghiệm. Bạn có thể thử lại hoặc nhập kết quả thủ công.
      </p>
      <div className="flex gap-2.5 pt-1">
        <button
          type="button"
          onClick={onRetry}
          className="flex-1 rounded-[14px] border border-[#E0A92E]/50 py-2.5 text-[14px] font-semibold text-[#8B6400]"
        >
          Thử lại
        </button>
        <button
          type="button"
          onClick={onManualEntry}
          className="flex-1 rounded-[14px] bg-[#17AE7B] py-2.5 text-[14px] font-semibold text-white"
        >
          Nhập thủ công
        </button>
      </div>
    </div>
  )
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function LabUploadPage() {
  const router = useRouter()
  const { user } = useAuth()
  const patientId = user?.patient_profile_id
  const catalog = useLabReference()

  const [mode, setMode] = React.useState<Mode>('camera')
  const [progressStep, setProgressStep] = React.useState<string | null>(null)
  const [file, setFile] = React.useState<File | null>(null)
  const [url, setUrl] = React.useState('')
  const [submitting, setSubmitting] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [ocrFailed, setOcrFailed] = React.useState(false)

  const [draft, setDraft] = React.useState<LabUploadDraft | null>(null)
  const [rows, setRows] = React.useState<OcrRow[]>([])
  const [labName, setLabName] = React.useState('')
  const [testDate, setTestDate] = React.useState('') // display DD/MM/YYYY
  const [testDateAuto, setTestDateAuto] = React.useState(false) // detected by OCR
  const [saving, setSaving] = React.useState(false)
  const [duplicateWarning, setDuplicateWarning] = React.useState<DuplicateCheckResponse | null>(
    null
  )
  const pendingResultsRef = React.useRef<{
    results: ManualLabItem[]
    labName: string | null
    isoDate: string
  } | null>(null)
  // Track when the review screen was first shown so we can compute review_time_seconds.
  const saveStartRef = React.useRef<number>(Date.now())

  const step: 'input' | 'review' = draft ? 'review' : 'input'
  // Mock OCR guard: provider_used==='mock' is only valid when explicitly opted-in via
  // MCP_OCR_PROVIDER=mock or MCP_ENABLE_MOCK_OCR=true. In production builds, block save
  // entirely so synthetic biomarkers can never be written to real patient records.
  const isMockOcrResult = Boolean(draft && draft.provider_used === 'mock' && !draft.manual_fallback)
  const isMockSaveBlocked = isMockOcrResult && process.env.NODE_ENV !== 'development'

  function pickFile(f: File | null) {
    setError(null)
    setOcrFailed(false)
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

  React.useEffect(() => {
    if (typeof window !== 'undefined') {
      const params = new URLSearchParams(window.location.search)
      if (params.get('manual') === '1') handleManualEntry()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function submitForDraft() {
    setError(null)
    setOcrFailed(false)
    setSubmitting(true)
    setProgressStep('Đang tải ảnh...')
    const t1 = setTimeout(() => setProgressStep('AI đang đọc xét nghiệm...'), 600)
    const t2 = setTimeout(() => setProgressStep('Đang chuẩn hóa chỉ số...'), 2200)
    try {
      const input = mode === 'url' ? { url: url.trim() } : file ? { file } : null
      if (!input || (mode === 'url' && !url.trim())) {
        setError(mode === 'url' ? 'Vui lòng dán đường link.' : 'Vui lòng chọn tệp.')
        setSubmitting(false)
        setProgressStep(null)
        clearTimeout(t1)
        clearTimeout(t2)
        return
      }
      if (!catalog) {
        setError('Đang tải danh mục. Vui lòng thử lại.')
        setSubmitting(false)
        setProgressStep(null)
        clearTimeout(t1)
        clearTimeout(t2)
        return
      }
      const d = await uploadLabDraft(input)
      clearTimeout(t1)
      clearTimeout(t2)
      setProgressStep('Chuẩn bị màn hình kiểm tra...')
      await new Promise((r) => setTimeout(r, 250))
      setDraft(d)
      saveStartRef.current = Date.now()
      setTestDate(isoToDisplayDate(d.extracted_test_date))
      setTestDateAuto(Boolean(d.extracted_test_date))
      const mapped: OcrRow[] = d.parsed_values.map((v) => buildOcrRow(catalog, v))
      setRows(mapped.length ? mapped : [makeEmptyOcrRow()])
    } catch {
      clearTimeout(t1)
      clearTimeout(t2)
      setOcrFailed(true)
    } finally {
      setProgressStep(null)
      setSubmitting(false)
    }
  }

  function handleManualEntry() {
    setOcrFailed(false)
    const syntheticDraft: LabUploadDraft = {
      provider_used: 'manual',
      confidence_avg: 0,
      parsed_values: [],
      warnings: [],
      raw_text_sha256: '',
      low_confidence: false,
      manual_fallback: true,
      extracted_test_date: null,
      test_date_label: null,
      test_date_confidence: 0,
      ocr_case_id: null,
      date_needs_confirmation: false,
    }
    setDraft(syntheticDraft)
    setRows([makeEmptyOcrRow()])
    saveStartRef.current = Date.now()
  }

  function buildResults(): ManualLabItem[] {
    if (!catalog) return []
    return rows
      .filter((r) => r.biomarker_key.trim())
      .map((r) => {
        const bm = catalog.biomarkers[r.biomarker_key] ?? null
        const unit = bm ? (bm.units.find((u) => u.key === r.unit_key) ?? null) : null
        const unitLabel = unit?.label ?? (r.unit_key || null)

        let refRange: string | null = null
        if (r.ref_range_source === 'catalog' && bm && unit) {
          refRange = formatRefRange(unit, bm.higher_is_better ?? false)
        } else if (r.ref_range_source === 'ocr') {
          refRange = r.original_reference_range
        } else if (r.ref_range_source === 'manual') {
          refRange = r.ref_range_manual.trim() || null
        }

        return {
          test_name: r.biomarker_key,
          value: r.value.trim() ? parseFloat(r.value) : null,
          unit: unitLabel,
          reference_range: refRange,
          original_value: r.original_value,
          original_unit: r.original_unit,
          original_reference_range: r.original_reference_range,
          original_test_name: r.original_test_name || null,
        }
      })
  }

  async function doSave(
    results: ManualLabItem[],
    labNameVal: string | null,
    isoDate: string,
    forceMode?: 'new' | 'overwrite',
    existingBatchId?: string
  ) {
    if (!patientId) return
    setSaving(true)
    setError(null)
    try {
      await createManualLabResults(patientId, {
        lab_name: labNameVal,
        test_date: isoDate,
        results,
        force_mode: forceMode,
        existing_batch_id: existingBatchId,
        ocr_case_id: draft?.ocr_case_id ?? null,
        review_time_seconds: draft ? (Date.now() - saveStartRef.current) / 1000 : null,
      })
      router.push('/labs')
    } catch (e: unknown) {
      console.error('[doSave] error:', e)
      if (e instanceof ApiError) {
        // Parse structured VALIDATION_ERROR detail from backend
        let msg: string
        try {
          const body = JSON.parse(e.detail) as {
            code?: string
            detail?: Array<{ field: string; message: string; received: string }>
          }
          if (body?.code === 'VALIDATION_ERROR' && Array.isArray(body.detail)) {
            msg = body.detail
              .map((err) => `${err.field}: ${err.message} (nhận được: "${err.received}")`)
              .join('\n')
          } else {
            msg = `${e.status} — ${e.detail}`
          }
        } catch {
          msg = `${e.status} — ${e.detail}`
        }
        setError(msg)
      } else {
        setError(e instanceof Error ? e.message : 'Lưu thất bại. Vui lòng thử lại.')
      }
      setSaving(false)
    }
  }

  async function confirmSave() {
    if (!patientId) return
    if (isMockSaveBlocked) {
      setError('Kết quả OCR mẫu không hợp lệ — không thể lưu dữ liệu mẫu.')
      return
    }
    const dateErr = validateExamDate(testDate)
    if (dateErr) {
      setError(dateErr)
      return
    }
    if (rows.some((r) => !r.biomarker_key)) {
      setError('Vui lòng chọn chỉ số xét nghiệm cho tất cả các dòng.')
      return
    }
    const results = buildResults()
    if (results.length === 0) {
      setError('Vui lòng nhập ít nhất một chỉ số.')
      return
    }
    if (results.some((r) => r.value == null)) {
      setError('Vui lòng nhập giá trị cho tất cả các chỉ số.')
      return
    }
    if (results.some((r) => r.value != null && Number.isNaN(r.value))) {
      setError('Giá trị phải là số.')
      return
    }

    const isoDate = displayDateToIso(testDate)
    if (!isoDate) {
      setError('Ngày xét nghiệm không hợp lệ.')
      return
    }
    const labNameVal = labName.trim() || null

    try {
      const dup = await checkDuplicate(patientId, {
        test_date: isoDate,
        lab_name: labNameVal ?? undefined,
        biomarker_names: results.map((r) => r.test_name),
      })
      if (dup.is_duplicate) {
        pendingResultsRef.current = { results, labName: labNameVal, isoDate }
        setDuplicateWarning(dup)
        return
      }
    } catch {
      // If duplicate check fails, proceed to save
    }

    await doSave(results, labNameVal, isoDate)
  }

  function handleDuplicateViewExisting() {
    setDuplicateWarning(null)
    router.push('/labs')
  }

  function handleDuplicateSaveNew() {
    const p = pendingResultsRef.current
    if (!p) return
    setDuplicateWarning(null)
    doSave(p.results, p.labName, p.isoDate, 'new')
  }

  function handleDuplicateOverwrite() {
    const p = pendingResultsRef.current
    if (!p) return
    const existingId = duplicateWarning?.existing_batch_id ?? undefined
    setDuplicateWarning(null)
    doSave(p.results, p.labName, p.isoDate, 'overwrite', existingId)
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

  return (
    <>
      {duplicateWarning && (
        <DuplicateModal
          onViewExisting={handleDuplicateViewExisting}
          onSaveNew={handleDuplicateSaveNew}
          onOverwrite={handleDuplicateOverwrite}
          saving={saving}
        />
      )}
      <div className="p-4 max-w-md mx-auto space-y-4 pb-28">
        <PageHeaderNeu
          title={step === 'input' ? 'Tải lên kết quả' : 'Kiểm tra & xác nhận'}
          onBack={() =>
            step === 'review' ? (setDraft(null), setError(null)) : router.push('/labs')
          }
        />

        {ocrFailed ? (
          <OcrErrorCard onRetry={() => setOcrFailed(false)} onManualEntry={handleManualEntry} />
        ) : (
          error && <PatientErrorState title="Lỗi" message={error} onRetry={() => setError(null)} />
        )}

        {step === 'input' && (
          <>
            <ModeTabs
              mode={mode}
              onChange={(m) => {
                setMode(m)
                setError(null)
                setOcrFailed(false)
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
              disabled={submitting || !catalog || (mode === 'url' ? !url.trim() : !file)}
              onClick={submitForDraft}
            >
              {submitting
                ? (progressStep ?? 'Đang xử lý...')
                : !catalog
                  ? 'Đang tải danh mục...'
                  : 'Phân tích bằng AI'}
            </NeuButton>
          </>
        )}

        {step === 'review' && draft && catalog && (
          <>
            {isMockSaveBlocked && (
              <div
                role="alert"
                className="rounded-[14px] bg-[#FEF2F2] border border-[#DC2626]/30 p-4"
              >
                <p className="text-[14px] font-bold text-[#991B1B]">Lỗi cấu hình OCR</p>
                <p className="text-[13px] text-[#991B1B]/80 mt-1">
                  Kết quả OCR mẫu không được phép lưu. Vui lòng liên hệ hỗ trợ kỹ thuật.
                </p>
              </div>
            )}
            {isMockOcrResult && !isMockSaveBlocked && (
              <div
                role="alert"
                className="rounded-[14px] bg-[#FFF7ED] border border-[#F59E0B]/40 p-4"
              >
                <p className="text-[13px] font-bold text-[#92400E]">[DEV] Dữ liệu OCR mẫu</p>
                <p className="text-[12px] text-[#92400E]/80 mt-0.5">
                  MCP_OCR_PROVIDER=mock hoặc MCP_ENABLE_MOCK_OCR=true đang bật — kết quả này không
                  phải từ ảnh thật.
                </p>
              </div>
            )}
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

            {/* Date needs confirmation — amber WARNING, not an error */}
            {draft.date_needs_confirmation && (
              <div
                role="alert"
                aria-label="date-confirmation-warning"
                className="flex items-start gap-2.5 rounded-[14px] bg-amber-50 border border-amber-300 px-4 py-3"
              >
                <AlertTriangle className="size-5 mt-0.5 shrink-0 text-amber-500" />
                <div>
                  <p className="text-[14px] font-bold text-amber-800">
                    Ngày xét nghiệm cần xác nhận
                  </p>
                  <p className="text-[13px] text-amber-700 mt-0.5">
                    Hệ thống không xác định được ngày xét nghiệm rõ ràng. Vui lòng kiểm tra và nhập ngày đúng bên dưới.
                  </p>
                </div>
              </div>
            )}

            {/* Persistent review reminder */}
            <div
              role="note"
              className="rounded-[14px] bg-[#FEF9EC] border border-[#E0A92E]/30 px-4 py-3"
            >
              <p className="text-[13px] font-semibold text-[#8B6400]">
                Vui lòng kiểm tra lại trước khi lưu
              </p>
            </div>

            {/* Backend warnings: cloud-fallback, OCR issues, etc.
                Date-specific warnings are surfaced via the date_needs_confirmation
                banner above; filter them here to avoid duplicate messages. */}
            {draft.warnings.filter(
              (w) => !(
                // Suppress warnings already shown in date_needs_confirmation banner.
                draft.date_needs_confirmation &&
                (w.includes('ngày xét nghiệm cần xác nhận') ||
                  w.includes('ngày sinh') ||
                  w.includes('độ tin cậy thấp') && w.includes('ngày'))
              )
            ).length > 0 && (
              <div className="space-y-1.5">
                {draft.warnings
                  .filter(
                    (w) => !(
                      draft.date_needs_confirmation &&
                      (w.includes('ngày xét nghiệm cần xác nhận') ||
                        w.includes('ngày sinh') ||
                        (w.includes('độ tin cậy thấp') && w.includes('ngày')))
                    )
                  )
                  .map((w, i) => (
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
                  Kết quả này đã cũ hơn 12 tháng — chỉ dùng để tham khảo lịch sử. Bạn vẫn có thể
                  lưu.
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

            {/* Catalog-bound OCR review rows */}
            <div className="space-y-3">
              {rows.map((row, i) => (
                <OcrReviewCard
                  key={row.id}
                  catalog={catalog}
                  row={row}
                  index={i}
                  onRowChange={(patch) =>
                    setRows((rs) => rs.map((r, idx) => (idx === i ? { ...r, ...patch } : r)))
                  }
                  onRemove={() => setRows((rs) => rs.filter((_, idx) => idx !== i))}
                />
              ))}

              <NeuButton
                variant="secondary"
                onClick={() => setRows((rs) => [...rs, makeEmptyOcrRow()])}
              >
                <Plus className="size-4" /> Thêm chỉ số
              </NeuButton>
            </div>

            <NeuButton disabled={saving || isMockSaveBlocked} onClick={confirmSave}>
              {saving ? 'Đang lưu...' : 'Xác nhận & lưu vào hồ sơ'}
            </NeuButton>
            <p className="text-center text-[13px] text-neu-subtle">
              Kết quả chỉ được lưu sau khi bạn xác nhận.
            </p>
          </>
        )}
      </div>
    </>
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

// ── Duplicate warning modal ────────────────────────────────────────────────────

function DuplicateModal({
  onViewExisting,
  onSaveNew,
  onOverwrite,
  saving,
}: {
  onViewExisting: () => void
  onSaveNew: () => void
  onOverwrite: () => void
  saving: boolean
}) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Kết quả trùng lặp"
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 px-4 pb-8"
    >
      <div className="w-full max-w-md rounded-[20px] bg-white p-6 space-y-4 shadow-2xl">
        <div className="flex items-center gap-3">
          <span className="flex size-11 shrink-0 items-center justify-center rounded-full bg-[#FEF9EC]">
            <AlertTriangle className="size-6 text-[#E0A92E]" />
          </span>
          <div>
            <p className="text-[16px] font-extrabold text-neu-text">Kết quả có thể trùng</p>
            <p className="text-[13px] text-neu-muted mt-0.5">
              Có vẻ kết quả xét nghiệm ngày này đã được lưu.
            </p>
          </div>
        </div>
        <div className="space-y-2.5">
          <NeuButton variant="secondary" onClick={onViewExisting} disabled={saving}>
            Xem kết quả đã lưu
          </NeuButton>
          <NeuButton variant="secondary" onClick={onOverwrite} disabled={saving}>
            {saving ? 'Đang lưu...' : 'Ghi đè kết quả cũ'}
          </NeuButton>
          <NeuButton onClick={onSaveNew} disabled={saving}>
            {saving ? 'Đang lưu...' : 'Lưu thành bản mới'}
          </NeuButton>
        </div>
      </div>
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
        className="flex w-full flex-col items-center gap-3 rounded-[18px] border-2 border-dashed border-[#bcd2cb] bg-[#eef3f1] py-8 transition-colors hover:bg-[#e6ece9]"
      >
        <span className="neu-pressed flex size-16 items-center justify-center rounded-full">
          {icon}
        </span>
        <span className="max-w-[200px] truncate text-[15px] font-semibold text-neu-text">
          {file ? `1 ảnh đã chọn` : 'Chạm để chọn'}
        </span>
        {file && (
          <span className="max-w-[220px] truncate px-2 text-[12px] text-neu-subtle">
            {file.name}
          </span>
        )}
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
