'use client'

import * as React from 'react'
import { BadgeCheck, ShieldAlert, Clock, ShieldX, Send } from 'lucide-react'
import {
  PageHeader,
  Card,
  Alert,
  Button,
  Input,
  Textarea,
  PageLoading,
  ErrorState,
} from '@/design-system'
import { formatVnd } from '@/components/marketplace'
import { ApiError } from '@/lib/api/client'
import type { DoctorVerificationStatus } from '@/lib/api/marketplace'
import {
  getMyDoctorProfile,
  updateMarketplaceProfile,
  submitForVerification,
  type DoctorProfileOut,
  type DoctorMarketplaceUpdate,
} from '@/lib/api/doctorMarketplace'

// ── Constraints (mirror backend validation) ───────────────────────────────────
const MAX_TEXT = 255
const MAX_YEARS = 80

// ── Verification banner config ────────────────────────────────────────────────

type BannerVariant = 'success' | 'warning' | 'danger'

interface BannerConfig {
  variant: BannerVariant
  title: string
  message: string
  Icon: React.ElementType
}

const BANNER: Record<DoctorVerificationStatus, BannerConfig> = {
  VERIFIED: {
    variant: 'success',
    title: 'Đã được duyệt',
    message: 'Hồ sơ của bạn đã được duyệt và đang hiển thị trên sàn tư vấn.',
    Icon: BadgeCheck,
  },
  PENDING_VERIFICATION: {
    variant: 'warning',
    title: 'Đang chờ duyệt',
    message:
      'Hồ sơ đang chờ quản trị viên duyệt. Bạn chưa hiển thị trên sàn tư vấn cho đến khi được duyệt.',
    Icon: Clock,
  },
  REJECTED: {
    variant: 'danger',
    title: 'Bị từ chối',
    message:
      'Hồ sơ chưa được duyệt. Vui lòng cập nhật thông tin cho đầy đủ, chính xác rồi gửi duyệt lại.',
    Icon: ShieldX,
  },
  SUSPENDED: {
    variant: 'danger',
    title: 'Đang tạm ngưng',
    message:
      'Hồ sơ của bạn đang bị tạm ngưng và không hiển thị trên sàn tư vấn. Vui lòng liên hệ quản trị viên.',
    Icon: ShieldAlert,
  },
}

// A doctor can (re)submit for verification when not yet verified and not suspended.
const CAN_SUBMIT: DoctorVerificationStatus[] = ['PENDING_VERIFICATION', 'REJECTED']

// ── Editable form state ───────────────────────────────────────────────────────

interface FormState {
  full_name: string
  specialty: string
  hospital_name: string
  years_experience: string
  consultation_fee: string
  languages: string
  consultation_methods: string
  avatar_url: string
  bio: string
}

function toForm(p: DoctorProfileOut): FormState {
  return {
    full_name: p.full_name ?? '',
    specialty: p.specialty ?? '',
    hospital_name: p.hospital_name ?? '',
    years_experience: p.years_experience != null ? String(p.years_experience) : '',
    consultation_fee: p.consultation_fee != null ? String(p.consultation_fee) : '',
    languages: p.languages ?? '',
    consultation_methods: p.consultation_methods ?? '',
    avatar_url: p.avatar_url ?? '',
    bio: p.bio ?? '',
  }
}

function friendlyError(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 403) return 'Bạn cần xác thực đa yếu tố (MFA) hoặc không có quyền thực hiện.'
    if (err.status === 422) return err.detail || 'Dữ liệu không hợp lệ. Vui lòng kiểm tra lại.'
    return err.detail || 'Đã có lỗi xảy ra. Vui lòng thử lại.'
  }
  return 'Đã có lỗi xảy ra. Vui lòng thử lại.'
}

export default function MarketplaceProfilePage() {
  const [profile, setProfile] = React.useState<DoctorProfileOut | null>(null)
  const [form, setForm] = React.useState<FormState | null>(null)
  const [loading, setLoading] = React.useState(true)
  const [loadError, setLoadError] = React.useState<string | null>(null)

  const [saving, setSaving] = React.useState(false)
  const [saveError, setSaveError] = React.useState<string | null>(null)
  const [saveOk, setSaveOk] = React.useState(false)

  const [submitting, setSubmitting] = React.useState(false)
  const [submitError, setSubmitError] = React.useState<string | null>(null)

  const load = React.useCallback(() => {
    setLoading(true)
    setLoadError(null)
    getMyDoctorProfile()
      .then((p) => {
        setProfile(p)
        setForm(toForm(p))
      })
      .catch((err: unknown) => setLoadError(friendlyError(err)))
      .finally(() => setLoading(false))
  }, [])

  React.useEffect(() => {
    load()
  }, [load])

  const setField = <K extends keyof FormState>(key: K, value: string) => {
    setForm((prev) => (prev ? { ...prev, [key]: value } : prev))
    setSaveOk(false)
  }

  const validate = (f: FormState): string | null => {
    const years = f.years_experience.trim()
    if (years !== '') {
      const n = Number(years)
      if (!Number.isInteger(n) || n < 0 || n > MAX_YEARS)
        return `Số năm kinh nghiệm phải là số nguyên từ 0 đến ${MAX_YEARS}.`
    }
    const fee = f.consultation_fee.trim()
    if (fee !== '') {
      const n = Number(fee)
      if (!Number.isFinite(n) || n < 0) return 'Phí tư vấn phải là số không âm.'
    }
    return null
  }

  const buildPayload = (f: FormState): DoctorMarketplaceUpdate => {
    const years = f.years_experience.trim()
    const fee = f.consultation_fee.trim()
    return {
      full_name: f.full_name.trim() || undefined,
      specialty: f.specialty.trim() || undefined,
      hospital_name: f.hospital_name.trim() || undefined,
      years_experience: years === '' ? undefined : Number(years),
      consultation_fee: fee === '' ? undefined : Number(fee),
      languages: f.languages.trim() || undefined,
      consultation_methods: f.consultation_methods.trim() || undefined,
      avatar_url: f.avatar_url.trim() || undefined,
      bio: f.bio.trim() || undefined,
    }
  }

  const handleSave = async () => {
    if (!form) return
    const validationError = validate(form)
    if (validationError) {
      setSaveError(validationError)
      return
    }
    setSaving(true)
    setSaveError(null)
    setSaveOk(false)
    try {
      const updated = await updateMarketplaceProfile(buildPayload(form))
      setProfile(updated)
      setForm(toForm(updated))
      setSaveOk(true)
    } catch (err) {
      setSaveError(friendlyError(err))
    } finally {
      setSaving(false)
    }
  }

  const handleSubmitVerification = async () => {
    setSubmitting(true)
    setSubmitError(null)
    try {
      const updated = await submitForVerification()
      setProfile(updated)
      setForm(toForm(updated))
    } catch (err) {
      setSubmitError(friendlyError(err))
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return (
      <div className="p-6">
        <PageLoading label="Đang tải hồ sơ..." />
      </div>
    )
  }

  if (loadError || !profile || !form) {
    return (
      <div className="p-6">
        <ErrorState
          title="Không thể tải hồ sơ"
          message={loadError ?? 'Vui lòng thử lại.'}
          onRetry={load}
        />
      </div>
    )
  }

  const banner = BANNER[profile.verification_status] ?? BANNER.PENDING_VERIFICATION
  const canSubmit = CAN_SUBMIT.includes(profile.verification_status)

  return (
    <div className="p-6 space-y-6 max-w-3xl">
      <PageHeader
        title="Hồ sơ tư vấn"
        subtitle="Quản lý thông tin hiển thị của bạn trên sàn tư vấn MetoCare"
      />

      {/* ── Verification status banner ── */}
      <Alert
        variant={banner.variant}
        title={banner.title}
        icon={<banner.Icon className="w-5 h-5" />}
      >
        <div className="flex flex-col gap-3">
          <p>{banner.message}</p>
          {canSubmit && (
            <div>
              <Button
                type="button"
                variant="primary"
                size="sm"
                loading={submitting}
                leftIcon={<Send className="w-4 h-4" />}
                onClick={handleSubmitVerification}
              >
                Gửi duyệt hồ sơ
              </Button>
            </div>
          )}
          {submitError && <p className="text-body-sm font-medium text-danger">{submitError}</p>}
        </div>
      </Alert>

      {/* ── Editable marketplace fields ── */}
      <Card padding="lg">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Input
            label="Họ và tên"
            value={form.full_name}
            onChange={(e) => setField('full_name', e.target.value)}
            fullWidth
          />
          <Input
            label="Chuyên khoa"
            placeholder="VD: Nội tiết, Tim mạch"
            value={form.specialty}
            onChange={(e) => setField('specialty', e.target.value)}
            fullWidth
          />
          <Input
            label="Bệnh viện / Phòng khám"
            maxLength={MAX_TEXT}
            value={form.hospital_name}
            onChange={(e) => setField('hospital_name', e.target.value)}
            fullWidth
          />
          <Input
            label="Số năm kinh nghiệm"
            type="number"
            min={0}
            max={MAX_YEARS}
            value={form.years_experience}
            onChange={(e) => setField('years_experience', e.target.value)}
            fullWidth
          />
          <Input
            label="Phí tư vấn (VND)"
            type="number"
            min={0}
            hint={
              form.consultation_fee.trim() !== '' && Number(form.consultation_fee) >= 0
                ? formatVnd(Number(form.consultation_fee))
                : 'Để trống nếu miễn phí'
            }
            value={form.consultation_fee}
            onChange={(e) => setField('consultation_fee', e.target.value)}
            fullWidth
          />
          <Input
            label="Ngôn ngữ"
            placeholder="VD: Tiếng Việt, English"
            maxLength={MAX_TEXT}
            value={form.languages}
            onChange={(e) => setField('languages', e.target.value)}
            fullWidth
          />
          <Input
            label="Hình thức tư vấn"
            placeholder="VD: Nhắn tin, Gọi video, Khám trực tiếp"
            maxLength={MAX_TEXT}
            value={form.consultation_methods}
            onChange={(e) => setField('consultation_methods', e.target.value)}
            fullWidth
          />
          <Input
            label="Ảnh đại diện (URL)"
            placeholder="https://…"
            value={form.avatar_url}
            onChange={(e) => setField('avatar_url', e.target.value)}
            fullWidth
          />
        </div>

        <div className="mt-4">
          <Textarea
            label="Giới thiệu"
            hint="Mô tả kinh nghiệm, thế mạnh của bạn để bệnh nhân hiểu rõ hơn."
            rows={5}
            value={form.bio}
            onChange={(e) => setField('bio', e.target.value)}
            fullWidth
          />
        </div>

        {saveError && (
          <div className="mt-4">
            <Alert variant="danger" title="Lưu thất bại">
              {saveError}
            </Alert>
          </div>
        )}
        {saveOk && (
          <div className="mt-4">
            <Alert variant="success" title="Đã lưu" dismissible onDismiss={() => setSaveOk(false)}>
              Thông tin hồ sơ đã được cập nhật.
            </Alert>
          </div>
        )}

        <div className="mt-6 flex justify-end">
          <Button type="button" variant="primary" loading={saving} onClick={handleSave}>
            Lưu thay đổi
          </Button>
        </div>
      </Card>
    </div>
  )
}
