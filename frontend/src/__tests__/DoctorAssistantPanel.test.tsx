import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { DoctorAssistantPanel } from '@/app/doctor/(doctor-shell)/patients/[id]/DoctorAssistantPanel'
import { askDoctorAssistant } from '@/lib/api/doctorAssistant'

jest.mock('@/lib/api/doctorAssistant', () => {
  const actual = jest.requireActual('@/lib/api/doctorAssistant')
  return {
    ...actual,
    // Default: disabled shell — resolves without a network call.
    askDoctorAssistant: jest.fn().mockResolvedValue({
      content: '',
      disclaimer: actual.DOCTOR_ASSISTANT_DISCLAIMER,
      disabled: true,
    }),
  }
})

const mockedAsk = askDoctorAssistant as jest.Mock

beforeEach(() => {
  jest.clearAllMocks()
})

async function openPanel() {
  render(<DoctorAssistantPanel patientId="pp1" />)
  fireEvent.click(screen.getByRole('button', { name: /Trợ lý AI cho bác sĩ/ }))
}

test('renders the disclaimer when expanded', async () => {
  await openPanel()
  expect(
    screen.getByText(/KHÔNG thay thế phán đoán của bác sĩ/),
  ).toBeInTheDocument()
})

test('renders the quick-prompt chips', async () => {
  await openPanel()
  expect(screen.getByText('Tóm tắt hồ sơ bệnh nhân')).toBeInTheDocument()
  expect(screen.getByText('Diễn giải xu hướng chỉ số gần đây')).toBeInTheDocument()
  expect(screen.getByText('Gợi ý câu hỏi thăm khám')).toBeInTheDocument()
  expect(screen.getByText('Soạn nháp ghi chú lâm sàng')).toBeInTheDocument()
})

test('disabled state shows the coming-soon banner and disables the input', async () => {
  await openPanel()
  expect(
    await screen.findByText(/Trợ lý AI cho bác sĩ sắp ra mắt/),
  ).toBeInTheDocument()
  expect(screen.getByLabelText('Câu hỏi cho trợ lý AI')).toBeDisabled()
})

test('clicking a quick prompt while disabled does NOT call the network', async () => {
  await openPanel()
  await waitFor(() => expect(mockedAsk).toHaveBeenCalled()) // the mount probe
  const callsAfterMount = mockedAsk.mock.calls.length

  const chip = screen.getByText('Tóm tắt hồ sơ bệnh nhân')
  fireEvent.click(chip)

  // Disabled chip button must not trigger an additional ask() call.
  expect(mockedAsk.mock.calls.length).toBe(callsAfterMount)
})
