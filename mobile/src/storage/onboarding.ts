import AsyncStorage from '@react-native-async-storage/async-storage'
import type { AsyncKV } from './installId'

/**
 * Onboarding completion state (first-run gate).
 *
 * Non-secret UI state, so it lives in AsyncStorage. Persisted across launches;
 * cleared implicitly on reinstall (AsyncStorage wipe) so a reinstalled app
 * re-runs onboarding — consistent with the install-id reset semantics.
 */

export const ONBOARDING_KEY = 'meto_onboarding_complete'
const DONE = '1'

export function createOnboardingStore(kv: AsyncKV = AsyncStorage) {
  return {
    async isComplete(): Promise<boolean> {
      try {
        return (await kv.getItem(ONBOARDING_KEY)) === DONE
      } catch {
        // Storage unavailable — degrade to "not complete" so the first-run gate
        // re-shows onboarding rather than crashing the app. Non-secret UI state,
        // so re-running onboarding is a safe fallback.
        return false
      }
    },
    async complete(): Promise<void> {
      try {
        await kv.setItem(ONBOARDING_KEY, DONE)
      } catch {
        // Best-effort persist: a failed write just means onboarding shows again
        // next launch. Never surface as an unhandled rejection to the UI.
      }
    },
    async reset(): Promise<void> {
      try {
        await kv.removeItem(ONBOARDING_KEY)
      } catch {
        // Best-effort clear: nothing actionable to surface for a gate reset.
      }
    },
  }
}

export const onboardingStore = createOnboardingStore()
