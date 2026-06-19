'use client'

import * as React from 'react'

interface AsyncDataState<T> {
  data: T | null
  loading: boolean
  error: string | null
}

/**
 * Minimal async data hook — loads once on mount (or when deps change).
 * Handles cancellation via a `mounted` flag so stale state is never set.
 *
 * Usage:
 *   const { data, loading, error, reload } = useAsyncData(
 *     () => getPatientProfile(patientId),
 *     [patientId],
 *   )
 */
export function useAsyncData<T>(
  fetcher: () => Promise<T>,
  deps: React.DependencyList,
): AsyncDataState<T> & { reload: () => void } {
  const [state, setState] = React.useState<AsyncDataState<T>>({
    data: null,
    loading: true,
    error: null,
  })
  const [rev, setRev] = React.useState(0)

  React.useEffect(() => {
    let mounted = true
    setState((s) => ({ ...s, loading: true, error: null }))
    fetcher()
      .then((data) => {
        if (mounted) setState({ data, loading: false, error: null })
      })
      .catch((err: unknown) => {
        if (mounted) {
          const msg = err instanceof Error ? err.message : 'Có lỗi xảy ra. Vui lòng thử lại.'
          setState({ data: null, loading: false, error: msg })
        }
      })
    return () => {
      mounted = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, rev])

  const reload = React.useCallback(() => setRev((r) => r + 1), [])

  return { ...state, reload }
}
