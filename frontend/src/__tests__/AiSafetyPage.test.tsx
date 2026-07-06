/**
 * /admin/ai-safety — regression: the page must render the empty state (not the
 * error state) when the backend returns an empty list, show sessions per tab,
 * and only show the error state when the request actually fails.
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import AiSafetyPage from '@/app/admin/(admin-shell)/ai-safety/page'
import { getAiSessions, reviewAiSession, type AiSession } from '@/lib/api/admin'

jest.mock('@/lib/api/admin', () => ({
  getAiSessions: jest.fn(),
  reviewAiSession: jest.fn(),
}))

const mockedGet = getAiSessions as jest.Mock
const mockedReview = reviewAiSession as jest.Mock

function sampleSession(overrides: Partial<AiSession> = {}): AiSession {
  return {
    id: 's1',
    patient_id: 'p1',
    patient_name: 'Nguyễn Văn A',
    explanation_type: 'Hỏi về đường huyết',
    safety_level: 'safe',
    flag: 'none',
    created_at: '2026-07-06T08:00:00Z',
    reviewed_by: null,
    reviewed_at: null,
    ...overrides,
  }
}

beforeEach(() => {
  jest.clearAllMocks()
})

test('renders the empty state (not an error) when there is no data', async () => {
  mockedGet.mockResolvedValue({ total: 0, flagged_count: 0, items: [] })
  render(<AiSafetyPage />)

  expect(await screen.findByText('Chưa có phiên AI nào')).toBeInTheDocument()
  expect(screen.queryByText(/Không thể tải/)).not.toBeInTheDocument()
})

test('empty "needs review" tab shows the dedicated empty state', async () => {
  mockedGet.mockResolvedValue({ total: 1, flagged_count: 0, items: [sampleSession()] })
  const user = userEvent.setup()
  render(<AiSafetyPage />)
  await screen.findByText('Nguyễn Văn A')

  await user.click(screen.getByRole('button', { name: 'Cần xem xét' }))
  expect(await screen.findByText('Chưa có phiên cần xem xét')).toBeInTheDocument()
})

test('urgent tab filters to safety_level=urgent sessions', async () => {
  mockedGet.mockResolvedValue({
    total: 2,
    flagged_count: 1,
    items: [
      sampleSession(),
      sampleSession({
        id: 's2',
        patient_name: 'Trần Thị B',
        safety_level: 'urgent',
        flag: 'urgent_response',
      }),
    ],
  })
  const user = userEvent.setup()
  render(<AiSafetyPage />)
  await screen.findByText('Nguyễn Văn A')

  await user.click(screen.getByRole('button', { name: 'Khẩn cấp' }))
  expect(screen.getByText('Trần Thị B')).toBeInTheDocument()
  expect(screen.queryByText('Nguyễn Văn A')).not.toBeInTheDocument()
})

test('shows the error state only when the request fails', async () => {
  mockedGet.mockRejectedValue(new Error('boom'))
  render(<AiSafetyPage />)

  expect(await screen.findByText(/Không thể tải danh sách phiên AI/)).toBeInTheDocument()
})

test('marking a session reviewed updates the card', async () => {
  const session = sampleSession({ flag: 'review_requested', safety_level: 'caution' })
  mockedGet.mockResolvedValue({ total: 1, flagged_count: 1, items: [session] })
  mockedReview.mockResolvedValue({
    ...session,
    reviewed_by: 'Safety Admin',
    reviewed_at: '2026-07-06T09:00:00Z',
  })
  const user = userEvent.setup()
  render(<AiSafetyPage />)

  await user.click(await screen.findByRole('button', { name: 'Đánh dấu đã xem xét' }))
  expect(await screen.findByText('Đã xem xét')).toBeInTheDocument()
  expect(mockedReview).toHaveBeenCalledWith('s1')
})
