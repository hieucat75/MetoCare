/**
 * Part 3 of the sharing-card suite — the legacy / never-granted state.
 *
 * Split for the same test-environment reason documented in part 2: past roughly
 * eight mount/unmount cycles in one file, this project's React 19 + RNTL setup
 * stops flushing the initial fetch and later tests time out on a card stuck in
 * its loading state. Separate files get separate module registries.
 *
 * What these cover is a product distinction, not a variant of the others: a
 * consultation booked before consent was recorded has NO consent row. Nothing
 * was granted, so nothing was withdrawn, and the card must never say "đã thu
 * hồi" — it must say "Chưa chia sẻ", explain why, and offer a first grant while
 * the lifecycle still permits one.
 */
import React from 'react'
import { fireEvent, render, waitFor } from '@testing-library/react-native'

jest.mock('../src/api/consultations', () => ({
  getDataSharingState: jest.fn(),
  getDataSharingPolicy: jest.fn(),
  revokeDataSharingConsent: jest.fn(),
  grantDataSharingConsent: jest.fn(),
}))

import { ApiError } from '../src/api/client'
import type { ApiClient } from '../src/api/client'
import {
  getDataSharingPolicy,
  getDataSharingState,
  grantDataSharingConsent,
  revokeDataSharingConsent,
} from '../src/api/consultations'
import { ConsultationSharingCard } from '../src/components/ConsultationSharingCard'

const mockedGet = getDataSharingState as jest.Mock
const mockedRevoke = revokeDataSharingConsent as jest.Mock
const mockedRestore = grantDataSharingConsent as jest.Mock
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

/** The explicit state envelope the endpoint now answers with. */
function sharing(overrides: Record<string, unknown> = {}) {
  return {
    consultation_id: 'c-1',
    state: 'ACTIVE',
    consultation_status: 'IN_PROGRESS',
    can_share: true,
    consent: consent(),
    ...overrides,
  }
}

/** REVOKED: a grant existed and the patient withdrew it. */
function revoked(consentOverrides: Record<string, unknown> = {}) {
  return sharing({
    state: 'REVOKED',
    consent: consent({ is_active: false, revoked_at: '2026-08-02T00:00:00Z', ...consentOverrides }),
  })
}

/** NEVER_GRANTED: booked before consent was recorded — no row has ever existed. */
function neverGranted(overrides: Record<string, unknown> = {}) {
  return sharing({ state: 'NEVER_GRANTED', consent: null, ...overrides })
}

let q: Awaited<ReturnType<typeof render>>

async function renderCard() {
  const utils = await render(
    <ConsultationSharingCard
      client={client}
      consultationId="c-1abc2def"
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
  mockedGet.mockResolvedValue(sharing())
  mockedPolicy.mockResolvedValue(POLICY)
  mockedRevoke.mockResolvedValue({ message: 'revoked' })
  mockedRestore.mockResolvedValue(sharing())
})

afterEach(() => {
  // Unmount explicitly. Left mounted, a card whose in-flight request resolves
  // after its test ends keeps updating React during the NEXT test.
  q?.unmount()
})

it('an eligible legacy consultation offers "Chia sẻ dữ liệu", not "Chia sẻ lại"', async () => {
  mockedGet.mockResolvedValue(neverGranted())

  await renderCard()

  expect(await q.findByTestId('sharing-share')).toBeTruthy()
  expect(q.getByText('Chia sẻ dữ liệu')).toBeTruthy()
  // "Chia sẻ lại" would imply a previous grant that never existed.
  expect(q.queryByTestId('sharing-reshare')).toBeNull()
  expect(q.queryByTestId('sharing-revoke')).toBeNull()
})

it('an ineligible legacy consultation states the status but offers no action', async () => {
  mockedGet.mockResolvedValue(neverGranted({ consultation_status: 'COMPLETED', can_share: false }))

  await renderCard()

  expect(await q.findByTestId('session-ended')).toBeTruthy()
  expect(q.queryByTestId('sharing-share')).toBeNull()
  expect(q.queryByTestId('sharing-reshare')).toBeNull()
})

it('the first grant goes through the full consent dialog, never one tap', async () => {
  mockedGet.mockResolvedValue(neverGranted())

  await renderCard()
  fireEvent.press(await q.findByTestId('sharing-share'))

  // The server's current copy, verbatim — the same terms as booking.
  expect(await q.findByTestId('consent-title')).toBeTruthy()
  expect(q.getByText('Đoạn một.')).toBeTruthy()
  expect(mockedRestore).not.toHaveBeenCalled()
})

it('the first grant sends the rendered versions and every disclosed category', async () => {
  mockedGet.mockResolvedValue(neverGranted())

  await renderCard()
  fireEvent.press(await q.findByTestId('sharing-share'))
  mockedGet.mockResolvedValueOnce(sharing())
  fireEvent.press(await q.findByTestId('consent-accept'))

  await waitFor(() => expect(mockedRestore).toHaveBeenCalledTimes(1))
  expect(mockedRestore).toHaveBeenCalledWith(client, 'c-1abc2def', {
    accepted: true,
    categories: CATEGORIES,
    consent_version: '1.0',
    policy_version: '1.1',
    source: 'mobile',
  })
})

it('declining the first-grant dialog grants nothing', async () => {
  mockedGet.mockResolvedValue(neverGranted())

  await renderCard()
  fireEvent.press(await q.findByTestId('sharing-share'))
  fireEvent.press(await q.findByTestId('consent-decline'))

  expect(mockedRestore).not.toHaveBeenCalled()
  expect(await q.findByTestId('sharing-status')).toHaveTextContent('Chưa chia sẻ')
})

it('the Android hardware back button dismisses the first-grant dialog without granting', async () => {
  mockedGet.mockResolvedValue(neverGranted())

  await renderCard()
  fireEvent.press(await q.findByTestId('sharing-share'))

  const modal = await q.findByTestId('consent-modal')
  modal.props.onRequestClose()

  await waitFor(() => expect(q.queryByTestId('consent-title')).toBeNull())
  expect(mockedRestore).not.toHaveBeenCalled()
  expect(q.getByTestId('sharing-status')).toHaveTextContent('Chưa chia sẻ')
})

it('a needs-reconsent state is not reported as a withdrawal', async () => {
  // We moved the terms; the patient did nothing. "Đã thu hồi" would blame them
  // for our version bump.
  mockedGet.mockResolvedValue(sharing({ state: 'NEEDS_RECONSENT' }))

  await renderCard()

  expect(await q.findByTestId('sharing-status')).toHaveTextContent('Cần xác nhận lại quyền chia sẻ')
  expect(q.queryByText('Đã thu hồi')).toBeNull()
})

it('an unavailable state is an error, never a statement about the patient', async () => {
  mockedGet.mockRejectedValue(new Error('network down'))

  await renderCard()

  expect(await q.findByTestId('sharing-retry')).toBeTruthy()
  expect(q.queryByTestId('sharing-status')).toBeNull()
})

it('the legacy card is announced and labelled for assistive tech', async () => {
  mockedGet.mockResolvedValue(neverGranted())

  await renderCard()

  expect(q.getByText('Chia sẻ dữ liệu với bác sĩ').props.accessibilityRole).toBe('header')
  // The status line is a live region, so the state change is announced.
  expect((await q.findByTestId('sharing-status')).props.accessibilityLiveRegion).toBe('polite')
  expect(q.getByTestId('sharing-share').props.accessibilityRole).toBe('button')
})

it('the legacy explainer is plain text, so it reflows at large font sizes', async () => {
  mockedGet.mockResolvedValue(neverGranted())

  await renderCard()

  const explainer = await q.findByTestId('never-granted-explainer')
  // No numberOfLines cap: at 200% system font the sentence must wrap, not clip.
  expect(explainer.props.numberOfLines).toBeUndefined()
})
