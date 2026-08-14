'use client'

import * as React from 'react'
import { Plus, Trash2 } from 'lucide-react'
import {
  Alert,
  Badge,
  Button,
  FormField,
  Input,
  Modal,
  Select,
} from '@/design-system'
import {
  classifyLabValue,
  formatRefRange,
  primaryUnit,
  useLabReference,
  type LabBiomarker,
  type LabCatalog,
  type LabUnit,
} from '@/lib/api/labReference'
import { createManualLabResults, type ManualLabItem } from '@/lib/api/patient'
import { displayDateToIso, formatDateInput, validateExamDate } from '@/lib/utils'

interface Row {
  category: string
  biomarker: string
  value: string
  unit: string // unit key
}

const EMPTY: Row = { category: '', biomarker: '', value: '', unit: '' }

function biomarkerOf(cat: LabCatalog, key: string): LabBiomarker | null {
  return key ? cat.biomarkers[key] ?? null : null
}
function unitOf(b: LabBiomarker | null, key: string): LabUnit | null {
  return b ? b.units.find((u) => u.key === key) ?? null : null
}

// ── One editable measurement row ─────────────────────────────────────────────

function EntryRow({
  cat,
  row,
  index,
  canRemove,
  onChange,
  onRemove,
}: {
  cat: LabCatalog
  row: Row
  index: number
  canRemove: boolean
  onChange: (patch: Partial<Row>) => void
  onRemove: () => void
}) {
  const categoryOptions = cat.categories.map((c) => ({ value: c.key, label: c.name }))
  const biomarkerOptions = React.useMemo(() => {
    const c = cat.categories.find((x) => x.key === row.category)
    if (!c) return []
    return c.biomarkers
      .map((k) => ({ value: k, label: cat.biomarkers[k].name_vn }))
      .sort((a, b) => a.label.localeCompare(b.label, 'vi'))
  }, [cat, row.category])

  const bm = biomarkerOf(cat, row.biomarker)
  const unitOptions = bm ? bm.units.map((u) => ({ value: u.key, label: u.label })) : []
  const unit = unitOf(bm, row.unit)
  const numeric = row.value.trim() === '' ? null : Number(row.value)
  const status =
    bm && unit && numeric != null && !Number.isNaN(numeric)
      ? classifyLabValue(numeric, unit, bm.higher_is_better)
      : null

  return (
    <div className="rounded-2xl border border-mint-100 bg-white/70 p-3 space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-[15px] font-semibold text-mint-700">Chỉ số #{index + 1}</span>
        {canRemove && (
          <button
            type="button"
            onClick={onRemove}
            aria-label="Xoá chỉ số"
            className="p-1.5 text-danger hover:bg-danger-light rounded-md"
          >
            <Trash2 className="size-4" />
          </button>
        )}
      </div>

      <Select
        label="Loại xét nghiệm"
        placeholder="Chọn loại…"
        fullWidth
        value={row.category || undefined}
        options={categoryOptions}
        onValueChange={(v) => onChange({ category: v, biomarker: '', unit: '', value: '' })}
      />

      <Select
        label="Chỉ số xét nghiệm"
        placeholder={row.category ? 'Chọn chỉ số…' : 'Chọn loại trước'}
        fullWidth
        disabled={!row.category}
        value={row.biomarker || undefined}
        options={biomarkerOptions}
        onValueChange={(v) => {
          const nb = cat.biomarkers[v]
          onChange({ biomarker: v, unit: nb ? primaryUnit(nb).key : '', value: '' })
        }}
      />

      {bm && (
        <>
          <div className="grid grid-cols-2 gap-2">
            <FormField label="Giá trị">
              <Input
                type="number"
                step="any"
                inputMode="decimal"
                aria-label={`Giá trị ${bm.name_vn}`}
                placeholder="Nhập số"
                value={row.value}
                onChange={(e) => onChange({ value: e.target.value })}
                fullWidth
              />
            </FormField>
            <Select
              label="Đơn vị"
              fullWidth
              value={row.unit || undefined}
              options={unitOptions}
              disabled={unitOptions.length <= 1}
              onValueChange={(v) => onChange({ unit: v })}
            />
          </div>

          {unit && (
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="mint" size="sm">
                Bình thường: {formatRefRange(unit, bm.higher_is_better)}
              </Badge>
              {status && (
                <Badge variant={status.tone} size="sm">
                  {status.label}
                </Badge>
              )}
            </div>
          )}
          {status?.implausible && (
            <p className="text-[14px] text-danger">
              Giá trị có vẻ bất thường — vui lòng kiểm tra lại.
            </p>
          )}
          {bm.notes && <p className="text-[13px] text-text-subtle">{bm.notes}</p>}
        </>
      )}
    </div>
  )
}

// ── Modal ─────────────────────────────────────────────────────────────────────

export function LabEntryModal({
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
  const catalog = useLabReference()
  const [labName, setLabName] = React.useState('')
  const [testDate, setTestDate] = React.useState('')
  const [rows, setRows] = React.useState<Row[]>([{ ...EMPTY }])
  const [submitting, setSubmitting] = React.useState(false)
  const [err, setErr] = React.useState<string | null>(null)
  const [confirmOdd, setConfirmOdd] = React.useState(false)

  React.useEffect(() => {
    if (open) {
      setLabName('')
      setTestDate('')
      setRows([{ ...EMPTY }])
      setErr(null)
      setConfirmOdd(false)
    }
  }, [open])

  function setRow(i: number, patch: Partial<Row>) {
    setRows((rs) => rs.map((r, idx) => (idx === i ? { ...r, ...patch } : r)))
    setConfirmOdd(false)
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!catalog) return
    const dateErr = validateExamDate(testDate)
    if (dateErr) return setErr(dateErr)

    const valid = rows.filter((r) => r.biomarker && r.value.trim() !== '')
    if (valid.length === 0) return setErr('Vui lòng chọn chỉ số và nhập giá trị.')
    if (valid.some((r) => Number.isNaN(Number(r.value))))
      return setErr('Giá trị phải là số.')

    // Soft confirm on implausible values.
    const hasOdd = valid.some((r) => {
      const b = catalog.biomarkers[r.biomarker]
      const u = b.units.find((x) => x.key === r.unit)
      return u && classifyLabValue(Number(r.value), u, b.higher_is_better).implausible
    })
    if (hasOdd && !confirmOdd) {
      setConfirmOdd(true)
      setErr('Một số giá trị bất thường. Nếu chắc chắn đúng, nhấn "Vẫn lưu".')
      return
    }

    const results: ManualLabItem[] = valid.map((r) => {
      const b = catalog.biomarkers[r.biomarker]
      const u = b.units.find((x) => x.key === r.unit) ?? primaryUnit(b)
      return {
        test_name: r.biomarker, // canonical key → promotes to health_metrics (dashboard sync)
        value: Number(r.value),
        unit: u.label,
        // No client-computed reference_range — the backend attaches this via
        // resolve_lab_semantics at write/read time (Unified LabResult Contract).
      }
    })

    setSubmitting(true)
    setErr(null)
    try {
      await createManualLabResults(patientId, {
        lab_name: labName.trim() || null,
        test_date: displayDateToIso(testDate),
        results,
      })
      onSaved()
      onClose()
    } catch (e2: unknown) {
      setErr(e2 instanceof Error ? e2.message : 'Lưu thất bại. Vui lòng thử lại.')
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
          <Button
            variant="mint"
            size="sm"
            type="submit"
            form="lab-entry-form"
            loading={submitting}
            disabled={!catalog}
          >
            {confirmOdd ? 'Vẫn lưu' : 'Lưu'}
          </Button>
        </>
      }
    >
      {!catalog ? (
        <p className="text-[16px] text-text-muted py-6 text-center">Đang tải danh mục…</p>
      ) : (
        <form id="lab-entry-form" onSubmit={handleSubmit} className="space-y-4">
          {err && <Alert variant={confirmOdd ? 'warning' : 'danger'} title={err} />}

          <div className="grid grid-cols-2 gap-3">
            <FormField label="Tên phòng khám">
              <Input
                value={labName}
                onChange={(e) => setLabName(e.target.value)}
                placeholder="VD: Đa khoa…"
                fullWidth
              />
            </FormField>
            <FormField label="Ngày xét nghiệm" required>
              <Input
                inputMode="numeric"
                placeholder="DD/MM/YYYY"
                value={testDate}
                onChange={(e) => setTestDate(formatDateInput(e.target.value))}
                fullWidth
              />
            </FormField>
          </div>

          <div className="space-y-3">
            {rows.map((row, i) => (
              <EntryRow
                key={i}
                cat={catalog}
                row={row}
                index={i}
                canRemove={rows.length > 1}
                onChange={(patch) => setRow(i, patch)}
                onRemove={() => setRows((rs) => rs.filter((_, idx) => idx !== i))}
              />
            ))}
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setRows((rs) => [...rs, { ...EMPTY }])}
            >
              <Plus className="size-4 mr-1" aria-hidden="true" /> Thêm chỉ số khác
            </Button>
          </div>
        </form>
      )}
    </Modal>
  )
}
