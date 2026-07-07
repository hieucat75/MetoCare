import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import ClinicalNotesPage from '@/app/doctor/(doctor-shell)/notes/page'
import { getDoctorNotes } from '@/lib/api/doctor'
import { ApiError } from '@/lib/api/client'

jest.mock('@/lib/api/doctor', () => ({
  getDoctorNotes: jest.fn(),
}))

const mockPush = jest.fn()
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush, replace: jest.fn() }),
}))

const mockedGetDoctorNotes = getDoctorNotes as jest.Mock

function sampleNote(overrides = {}) {
  return {
    id: 'note-1',
    consultation_id: 'c-1',
    patient_id: 'pp1',
    patient_name: 'Trần Văn B',
    note_type: 'recommendation',
    status: 'draft',
    content_preview: 'Theo dõi đường huyết mỗi ngày',
    created_at: '2026-07-07T02:00:00Z',
    finalized_at: null,
    ...overrides,
  }
}

const empty = { total: 0, items: [] }

beforeEach(() => {
  jest.clearAllMocks()
})

test('renders notes from the API', async () => {
  mockedGetDoctorNotes.mockResolvedValue({ total: 1, items: [sampleNote()] })

  render(<ClinicalNotesPage />)

  expect(await screen.findByText('Trần Văn B')).toBeInTheDocument()
  expect(screen.getByText('Theo dõi đường huyết mỗi ngày')).toBeInTheDocument()
  // "Nháp" also appears as a tab label, so at least the status badge copy renders.
  expect(screen.getAllByText('Nháp').length).toBeGreaterThan(0)
})

test('shows empty state (not an error) when there are no notes', async () => {
  mockedGetDoctorNotes.mockResolvedValue(empty)

  render(<ClinicalNotesPage />)

  expect(await screen.findByText('Không có ghi chú')).toBeInTheDocument()
})

test('shows a status-aware error state with retry on failure', async () => {
  mockedGetDoctorNotes.mockRejectedValueOnce(new ApiError(404, 'not found'))
  mockedGetDoctorNotes.mockResolvedValueOnce(empty)

  render(<ClinicalNotesPage />)

  expect(await screen.findByText('Không tìm thấy')).toBeInTheDocument()

  fireEvent.click(screen.getByRole('button', { name: 'Thử lại' }))

  await waitFor(() => expect(screen.getByText('Không có ghi chú')).toBeInTheDocument())
})

test('switching to the draft filter refetches with status=draft', async () => {
  mockedGetDoctorNotes.mockResolvedValue({ total: 1, items: [sampleNote()] })

  render(<ClinicalNotesPage />)
  await screen.findByText('Trần Văn B')

  fireEvent.click(screen.getByRole('tab', { name: 'Nháp' }))

  await waitFor(() =>
    expect(mockedGetDoctorNotes).toHaveBeenLastCalledWith(
      expect.objectContaining({ status: 'draft' }),
    ),
  )
})

test('clicking a note navigates to its consultation detail page', async () => {
  mockedGetDoctorNotes.mockResolvedValue({ total: 1, items: [sampleNote()] })

  render(<ClinicalNotesPage />)
  const card = await screen.findByText('Trần Văn B')

  fireEvent.click(card)

  expect(mockPush).toHaveBeenCalledWith('/doctor/consultations/c-1')
})

test('search filters by patient name client-side', async () => {
  mockedGetDoctorNotes.mockResolvedValue({
    total: 2,
    items: [
      sampleNote({ id: 'n1', patient_name: 'Nguyễn Thị A' }),
      sampleNote({ id: 'n2', patient_name: 'Lê Văn C' }),
    ],
  })

  render(<ClinicalNotesPage />)
  await screen.findByText('Nguyễn Thị A')

  fireEvent.change(screen.getByPlaceholderText('Tìm theo tên bệnh nhân...'), {
    target: { value: 'nguyễn' },
  })

  expect(screen.getByText('Nguyễn Thị A')).toBeInTheDocument()
  expect(screen.queryByText('Lê Văn C')).not.toBeInTheDocument()
})
