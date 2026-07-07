import { renderHook, act } from '@testing-library/react'
import { useMediaQuery, useBreakpoint, BREAKPOINT_LG } from '../useMediaQuery'

// ---------------------------------------------------------------------------
// matchMedia mock — jsdom does not implement it. We map query -> matches via a
// predicate and keep a listener set so we can simulate viewport changes.
// ---------------------------------------------------------------------------

type MatchPredicate = (query: string) => boolean

interface MockMql {
  matches: boolean
  media: string
  listeners: Set<() => void>
}

function installMatchMedia(predicate: MatchPredicate): MockMql[] {
  const created: MockMql[] = []

  window.matchMedia = jest.fn().mockImplementation((query: string) => {
    const mql: MockMql = {
      matches: predicate(query),
      media: query,
      listeners: new Set(),
    }
    created.push(mql)
    return {
      get matches() {
        return mql.matches
      },
      media: query,
      addEventListener: (_: string, cb: () => void) => mql.listeners.add(cb),
      removeEventListener: (_: string, cb: () => void) => mql.listeners.delete(cb),
      // legacy API — unused but part of the interface
      addListener: (cb: () => void) => mql.listeners.add(cb),
      removeListener: (cb: () => void) => mql.listeners.delete(cb),
      dispatchEvent: () => true,
    }
  })

  return created
}

function fireChange(mqls: MockMql[], next: MatchPredicate) {
  act(() => {
    for (const mql of mqls) {
      mql.matches = next(mql.media)
      mql.listeners.forEach((cb) => cb())
    }
  })
}

afterEach(() => {
  jest.restoreAllMocks()
})

describe('useMediaQuery', () => {
  test('returns the real match after mount', () => {
    // Arrange — viewport matches the query
    installMatchMedia(() => true)

    // Act
    const { result } = renderHook(() => useMediaQuery('(min-width: 1024px)'))

    // Assert
    expect(result.current).toBe(true)
  })

  test('returns false when the query does not match', () => {
    installMatchMedia(() => false)

    const { result } = renderHook(() => useMediaQuery('(min-width: 1024px)'))

    expect(result.current).toBe(false)
  })

  test('updates when the viewport changes', () => {
    const mqls = installMatchMedia(() => false)

    const { result } = renderHook(() => useMediaQuery('(min-width: 1024px)'))
    expect(result.current).toBe(false)

    // Simulate viewport growing past lg
    fireChange(mqls, () => true)

    expect(result.current).toBe(true)
  })
})

describe('useBreakpoint', () => {
  test('reports desktop when width is >= lg', () => {
    // (min-width: 1024px) matches -> desktop
    installMatchMedia((q) => q.includes(`min-width: ${BREAKPOINT_LG}px`))

    const { result } = renderHook(() => useBreakpoint())

    expect(result.current.isDesktop).toBe(true)
    expect(result.current.isMobile).toBe(false)
  })

  test('reports mobile (isMobile true) when width is below lg', () => {
    // Nothing matches the lg min-width -> below lg
    installMatchMedia(() => false)

    const { result } = renderHook(() => useBreakpoint())

    expect(result.current.isDesktop).toBe(false)
    expect(result.current.isMobile).toBe(true)
  })

  test('flags tablet range (md <= width < lg) as mobile too', () => {
    // Only the md..lg range query matches, the lg query does not.
    installMatchMedia((q) => q.includes('max-width'))

    const { result } = renderHook(() => useBreakpoint())

    expect(result.current.isTablet).toBe(true)
    expect(result.current.isMobile).toBe(true)
    expect(result.current.isDesktop).toBe(false)
  })
})
