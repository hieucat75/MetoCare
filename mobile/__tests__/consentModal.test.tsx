import React from 'react'
import { fireEvent, render } from '@testing-library/react-native'

jest.mock('../src/api/consultations', () => ({
  getDataSharingPolicy: jest.fn(),
}))

import type { ApiClient } from '../src/api/client'
import { getDataSharingPolicy } from '../src/api/consultations'
import { DataSharingConsentModal } from '../src/components/DataSharingConsentModal'

const mockPolicy = getDataSharingPolicy as jest.Mock
const client = {} as ApiClient

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

/**
 * Queries for the most recently rendered modal. This project's RNTL setup does
 * not expose the `screen` global, so the render result is bound here and every
 * test reads through `q`.
 */
let q: Awaited<ReturnType<typeof render>>

async function renderModal(
  overrides: Partial<React.ComponentProps<typeof DataSharingConsentModal>> = {}
) {
  const onAccept = jest.fn()
  const onDecline = jest.fn()
  const utils = await render(
    <DataSharingConsentModal
      visible
      client={client}
      submitting={false}
      errorMsg={null}
      onAccept={onAccept}
      onDecline={onDecline}
      {...overrides}
    />
  )
  q = utils
  return { ...utils, onAccept, onDecline }
}

beforeEach(() => {
  jest.clearAllMocks()
  mockPolicy.mockResolvedValue(POLICY)
})

it('renders the server copy verbatim, paragraph by paragraph', async () => {
  await renderModal()

  for (const paragraph of POLICY.body.split('\n\n')) {
    expect(await q.findByText(paragraph)).toBeTruthy()
  }
  expect(q.getByTestId('consent-title')).toHaveTextContent(POLICY.title)
})

it('names every category being shared', async () => {
  await renderModal()

  for (const category of POLICY.categories) {
    expect(await q.findByText(category.label)).toBeTruthy()
  }
})

it('grants nothing until accept is pressed', async () => {
  const { onAccept } = await renderModal()
  await q.findByText(POLICY.title)

  expect(onAccept).not.toHaveBeenCalled()
})

it('accept emits exactly the rendered categories and versions', async () => {
  const { onAccept } = await renderModal()
  await q.findByText(POLICY.title)

  fireEvent.press(q.getByTestId('consent-accept'))

  expect(onAccept).toHaveBeenCalledWith({
    categories: [
      'health_records',
      'medications_and_adherence',
      'lab_results',
      'medical_documents',
      'patient_profile',
    ],
    consentVersion: '1.0',
    policyVersion: '1.0',
  })
})

it('declining never grants', async () => {
  const { onAccept, onDecline } = await renderModal()
  await q.findByText(POLICY.title)

  fireEvent.press(q.getByTestId('consent-decline'))

  expect(onDecline).toHaveBeenCalledTimes(1)
  expect(onAccept).not.toHaveBeenCalled()
})

it('there is no pre-ticked checkbox to leave alone', async () => {
  await renderModal()
  await q.findByText(POLICY.title)

  expect(q.queryAllByRole('checkbox')).toHaveLength(0)
})

it('accept is disabled until the copy has loaded', async () => {
  let resolvePolicy: (v: unknown) => void = () => {}
  mockPolicy.mockImplementation(
    () =>
      new Promise((res) => {
        resolvePolicy = res
      })
  )

  const { onAccept } = await renderModal()

  const accept = q.getByTestId('consent-accept')
  expect(accept.props.accessibilityState?.disabled).toBe(true)
  fireEvent.press(accept)
  expect(onAccept).not.toHaveBeenCalled()

  resolvePolicy(POLICY)
  await q.findByText(POLICY.title)
})

it('a failed policy load offers a retry and blocks consent meanwhile', async () => {
  mockPolicy.mockRejectedValueOnce(new Error('offline'))
  const { onAccept } = await renderModal()

  const retry = await q.findByTestId('consent-retry')
  fireEvent.press(q.getByTestId('consent-accept'))
  expect(onAccept).not.toHaveBeenCalled()

  mockPolicy.mockResolvedValueOnce(POLICY)
  fireEvent.press(retry)

  await q.findByText(POLICY.title)
  fireEvent.press(q.getByTestId('consent-accept'))
  expect(onAccept).toHaveBeenCalledTimes(1)
})

it('a submit in flight cannot be re-pressed or dismissed by the back button', async () => {
  const { onAccept, onDecline } = await renderModal({ submitting: true })
  await q.findByText(POLICY.title)

  fireEvent.press(q.getByTestId('consent-accept'))
  fireEvent.press(q.getByTestId('consent-accept'))
  expect(onAccept).not.toHaveBeenCalled()

  // Android hardware back while submitting: ignored, because the booking may
  // already exist server-side.
  fireEvent(q.getByTestId('consent-modal'), 'requestClose')
  expect(onDecline).not.toHaveBeenCalled()
})

it('the back button declines when nothing is in flight', async () => {
  const { onAccept, onDecline } = await renderModal()
  await q.findByText(POLICY.title)

  fireEvent(q.getByTestId('consent-modal'), 'requestClose')

  expect(onDecline).toHaveBeenCalledTimes(1)
  expect(onAccept).not.toHaveBeenCalled()
})

it('a booking failure is shown inside the dialog', async () => {
  await renderModal({ errorMsg: 'Không thể đặt lịch. Vui lòng thử lại.' })
  await q.findByText(POLICY.title)

  expect(q.getByTestId('consent-error')).toHaveTextContent(
    'Không thể đặt lịch. Vui lòng thử lại.'
  )
})

it('both decisions are exposed as pressable buttons to assistive tech', async () => {
  await renderModal()
  await q.findByText(POLICY.title)

  const accept = q.getByTestId('consent-accept')
  const decline = q.getByTestId('consent-decline')
  expect(accept.props.accessibilityRole).toBe('button')
  expect(decline.props.accessibilityRole).toBe('button')
  expect(accept.props.accessibilityState?.disabled).toBe(false)
  expect(decline.props.accessibilityState?.disabled).toBe(false)
})
