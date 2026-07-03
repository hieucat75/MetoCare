'use client'

import * as React from 'react'
import { useParams, useRouter } from 'next/navigation'
import { ArrowLeft, ShieldOff, ShieldCheck, Send, Download } from 'lucide-react'
import {
  PageHeader,
  Card,
  Badge,
  Button,
  Modal,
  EmptyState,
  ErrorState,
  CardSkeleton,
} from '@/design-system'
import {
  getPatientDetail,
  updatePatientStatus,
  requestPatientProfileUpdate,
  type AdminPatientDetail,
} from '@/lib/api/admin'
import { useAuth } from '@/lib/auth/context'

function formatDateTime(iso: string | null): string {
  if (!iso) return '—'
  try {
    return new Intl.DateTimeFormat('vi-VN', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    }).format(new Date(iso))
  } catch {
    return iso
  }
}

function genderLabel(gender: string | null): string {
  if (gender === 'male') return 'Nam'
  if (gender === 'female') return 'Nữ'
  if (gender === 'other') return 'Khác'
  return 'Chưa cập nhật'
}

const CONSENT_LABEL: Record<string, { label: string; variant: 'success' | 'danger' | 'default' }> = {
  valid: { label: 'Đã đồng ý điều khoản', variant: 'success' },
  revoked: { label: 'Đã thu hồi đồng ý', variant: 'danger' },
  none: { label: 'Chưa đồng ý điều khoản', variant: 'default' },
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card className="p-5">
      <h2 className="text-lg font-semibold text-text mb-3">{title}</h2>
      {children}
    </Card>
  )
}

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <p className="text-sm text-text-muted">{label}</p>
      <p className="text-base text-text">{value ?? '—'}</p>
    </div>
  )
}

export default function AdminPatientDetailPage() {
  const params = useParams<{ patientId: string }>()
  const patientId = params.patientId
  const router = useRouter()
  const { user: authUser } = useAuth()
  const isSuperAdmin = authUser?.role === 'super_admin'

  const [detail, setDetail] = React.useState<AdminPatientDetail | null>(null)
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)

  const [showBlockConfirm, setShowBlockConfirm] = React.useState(false)
  const [toggling, setToggling] = React.useState(false)

  const [requestSent, setRequestSent] = React.useState(false)
  const [requestSending, setRequestSending] = React.useState(false)

  const load = React.useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await getPatientDetail(patientId)
      setDetail(data)
    } catch {
      setError('Không thể tải hồ sơ bệnh nhân. Vui lòng thử lại.')
    } finally {
      setLoading(false)
    }
  }, [patientId])

  React.useEffect(() => {
    void load()
  }, [load])

  const toggleStatus = React.useCallback(
    async (isActive: boolean) => {
      if (!detail) return
      setToggling(true)
      try {
        const updated = await updatePatientStatus(detail.id, isActive)
        setDetail((prev) => (prev ? { ...prev, is_active: updated.is_active } : prev))
      } catch {
        // silently ignore; admin can retry
      } finally {
        setToggling(false)
        setShowBlockConfirm(false)
      }
    },
    [detail],
  )

  const handleRequestUpdate = React.useCallback(async () => {
    if (!detail) return
    setRequestSending(true)
    try {
      await requestPatientProfileUpdate(detail.user_id)
      setRequestSent(true)
    } catch {
      // silently ignore; button stays enabled for retry
    } finally {
      setRequestSending(false)
    }
  }, [detail])

  if (loading) {
    return (
      <div className="px-6 py-6 flex flex-col gap-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <CardSkeleton key={i} lines={3} />
        ))}
      </div>
    )
  }

  if (error || !detail) {
    return (
      <div className="px-6 py-6">
        <ErrorState variant="inline" title={error ?? 'Không tìm thấy bệnh nhân.'} onRetry={load} />
      </div>
    )
  }

  const consentMeta = CONSENT_LABEL[detail.consent_status] ?? CONSENT_LABEL.none
  const medications = Array.isArray(detail.summary?.medications)
    ? (detail.summary.medications as Record<string, unknown>[])
    : []
  const labDocuments = Array.isArray(detail.summary?.lab_documents)
    ? (detail.summary.lab_documents as Record<string, unknown>[])
    : []
  const activeCarePlans = Array.isArray(detail.summary?.active_care_plans)
    ? (detail.summary.active_care_plans as Record<string, unknown>[])
    : []

  return (
    <div className="px-6 py-6">
      <Button
        variant="ghost"
        size="sm"
        className="min-h-11 mb-4"
        onClick={() => router.push('/admin/patients')}
      >
        <ArrowLeft className="h-4 w-4 mr-1" aria-hidden />
        Quay lại danh sách
      </Button>

      <PageHeader
        title={detail.full_name ?? 'Bệnh nhân'}
        subtitle={detail.phone ?? detail.email ?? undefined}
        actions={
          <Badge variant={detail.is_active ? 'success' : 'danger'} size="md">
            {detail.is_active ? 'Đang hoạt động' : 'Đã khóa'}
          </Badge>
        }
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
        <Section title="Thông tin định danh">
          <div className="grid grid-cols-2 gap-4">
            <Field label="Họ tên" value={detail.full_name} />
            <Field label="Giới tính" value={genderLabel(detail.gender)} />
            <Field label="Tuổi" value={detail.age != null ? `${detail.age} tuổi` : null} />
            <Field label="Ngày tạo hồ sơ" value={formatDateTime(detail.created_at)} />
          </div>
        </Section>

        <Section title="Thông tin liên hệ">
          <div className="grid grid-cols-2 gap-4">
            <Field label="Số điện thoại" value={detail.phone} />
            <Field label="Email" value={detail.email} />
            <Field label="Địa chỉ" value={detail.address} />
            <Field label="Hoạt động gần nhất" value={formatDateTime(detail.last_activity_at)} />
          </div>
        </Section>

        <Section title="Hồ sơ sức khỏe tổng quan">
          <div className="grid grid-cols-2 gap-4">
            <Field
              label="Chiều cao / Cân nặng"
              value={
                detail.height_cm || detail.weight_kg
                  ? `${detail.height_cm ?? '—'} cm / ${detail.weight_kg ?? '—'} kg`
                  : null
              }
            />
            <Field label="Vòng eo" value={detail.waist_cm ? `${detail.waist_cm} cm` : null} />
            <Field label="Phân nhóm nguy cơ" value={detail.risk_segment} />
            <Field label="Bệnh nền" value={detail.known_conditions} />
            <Field label="Dị ứng" value={detail.allergies} />
            <Field label="Tiền sử gia đình" value={detail.family_history} />
          </div>
        </Section>

        <Section title="Trạng thái Consent">
          <Badge variant={consentMeta.variant} size="md">
            {consentMeta.label}
          </Badge>
          {detail.consent && (
            <div className="grid grid-cols-2 gap-4 mt-3">
              <Field label="Phiên bản điều khoản" value={detail.consent.terms_version} />
              <Field label="Ngày chấp nhận" value={formatDateTime(detail.consent.accepted_at)} />
            </div>
          )}
        </Section>

        <Section title="Lab gần nhất">
          {labDocuments.length === 0 ? (
            <EmptyState title="Chưa có dữ liệu xét nghiệm" size="sm" />
          ) : (
            <ul className="flex flex-col gap-2 text-base text-text">
              {labDocuments.map((doc, i) => (
                <li key={i} className="border-b border-border pb-2 last:border-none">
                  {String(doc.lab_name ?? 'Xét nghiệm')} —{' '}
                  {String(doc.status ?? doc.ocr_status ?? '')}
                </li>
              ))}
            </ul>
          )}
        </Section>

        <Section title="Medication đang dùng">
          {medications.length === 0 ? (
            <EmptyState title="Chưa có medication" size="sm" />
          ) : (
            <ul className="flex flex-col gap-2 text-base text-text">
              {medications.map((med, i) => (
                <li key={i} className="border-b border-border pb-2 last:border-none">
                  {String(med.name ?? '—')} {med.dose ? `— ${String(med.dose)}` : ''}
                </li>
              ))}
            </ul>
          )}
        </Section>

        <Section title="Care plan">
          {activeCarePlans.length === 0 ? (
            <EmptyState title="Chưa có care plan đang hoạt động" size="sm" />
          ) : (
            <ul className="flex flex-col gap-2 text-base text-text">
              {activeCarePlans.map((cp, i) => (
                <li key={i}>{String(cp.title ?? '—')}</li>
              ))}
            </ul>
          )}
        </Section>

        <Section title="Bác sĩ / phòng khám liên quan">
          {detail.consultations.length === 0 ? (
            <EmptyState title="Chưa có tư vấn nào với bác sĩ" size="sm" />
          ) : (
            <ul className="flex flex-col gap-2 text-base text-text">
              {detail.consultations.map((c) => (
                <li key={c.id} className="border-b border-border pb-2 last:border-none">
                  {c.doctor_name ?? '—'} {c.clinic_name ? `(${c.clinic_name})` : ''} —{' '}
                  <Badge variant="default" size="sm">
                    {c.status}
                  </Badge>
                </li>
              ))}
            </ul>
          )}
        </Section>

        <Section title="Nhật ký hoạt động / audit">
          {detail.audit_log.length === 0 ? (
            <EmptyState title="Chưa có hoạt động được ghi nhận" size="sm" />
          ) : (
            <ul className="flex flex-col gap-2 text-base text-text">
              {detail.audit_log.map((entry) => (
                <li key={entry.id} className="border-b border-border pb-2 last:border-none">
                  <span className="text-text-muted text-sm mr-2">
                    {formatDateTime(entry.timestamp)}
                  </span>
                  {entry.action} ({entry.resource_type})
                </li>
              ))}
            </ul>
          )}
        </Section>
      </div>

      <Section title="Hành động quản trị">
        <div className="flex flex-wrap gap-3">
          {detail.is_active ? (
            <Button
              variant="danger"
              size="sm"
              className="min-h-11"
              disabled={!isSuperAdmin}
              onClick={() => setShowBlockConfirm(true)}
            >
              <ShieldOff className="h-4 w-4 mr-1" aria-hidden />
              Khóa tài khoản
            </Button>
          ) : (
            <Button
              variant="primary"
              size="sm"
              className="min-h-11"
              disabled={!isSuperAdmin}
              loading={toggling}
              onClick={() => void toggleStatus(true)}
            >
              <ShieldCheck className="h-4 w-4 mr-1" aria-hidden />
              Mở khóa tài khoản
            </Button>
          )}

          <Button
            variant="outline"
            size="sm"
            className="min-h-11"
            loading={requestSending}
            disabled={requestSent}
            onClick={() => void handleRequestUpdate()}
          >
            <Send className="h-4 w-4 mr-1" aria-hidden />
            {requestSent ? 'Đã gửi yêu cầu' : 'Gửi yêu cầu cập nhật thông tin'}
          </Button>

          <Button
            variant="outline"
            size="sm"
            className="min-h-11"
            disabled
            title="Chức năng xuất dữ liệu chưa được hỗ trợ ở phiên bản này — sẽ bổ sung sau"
          >
            <Download className="h-4 w-4 mr-1" aria-hidden />
            Xuất CSV (sắp ra mắt)
          </Button>
        </div>
      </Section>

      <Modal
        open={showBlockConfirm}
        onOpenChange={setShowBlockConfirm}
        title="Xác nhận khóa tài khoản"
        footer={
          <>
            <Button
              variant="outline"
              size="sm"
              className="min-h-11"
              onClick={() => setShowBlockConfirm(false)}
              disabled={toggling}
            >
              Hủy
            </Button>
            <Button
              variant="danger"
              size="sm"
              className="min-h-11"
              loading={toggling}
              onClick={() => void toggleStatus(false)}
            >
              Khóa tài khoản
            </Button>
          </>
        }
      >
        <p className="text-base text-text">
          Bạn có chắc muốn khóa tài khoản của {detail.full_name ?? 'bệnh nhân này'}? Bệnh nhân sẽ
          không thể đăng nhập cho đến khi được mở khóa lại.
        </p>
      </Modal>
    </div>
  )
}
