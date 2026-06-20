'use client'

import * as React from 'react'
import { api } from './client'

/**
 * Feature flags exposed by the public GET /api/v1/info endpoint.
 * Patient-facing AI/OCR surfaces default OFF for the MVP (no real AI).
 */
export interface FeatureFlags {
  ai_assistant: boolean
  ocr: boolean
  ai_recommendation: boolean
  [key: string]: boolean
}

interface SystemInfo {
  feature_flags?: Record<string, boolean>
}

export async function getFeatureFlags(): Promise<FeatureFlags> {
  const info = await api.get<SystemInfo>('/info', { skipAuth: true })
  const flags = info.feature_flags ?? {}
  return {
    ai_assistant: Boolean(flags.ai_assistant),
    ocr: Boolean(flags.ocr),
    ai_recommendation: Boolean(flags.ai_recommendation),
    ...flags,
  }
}

/**
 * Fetch feature flags once. Returns `null` while loading (treat as "unknown" —
 * callers should hide gated UI until flags resolve to avoid a flash).
 */
export function useFeatureFlags(): FeatureFlags | null {
  const [flags, setFlags] = React.useState<FeatureFlags | null>(null)
  React.useEffect(() => {
    let alive = true
    getFeatureFlags()
      .then((f) => {
        if (alive) setFlags(f)
      })
      .catch(() => {
        // On error, fail closed: treat all gated features as OFF.
        if (alive) setFlags({ ai_assistant: false, ocr: false, ai_recommendation: false })
      })
    return () => {
      alive = false
    }
  }, [])
  return flags
}
