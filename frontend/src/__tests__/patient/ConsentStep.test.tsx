/**
 * ConsentStep — the final registration screen (Terms + Privacy).
 * Verifies the consent checkbox gates the primary CTA, the summary + legal
 * links render, and the secondary CTA calls back.
 */
import * as React from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ConsentStep } from '@/components/patient/consent/ConsentStep'
import { CONSENT_SUMMARY } from '@/lib/legal'

jest.mock('next/link', () => ({
  __esModule: true,
  default: ({ children, href, ...props }: { children: React.ReactNode; href: string }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}))

const CTA = 'Đồng ý và tạo tài khoản'

describe('ConsentStep', () => {
  it('renders all five summary points and both legal links', () => {
    render(<ConsentStep onAccept={() => {}} onBack={() => {}} />)
    for (const point of CONSENT_SUMMARY) {
      expect(screen.getByText(point)).toBeInTheDocument()
    }
    expect(screen.getByRole('link', { name: /Xem đầy đủ Điều khoản sử dụng/ })).toHaveAttribute(
      'href',
      '/terms'
    )
    expect(screen.getByRole('link', { name: /Xem Chính sách quyền riêng tư/ })).toHaveAttribute(
      'href',
      '/privacy'
    )
  })

  it('keeps the primary CTA disabled until the checkbox is checked', async () => {
    const user = userEvent.setup()
    const onAccept = jest.fn()
    render(<ConsentStep onAccept={onAccept} onBack={() => {}} />)

    const cta = screen.getByRole('button', { name: CTA })
    expect(cta).toBeDisabled()

    await user.click(screen.getByRole('checkbox'))
    expect(cta).toBeEnabled()

    await user.click(cta)
    expect(onAccept).toHaveBeenCalledTimes(1)
  })

  it('does not call onAccept while unchecked', async () => {
    const user = userEvent.setup()
    const onAccept = jest.fn()
    render(<ConsentStep onAccept={onAccept} onBack={() => {}} />)
    await user.click(screen.getByRole('button', { name: CTA }))
    expect(onAccept).not.toHaveBeenCalled()
  })

  it('calls onBack when the secondary CTA is pressed', async () => {
    const user = userEvent.setup()
    const onBack = jest.fn()
    render(<ConsentStep onAccept={() => {}} onBack={onBack} />)
    await user.click(screen.getByRole('button', { name: 'Quay lại' }))
    expect(onBack).toHaveBeenCalledTimes(1)
  })

  it('shows a loading label while submitting', () => {
    render(<ConsentStep onAccept={() => {}} onBack={() => {}} isLoading />)
    expect(screen.getByText('Đang tạo tài khoản…')).toBeInTheDocument()
  })
})
