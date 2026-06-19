'use client'

import * as React from 'react'
import { PatientErrorState } from '@/components/patient/states'

export default function PatientError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  React.useEffect(() => {
    // Digest is a server-side error ID — useful for support, not logged to console
    void error
  }, [error])

  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <PatientErrorState
        title="Đã có sự cố nhỏ"
        message="Đừng lo, dữ liệu của bạn vẫn an toàn. Hãy thử lại nhé."
        onRetry={reset}
      />
    </div>
  )
}
