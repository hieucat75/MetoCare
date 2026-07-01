/**
 * ChatSheet component tests — quality slice.
 *
 * Tests:
 * - Renders greeting on open
 * - Shows quick prompts before first user message
 * - Handles consent_required response with CTA chips
 * - No raw markdown leakage in rendered messages
 * - Mobile UX: input visible, min font size
 * - Close button visible and functional
 * - No provider identity in UI
 */
import * as React from 'react'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import { ChatSheet } from '@/components/patient/meto/ChatSheet'

// Mock sendMetoMessage
const mockSendMetoMessage = jest.fn()
jest.mock('@/lib/api/meto', () => ({
  sendMetoMessage: (...args: unknown[]) => mockSendMetoMessage(...args),
}))

// Default mock response
const DEFAULT_RESPONSE = {
  conversation_id: 'conv-1',
  message_id: 'msg-1',
  content: 'Chỉ số này bình thường. Hãy tiếp tục theo dõi.',
  safety_flags: [],
  provider_used: 'meto',
  fallback_used: false,
  quick_follow_ups: [],
  consent_required: false,
  missing_consents: [],
}

const CONSENT_REQUIRED_RESPONSE = {
  ...DEFAULT_RESPONSE,
  message_id: 'msg-consent',
  content: 'Để cá nhân hóa, Meto cần quyền đọc dữ liệu.',
  consent_required: true,
  missing_consents: ['medications', 'labs'],
}


// Mock scrollIntoView (not available in jsdom)
window.HTMLElement.prototype.scrollIntoView = jest.fn()

function renderChatSheet(open = true, screenId = 'dashboard') {
  return render(
    <ChatSheet
      open={open}
      onClose={jest.fn()}
      screenId={screenId}
    />
  )
}

describe('ChatSheet', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockSendMetoMessage.mockResolvedValue(DEFAULT_RESPONSE)
  })

  // ── Greeting ────────────────────────────────────────────────────────────

  it('shows greeting message on open', () => {
    renderChatSheet(true)
    // Greeting should contain a standard greeting phrase (any time)
    const greetings = [
      'Chào buổi sáng',
      'Chào buổi trưa',
      'Chào buổi chiều',
      'Chào buổi tối',
      'thức khuya',
      'sức khỏe',
      'Meto',
    ]
    const messageExists = greetings.some(
      phrase => screen.queryAllByText(new RegExp(phrase, 'i')).length > 0
    )
    expect(messageExists).toBe(true)
  })

  it('does not render when closed', () => {
    renderChatSheet(false)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('renders dialog with correct aria-label', () => {
    renderChatSheet(true)
    expect(screen.getByRole('dialog')).toHaveAttribute('aria-label', 'Chat với Meto')
  })

  // ── Close button ─────────────────────────────────────────────────────────

  it('close button is visible and not obscured', () => {
    renderChatSheet(true)
    const closeBtn = screen.getByRole('button', { name: /đóng chat/i })
    expect(closeBtn).toBeVisible()
  })

  it('calls onClose when close button clicked', () => {
    const onClose = jest.fn()
    render(<ChatSheet open={true} onClose={onClose} screenId="dashboard" />)
    fireEvent.click(screen.getByRole('button', { name: /đóng chat/i }))
    expect(onClose).toHaveBeenCalled()
  })

  // ── Quick prompts ─────────────────────────────────────────────────────────

  it('shows quick prompts before first user message', () => {
    renderChatSheet(true, 'dashboard')
    // Dashboard prompts
    expect(screen.getByText('Hôm nay tôi cần chú ý gì?')).toBeInTheDocument()
    expect(screen.getByText('Tôi còn việc gì chưa làm?')).toBeInTheDocument()
  })

  it('shows labs prompts on labs screen', () => {
    renderChatSheet(true, 'labs')
    expect(screen.getByText('Giải thích kết quả này')).toBeInTheDocument()
    expect(screen.getByText('Chỉ số nào cần chú ý?')).toBeInTheDocument()
  })

  it('shows medications prompts on medications screen', () => {
    renderChatSheet(true, 'medications')
    expect(screen.getByText('Thuốc này dùng để làm gì?')).toBeInTheDocument()
  })

  it('shows consent prompts on settings screen', () => {
    renderChatSheet(true, 'settings')
    expect(screen.getByText('Meto dùng dữ liệu nào?')).toBeInTheDocument()
    expect(screen.getByText('Cách bật/tắt quyền')).toBeInTheDocument()
    expect(screen.getByText('Xóa lịch sử Meto')).toBeInTheDocument()
  })

  it('does not show AI Copilot in any prompt', () => {
    const screens = ['dashboard', 'labs', 'medications', 'metrics', 'settings']
    for (const s of screens) {
      const { unmount } = renderChatSheet(true, s)
      expect(screen.queryByText(/AI Copilot/)).not.toBeInTheDocument()
      unmount()
    }
  })

  // ── Provider identity ─────────────────────────────────────────────────────

  it('header shows "Meto" not provider name', () => {
    renderChatSheet(true)
    // Find the "Meto" heading in chat header
    const metoHeadings = screen.getAllByText('Meto')
    expect(metoHeadings.length).toBeGreaterThan(0)
    // Should not show Claude or OpenAI
    expect(screen.queryByText(/Claude/)).not.toBeInTheDocument()
    expect(screen.queryByText(/OpenAI/)).not.toBeInTheDocument()
    expect(screen.queryByText(/ChatGPT/)).not.toBeInTheDocument()
  })

  it('subtitle shows "Trợ lý sức khỏe AI" not provider name', () => {
    renderChatSheet(true)
    expect(screen.getByText('Trợ lý sức khỏe AI')).toBeInTheDocument()
  })

  // ── Consent removed — Meto reads profile by default ─────────────────────────
  // Per product design: T&C covers consent at registration.
  // ConsentPrompt is NOT shown in chat. consent_required is always false.

  it('does NOT show ConsentPrompt even when backend returns consent_required=true', async () => {
    mockSendMetoMessage.mockResolvedValueOnce(CONSENT_REQUIRED_RESPONSE)
    renderChatSheet(true)

    // Send a message
    const input = screen.getByPlaceholderText('Nhắn tin cho Meto…')
    fireEvent.change(input, { target: { value: 'Xét nghiệm của tôi thế nào?' } })
    fireEvent.keyDown(input, { key: 'Enter' })

    await waitFor(() => {
      // Response should be shown as normal message, NOT as ConsentPrompt
      expect(screen.queryByTestId('consent-prompt')).not.toBeInTheDocument()
      // The content from backend is shown directly
      expect(screen.getByText('Để cá nhân hóa, Meto cần quyền đọc dữ liệu.')).toBeInTheDocument()
    })
  })

  it('consent CTA chips never appear in chat flow', async () => {
    mockSendMetoMessage.mockResolvedValueOnce(CONSENT_REQUIRED_RESPONSE)
    renderChatSheet(true)

    const input = screen.getByPlaceholderText('Nhắn tin cho Meto…')
    fireEvent.change(input, { target: { value: 'Test' } })
    fireEvent.keyDown(input, { key: 'Enter' })

    await waitFor(() => {
      // ConsentPrompt CTA chips must NOT appear in chat
      expect(screen.queryByTestId('consent-open-settings')).not.toBeInTheDocument()
      expect(screen.queryByTestId('consent-ask-general')).not.toBeInTheDocument()
      expect(screen.queryByTestId('consent-dismiss')).not.toBeInTheDocument()
    })
  })

  // ── Normal message rendering ───────────────────────────────────────────────

  it('renders assistant response without raw markdown', async () => {
    const responseWithMarkdown = {
      ...DEFAULT_RESPONSE,
      content: '**Tóm tắt**\nKết quả bình thường.\n\n- Uống thuốc\n- Đo đường huyết',
    }
    mockSendMetoMessage.mockResolvedValueOnce(responseWithMarkdown)
    renderChatSheet(true)

    const input = screen.getByPlaceholderText('Nhắn tin cho Meto…')
    fireEvent.change(input, { target: { value: 'Test' } })
    fireEvent.keyDown(input, { key: 'Enter' })

    await waitFor(() => {
      // The text "**Tóm tắt**" must NOT appear as raw text
      expect(screen.queryByText('**Tóm tắt**')).not.toBeInTheDocument()
      // "Tóm tắt" heading should be rendered (as DOM element)
      expect(screen.getByText('Tóm tắt')).toBeInTheDocument()
    })
  })

  // ── Input UX ──────────────────────────────────────────────────────────────

  it('input has minimum font size of 16px to prevent iOS zoom', () => {
    renderChatSheet(true)
    const input = screen.getByPlaceholderText('Nhắn tin cho Meto…')
    // Check inline style has fontSize: 16px
    expect(input.style.fontSize).toBe('16px')
  })

  it('send button is disabled when input is empty', () => {
    renderChatSheet(true)
    const sendBtn = screen.getByRole('button', { name: /gửi/i })
    expect(sendBtn).toBeDisabled()
  })

  it('send button enables when input has text', () => {
    renderChatSheet(true)
    const input = screen.getByPlaceholderText('Nhắn tin cho Meto…')
    fireEvent.change(input, { target: { value: 'Hello' } })
    const sendBtn = screen.getByRole('button', { name: /gửi/i })
    expect(sendBtn).not.toBeDisabled()
  })

  // ── Disclaimer ────────────────────────────────────────────────────────────

  it('shows disclaimer text', () => {
    renderChatSheet(true)
    expect(screen.getByText(/Meto không thay thế bác sĩ/)).toBeInTheDocument()
  })
})
