'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import { Building2 } from 'lucide-react'
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
  FormField,
  Input,
  Button,
  Alert,
  PageLoading,
} from '@/design-system'
import { useAuth } from '@/lib/auth/context'
import { toPageError, type PageError } from '@/lib/api/client'
import { createClinic } from '@/lib/api/clinics'

/**
 * Self-serve clinic onboarding (`POST /clinics`) — the caller becomes the new
 * clinic's Owner in `trial` status. Deliberately lives OUTSIDE the
 * `(clinic-shell)` route group / `ClinicProvider`: a brand-new clinic can't
 * be created by someone `ClinicRouteGuard` would otherwise reject for having
 * no active membership yet — this is the one `/clinic/*` page reachable
 * without one. Still requires plain authentication (any platform role).
 */
export default function ClinicOnboardingPage() {
  const router = useRouter()
  const { isAuthenticated, isLoading: authLoading } = useAuth()

  const [name, setName] = React.useState('')
  const [legalName, setLegalName] = React.useState('')
  const [phone, setPhone] = React.useState('')
  const [email, setEmail] = React.useState('')
  const [address, setAddress] = React.useState('')
  const [submitting, setSubmitting] = React.useState(false)
  const [error, setError] = React.useState<PageError | null>(null)

  React.useEffect(() => {
    if (!authLoading && !isAuthenticated) router.replace('/login')
  }, [authLoading, isAuthenticated, router])

  if (authLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <PageLoading label="Đang tải..." />
      </div>
    )
  }

  if (!isAuthenticated) return null

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      await createClinic({
        name,
        legal_name: legalName || null,
        phone: phone || null,
        email: email || null,
        address: address || null,
      })
      router.replace('/clinic/dashboard')
    } catch (err: unknown) {
      setError(toPageError(err))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4 py-10">
      <Card variant="default" padding="lg" className="w-full max-w-lg">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Building2 className="h-5 w-5 text-primary" aria-hidden="true" />
            Tạo phòng khám mới
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            {error && (
              <Alert variant="danger" title={error.title}>
                {error.message}
              </Alert>
            )}

            <FormField label="Tên phòng khám" required>
              <Input value={name} onChange={(e) => setName(e.target.value)} required autoFocus />
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

            <p className="text-body-xs text-text-muted">
              Bạn sẽ trở thành Chủ phòng khám. Phòng khám mới bắt đầu ở trạng thái dùng thử.
            </p>

            <Button type="submit" loading={submitting} fullWidth>
              Tạo phòng khám
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
