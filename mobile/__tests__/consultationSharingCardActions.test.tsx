/**
 * Part 2 of the sharing-card suite.
 *
 * Split from consultationSharingCard.test.tsx purely for test-environment
 * reasons: past roughly eight mount/unmount cycles in one file, this project's
 * React 19 + RNTL setup stops flushing the initial fetch and every later test
 * times out waiting for a card that never leaves its loading state. Each test
 * passes individually; separate files get separate module registries, which
 * avoids the accumulation. No product behaviour differs between the two files.
 */
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

it('a failed revoke keeps the sharing active and announces the error', async () => {
  mockedRevoke.mockRejectedValueOnce(new Error('boom'))

  await renderCard()
  await q.findByTestId('sharing-status')
  fireEvent.press(q.getByTestId('sharing-revoke'))
  fireEvent.press(await q.findByTestId('revoke-confirm'))

  const error = await q.findByTestId('revoke-error')
  expect(error.props.accessibilityLiveRegion).toBe('assertive')
  expect(q.getByTestId('sharing-status')).toHaveTextContent('Đang chia sẻ')
})

// ---------------------------------------------------------------------------
// Re-share
// ---------------------------------------------------------------------------

it('re-sharing shows the consent terms — never a silent one-tap re-grant', async () => {
  mockedGet.mockResolvedValue(consent({ is_active: false }))

  await renderCard()
  fireEvent.press(await q.findByTestId('sharing-reshare'))

  // The same terms as booking, not a bare confirm.
  expect(await q.findByText('Đoạn một.')).toBeTruthy()
  expect(mockedRestore).not.toHaveBeenCalled()
})

it('re-sharing sends the rendered versions so the record matches what was shown', async () => {
  mockedGet.mockResolvedValue(consent({ is_active: false }))

  await renderCard()
  fireEvent.press(await q.findByTestId('sharing-reshare'))
  await q.findByText('Đoạn một.')

  mockedGet.mockResolvedValueOnce(consent({ is_active: true }))
  fireEvent.press(q.getByTestId('consent-accept'))

  expect(await q.findByTestId('sharing-revoke')).toBeTruthy()
  expect(mockedRestore).toHaveBeenCalledWith(client, 'c-1abc2def', {
    accepted: true,
    categories: CATEGORIES,
    consent_version: '1.0',
    policy_version: '1.1',
  })
})

it('declining the re-share dialog re-grants nothing', async () => {
  mockedGet.mockResolvedValue(consent({ is_active: false }))

  await renderCard()
  fireEvent.press(await q.findByTestId('sharing-reshare'))
  fireEvent.press(await q.findByTestId('consent-decline'))

  expect(mockedRestore).not.toHaveBeenCalled()
  expect(q.getByTestId('sharing-status')).toHaveTextContent('Đã thu hồi')
})

it('an ended consultation never claims to be sharing, and offers no re-share', async () => {
  const utils = await render(
    <ConsultationSharingCard
      client={client}
      consultationId="c-1abc2def"
      consultationStatus="COMPLETED"
      doctorName="BS Nguyễn Văn A"
    />
  )
  q = utils

  expect(await q.findByTestId('session-ended')).toBeTruthy()
  expect(q.queryByTestId('sharing-reshare')).toBeNull()
  expect(q.queryByTestId('sharing-revoke')).toBeNull()
})

it('a revoke that lands but cannot be re-read drops to retry, not a stale status', async () => {
  await renderCard()
  await q.findByTestId('sharing-status')
  fireEvent.press(q.getByTestId('sharing-revoke'))

  mockedGet.mockRejectedValueOnce(new Error('gateway'))
  fireEvent.press(await q.findByTestId('revoke-confirm'))

  // The revoke DID land, so showing "Đang chia sẻ" would be a lie.
  expect(await q.findByTestId('sharing-retry')).toBeTruthy()
  expect(q.queryByTestId('sharing-status')).toBeNull()
})

// ---------------------------------------------------------------------------
// Loading / error / retry
// ---------------------------------------------------------------------------

it('a failed load offers a retry rather than a dead card', async () => {
  mockedGet.mockRejectedValueOnce(new Error('offline'))

  await renderCard()

  const retry = await q.findByTestId('sharing-retry')
  mockedGet.mockResolvedValueOnce(consent())
  fireEvent.press(retry)

  expect(await q.findByTestId('sharing-status')).toHaveTextContent('Đang chia sẻ')
})

// ---------------------------------------------------------------------------
// Accessibility
// ---------------------------------------------------------------------------

it('the section and confirmation expose headers and real buttons', async () => {
  await renderCard()
  await q.findByTestId('sharing-status')

  expect(q.getByText('Chia sẻ dữ liệu với bác sĩ').props.accessibilityRole).toBe('header')
  expect(q.getByTestId('sharing-revoke').props.accessibilityRole).toBe('button')

  fireEvent.press(q.getByTestId('sharing-revoke'))
  expect((await q.findByText('Thu hồi quyền chia sẻ?')).props.accessibilityRole).toBe('header')
  expect(q.getByTestId('revoke-confirm').props.accessibilityRole).toBe('button')
  expect(q.getByTestId('revoke-cancel').props.accessibilityRole).toBe('button')
})

// ---------------------------------------------------------------------------
// Held-promise tests LAST
// ---------------------------------------------------------------------------
//
// A test that leaves a request unresolved stops this environment flushing
// promises for every test after it, so those tests sit in the card's loading
// state until they time out. Keeping them at the end of the file makes the
// ordering constraint explicit instead of mysterious.
//

it('double-pressing accept in the re-share dialog restores exactly once', async () => {
  mockedGet.mockResolvedValue(consent({ is_active: false }))
  let resolveRestore: (v: unknown) => void = () => {}
  mockedRestore.mockImplementation(
    () =>
      new Promise((res) => {
        resolveRestore = res
      })
  )

  await renderCard()
  fireEvent.press(await q.findByTestId('sharing-reshare'))
  const accept = await q.findByTestId('consent-accept')

  // The refetch that follows a successful restore returns the ACTIVE consent.
  mockedGet.mockResolvedValueOnce(consent({ is_active: true }))
  fireEvent.press(accept)
  fireEvent.press(accept)

  expect(mockedRestore).toHaveBeenCalledTimes(1)
  resolveRestore(consent())
  await waitFor(() => expect(q.queryByTestId('sharing-revoke')).not.toBeNull())
})
