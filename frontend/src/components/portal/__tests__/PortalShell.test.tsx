import { render, screen } from '@testing-library/react'
import { LayoutDashboard } from 'lucide-react'
import type { NavItem } from '@/design-system'
import { PortalShell } from '../PortalShell'
import { BREAKPOINT_LG } from '@/lib/hooks/useMediaQuery'

// ---------------------------------------------------------------------------
// matchMedia mock — jsdom has no layout, so we drive `useBreakpoint` (which
// PortalShell reads) by mapping the desktop `(min-width: lg)` query to a
// boolean. Same pattern as src/lib/hooks/__tests__/useMediaQuery.test.ts.
// ---------------------------------------------------------------------------

function installMatchMedia(isDesktop: boolean) {
  window.matchMedia = jest.fn().mockImplementation((query: string) => {
    // Desktop shell keys off `(min-width: 1024px)`. The tablet sub-range query
    // (which contains `max-width`) is never desktop, so it must stay false.
    const matches = query.includes(`min-width: ${BREAKPOINT_LG}px`)
      ? isDesktop
      : query.includes('max-width')
        ? !isDesktop
        : false
    return {
      matches,
      media: query,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => true,
    }
  })
}

const NAV_ITEMS: NavItem[] = [
  {
    id: 'dashboard',
    label: 'Tổng quan',
    icon: <LayoutDashboard className="h-5 w-5" />,
    href: '/doctor/dashboard',
  },
]

function renderShell() {
  return render(
    <PortalShell
      title="Cổng bác sĩ"
      roleLabel="Bác sĩ"
      navItems={NAV_ITEMS}
      activeItemId="dashboard"
      onNavItem={() => {}}
      onLogout={() => {}}
    >
      <div>Nội dung trang</div>
    </PortalShell>,
  )
}

afterEach(() => {
  jest.restoreAllMocks()
})

describe('PortalShell — responsive breakpoint behavior', () => {
  test('renders the mobile top bar + hamburger when viewport is below lg', () => {
    // Arrange — force MOBILE (< lg)
    installMatchMedia(false)

    // Act
    renderShell()

    // Assert — the mobile top bar hamburger (aria-label from MobileTopBar)
    expect(screen.getByRole('button', { name: 'Mở menu điều hướng' })).toBeInTheDocument()
    // The mobile drawer variant renders the labelled navigation drawer aside.
    expect(screen.getByLabelText('Navigation drawer')).toBeInTheDocument()
    // The desktop TopNav collapse toggle must NOT be present on mobile.
    expect(screen.queryByRole('button', { name: 'Toggle sidebar' })).not.toBeInTheDocument()
    // Content still renders.
    expect(screen.getByText('Nội dung trang')).toBeInTheDocument()
  })

  test('renders the expanded desktop sidebar (no hamburger) when viewport is >= lg', () => {
    // Arrange — force DESKTOP (>= lg)
    installMatchMedia(true)

    // Act
    renderShell()

    // Assert — desktop uses the fixed sidebar + TopNav collapse toggle.
    expect(screen.getByLabelText('Sidebar navigation')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Toggle sidebar' })).toBeInTheDocument()
    // The mobile-only hamburger must NOT be present on desktop.
    expect(screen.queryByRole('button', { name: 'Mở menu điều hướng' })).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Navigation drawer')).not.toBeInTheDocument()
    // Content still renders.
    expect(screen.getByText('Nội dung trang')).toBeInTheDocument()
  })

  test('renders the nav item label in both viewports', () => {
    installMatchMedia(false)
    const mobile = renderShell()
    expect(screen.getByText('Tổng quan')).toBeInTheDocument()
    mobile.unmount()

    installMatchMedia(true)
    renderShell()
    expect(screen.getByText('Tổng quan')).toBeInTheDocument()
  })
})
