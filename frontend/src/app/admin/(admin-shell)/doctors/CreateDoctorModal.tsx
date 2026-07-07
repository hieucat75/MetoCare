'use client'

import * as React from 'react'
import { Modal, Button, Alert, Input, PasswordInput, Textarea } from '@/design-system'
import { createDoctor, type DoctorAdminOut } from '@/lib/api/adminDoctors'
import { ApiError } from '@/lib/api/client'

const PASSWORD_MIN_LENGTH = 6
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

interface FormValues {
  full_name: string
  email: string
  password: string
  specialty: string
  license_no: string
  bio: string
}

const EMPTY_FORM: FormValues = {
  full_name: '',
  email: '',
  password: '',
  specialty: '',
  license_no: '',
  bio: '',
}

type FieldErrors = Partial<Record<'full_name' | 'email' | 'password', string>>

function validate(values: FormValues): FieldErrors {
  const errors: FieldErrors = {}
  if (!values.full_name.trim()) {
    errors.full_name = 'Vui lòng nhập họ tên bác sĩ.'
  }
  if (!values.email.trim()) {
    errors.email = 'Vui lòng nhập email.'
  } else if (!EMAIL_PATTERN.test(values.email.trim())) {
    errors.email = 'Email không hợp lệ.'
  }
  if (!values.password) {
    errors.password = 'Vui lòng nhập mật khẩu.'
  } else if (values.password.length < PASSWORD_MIN_LENGTH) {
    errors.password = `Mật khẩu phải có ít nhất ${PASSWORD_MIN_LENGTH} ký tự.`
  }
  return errors
}

function submitErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 409) {
      return 'Email này đã được đăng ký. Vui lòng dùng email khác.'
    }
    if (err.status === 403) {
      return 'Bạn không có quyền hoặc cần xác thực đa yếu tố (MFA) để tạo tài khoản bác sĩ.'
    }
    if (err.status === 422) {
      return 'Dữ liệu không hợp lệ. Vui lòng kiểm tra lại các trường đã nhập.'
    }
  }
  return 'Đã xảy ra lỗi khi tạo tài khoản bác sĩ. Vui lòng thử lại.'
}

export interface CreateDoctorModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Called with the created account after a successful submit. */
  onCreated: (doctor: DoctorAdminOut) => void
}

/**
 * Form modal for onboarding a new doctor (sales/ops flow). The created
 * account starts in PENDING_VERIFICATION and must be approved in the
 * verification queue before appearing in the marketplace.
 */
export function CreateDoctorModal({ open, onOpenChange, onCreated }: CreateDoctorModalProps) {
  const [values, setValues] = React.useState<FormValues>(EMPTY_FORM)
  const [fieldErrors, setFieldErrors] = React.useState<FieldErrors>({})
  const [submitError, setSubmitError] = React.useState<string | null>(null)
  const [submitting, setSubmitting] = React.useState(false)

  const setField = React.useCallback(
    (field: keyof FormValues) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
      const { value } = e.target
      setValues((prev) => ({ ...prev, [field]: value }))
    },
    []
  )

  const resetAndClose = React.useCallback(() => {
    setValues(EMPTY_FORM)
    setFieldErrors({})
    setSubmitError(null)
    onOpenChange(false)
  }, [onOpenChange])

  const handleSubmit = React.useCallback(async () => {
    const errors = validate(values)
    setFieldErrors(errors)
    if (Object.keys(errors).length > 0) return

    setSubmitting(true)
    setSubmitError(null)
    try {
      const created = await createDoctor({
        full_name: values.full_name.trim(),
        email: values.email.trim(),
        password: values.password,
        specialty: values.specialty.trim() || null,
        license_no: values.license_no.trim() || null,
        bio: values.bio.trim() || null,
      })
      setValues(EMPTY_FORM)
      setFieldErrors({})
      onOpenChange(false)
      onCreated(created)
    } catch (err) {
      setSubmitError(submitErrorMessage(err))
    } finally {
      setSubmitting(false)
    }
  }, [values, onCreated, onOpenChange])

  return (
    <Modal
      open={open}
      onOpenChange={(next) => {
        if (!next) resetAndClose()
      }}
      title="Thêm bác sĩ mới"
      description="Tạo tài khoản bác sĩ để team sales onboard vào hệ thống"
      footer={
        <>
          <Button variant="outline" size="sm" onClick={resetAndClose} disabled={submitting}>
            Hủy
          </Button>
          <Button variant="primary" size="sm" loading={submitting} onClick={handleSubmit}>
            Tạo bác sĩ
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        {submitError && (
          <Alert variant="danger" title="Không tạo được tài khoản">
            {submitError}
          </Alert>
        )}

        <Input
          label="Họ tên *"
          placeholder="VD: BS Nguyễn Văn An"
          value={values.full_name}
          onChange={setField('full_name')}
          error={fieldErrors.full_name}
          fullWidth
        />
        <Input
          label="Email *"
          type="email"
          placeholder="bacsi@benhvien.vn"
          value={values.email}
          onChange={setField('email')}
          error={fieldErrors.email}
          fullWidth
        />
        <PasswordInput
          label="Mật khẩu tạm *"
          placeholder={`Tối thiểu ${PASSWORD_MIN_LENGTH} ký tự`}
          value={values.password}
          onChange={setField('password')}
          error={fieldErrors.password}
          hint="Gửi mật khẩu này cho bác sĩ qua kênh an toàn và khuyến khích đổi mật khẩu sau lần đăng nhập đầu."
          fullWidth
        />
        <Input
          label="Chuyên khoa"
          placeholder="VD: Nội tiết"
          value={values.specialty}
          onChange={setField('specialty')}
          fullWidth
        />
        <Input
          label="Số chứng chỉ hành nghề (CCHN)"
          placeholder="VD: VN-01234"
          value={values.license_no}
          onChange={setField('license_no')}
          fullWidth
        />
        <Textarea
          label="Giới thiệu"
          placeholder="Kinh nghiệm, nơi công tác…"
          value={values.bio}
          onChange={setField('bio')}
          rows={3}
          fullWidth
        />
      </div>
    </Modal>
  )
}
