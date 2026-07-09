'use client'

import * as React from 'react'
import { UserRound, Plus, Search } from 'lucide-react'
import {
  PageHeader,
  Badge,
  Button,
  Modal,
  useModal,
  FormField,
  Input,
  Textarea,
  Select,
  Table,
  type Column,
  CardSkeleton,
  EmptyState,
  ErrorState,
} from '@/design-system'
import { ApiError, toPageError, type PageError } from '@/lib/api/client'
import {
  listClinicPatients,
  searchPatientCandidate,
  linkClinicPatient,
  createClinicPatient,
  updateClinicPatient,
  type ClinicPatientAdminOut,
  type ClinicPatientListItem,
  type ClinicPatientRelationshipStatus,
  type PatientCandidateOut,
} from '@/lib/api/clinics'
import { useClinic } from '@/lib/clinic/ClinicContext'

const STATUS_LABEL: Record<ClinicPatientRelationshipStatus, string> = {
  active: 'Đang hoạt động',
  inactive: 'Ngưng theo dõi',
  merged: 'Đã gộp',
}

function isAdminItem(item: ClinicPatientListItem): item is ClinicPatientAdminOut {
  return 'dob' in item
}

function formatDate(value: string | null): string {
  if (!value) return '—'
  try {
    return new Intl.DateTimeFormat('vi-VN', { dateStyle: 'medium' }).format(new Date(value))
  } catch {
    return value
  }
}

interface DuplicateCandidateBody {
  code: 'DUPLICATE_CANDIDATE'
  candidate: PatientCandidateOut
}

function parseDuplicateCandidate(err: ApiError): DuplicateCandidateBody | null {
  if (err.status !== 409) return null
  try {
    const body = JSON.parse(err.detail) as DuplicateCandidateBody
    return body?.code === 'DUPLICATE_CANDIDATE' ? body : null
  } catch {
    return null
  }
}

// ---------------------------------------------------------------------------
// Add patient — search-by-phone first (dedup), then link existing or create
// new (AC-M06-01 minimal fields / AC-M06-02 duplicate warning).
// ---------------------------------------------------------------------------

interface AddPatientModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onDone: () => void
  clinicId: string
}

function AddPatientModal({ open, onOpenChange, onDone, clinicId }: AddPatientModalProps) {
  const [phone, setPhone] = React.useState('')
  const [searching, setSearching] = React.useState(false)
  const [searched, setSearched] = React.useState(false)
  const [candidate, setCandidate] = React.useState<PatientCandidateOut | null>(null)
  const [fullName, setFullName] = React.useState('')
  const [dob, setDob] = React.useState('')
  const [gender, setGender] = React.useState('')
  const [address, setAddress] = React.useState('')
  const [overrideReason, setOverrideReason] = React.useState('')
  const [saving, setSaving] = React.useState(false)
  const [error, setError] = React.useState<PageError | null>(null)
  const [duplicate, setDuplicate] = React.useState<PatientCandidateOut | null>(null)

  const reset = () => {
    setPhone('')
    setSearching(false)
    setSearched(false)
    setCandidate(null)
    setFullName('')
    setDob('')
    setGender('')
    setAddress('')
    setOverrideReason('')
    setSaving(false)
    setError(null)
    setDuplicate(null)
  }

  const handleClose = (next: boolean) => {
    if (!next) reset()
    onOpenChange(next)
  }

  const handleSearch = async () => {
    setSearching(true)
    setError(null)
    try {
      const result = await searchPatientCandidate(clinicId, phone)
      setCandidate(result)
      setSearched(true)
    } catch (err: unknown) {
      setError(toPageError(err))
    } finally {
      setSearching(false)
    }
  }

  const handleLink = async () => {
    if (!candidate) return
    setSaving(true)
    setError(null)
    try {
      await linkClinicPatient(clinicId, { patient_id: candidate.patient_id, phone })
      handleClose(false)
      onDone()
    } catch (err: unknown) {
      setError(toPageError(err))
    } finally {
      setSaving(false)
    }
  }

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setError(null)
    setDuplicate(null)
    try {
      await createClinicPatient(clinicId, {
        full_name: fullName,
        phone,
        dob,
        gender,
        address: address || null,
        override_dedup_reason: overrideReason || null,
      })
      handleClose(false)
      onDone()
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        const dup = parseDuplicateCandidate(err)
        if (dup) {
          setDuplicate(dup.candidate)
        } else {
          setError(toPageError(err))
        }
      } else {
        setError(toPageError(err))
      }
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal open={open} onOpenChange={handleClose} title="Thêm bệnh nhân">
      <div className="flex flex-col gap-4">
        {error && <p className="text-body-xs text-danger">{error.message}</p>}

        <FormField label="Số điện thoại" required>
          <div className="flex gap-2">
            <Input
              value={phone}
              onChange={(e) => {
                setPhone(e.target.value)
                setSearched(false)
                setCandidate(null)
                setDuplicate(null)
              }}
              placeholder="0901234567"
              required
            />
            <Button
              type="button"
              variant="secondary"
              leftIcon={<Search className="h-4 w-4" />}
              loading={searching}
              disabled={!phone}
              onClick={() => void handleSearch()}
            >
              Tìm
            </Button>
          </div>
        </FormField>

        {searched && candidate && (
          <div className="rounded-lg border border-border p-3">
            <p className="text-body-sm font-semibold text-text">{candidate.full_name}</p>
            <p className="text-body-xs text-text-muted">{candidate.phone}</p>
            {candidate.already_linked ? (
              <p className="mt-2 text-body-xs text-warning">
                Bệnh nhân này đã được liên kết với phòng khám.
              </p>
            ) : (
              <Button className="mt-2" size="sm" loading={saving} onClick={() => void handleLink()}>
                Liên kết bệnh nhân này
              </Button>
            )}
          </div>
        )}

        {searched && !candidate && (
          <form onSubmit={handleCreate} className="flex flex-col gap-4 border-t border-border pt-4">
            <p className="text-body-xs text-text-muted">
              Không tìm thấy hồ sơ trùng — tạo bệnh nhân mới.
            </p>
            <FormField label="Họ và tên" required>
              <Input
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                required
                autoFocus
              />
            </FormField>
            <FormField label="Ngày sinh" required>
              <Input type="date" value={dob} onChange={(e) => setDob(e.target.value)} required />
            </FormField>
            <FormField label="Giới tính" required>
              <Select
                value={gender}
                onValueChange={setGender}
                placeholder="Chọn giới tính"
                options={[
                  { value: 'male', label: 'Nam' },
                  { value: 'female', label: 'Nữ' },
                  { value: 'other', label: 'Khác' },
                ]}
              />
            </FormField>
            <FormField label="Địa chỉ">
              <Input value={address} onChange={(e) => setAddress(e.target.value)} />
            </FormField>

            {duplicate && (
              <div className="rounded-lg border border-warning-300 bg-warning-50 p-3">
                <p className="text-body-xs text-text">
                  Đã tìm thấy hồ sơ nghi trùng: <strong>{duplicate.full_name}</strong> (
                  {duplicate.phone})
                </p>
                <FormField label="Lý do vẫn tạo mới (VD: vợ chồng dùng chung SĐT)" className="mt-2">
                  <Textarea
                    value={overrideReason}
                    onChange={(e) => setOverrideReason(e.target.value)}
                    rows={2}
                  />
                </FormField>
              </div>
            )}

            <Button type="submit" loading={saving} disabled={!gender} fullWidth>
              {duplicate ? 'Vẫn tạo mới' : 'Tạo bệnh nhân'}
            </Button>
          </form>
        )}
      </div>
    </Modal>
  )
}

// ---------------------------------------------------------------------------
// Patient detail / edit (Owner/Admin only for the edit fields)
// ---------------------------------------------------------------------------

interface PatientDetailModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSaved: () => void
  clinicId: string
  patient: ClinicPatientAdminOut | null
  canEdit: boolean
}

function PatientDetailModal({
  open,
  onOpenChange,
  onSaved,
  clinicId,
  patient,
  canEdit,
}: PatientDetailModalProps) {
  const [status, setStatus] = React.useState<ClinicPatientRelationshipStatus>('active')
  const [notes, setNotes] = React.useState('')
  const [saving, setSaving] = React.useState(false)
  const [error, setError] = React.useState<PageError | null>(null)

  React.useEffect(() => {
    if (patient) {
      setStatus(patient.status ?? 'active')
      setNotes(patient.internal_notes ?? '')
    }
  }, [patient])

  if (!patient) return null

  const handleSave = async () => {
    setSaving(true)
    setError(null)
    try {
      await updateClinicPatient(clinicId, patient.patient_id, {
        status,
        internal_notes: notes,
      })
      onOpenChange(false)
      onSaved()
    } catch (err: unknown) {
      setError(toPageError(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal open={open} onOpenChange={onOpenChange} title={patient.full_name ?? 'Bệnh nhân'}>
      <div className="flex flex-col gap-3">
        {error && <p className="text-body-xs text-danger">{error.message}</p>}
        <div className="grid grid-cols-2 gap-3 text-body-sm">
          <div>
            <p className="text-body-xs text-text-muted">Số điện thoại</p>
            <p className="text-text">{patient.phone ?? '—'}</p>
          </div>
          <div>
            <p className="text-body-xs text-text-muted">Ngày sinh</p>
            <p className="text-text">{formatDate(patient.dob)}</p>
          </div>
          <div>
            <p className="text-body-xs text-text-muted">Giới tính</p>
            <p className="text-text">{patient.gender ?? '—'}</p>
          </div>
          <div>
            <p className="text-body-xs text-text-muted">Mã bệnh nhân</p>
            <p className="text-text">{patient.patient_code ?? '—'}</p>
          </div>
        </div>
        {patient.address && (
          <div>
            <p className="text-body-xs text-text-muted">Địa chỉ</p>
            <p className="text-body-sm text-text">{patient.address}</p>
          </div>
        )}

        {patient.patient_code === null ? (
          <p className="mt-2 text-body-xs text-text-muted">
            Hồ sơ này được xem qua quyền chia sẻ (consent) từ phòng khám khác — không thuộc phòng
            khám của bạn nên không thể chỉnh sửa trạng thái/ghi chú tại đây.
          </p>
        ) : canEdit ? (
          <div className="mt-2 flex flex-col gap-3 border-t border-border pt-3">
            <FormField label="Trạng thái">
              <Select
                value={status}
                onValueChange={(v) => setStatus(v as ClinicPatientRelationshipStatus)}
                options={[
                  { value: 'active', label: STATUS_LABEL.active },
                  { value: 'inactive', label: STATUS_LABEL.inactive },
                  { value: 'merged', label: STATUS_LABEL.merged },
                ]}
              />
            </FormField>
            <FormField label="Ghi chú nội bộ (không chứa dữ liệu lâm sàng)">
              <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} />
            </FormField>
            <Button loading={saving} onClick={() => void handleSave()}>
              Lưu thay đổi
            </Button>
          </div>
        ) : (
          <Badge variant={status === 'active' ? 'success' : 'default'} size="sm">
            {STATUS_LABEL[status]}
          </Badge>
        )}
      </div>
    </Modal>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function ClinicPatientsPage() {
  const { clinic, capabilities } = useClinic()
  const addModal = useModal()
  const detailModal = useModal()

  const [items, setItems] = React.useState<ClinicPatientListItem[]>([])
  const [total, setTotal] = React.useState(0)
  const [search, setSearch] = React.useState('')
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<PageError | null>(null)
  const [selected, setSelected] = React.useState<ClinicPatientAdminOut | null>(null)

  const load = React.useCallback(
    async (searchValue?: string) => {
      if (!clinic) return
      setLoading(true)
      setError(null)
      try {
        const data = await listClinicPatients(clinic.id, {
          limit: 100,
          search: searchValue ?? search,
        })
        setItems(data.items)
        setTotal(data.total)
      } catch (err: unknown) {
        setError(toPageError(err))
      } finally {
        setLoading(false)
      }
    },
    [clinic, search]
  )

  React.useEffect(() => {
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clinic])

  if (!clinic) return null

  const handleRowClick = (row: ClinicPatientListItem) => {
    if (!isAdminItem(row)) return // Care Coordinator's narrow shape has no edit surface
    setSelected(row)
    detailModal.onOpenChange(true)
  }

  const columns: Column<ClinicPatientListItem>[] = [
    {
      key: 'full_name',
      header: 'Họ và tên',
      cell: (row) => row.full_name ?? '—',
    },
    {
      key: 'phone',
      header: 'Số điện thoại',
      cell: (row) => row.phone ?? '—',
    },
    {
      key: 'patient_code',
      header: 'Mã BN',
      cell: (row) => row.patient_code ?? '—',
    },
    {
      key: 'status',
      header: 'Trạng thái',
      cell: (row) =>
        row.status ? (
          <Badge variant={row.status === 'active' ? 'success' : 'default'} size="sm">
            {STATUS_LABEL[row.status]}
          </Badge>
        ) : (
          '—'
        ),
    },
    {
      key: 'first_seen_at',
      header: 'Lần đầu tiếp nhận',
      cell: (row) => formatDate(row.first_seen_at),
    },
  ]

  return (
    <div className="px-4 py-6 sm:px-6">
      <PageHeader
        title="Bệnh nhân"
        actions={
          capabilities.canManagePatients && (
            <Button leftIcon={<Plus className="h-4 w-4" />} {...addModal.triggerProps}>
              Thêm bệnh nhân
            </Button>
          )
        }
      />

      <div className="mb-4">
        <Input
          placeholder="Tìm theo tên, số điện thoại hoặc mã BN…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') void load(search)
          }}
          leftIcon={<Search className="h-4 w-4" />}
        />
      </div>

      {loading ? (
        <div className="grid gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <CardSkeleton key={i} lines={2} />
          ))}
        </div>
      ) : error ? (
        <ErrorState
          variant="card"
          title={error.title}
          code={error.code}
          message={error.message}
          onRetry={() => void load()}
        />
      ) : items.length === 0 ? (
        <EmptyState
          icon={<UserRound />}
          title="Chưa có bệnh nhân"
          description="Phòng khám này chưa có bệnh nhân nào trong danh sách."
          {...(capabilities.canManagePatients
            ? { action: { label: 'Thêm bệnh nhân', onClick: () => addModal.onOpenChange(true) } }
            : {})}
          size="md"
        />
      ) : (
        <>
          <Table columns={columns} data={items} rowKey="patient_id" onRowClick={handleRowClick} />
          <p className="mt-2 text-body-xs text-text-muted">
            Hiển thị {items.length} / {total} bệnh nhân
          </p>
        </>
      )}

      {capabilities.canManagePatients && (
        <AddPatientModal {...addModal.modalProps} clinicId={clinic.id} onDone={() => void load()} />
      )}

      <PatientDetailModal
        {...detailModal.modalProps}
        clinicId={clinic.id}
        patient={selected}
        canEdit={capabilities.canUpdatePatientRecord}
        onSaved={() => void load()}
      />
    </div>
  )
}
