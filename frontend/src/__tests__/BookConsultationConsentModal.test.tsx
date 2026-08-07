import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import BookConsultationPage from '@/app/(patient)/marketplace/[doctorId]/book/page'
import { getDoctorDetail } from '@/lib/api/marketplace'
import { createConsultation, getDataSharingPolicy, payConsultation } from '@/lib/api/consultations'
import { ApiError } from '@/lib/api/client'

jest.mock('@/lib/api/marketplace', () => ({
  getDoctorDetail: jest.fn(),
}))

jest.mock('@/lib/api/consultations', () => ({
  createConsultation: jest.fn(),
  payConsultation: jest.fn(),
  getDataSharingPolicy: jest.fn(),
}))

const mockPush = jest.fn()
const mockBack = jest.fn()
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush, replace: jest.fn(), back: mockBack }),
  useParams: () => ({ doctorId: 'doc-1' }),
}))

const mockedGetDoctorDetail = getDoctorDetail as jest.Mock
const mockedCreate = createConsultation as jest.Mock
const mockedPay = payConsultation as jest.Mock
const mockedPolicy = getDataSharingPolicy as jest.Mock

const POLICY = {
  consent_version: '1.0',
  policy_version: '1.0',
  purpose: 'doctor_consultation',
  title: 'Chia sẻ thông tin sức khỏe với bác sĩ?',
  body:
    'Để bác sĩ có đủ thông tin phục vụ buổi tư vấn, MetoCare có thể chia sẻ các thông tin sức khỏe liên quan của bạn.\n\n' +
    'Thông tin chỉ được cung cấp cho bác sĩ thực hiện buổi tư vấn này.\n\n' +
    'Bạn có thể quản lý hoặc thu hồi quyền chia sẻ trong phần Quyền riêng tư.',
  accept_label: 'Đồng ý và tiếp tục',
  decline_label: 'Không chia sẻ',
  categories: [
    { key: 'health_records', label: 'Hồ sơ sức khỏe và chỉ số' },
    { key: 'medications_and_adherence', label: 'Thuốc đang sử dụng và mức độ tuân thủ' },
    { key: 'lab_results', label: 'Kết quả xét nghiệm' },
    { key: 'medical_documents', label: 'Tài liệu y tế đã xác nhận' },
    { key: 'patient_profile', label: 'Thông tin hồ sơ cá nhân liên quan' },
  ],
}

const CONSULTATION = {
  id: 'c-1',
  patient_id: 'pp-1',
  doctor_id: 'doc-1',
  consultation_type: 'CHAT',
  status: 'REQUESTED',
  consultation_price: 200000,
  data_consent_accepted: true,
}

beforeEach(() => {
  jest.clearAllMocks()
  mockedGetDoctorDetail.mockResolvedValue({
    id: 'doc-1',
    full_name: 'BS Nguyễn Văn A',
    specialty: 'Nội tiết',
    consultation_fee: 200000,
  })
  mockedPolicy.mockResolvedValue(POLICY)
  mockedCreate.mockResolvedValue(CONSULTATION)
  mockedPay.mockResolvedValue({ payment_status: 'PAID' })
})

async function openConsentModal() {
  render(<BookConsultationPage />)
  const submit = await screen.findByRole('button', { name: 'Xác nhận đặt tư vấn' })
  await userEvent.click(submit)
  return await screen.findByRole('dialog')
}

// ---------------------------------------------------------------------------
// The modal blocks booking
// ---------------------------------------------------------------------------

test('pressing the booking action opens the consent dialog and books nothing yet', async () => {
  const dialog = await openConsentModal()

  expect(dialog).toBeInTheDocument()
  expect(await screen.findByText(POLICY.title)).toBeInTheDocument()
  // The decisive assertion: opening the dialog created no consultation.
  expect(mockedCreate).not.toHaveBeenCalled()
})

test('nothing is pre-consented — there is no ticked checkbox to leave alone', async () => {
  await openConsentModal()

  expect(screen.queryAllByRole('checkbox')).toHaveLength(0)
  expect(mockedCreate).not.toHaveBeenCalled()
})

test('accepting books the consultation with the rendered categories and versions', async () => {
  await openConsentModal()

  await userEvent.click(await screen.findByRole('button', { name: POLICY.accept_label }))

  await waitFor(() => expect(mockedCreate).toHaveBeenCalledTimes(1))
  const payload = mockedCreate.mock.calls[0][0]
  expect(payload.doctor_id).toBe('doc-1')
  expect(payload.data_sharing_consent).toMatchObject({
    accepted: true,
    categories: [
      'health_records',
      'medications_and_adherence',
      'lab_results',
      'medical_documents',
      'patient_profile',
    ],
    consent_version: '1.0',
    policy_version: '1.0',
    source: 'web',
  })
})

// ---------------------------------------------------------------------------
// Every dismissal path means no consent
// ---------------------------------------------------------------------------

test('pressing "Không chia sẻ" closes the dialog without booking', async () => {
  await openConsentModal()

  await userEvent.click(await screen.findByRole('button', { name: POLICY.decline_label }))

  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  expect(mockedCreate).not.toHaveBeenCalled()
})

test('pressing Escape closes the dialog without booking', async () => {
  await openConsentModal()

  fireEvent.keyDown(document.activeElement || document.body, { key: 'Escape', code: 'Escape' })

  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  expect(mockedCreate).not.toHaveBeenCalled()
})

test('re-opening after a dismissal still books nothing until accept', async () => {
  await openConsentModal()
  await userEvent.click(await screen.findByRole('button', { name: POLICY.decline_label }))
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())

  await userEvent.click(screen.getByRole('button', { name: 'Xác nhận đặt tư vấn' }))
  expect(await screen.findByRole('dialog')).toBeInTheDocument()
  expect(mockedCreate).not.toHaveBeenCalled()
})

// ---------------------------------------------------------------------------
// Double submission
// ---------------------------------------------------------------------------

test('double-clicking accept creates exactly one consultation', async () => {
  let resolveCreate: (value: unknown) => void = () => {}
  mockedCreate.mockImplementation(
    () =>
      new Promise((resolve) => {
        resolveCreate = resolve
      }),
  )

  await openConsentModal()
  const accept = await screen.findByRole('button', { name: POLICY.accept_label })

  fireEvent.click(accept)
  fireEvent.click(accept)
  fireEvent.click(accept)

  expect(mockedCreate).toHaveBeenCalledTimes(1)
  resolveCreate(CONSULTATION)
  await waitFor(() => expect(mockedCreate).toHaveBeenCalledTimes(1))
})

test('a submit in flight cannot be dismissed by Escape', async () => {
  mockedCreate.mockImplementation(() => new Promise(() => {}))

  await openConsentModal()
  fireEvent.click(await screen.findByRole('button', { name: POLICY.accept_label }))

  await screen.findByRole('button', { name: 'Đang xử lý…' })
  fireEvent.keyDown(document.activeElement || document.body, { key: 'Escape', code: 'Escape' })

  // Still open — the booking may already exist server-side.
  expect(screen.getByRole('dialog')).toBeInTheDocument()
})

// ---------------------------------------------------------------------------
// Loading, error and retry
// ---------------------------------------------------------------------------

test('a failed booking shows the error inside the dialog and allows a retry', async () => {
  mockedCreate.mockRejectedValueOnce(new ApiError(500, 'Máy chủ bận'))

  await openConsentModal()
  await userEvent.click(await screen.findByRole('button', { name: POLICY.accept_label }))

  expect(await screen.findByRole('alert')).toHaveTextContent('Máy chủ bận')
  expect(screen.getByRole('dialog')).toBeInTheDocument()

  mockedCreate.mockResolvedValueOnce(CONSULTATION)
  await userEvent.click(screen.getByRole('button', { name: POLICY.accept_label }))
  await waitFor(() => expect(mockedCreate).toHaveBeenCalledTimes(2))
})

test('a stale consent version tells the patient to reload rather than retry blindly', async () => {
  mockedCreate.mockRejectedValueOnce(new ApiError(409, ''))

  await openConsentModal()
  await userEvent.click(await screen.findByRole('button', { name: POLICY.accept_label }))

  expect(await screen.findByRole('alert')).toHaveTextContent(/tải lại trang/i)
})

test('a failed policy load blocks accept and offers a retry', async () => {
  mockedPolicy.mockRejectedValueOnce(new Error('offline'))

  await openConsentModal()

  const retry = await screen.findByRole('button', { name: 'Thử lại' })
  // Consent cannot be given against copy that never rendered.
  expect(screen.getByRole('button', { name: 'Đồng ý và tiếp tục' })).toBeDisabled()

  mockedPolicy.mockResolvedValueOnce(POLICY)
  await userEvent.click(retry)

  await waitFor(() => expect(screen.getByRole('button', { name: POLICY.accept_label })).toBeEnabled())
})

// ---------------------------------------------------------------------------
// Accessibility
// ---------------------------------------------------------------------------

test('the dialog is a labelled, described modal', async () => {
  const dialog = await openConsentModal()
  await screen.findByText(POLICY.title)

  expect(dialog).toHaveAttribute('aria-modal', 'true')

  // Assert what a screen reader actually announces, not the generated ids:
  // the label must be the question, the description must be the sharing terms.
  const labelledBy = dialog.getAttribute('aria-labelledby') as string
  expect(document.getElementById(labelledBy)).toHaveTextContent(POLICY.title)

  const describedBy = dialog.getAttribute('aria-describedby') as string
  expect(document.getElementById(describedBy)).toHaveTextContent(
    'Thông tin chỉ được cung cấp cho bác sĩ thực hiện buổi tư vấn này.',
  )
})

test('both decisions are reachable as buttons, neither hidden from assistive tech', async () => {
  await openConsentModal()

  const accept = await screen.findByRole('button', { name: POLICY.accept_label })
  const decline = screen.getByRole('button', { name: POLICY.decline_label })
  expect(accept).toBeEnabled()
  expect(decline).toBeEnabled()
})

test('focus moves into the dialog when it opens', async () => {
  const dialog = await openConsentModal()
  await screen.findByText(POLICY.title)

  await waitFor(() => expect(dialog.contains(document.activeElement)).toBe(true))
})

test('every granted category is named on screen, not just summarised', async () => {
  await openConsentModal()

  for (const category of POLICY.categories) {
    expect(await screen.findByText(category.label)).toBeInTheDocument()
  }
})

test('the dialog renders the server copy verbatim, including every paragraph', async () => {
  await openConsentModal()

  for (const paragraph of POLICY.body.split('\n\n')) {
    expect(await screen.findByText(paragraph)).toBeInTheDocument()
  }
})
