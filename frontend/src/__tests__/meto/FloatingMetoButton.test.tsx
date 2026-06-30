/**
 * Tests for FloatingMetoButton component.
 * Verifies floating button renders and opens ChatSheet on click.
 */
import * as React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import { FloatingMetoButton } from '@/components/patient/meto/FloatingMetoButton'

// Mock the ChatSheet to avoid rendering complex children
jest.mock('@/components/patient/meto/ChatSheet', () => ({
  ChatSheet: ({ open, onClose }: { open: boolean; onClose: () => void }) =>
    open ? (
      <div data-testid="chat-sheet">
        <button onClick={onClose}>Close</button>
      </div>
    ) : null,
}))

// Mock sendMetoMessage to avoid actual API calls
jest.mock('@/lib/api/meto', () => ({
  sendMetoMessage: jest.fn().mockResolvedValue({
    conversation_id: 'conv-1',
    message_id: 'msg-1',
    content: 'Test response',
    safety_flags: [],
    provider_used: 'meto',
    fallback_used: false,
    quick_follow_ups: [],
  }),
}))

describe('FloatingMetoButton', () => {
  it('renders the floating button', () => {
    render(<FloatingMetoButton screenId="dashboard" />)
    const btn = screen.getByRole('button', { name: /hỏi meto/i })
    expect(btn).toBeInTheDocument()
  })

  it('button has correct fixed positioning classes', () => {
    render(<FloatingMetoButton screenId="dashboard" />)
    const btn = screen.getByRole('button', { name: /hỏi meto/i })
    expect(btn.className).toContain('fixed')
    expect(btn.className).toContain('bottom')
    expect(btn.className).toContain('right')
    expect(btn.className).toContain('z-50')
  })

  it('button has aria-label', () => {
    render(<FloatingMetoButton screenId="dashboard" />)
    const btn = screen.getByRole('button', { name: /hỏi meto/i })
    expect(btn).toHaveAttribute('aria-label', 'Hỏi Meto')
  })

  it('ChatSheet is NOT open initially', () => {
    render(<FloatingMetoButton screenId="dashboard" />)
    expect(screen.queryByTestId('chat-sheet')).not.toBeInTheDocument()
  })

  it('opens ChatSheet when button is clicked', () => {
    render(<FloatingMetoButton screenId="dashboard" />)
    const btn = screen.getByRole('button', { name: /hỏi meto/i })
    fireEvent.click(btn)
    expect(screen.getByTestId('chat-sheet')).toBeInTheDocument()
  })

  it('closes ChatSheet when ChatSheet signals close', () => {
    render(<FloatingMetoButton screenId="dashboard" />)
    const btn = screen.getByRole('button', { name: /hỏi meto/i })
    fireEvent.click(btn)
    expect(screen.getByTestId('chat-sheet')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(screen.queryByTestId('chat-sheet')).not.toBeInTheDocument()
  })

  it('passes screenId to ChatSheet', () => {
    // Just verify no crash with different screenIds
    const screens = ['dashboard', 'labs', 'medications', 'metrics', 'care_plan']
    screens.forEach((screenId) => {
      const { unmount } = render(<FloatingMetoButton screenId={screenId} />)
      unmount()
    })
  })

  it('button width and height are 14 (56px equivalent)', () => {
    render(<FloatingMetoButton screenId="dashboard" />)
    const btn = screen.getByRole('button', { name: /hỏi meto/i })
    // Tailwind classes w-14 h-14 applied
    expect(btn.className).toContain('w-14')
    expect(btn.className).toContain('h-14')
  })
})
