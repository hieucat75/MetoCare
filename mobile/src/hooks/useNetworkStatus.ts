import { useEffect, useState } from 'react'
import NetInfo from '@react-native-community/netinfo'

/**
 * Offline-aware network status. `isOffline` is true only when we're confident
 * there's no connectivity; unknown states are treated as online to avoid
 * false "offline" banners on first mount.
 */
export function useNetworkStatus(): { isOffline: boolean } {
  const [isOffline, setIsOffline] = useState(false)

  useEffect(() => {
    let mounted = true

    NetInfo.fetch().then((state) => {
      if (mounted) setIsOffline(state.isConnected === false)
    })

    const unsubscribe = NetInfo.addEventListener((state) => {
      if (mounted) setIsOffline(state.isConnected === false)
    })

    return () => {
      mounted = false
      unsubscribe()
    }
  }, [])

  return { isOffline }
}
