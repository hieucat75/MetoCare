import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ClinicalCopilotPanel } from '../ClinicalCopilotPanel'
import { api } from '@/lib/api/client'
import { useBreakpoint } from '@/lib/hooks/useMediaQuery'

// NEXT_PUBLIC_CLINICAL_COPILOT is unset in the test env, so the panel stays
// in its default-disabled "Sắp ra mắt" shell — no clinicalCopilot mock needed.

jest.mock('@/lib/hooks/useMediaQuery', () => ({
  useBreakpoint: jest.fn(),
}))

// `clinicalCopilot.ts` imports the client as a sibling (`./client`), which the
// jest.config.js moduleNameMapper for `@/lib/api/client` doesn't catch by
// specifier text — mock it explicitly so `api.post` is inspectable here.
jest.mock('@/lib/api/client', () => ({
  api: {
    get: jest.fn().mockResolvedValue({}),
    post: jest.fn().mockResolvedValue({}),
    patch: jest.fn().mockResolvedValue({}),
    del: jest.fn().mockResolvedValue(undefined),
  },
  ApiError: class ApiError extends Error {},
}))

const mockedUseBreakpoint = useBreakpoint as jest.Mock

beforeEach(() => {
  jest.clearAllMocks()
  mockedUseBreakpoint.mockReturnValue({ isDesktop: true, isTablet: false, isMobile: false })
})

async function openPanel() {
  render(<ClinicalCopilotPanel scope={{ patientId: 'pp1' }} />)
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: /Meto phân tích hồ sơ/ }))
}

test('disabled (default) flag: expanding shows the coming-soon alert and makes zero network calls', async () => {
  await openPanel()

  expect(await screen.findByText(/Meto phân tích hồ sơ sắp ra mắt/)).toBeInTheDocument()
  expect(api.post).not.toHaveBeenCalled()
})

test('standing disclaimer is always shown once expanded', async () => {
  await openPanel()
  expect(await screen.findByText(/Gợi ý AI chỉ mang tính hỗ trợ/)).toBeInTheDocument()
})

test('desktop renders the body inline — no dialog role', async () => {
  mockedUseBreakpoint.mockReturnValue({ isDesktop: true, isTablet: false, isMobile: false })
  await openPanel()

  expect(await screen.findByText(/sắp ra mắt/)).toBeInTheDocument()
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
})

test('mobile renders the body inside a full-screen bottom sheet (dialog role)', async () => {
  mockedUseBreakpoint.mockReturnValue({ isDesktop: false, isTablet: false, isMobile: true })
  await openPanel()

  expect(await screen.findByRole('dialog', { name: 'Meto phân tích hồ sơ' })).toBeInTheDocument()
})
