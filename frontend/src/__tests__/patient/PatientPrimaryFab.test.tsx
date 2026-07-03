/**
 * Tests for the shared PatientPrimaryFab component.
 * Verifies canonical positioning, label/icon, click behavior, and href mode.
 */
import * as React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import { PatientPrimaryFab } from '@/components/patient/PatientPrimaryFab'

jest.mock('next/link', () => ({
  __esModule: true,
  default: ({ children, href, ...props }: { children: React.ReactNode; href: string }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}))

describe('PatientPrimaryFab', () => {
  it('renders a button with the aria-label', () => {
    render(<PatientPrimaryFab ariaLabel="Ghi chỉ số" onClick={() => {}} />)
    expect(screen.getByRole('button', { name: 'Ghi chỉ số' })).toBeInTheDocument()
  })

  it('applies the canonical FAB position/size classes', () => {
    render(<PatientPrimaryFab ariaLabel="Ghi chỉ số" onClick={() => {}} />)
    const el = screen.getByRole('button', { name: 'Ghi chỉ số' })
    expect(el.className).toContain('fixed')
    expect(el.className).toContain('bottom-28')
    expect(el.className).toContain('right-5')
    expect(el.className).toContain('z-30')
    expect(el.className).toContain('size-14')
    expect(el.className).toContain('rounded-full')
  })

  it('uses the default neu-btn-primary skin when no className is given', () => {
    render(<PatientPrimaryFab ariaLabel="Ghi chỉ số" onClick={() => {}} />)
    expect(screen.getByRole('button', { name: 'Ghi chỉ số' }).className).toContain(
      'neu-btn-primary'
    )
  })

  it('replaces the default skin when className is provided (e.g. medications)', () => {
    render(
      <PatientPrimaryFab
        ariaLabel="Thêm thuốc"
        onClick={() => {}}
        className=""
        style={{ background: 'linear-gradient(160deg,#0F9C6E,#0a7a57)' }}
      />
    )
    const el = screen.getByRole('button', { name: 'Thêm thuốc' })
    expect(el.className).not.toContain('neu-btn-primary')
    expect(el.className).toContain('fixed') // positioning still applied
  })

  it('fires onClick when clicked', () => {
    const onClick = jest.fn()
    render(<PatientPrimaryFab ariaLabel="Ghi chỉ số" onClick={onClick} />)
    fireEvent.click(screen.getByRole('button', { name: 'Ghi chỉ số' }))
    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it('renders a link when href is provided', () => {
    render(<PatientPrimaryFab ariaLabel="Ghi chỉ số" href="/metrics/log" />)
    const link = screen.getByRole('link', { name: 'Ghi chỉ số' })
    expect(link).toHaveAttribute('href', '/metrics/log')
  })

  it('renders a custom icon when provided', () => {
    render(
      <PatientPrimaryFab
        ariaLabel="Ghi chỉ số"
        onClick={() => {}}
        icon={<span data-testid="custom-icon">+</span>}
      />
    )
    expect(screen.getByTestId('custom-icon')).toBeInTheDocument()
  })
})
