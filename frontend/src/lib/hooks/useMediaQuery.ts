'use client'

import { useEffect, useState } from 'react'

// ---------------------------------------------------------------------------
// Breakpoints — mirror Tailwind defaults (md 768, lg 1024).
// The portal shell switches desktop <-> mobile at the `lg` boundary.
// ---------------------------------------------------------------------------

export const BREAKPOINT_MD = 768
export const BREAKPOINT_LG = 1024

/**
 * SSR-safe media-query hook.
 *
 * Renders `defaultValue` on the server and during the first client render
 * (so hydration never mismatches), then syncs to the real `matchMedia`
 * result after mount. Subscribes to changes and cleans up on unmount.
 *
 * @param query   A CSS media query string, e.g. `(min-width: 1024px)`.
 * @param defaultValue Value used before mount (default `false`).
 */
export function useMediaQuery(query: string, defaultValue = false): boolean {
  const [matches, setMatches] = useState<boolean>(defaultValue)

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      return
    }

    const mediaQueryList = window.matchMedia(query)
    const update = () => setMatches(mediaQueryList.matches)

    // Sync immediately in case the value changed between render and mount.
    update()

    mediaQueryList.addEventListener('change', update)
    return () => mediaQueryList.removeEventListener('change', update)
  }, [query])

  return matches
}

// ---------------------------------------------------------------------------
// useBreakpoint
// ---------------------------------------------------------------------------

export interface Breakpoint {
  /** width < lg (1024px) — the portal switches to the mobile drawer shell */
  isMobile: boolean
  /** md (768px) <= width < lg (1024px) — informational sub-range of mobile */
  isTablet: boolean
  /** width >= lg (1024px) — the always-expanded desktop shell */
  isDesktop: boolean
}

/**
 * Responsive breakpoint state keyed to the `lg` (1024px) boundary.
 *
 * SSR-safe: defaults to the desktop layout on the server and first render,
 * then corrects after mount. `isMobile` is the source of truth for the
 * portal shell switch (mobile = anything below `lg`, tablet included).
 */
export function useBreakpoint(): Breakpoint {
  const isDesktop = useMediaQuery(`(min-width: ${BREAKPOINT_LG}px)`, true)
  const isTablet = useMediaQuery(
    `(min-width: ${BREAKPOINT_MD}px) and (max-width: ${BREAKPOINT_LG - 0.02}px)`,
    false,
  )

  return {
    isDesktop,
    isTablet,
    isMobile: !isDesktop,
  }
}
