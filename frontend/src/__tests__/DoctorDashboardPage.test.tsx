import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import DoctorDashboardPage from '@/app/doctor/(doctor-shell)/dashboard/page'
import { getDoctorStats, getReviewQueue } from '@/lib/api/doctor'
import { ApiError } from '@/lib/api/client'

jest.mock('@/lib/api/doctor', () => ({
  getDoctorStats: jest.fn(),
  getReviewQueue: jest.fn(),
}))

const mockPush = jest.fn()
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush, replace: jest.fn() }),
}))

const mockedGetDoctorStats = getDoctorStats as jest.Mock
const mockedGetReviewQueue = getReviewQueue as jest.Mock

const sampleStats = {
  pending_reviews: 3,
  urgent_reviews: 1,
  total_patients: 12,
  reviews_today: 2,
  avg_review_time_min: 15,
}

const emptyQueue = { total: 0, pending_count: 0, items: [] }

beforeEach(() => {
  jest.clearAllMocks()
})

test('renders stats and recent queue from the API', async () => {
  mockedGetDoctorStats.mockResolvedValue(sampleStats)
  mockedGetReviewQueue.mockResolvedValue({
    total: 1,
    pending_count: 1,
    items: [
      {
        id: 'lab_result:1',
        patient_id: 'pp1',
        patient_name: 'Nguyễn Văn A',
        item_type: 'lab_result',
        priority: 'urgent',
        status: 'pending_review',
        summary: 'HbA1c cao',
        submitted_at: '2026-07-07T02:00:00Z',
        assigned_doctor_id: null,
      },
    ],
  })

  render(<DoctorDashboardPage />)

  expect(await screen.findByText('3')).toBeInTheDocument()
  expect(screen.getByText('Nguyễn Văn A')).toBeInTheDocument()
})

test('shows empty state (not an error) for an empty queue', async () => {
  mockedGetDoctorStats.mockResolvedValue(sampleStats)
  mockedGetReviewQueue.mockResolvedValue(emptyQueue)

  render(<DoctorDashboardPage />)

  expect(await screen.findByText('Không có mục nào trong hàng chờ.')).toBeInTheDocument()
})

test('stats and queue fail independently with status-aware errors + retry', async () => {
  mockedGetDoctorStats.mockRejectedValueOnce(new ApiError(403, 'no access'))
  mockedGetReviewQueue.mockRejectedValueOnce(new ApiError(500, 'boom'))

  render(<DoctorDashboardPage />)

  expect(await screen.findByText('Không có quyền')).toBeInTheDocument()
  expect(screen.getByText('Lỗi máy chủ')).toBeInTheDocument()

  mockedGetDoctorStats.mockResolvedValueOnce(sampleStats)
  const retryButtons = screen.getAllByRole('button', { name: 'Thử lại' })
  fireEvent.click(retryButtons[0])

  await waitFor(() => expect(mockedGetDoctorStats).toHaveBeenCalledTimes(2))
})
