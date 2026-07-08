'use client'

import * as React from 'react'
import { Building2, Plus, Phone } from 'lucide-react'
import {
  PageHeader,
  Card,
  Badge,
  Button,
  Modal,
  useModal,
  FormField,
  Input,
  EmptyState,
  ErrorState,
} from '@/design-system'
import type { ClinicBranchStatus } from '@/lib/api/clinics'
import { toPageError, type PageError } from '@/lib/api/client'
import { createBranch, setBranchStatus, type ClinicBranchOut } from '@/lib/api/clinics'
import { useClinic } from '@/lib/clinic/ClinicContext'

const STATUS_LABEL: Record<ClinicBranchStatus, string> = {
  active: 'Đang hoạt động',
  paused: 'Tạm dừng',
  archived: 'Đã lưu trữ',
}

const STATUS_BADGE: Record<ClinicBranchStatus, 'success' | 'warning' | 'default'> = {
  active: 'success',
  paused: 'warning',
  archived: 'default',
}

// ---------------------------------------------------------------------------
// Branch card — table-as-cards on every breakpoint (no horizontal-scroll
// table; a plain responsive card grid reads fine at any width).
// ---------------------------------------------------------------------------

interface BranchCardProps {
  branch: ClinicBranchOut
  canManage: boolean
  onToggleStatus: (branch: ClinicBranchOut) => void
  busy: boolean
}

function BranchCard({ branch, canManage, onToggleStatus, busy }: BranchCardProps) {
  return (
    <Card variant="default" padding="md">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="flex items-center gap-2 text-body-sm font-semibold text-text">
            <Building2 className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
            <span className="truncate">{branch.name}</span>
          </p>
          {branch.phone && (
            <p className="mt-1 flex items-center gap-1.5 text-body-xs text-text-muted">
              <Phone className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              {branch.phone}
            </p>
          )}
        </div>
        <Badge variant={STATUS_BADGE[branch.status]} size="sm">
          {STATUS_LABEL[branch.status]}
        </Badge>
      </div>

      {canManage && (
        <div className="mt-3 flex gap-2">
          {branch.status === 'active' ? (
            <Button
              size="sm"
              variant="secondary"
              loading={busy}
              onClick={() => onToggleStatus(branch)}
            >
              Tạm dừng
            </Button>
          ) : (
            <Button
              size="sm"
              variant="secondary"
              loading={busy}
              onClick={() => onToggleStatus(branch)}
            >
              Kích hoạt lại
            </Button>
          )}
        </div>
      )}
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Create-branch form (Owner/Admin only)
// ---------------------------------------------------------------------------

interface CreateBranchModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated: () => void
  clinicId: string
}

function CreateBranchModal({ open, onOpenChange, onCreated, clinicId }: CreateBranchModalProps) {
  const [name, setName] = React.useState('')
  const [phone, setPhone] = React.useState('')
  const [saving, setSaving] = React.useState(false)
  const [error, setError] = React.useState<PageError | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setError(null)
    try {
      // Working hours editing is out of C0 UI scope for this pass — default
      // to "every day, always open" so the required field is always valid;
      // Owner/Admin can refine hours via a future dedicated editor.
      await createBranch(clinicId, {
        name,
        phone: phone || null,
        working_hours: {
          mon: '00:00-23:59',
          tue: '00:00-23:59',
          wed: '00:00-23:59',
          thu: '00:00-23:59',
          fri: '00:00-23:59',
          sat: '00:00-23:59',
          sun: '00:00-23:59',
        },
      })
      setName('')
      setPhone('')
      onOpenChange(false)
      onCreated()
    } catch (err: unknown) {
      setError(toPageError(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal open={open} onOpenChange={onOpenChange} title="Thêm chi nhánh mới">
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        {error && <p className="text-body-xs text-danger">{error.message}</p>}
        <FormField label="Tên chi nhánh" required>
          <Input value={name} onChange={(e) => setName(e.target.value)} required autoFocus />
        </FormField>
        <FormField label="Số điện thoại">
          <Input value={phone} onChange={(e) => setPhone(e.target.value)} />
        </FormField>
        <Button type="submit" loading={saving} fullWidth>
          Tạo chi nhánh
        </Button>
      </form>
    </Modal>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function ClinicBranchesPage() {
  const { clinic, branches, capabilities, refresh } = useClinic()
  const createModal = useModal()
  const [busyId, setBusyId] = React.useState<string | null>(null)
  const [actionError, setActionError] = React.useState<PageError | null>(null)

  if (!capabilities.canViewBranches) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center px-4">
        <EmptyState
          title="Không có quyền truy cập"
          description="Vai trò của bạn tại phòng khám này không có quyền xem danh sách chi nhánh."
          size="md"
        />
      </div>
    )
  }

  if (!clinic) return null

  const handleToggleStatus = async (branch: ClinicBranchOut) => {
    setBusyId(branch.id)
    setActionError(null)
    try {
      const next = branch.status === 'active' ? 'paused' : 'active'
      await setBranchStatus(clinic.id, branch.id, next)
      await refresh()
    } catch (err: unknown) {
      setActionError(toPageError(err))
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="px-4 py-6 sm:px-6">
      <PageHeader
        title="Chi nhánh"
        actions={
          capabilities.canManageClinic && (
            <Button leftIcon={<Plus className="h-4 w-4" />} {...createModal.triggerProps}>
              Thêm chi nhánh
            </Button>
          )
        }
      />

      {actionError && (
        <ErrorState
          variant="inline"
          title={actionError.title}
          message={actionError.message}
          className="mb-4"
        />
      )}

      {branches.length === 0 ? (
        <EmptyState
          icon={<Building2 />}
          title="Chưa có chi nhánh"
          description="Phòng khám này chưa có chi nhánh nào."
          {...(capabilities.canManageClinic
            ? { action: { label: 'Thêm chi nhánh', onClick: () => createModal.onOpenChange(true) } }
            : {})}
          size="md"
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {branches.map((branch) => (
            <BranchCard
              key={branch.id}
              branch={branch}
              canManage={capabilities.canManageClinic}
              onToggleStatus={(b) => void handleToggleStatus(b)}
              busy={busyId === branch.id}
            />
          ))}
        </div>
      )}

      {capabilities.canManageClinic && (
        <CreateBranchModal
          {...createModal.modalProps}
          clinicId={clinic.id}
          onCreated={() => void refresh()}
        />
      )}
    </div>
  )
}
