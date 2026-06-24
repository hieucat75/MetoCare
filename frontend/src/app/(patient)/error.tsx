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
    <div className="flex items-center justify-center min-h-[60vh] px-4">
      <PatientErrorState message="Đã xảy ra lỗi. Vui lòng thử lại." onRetry={reset} />
    </div>
  )
}
