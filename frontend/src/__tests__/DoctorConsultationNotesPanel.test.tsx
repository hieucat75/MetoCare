import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import DoctorConsultationDetailPage from '@/app/doctor/(doctor-shell)/consultations/[id]/page'
import {
  getConsultation,
  getPatientSummary,
  listNotes,
  createNote,
} from '@/lib/api/consultations'
import { ApiError } from '@/lib/api/client'

jest.mock('@/lib/api/consultations', () => ({
  getConsultation: jest.fn(),
  confirmConsultation: jest.fn(),
  startConsultation: jest.fn(),
  completeConsultation: jest.fn(),
  cancelConsultation: jest.fn(),
  getPatientSummary: jest.fn(),
  listNotes: jest.fn(),
  createNote: jest.fn(),
}))

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn(), replace: jest.fn() }),
  useParams: () => ({ id: 'c-1' }),
}))

const mockedGetConsultation = getConsultation as jest.Mock
const mockedGetPatientSummary = getPatientSummary as jest.Mock
const mockedListNotes = listNotes as jest.Mock
const mockedCreateNote = createNote as jest.Mock

function sampleConsultation(overrides = {}) {
  return {
    id: 'c-1',
    patient_id: 'pp1',
    doctor_id: 'd1',
    consultation_type: 'CHAT',
    status: 'PAID',
    consultation_price: 200000,
    data_consent_accepted: true,
    ...overrides,
  }
}

beforeEach(() => {
  jest.clearAllMocks()
  mockedGetConsultation.mockResolvedValue(sampleConsultation())
  // Patient-summary access is a separate concern from notes — keep it out of
  // the way with a graceful 403 (the page already treats that as no-access).
  mockedGetPatientSummary.mockRejectedValue(new ApiError(403, 'no access'))
})

test('shows a draft badge and resumes the latest draft into the editor', async () => {
  mockedListNotes.mockResolvedValue([
    {
      id: 'n1',
      consultation_id: 'c-1',
      doctor_id: 'd1',
      content: 'ghi chú đang soạn',
      note_type: 'recommendation',
      status: 'draft',
      finalized_at: null,
      created_at: '2026-07-07T02:00:00Z',
    },
  ])

  render(<DoctorConsultationDetailPage />)

  expect(await screen.findByText('Nháp')).toBeInTheDocument()
  expect(screen.getByDisplayValue('ghi chú đang soạn')).toBeInTheDocument()
})

test('Lưu nháp saves with status=draft and keeps the textarea filled', async () => {
  mockedListNotes.mockResolvedValue([])
  mockedCreateNote.mockResolvedValue({
    id: 'n2',
    consultation_id: 'c-1',
    doctor_id: 'd1',
    content: 'bản nháp mới',
    note_type: 'recommendation',
    status: 'draft',
    finalized_at: null,
    created_at: '2026-07-07T03:00:00Z',
  })

  render(<DoctorConsultationDetailPage />)
  const textarea = await screen.findByLabelText('Nội dung')

  fireEvent.change(textarea, { target: { value: 'bản nháp mới' } })
  fireEvent.click(screen.getByRole('button', { name: 'Lưu nháp' }))

  await waitFor(() =>
    expect(mockedCreateNote).toHaveBeenCalledWith('c-1', {
      content: 'bản nháp mới',
      note_type: 'recommendation',
      status: 'draft',
    }),
  )
  // Draft save keeps content in the textarea (unlike finalize, which clears it).
  expect(textarea).toHaveValue('bản nháp mới')
})

test('Hoàn tất ghi chú saves with status=finalized and clears the editor', async () => {
  mockedListNotes.mockResolvedValue([])
  mockedCreateNote.mockResolvedValue({
    id: 'n3',
    consultation_id: 'c-1',
    doctor_id: 'd1',
    content: 'ghi chú hoàn tất',
    note_type: 'recommendation',
    status: 'finalized',
    finalized_at: '2026-07-07T03:00:00Z',
    created_at: '2026-07-07T03:00:00Z',
  })

  render(<DoctorConsultationDetailPage />)
  const textarea = await screen.findByLabelText('Nội dung')

  fireEvent.change(textarea, { target: { value: 'ghi chú hoàn tất' } })
  fireEvent.click(screen.getByRole('button', { name: 'Hoàn tất ghi chú' }))

  await waitFor(() =>
    expect(mockedCreateNote).toHaveBeenCalledWith('c-1', {
      content: 'ghi chú hoàn tất',
      note_type: 'recommendation',
      status: 'finalized',
    }),
  )
  await waitFor(() => expect(textarea).toHaveValue(''))
  expect(await screen.findByText('Đã hoàn tất')).toBeInTheDocument()
})
