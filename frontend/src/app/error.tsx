'use client'

import { useEffect } from 'react'
import Button from '@/design-system/components/core/Button'

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => {
    console.error(error)
  }, [error])

  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-4">
      <div className="max-w-sm w-full text-center">
        <div className="w-16 h-16 rounded-2xl bg-danger-light flex items-center justify-center mx-auto mb-6">
          <span className="text-3xl font-bold text-danger">!</span>
        </div>
        <h2 className="text-display-xs font-bold text-text mb-2">Có lỗi xảy ra</h2>
        <p className="text-body-sm text-text-muted mb-8">
          Ứng dụng gặp sự cố không mong muốn. Vui lòng thử lại.
        </p>
        <div className="flex flex-col gap-3">
          <Button variant="primary" fullWidth onClick={reset}>
            Thử lại
          </Button>
          <Button variant="ghost" fullWidth onClick={() => (window.location.href = '/')}>
            Về trang chủ
          </Button>
        </div>
      </div>
    </div>
  )
}
