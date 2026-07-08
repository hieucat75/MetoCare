'use client'

import * as React from 'react'
import { Stethoscope, Plus } from 'lucide-react'
import {
  PageHeader,
  Card,
  Badge,
  Button,
  Modal,
  useModal,
  FormField,
  Input,
  CardSkeleton,
  EmptyState,
  ErrorState,
} from '@/design-system'
import { ApiError, toPageError, type PageError } from '@/lib/api/client'
import {
  createService,
  listServices,
  updateService,
  type ClinicServiceOut,
} from '@/lib/api/clinics'
import { useClinic } from '@/lib/clinic/ClinicContext'

function formatPrice(price: number): string {
  return new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(price)
}

// ---------------------------------------------------------------------------
// Service card — table-as-cards, no horizontal-scroll table on mobile.
// ---------------------------------------------------------------------------

interface ServiceCardProps {
  service: ClinicServiceOut
  canManage: boolean
  onToggleStatus: (service: ClinicServiceOut) => void
  busy: boolean
}

function ServiceCard({ service, canManage, onToggleStatus, busy }: ServiceCardProps) {
  return (
    <Card variant="default" padding="md">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="flex items-center gap-2 text-body-sm font-semibold text-text">
            <Stethoscope className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
            <span className="truncate">{service.name}</span>
          </p>
          <p className="mt-1 text-body-sm text-text">{formatPrice(service.price)}</p>
          {service.package_visit_count && (
            <p className="text-body-xs text-text-muted">Gói {service.package_visit_count} lượt</p>
          )}
        </div>
        <Badge variant={service.status === 'active' ? 'success' : 'default'} size="sm">
          {service.status === 'active' ? 'Đang bán' : 'Ngừng bán'}
        </Badge>
      </div>

      {canManage && (
        <div className="mt-3">
          <Button
            size="sm"
            variant="secondary"
            loading={busy}
            onClick={() => onToggleStatus(service)}
          >
            {service.status === 'active' ? 'Ngừng bán' : 'Kích hoạt lại'}
          </Button>
        </div>
      )}
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Create-service form (Owner/Admin only)
// ---------------------------------------------------------------------------

interface CreateServiceModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated: () => void
  clinicId: string
}

function CreateServiceModal({ open, onOpenChange, onCreated, clinicId }: CreateServiceModalProps) {
  const [name, setName] = React.useState('')
  const [price, setPrice] = React.useState('')
  const [saving, setSaving] = React.useState(false)
  const [error, setError] = React.useState<PageError | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setError(null)
    try {
      const priceValue = Number(price)
      if (!Number.isFinite(priceValue) || priceValue < 0) {
        throw new Error('Giá dịch vụ không hợp lệ.')
      }
      await createService(clinicId, { name, price: priceValue })
      setName('')
      setPrice('')
      onOpenChange(false)
      onCreated()
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setError(toPageError(err))
      } else if (err instanceof Error) {
        // Client-side validation error (e.g. invalid price) — not an API
        // failure, so render its own message rather than the generic
        // "can't reach the server" fallback `toPageError` gives non-ApiError.
        setError({ message: err.message })
      } else {
        setError(toPageError(err))
      }
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal open={open} onOpenChange={onOpenChange} title="Thêm dịch vụ mới">
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        {error && <p className="text-body-xs text-danger">{error.message}</p>}
        <FormField label="Tên dịch vụ" required>
          <Input value={name} onChange={(e) => setName(e.target.value)} required autoFocus />
        </FormField>
        <FormField label="Giá (VNĐ)" required>
          <Input
            type="number"
            min={0}
            value={price}
            onChange={(e) => setPrice(e.target.value)}
            required
          />
        </FormField>
        <Button type="submit" loading={saving} fullWidth>
          Tạo dịch vụ
        </Button>
      </form>
    </Modal>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function ClinicServicesPage() {
  const { clinic } = useClinic()
  const createModal = useModal()

  const [services, setServices] = React.useState<ClinicServiceOut[]>([])
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<PageError | null>(null)
  const [busyId, setBusyId] = React.useState<string | null>(null)
  const [actionError, setActionError] = React.useState<PageError | null>(null)

  // Every clinic role reads the services catalog per RBAC_MATRIX.md M05 row
  // (Owner/Admin manage, everyone else R) — the write actions below are
  // additionally gated by `capabilities.canManageServices`.
  const { capabilities } = useClinic()

  const load = React.useCallback(async () => {
    if (!clinic) return
    setLoading(true)
    setError(null)
    try {
      const data = await listServices(clinic.id, { limit: 200 })
      setServices(data.items)
    } catch (err: unknown) {
      setError(toPageError(err))
    } finally {
      setLoading(false)
    }
  }, [clinic])

  React.useEffect(() => {
    void load()
  }, [load])

  if (!clinic) return null

  const handleToggleStatus = async (service: ClinicServiceOut) => {
    setBusyId(service.id)
    setActionError(null)
    try {
      const next = service.status === 'active' ? 'inactive' : 'active'
      await updateService(clinic.id, service.id, { status: next })
      await load()
    } catch (err: unknown) {
      setActionError(toPageError(err))
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="px-4 py-6 sm:px-6">
      <PageHeader
        title="Dịch vụ"
        actions={
          capabilities.canManageServices && (
            <Button leftIcon={<Plus className="h-4 w-4" />} {...createModal.triggerProps}>
              Thêm dịch vụ
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

      {loading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
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
      ) : services.length === 0 ? (
        <EmptyState
          icon={<Stethoscope />}
          title="Chưa có dịch vụ"
          description="Phòng khám này chưa có dịch vụ nào trong bảng giá."
          {...(capabilities.canManageServices
            ? { action: { label: 'Thêm dịch vụ', onClick: () => createModal.onOpenChange(true) } }
            : {})}
          size="md"
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {services.map((service) => (
            <ServiceCard
              key={service.id}
              service={service}
              canManage={capabilities.canManageServices}
              onToggleStatus={(s) => void handleToggleStatus(s)}
              busy={busyId === service.id}
            />
          ))}
        </div>
      )}

      {capabilities.canManageServices && (
        <CreateServiceModal
          {...createModal.modalProps}
          clinicId={clinic.id}
          onCreated={() => void load()}
        />
      )}
    </div>
  )
}
