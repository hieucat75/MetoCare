import React from 'react'
import { fireEvent, render, waitFor } from '@testing-library/react-native'

jest.mock('../src/api/consultations', () => ({
  getDataSharingConsent: jest.fn(),
  getDataSharingPolicy: jest.fn(),
  revokeDataSharingConsent: jest.fn(),
  restoreDataSharingConsent: jest.fn(),
}))

import { ApiError } from '../src/api/client'
import type { ApiClient } from '../src/api/client'
import {
  getDataSharingConsent,
  getDataSharingPolicy,
  restoreDataSharingConsent,
  revokeDataSharingConsent,
} from '../src/api/consultations'
import { ConsultationSharingCard } from '../src/components/ConsultationSharingCard'

const mockedGet = getDataSharingConsent as jest.Mock
const mockedRevoke = revokeDataSharingConsent as jest.Mock
const mockedRestore = restoreDataSharingConsent as jest.Mock
const mockedPolicy = getDataSharingPolicy as jest.Mock

const POLICY = {
  consent_version: '1.0',
  policy_version: '1.1',
  purpose: 'doctor_consultation',
  title: 'Chia sẻ thông tin sức khỏe với bác sĩ?',
  body: 'Đoạn một.\n\nĐoạn hai.',
  accept_label: 'Đồng ý và tiếp tục',
  decline_label: 'Không chia sẻ',
  categories: [
    { key: 'health_records', label: 'Hồ sơ sức khỏe' },
    { key: 'medications_and_adherence', label: 'Thuốc và tuân thủ điều trị' },
    { key: 'lab_results', label: 'Kết quả xét nghiệm' },
    { key: 'medical_documents', label: 'Tài liệu y tế' },
    { key: 'patient_profile', label: 'Thông tin hồ sơ liên quan' },
  ],
}


const client = {} as ApiClient

const CATEGORIES = [
  'health_records',
  'medications_and_adherence',
  'lab_results',
  'medical_documents',
  'patient_profile',
]

function consent(overrides: Record<string, unknown> = {}) {
  return {
    id: 'cons-1',
    consultation_id: 'c-1',
    doctor_id: 'doc-1',
    purpose: 'doctor_consultation',
    consent_version: '1.0',
    policy_version: '1.1',
    categories: CATEGORIES,
    granted_at: '2026-08-01T02:00:00Z',
    revoked_at: null,
    is_active: true,
    source: 'mobile',
    ...overrides,
  }
}

let q: Awaited<ReturnType<typeof render>>

async function renderCard() {
  const utils = await render(
    <ConsultationSharingCard
      client={client}
      consultationId="c-1abc2def"
      consultationStatus="IN_PROGRESS"
      doctorName="BS Nguyễn Văn A"
      consultationDate="2026-08-01T02:00:00Z"
    />
  )
  q = utils
  return utils
}

beforeEach(() => {
  // resetAllMocks, not clearAllMocks: clear leaves both implementations and
  // any unconsumed mock*ValueOnce queue in place, so one test's leftovers
  // become the next test's first response.
  jest.resetAllMocks()
  mockedGet.mockResolvedValue(consent())
  mockedPolicy.mockResolvedValue(POLICY)
  mockedRevoke.mockResolvedValue({ message: 'revoked' })
  mockedRestore.mockResolvedValue(consent())
})

afterEach(() => {
  // Unmount explicitly. Left mounted, a card whose in-flight request resolves
  // after its test ends keeps updating React during the NEXT test.
  q?.unmount()
})

// ---------------------------------------------------------------------------
// Initial state
// ---------------------------------------------------------------------------

it('shows the active state with doctor, reference and every shared category', async () => {
  await renderCard()

  expect(await q.findByTestId('sharing-status')).toHaveTextContent('Đang chia sẻ')
  expect(q.getByText('Chia sẻ dữ liệu với bác sĩ')).toBeTruthy()
  expect(q.getByText(/BS Nguyễn Văn A/)).toBeTruthy()
  expect(q.getByText(/C-1ABC2D/)).toBeTruthy()

  for (const label of [
    'Hồ sơ sức khỏe',
    'Thuốc và tuân thủ điều trị',
    'Kết quả xét nghiệm',
    'Tài liệu y tế',
    'Thông tin hồ sơ liên quan',
  ]) {
    expect(q.getByText(label)).toBeTruthy()
  }
})

it('renders nothing for a consultation booked before the feature', async () => {
  mockedGet.mockRejectedValue(new ApiError(404, 'not found', 'not found'))

  await renderCard()

  expect(q.queryByTestId('sharing-card')).toBeNull()
  expect(q.queryByTestId('sharing-status')).toBeNull()
})

it('shows the revoked state with a re-share action', async () => {
  mockedGet.mockResolvedValue(consent({ is_active: false, revoked_at: '2026-08-02T00:00:00Z' }))

  await renderCard()

  expect(await q.findByTestId('sharing-status')).toHaveTextContent('Đã thu hồi')
  expect(q.getByTestId('sharing-reshare')).toBeTruthy()
  expect(q.queryByTestId('sharing-revoke')).toBeNull()
})

// ---------------------------------------------------------------------------
// Revoke
// ---------------------------------------------------------------------------

it('revoking requires confirmation — the button alone does not revoke', async () => {
  await renderCard()
  await q.findByTestId('sharing-status')

  fireEvent.press(q.getByTestId('sharing-revoke'))

  expect(await q.findByText('Thu hồi quyền chia sẻ?')).toBeTruthy()
  expect(mockedRevoke).not.toHaveBeenCalled()
})

it('the confirmation states what survives', async () => {
  await renderCard()
  await q.findByTestId('sharing-status')
  fireEvent.press(q.getByTestId('sharing-revoke'))

  expect(await q.findByText(/vẫn được giữ lại/)).toBeTruthy()
})

it('"Giữ quyền chia sẻ" cancels without revoking', async () => {
  await renderCard()
  await q.findByTestId('sharing-status')
  fireEvent.press(q.getByTestId('sharing-revoke'))
  fireEvent.press(await q.findByTestId('revoke-cancel'))

  expect(mockedRevoke).not.toHaveBeenCalled()
  expect(q.getByTestId('sharing-status')).toHaveTextContent('Đang chia sẻ')
})

it('confirming revokes and flips the card to revoked', async () => {
  await renderCard()
  await q.findByTestId('sharing-status')
  fireEvent.press(q.getByTestId('sharing-revoke'))

  mockedGet.mockResolvedValueOnce(consent({ is_active: false }))
  fireEvent.press(await q.findByTestId('revoke-confirm'))

  expect(await q.findByTestId('sharing-reshare')).toBeTruthy()
  expect(mockedRevoke).toHaveBeenCalledWith(client, 'c-1abc2def')
  // The status line announces the outcome so a screen reader hears it.
  expect(q.getByTestId('sharing-status')).toHaveTextContent('Đã thu hồi quyền chia sẻ.')
})

it('double-confirming revokes exactly once', async () => {
  let resolveRevoke: (v: unknown) => void = () => {}
  mockedRevoke.mockImplementation(
    () =>
      new Promise((res) => {
        resolveRevoke = res
      })
  )

  await renderCard()
  await q.findByTestId('sharing-status')
  fireEvent.press(q.getByTestId('sharing-revoke'))

  const confirm = await q.findByTestId('revoke-confirm')
  fireEvent.press(confirm)
  fireEvent.press(confirm)
  fireEvent.press(confirm)

  expect(mockedRevoke).toHaveBeenCalledTimes(1)
  resolveRevoke({ message: 'revoked' })
  // Wait for something that is only true AFTER the whole chain settles —
  // the dialog closing. Asserting the call count again would pass instantly
  // without flushing, leaving React to update during the NEXT test.
  await waitFor(() => expect(q.queryByTestId('revoke-confirm')).toBeNull())
})
