import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import DoctorQueuePage from '@/app/doctor/(doctor-shell)/queue/page'
import { getReviewQueue } from '@/lib/api/doctor'

jest.mock('@/lib/api/doctor', () => ({
  getReviewQueue: jest.fn(),
  submitReviewDecision: jest.fn(),
}))

const mockedGetReviewQueue = getReviewQueue as jest.Mock

function sampleItem(overrides = {}) {
  return {
    id: 'lab_result:uuid-1',
    patient_id: 'pp1',
    patient_name: 'Phạm Thị D',
    item_type: 'lab_result',
    priority: 'urgent',
    status: 'pending_review',
    summary: 'HbA1c 8.2%',
    submitted_at: '2026-06-03T08:00:00Z',
    assigned_doctor_id: null,
  }
}

beforeEach(() => {
  jest.clearAllMocks()
})

test('renders queue items from the API', async () => {
  mockedGetReviewQueue.mockResolvedValue({
    total: 1,
    pending_count: 1,
    items: [sampleItem()],
  })

  render(<DoctorQueuePage />)

  expect(await screen.findByText('Phạm Thị D')).toBeInTheDocument()
})

test('selecting an item swaps to the detail/decision view (master-detail)', async () => {
  mockedGetReviewQueue.mockResolvedValue({
    total: 1,
    pending_count: 1,
    items: [sampleItem()],
  })

  render(<DoctorQueuePage />)
  const queueItem = await screen.findByText('Phạm Thị D')

  // Decision panel is not shown until an item is selected.
  expect(screen.queryByText('Quyết Định Xét Duyệt')).not.toBeInTheDocument()

  fireEvent.click(queueItem)

  // The detail view (decision panel + mobile back control) now renders.
  await waitFor(() =>
    expect(screen.getByText('Quyết Định Xét Duyệt')).toBeInTheDocument(),
  )
  expect(
    screen.getByRole('button', { name: /Quay lại danh sách/ }),
  ).toBeInTheDocument()
})
