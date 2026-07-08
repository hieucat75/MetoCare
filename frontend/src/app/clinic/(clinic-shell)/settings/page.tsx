'use client'

import * as React from 'react'
import {
  Card,
  CardContent,
  PageHeader,
  FormField,
  Input,
  Button,
  Alert,
  EmptyState,
} from '@/design-system'
import { toPageError, type PageError } from '@/lib/api/client'
import { updateClinicSettings, deactivateClinic } from '@/lib/api/clinics'
import { useClinic } from '@/lib/clinic/ClinicContext'

/**
 * Clinic profile edit — Owner/Admin only per RBAC_MATRIX.md's "Clinic config
 * (M01)" row (everyone else is ✗). `ClinicShell`'s nav already hides this
 * page's link for other tiers; this page independently re-checks
 * `capabilities.canManageClinic` and renders a Vietnamese no-access state if
 * a direct link is visited by someone who lacks it — so access is enforced
 * at the page, not just by hiding the menu entry.
 */
export default function ClinicSettingsPage() {
  const { clinic, capabilities, refresh } = useClinic()
  const canDeactivate = capabilities.canDeactivateClinic

  const [name, setName] = React.useState(clinic?.name ?? '')
  const [legalName, setLegalName] = React.useState(clinic?.legal_name ?? '')
  const [phone, setPhone] = React.useState(clinic?.phone ?? '')
  const [email, setEmail] = React.useState(clinic?.email ?? '')
  const [address, setAddress] = React.useState(clinic?.address ?? '')

  const [saving, setSaving] = React.useState(false)
  const [saveError, setSaveError] = React.useState<PageError | null>(null)
  const [saved, setSaved] = React.useState(false)

  const [deactivating, setDeactivating] = React.useState(false)
  const [deactivateError, setDeactivateError] = React.useState<PageError | null>(null)

  if (!capabilities.canManageClinic) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center px-4">
        <EmptyState
          title="Không có quyền truy cập"
          description="Chỉ Chủ phòng khám hoặc Quản trị viên phòng khám mới có thể chỉnh sửa cài đặt này."
          size="md"
        />
      </div>
    )
  }

  if (!clinic) return null

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setSaveError(null)
    setSaved(false)
    try {
      await updateClinicSettings(clinic.id, {
        name,
        legal_name: legalName || null,
        phone: phone || null,
        email: email || null,
        address: address || null,
      })
      await refresh()
      setSaved(true)
    } catch (err: unknown) {
      setSaveError(toPageError(err))
    } finally {
      setSaving(false)
    }
  }

  const handleDeactivate = async () => {
    if (
      !window.confirm(
        'Bạn có chắc muốn ngừng hoạt động phòng khám? Hành động này không thể hoàn tác.'
      )
    ) {
      return
    }
    setDeactivating(true)
    setDeactivateError(null)
    try {
      await deactivateClinic(clinic.id)
      await refresh()
    } catch (err: unknown) {
      setDeactivateError(toPageError(err))
    } finally {
      setDeactivating(false)
    }
  }

  return (
    <div className="px-4 py-6 sm:px-6 max-w-2xl">
      <PageHeader title="Cài đặt phòng khám" />

      <Card variant="default" padding="lg">
        <CardContent>
          <form onSubmit={handleSave} className="flex flex-col gap-4">
            {saved && <Alert variant="success">Đã lưu thay đổi.</Alert>}
            {saveError && (
              <Alert variant="danger" title={saveError.title}>
                {saveError.message}
              </Alert>
            )}

            <FormField label="Tên phòng khám" required>
              <Input value={name} onChange={(e) => setName(e.target.value)} required />
            </FormField>

            <FormField label="Tên pháp lý">
              <Input value={legalName} onChange={(e) => setLegalName(e.target.value)} />
            </FormField>

            <FormField label="Số điện thoại">
              <Input value={phone} onChange={(e) => setPhone(e.target.value)} />
            </FormField>

            <FormField label="Email">
              <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
            </FormField>

            <FormField label="Địa chỉ">
              <Input value={address} onChange={(e) => setAddress(e.target.value)} />
            </FormField>

            <Button type="submit" loading={saving} fullWidth>
              Lưu thay đổi
            </Button>
          </form>
        </CardContent>
      </Card>

      {canDeactivate && (
        <Card variant="outlined" padding="lg" className="mt-6 border-danger/30">
          <CardContent>
            <p className="mb-1 text-body-md font-semibold text-danger">Vùng nguy hiểm</p>
            <p className="mb-4 text-body-sm text-text-muted">
              Ngừng hoạt động phòng khám là hành động vĩnh viễn (chỉ Chủ phòng khám mới thực hiện
              được).
            </p>
            {deactivateError && (
              <Alert variant="danger" title={deactivateError.title} className="mb-4">
                {deactivateError.message}
              </Alert>
            )}
            <Button variant="danger" loading={deactivating} onClick={() => void handleDeactivate()}>
              Ngừng hoạt động phòng khám
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
