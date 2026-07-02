'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/lib/auth/context'
import { acceptTerms, getRoleHomePath } from '@/lib/api/auth'
import { ApiError } from '@/lib/api/client'
import { ConsentStep } from '@/components/patient/consent/ConsentStep'
import { buildConsentPayload, isTermsOutdated } from '@/lib/legal'

/**
 * Login/version gate destination: shown when a logged-in user must re-accept an
 * updated Terms version before continuing into the app.
 */
export default function ReconsentPage() {
  const { user, isLoading, refresh } = useAuth()
  const router = useRouter()
  const [submitting, setSubmitting] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  const home = user ? getRoleHomePath(user.role) : '/login'

  React.useEffect(() => {
    if (isLoading) return
    if (!user) {
      router.replace('/login')
      return
    }
    // Already on the current version — nothing to accept.
    if (!isTermsOutdated(user.accepted_terms_version)) {
      router.replace(home)
    }
  }, [isLoading, user, home, router])

  const handleAccept = async () => {
    setError(null)
    setSubmitting(true)
    try {
      await acceptTerms(buildConsentPayload(true, 'reconsent'))
      await refresh()
      router.replace(home)
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.detail || 'Có lỗi xảy ra. Vui lòng thử lại.'
          : 'Không thể kết nối máy chủ. Kiểm tra kết nối mạng.',
      )
      setSubmitting(false)
    }
  }

  if (isLoading || !user || !isTermsOutdated(user.accepted_terms_version)) {
    return null
  }

  return (
    <div>
      <p className="mb-4 rounded-[14px] border border-neu-green/20 bg-mint-100/50 p-3 text-[16px] leading-relaxed text-text dark:bg-mint-100/10 dark:text-white/90">
        Điều khoản sử dụng của MetoCare đã được cập nhật. Vui lòng xem và đồng ý để tiếp tục.
      </p>
      <ConsentStep
        onAccept={handleAccept}
        isLoading={submitting}
        error={error}
        submitLabel="Đồng ý và tiếp tục"
      />
    </div>
  )
}
