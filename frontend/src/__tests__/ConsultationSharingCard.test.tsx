import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ConsultationSharingCard } from '@/components/marketplace/ConsultationSharingCard'
import {
  getDataSharingState,
  getDataSharingPolicy,
  revokeDataSharingConsent,
  grantDataSharingConsent,
} from '@/lib/api/consultations'
import { ApiError } from '@/lib/api/client'

jest.mock('@/lib/api/consultations', () => ({
  getDataSharingState: jest.fn(),
  getDataSharingPolicy: jest.fn(),
  revokeDataSharingConsent: jest.fn(),
  grantDataSharingConsent: jest.fn(),
}))

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

const CATEGORIES = [
  'health_records',
  'medications_and_adherence',
  'lab_results',
  'medical_documents',
  'patient_profile',
]

function consent(overrides = {}) {
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
    source: 'web',
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
function revoked(consentOverrides = {}) {
  return sharing({
    state: 'REVOKED',
    consent: consent({ is_active: false, revoked_at: '2026-08-02T00:00:00Z', ...consentOverrides }),
  })
}

/** NEVER_GRANTED: booked before consent was recorded — no row has ever existed. */
function neverGranted(overrides: Record<string, unknown> = {}) {
  return sharing({ state: 'NEVER_GRANTED', consent: null, ...overrides })
}

function renderCard() {
  return render(
    <ConsultationSharingCard
      consultationId="c-1abc2def"
      doctorName="BS Nguyễn Văn A"
      consultationDate="2026-08-01T02:00:00Z"
    />
  )
}

/** Re-sharing goes through the consent dialog; accept its terms. */
async function acceptReshare() {
  await userEvent.click(await screen.findByTestId('reshare-button'))
  await userEvent.click(await screen.findByRole('button', { name: POLICY.accept_label }))
}

beforeEach(() => {
  jest.clearAllMocks()
  mockedGet.mockResolvedValue(sharing())
  mockedPolicy.mockResolvedValue(POLICY)
  mockedRevoke.mockResolvedValue({ message: 'revoked' })
  mockedRestore.mockResolvedValue(sharing())
})

// ---------------------------------------------------------------------------
// Initial state
// ---------------------------------------------------------------------------

test('shows the active sharing state with doctor, reference, date and categories', async () => {
  renderCard()

  expect(await screen.findByTestId('sharing-status')).toHaveTextContent('Đang chia sẻ')
  expect(screen.getByText('Chia sẻ dữ liệu với bác sĩ')).toBeInTheDocument()
  expect(screen.getByText('BS Nguyễn Văn A')).toBeInTheDocument()
  expect(screen.getByText('C-1ABC2D')).toBeInTheDocument()

  for (const label of [
    'Hồ sơ sức khỏe',
    'Thuốc và tuân thủ điều trị',
    'Kết quả xét nghiệm',
    'Tài liệu y tế',
    'Thông tin hồ sơ liên quan',
  ]) {
    expect(screen.getByText(label)).toBeInTheDocument()
  }
})

test('a consultation booked before the feature says "Chưa chia sẻ" and explains why', async () => {
  // It used to render nothing here, which left the patient with no statement of
  // whether their doctor could see anything, on the screen that exists to say so.
  mockedGet.mockResolvedValue(neverGranted())

  renderCard()

  expect(await screen.findByTestId('sharing-status')).toHaveTextContent('Chưa chia sẻ')
  expect(screen.getByText('Chia sẻ dữ liệu với bác sĩ')).toBeInTheDocument()
  expect(screen.getByTestId('never-granted-explainer')).toHaveTextContent(
    /được tạo trước khi MetoCare ghi nhận quyền chia sẻ dữ liệu/
  )
  // Never the withdrawal wording — nothing was ever granted.
  expect(screen.queryByText(/đã thu hồi/i)).not.toBeInTheDocument()
})

test('shows the revoked state with a re-share action', async () => {
  mockedGet.mockResolvedValue(revoked())

  renderCard()

  expect(await screen.findByTestId('sharing-status')).toHaveTextContent('Đã thu hồi')
  expect(screen.getByTestId('reshare-button')).toHaveTextContent('Chia sẻ lại')
  expect(screen.queryByTestId('revoke-button')).not.toBeInTheDocument()
})

// ---------------------------------------------------------------------------
// Revoke
// ---------------------------------------------------------------------------

test('revoking requires confirmation — the button alone does not revoke', async () => {
  renderCard()

  await userEvent.click(await screen.findByTestId('revoke-button'))

  expect(await screen.findByRole('dialog')).toBeInTheDocument()
  expect(screen.getByText('Thu hồi quyền chia sẻ?')).toBeInTheDocument()
  expect(mockedRevoke).not.toHaveBeenCalled()
})

test('the confirmation says what survives, so withdrawing is not mistaken for deletion', async () => {
  renderCard()
  await userEvent.click(await screen.findByTestId('revoke-button'))

  const dialog = await screen.findByRole('dialog')
  // Names the doctor who loses access, so it is not an abstract decision.
  expect(dialog).toHaveTextContent(/BS Nguyễn Văn A sẽ không thể tiếp tục xem/i)
  // And the three consequences a patient could otherwise get wrong.
  expect(dialog).toHaveTextContent(/danh sách thuốc và kết quả xét nghiệm/i)
  expect(dialog).toHaveTextContent(/vẫn tiếp tục và không được hoàn tiền/i)
  expect(dialog).toHaveTextContent(/vẫn được giữ lại/i)
  expect(dialog).toHaveTextContent(/chia sẻ lại bất cứ lúc nào/i)
})

test('"Giữ quyền chia sẻ" cancels without revoking', async () => {
  renderCard()
  await userEvent.click(await screen.findByTestId('revoke-button'))
  await userEvent.click(await screen.findByTestId('revoke-cancel'))

  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  expect(mockedRevoke).not.toHaveBeenCalled()
  expect(screen.getByTestId('sharing-status')).toHaveTextContent('Đang chia sẻ')
})

test('confirming revokes and the card flips to the revoked state', async () => {
  renderCard()
  await userEvent.click(await screen.findByTestId('revoke-button'))

  mockedGet.mockResolvedValueOnce(revoked())
  await userEvent.click(await screen.findByTestId('revoke-confirm'))

  await waitFor(() => expect(mockedRevoke).toHaveBeenCalledWith('c-1abc2def'))
  expect(await screen.findByTestId('sharing-status')).toHaveTextContent('Đã thu hồi')
  expect(screen.getByTestId('reshare-button')).toBeInTheDocument()
})

test('double-confirming revokes exactly once', async () => {
  let resolveRevoke: (v: unknown) => void = () => {}
  mockedRevoke.mockImplementation(
    () =>
      new Promise((resolve) => {
        resolveRevoke = resolve
      })
  )

  renderCard()
  await userEvent.click(await screen.findByTestId('revoke-button'))
  const confirm = await screen.findByTestId('revoke-confirm')

  fireEvent.click(confirm)
  fireEvent.click(confirm)
  fireEvent.click(confirm)

  expect(mockedRevoke).toHaveBeenCalledTimes(1)
  resolveRevoke({ message: 'revoked' })
  await waitFor(() => expect(mockedRevoke).toHaveBeenCalledTimes(1))
})

test('a revoke in flight cannot be dismissed by Escape', async () => {
  mockedRevoke.mockImplementation(() => new Promise(() => {}))

  renderCard()
  await userEvent.click(await screen.findByTestId('revoke-button'))
  fireEvent.click(await screen.findByTestId('revoke-confirm'))

  await screen.findByText('Đang xử lý…')
  fireEvent.keyDown(document.activeElement || document.body, { key: 'Escape', code: 'Escape' })

  expect(screen.getByRole('dialog')).toBeInTheDocument()
})

test('a failed revoke is reported inside the dialog and can be retried', async () => {
  mockedRevoke.mockRejectedValueOnce(new ApiError(500, 'Máy chủ bận'))

  renderCard()
  await userEvent.click(await screen.findByTestId('revoke-button'))
  await userEvent.click(await screen.findByTestId('revoke-confirm'))

  expect(await screen.findByRole('alert')).toHaveTextContent('Máy chủ bận')
  // Still sharing — a failed revoke must not look like it worked.
  expect(screen.getByTestId('sharing-status')).toHaveTextContent('Đang chia sẻ')

  mockedRevoke.mockResolvedValueOnce({ message: 'revoked' })
  mockedGet.mockResolvedValueOnce(consent({ is_active: false }))
  await userEvent.click(screen.getByTestId('revoke-confirm'))
  await waitFor(() => expect(mockedRevoke).toHaveBeenCalledTimes(2))
})

// ---------------------------------------------------------------------------
// Re-share
// ---------------------------------------------------------------------------

test('re-sharing shows the consent terms — it is never a silent one-tap re-grant', async () => {
  mockedGet.mockResolvedValue(revoked())

  renderCard()
  await userEvent.click(await screen.findByTestId('reshare-button'))

  // The same terms as booking, not a bare confirm.
  expect(await screen.findByText('Đoạn một.')).toBeInTheDocument()
  expect(screen.getByText('Đoạn hai.')).toBeInTheDocument()
  expect(mockedRestore).not.toHaveBeenCalled()
})

test('re-sharing sends the rendered versions, so the record matches what was shown', async () => {
  mockedGet.mockResolvedValue(revoked())

  renderCard()
  mockedGet.mockResolvedValueOnce(sharing())
  await acceptReshare()

  await waitFor(() => expect(mockedRestore).toHaveBeenCalledTimes(1))
  expect(mockedRestore).toHaveBeenCalledWith('c-1abc2def', {
    accepted: true,
    categories: CATEGORIES,
    consent_version: '1.0',
    policy_version: '1.1',
    source: 'web',
  })
  expect(await screen.findByTestId('sharing-status')).toHaveTextContent(
    /Đã chia sẻ lại|Đang chia sẻ/
  )
})

test('re-sharing a narrower grant offers only what was originally granted', async () => {
  mockedGet.mockResolvedValue(revoked({ categories: ['medications_and_adherence'] }))

  renderCard()
  await userEvent.click(await screen.findByTestId('reshare-button'))
  await screen.findByText('Đoạn một.')

  const dialog = screen.getByRole('dialog')
  expect(dialog).toHaveTextContent('Thuốc và tuân thủ điều trị')
  // Offering the full five would be a wider grant than the patient ever made.
  expect(dialog).not.toHaveTextContent('Kết quả xét nghiệm')

  mockedGet.mockResolvedValueOnce(sharing())
  await userEvent.click(screen.getByRole('button', { name: POLICY.accept_label }))

  await waitFor(() =>
    expect(mockedRestore).toHaveBeenCalledWith(
      'c-1abc2def',
      expect.objectContaining({ categories: ['medications_and_adherence'] })
    )
  )
})

test('declining the re-share dialog re-grants nothing', async () => {
  mockedGet.mockResolvedValue(revoked())

  renderCard()
  await userEvent.click(await screen.findByTestId('reshare-button'))
  await userEvent.click(await screen.findByRole('button', { name: POLICY.decline_label }))

  expect(mockedRestore).not.toHaveBeenCalled()
  expect(screen.getByTestId('sharing-status')).toHaveTextContent('Đã thu hồi')
})

test('a failed re-share leaves the state revoked and says so', async () => {
  mockedGet.mockResolvedValue(revoked())
  mockedRestore.mockRejectedValueOnce(new ApiError(500, 'Máy chủ bận'))

  renderCard()
  await acceptReshare()

  expect(await screen.findByRole('alert')).toHaveTextContent('Máy chủ bận')
  expect(screen.getByTestId('sharing-status')).toHaveTextContent('Đã thu hồi')
})

// ---------------------------------------------------------------------------
// A finished consultation
// ---------------------------------------------------------------------------

test('an ended consultation never claims to be sharing, and offers no re-share', async () => {
  mockedGet.mockResolvedValue(
    sharing({ state: 'REVOKED', consultation_status: 'COMPLETED', can_share: false })
  )

  renderCard()

  expect(await screen.findByTestId('sharing-status')).toHaveTextContent(/đã xong/i)
  expect(screen.getByTestId('session-ended')).toBeInTheDocument()
  // Re-sharing here would reopen nothing — the access grant is already closed.
  expect(screen.queryByTestId('reshare-button')).not.toBeInTheDocument()
  expect(screen.queryByTestId('revoke-button')).not.toBeInTheDocument()
})

// ---------------------------------------------------------------------------
// Never assert a status we could not re-read
// ---------------------------------------------------------------------------

test('a revoke that lands but cannot be re-read drops to retry, not a stale status', async () => {
  renderCard()
  await userEvent.click(await screen.findByTestId('revoke-button'))

  mockedGet.mockRejectedValueOnce(new ApiError(502, 'gateway'))
  await userEvent.click(await screen.findByTestId('revoke-confirm'))

  // The revoke DID land, so "Đang chia sẻ" would be a lie; so would claiming
  // the action failed.
  expect(await screen.findByRole('alert')).toHaveTextContent(/Không tải lại được/)
  expect(screen.queryByTestId('sharing-status')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Thử lại' })).toBeInTheDocument()
})

// ---------------------------------------------------------------------------
// Loading, error, retry
// ---------------------------------------------------------------------------

test('a failed load offers a retry rather than a dead card', async () => {
  mockedGet.mockRejectedValueOnce(new ApiError(500, 'boom'))

  renderCard()

  expect(await screen.findByRole('alert')).toHaveTextContent(/Không tải được/)

  mockedGet.mockResolvedValueOnce(sharing())
  await userEvent.click(screen.getByRole('button', { name: 'Thử lại' }))

  expect(await screen.findByTestId('sharing-status')).toHaveTextContent('Đang chia sẻ')
})

// ---------------------------------------------------------------------------
// Accessibility
// ---------------------------------------------------------------------------

test('the confirmation is a labelled, described modal with both choices as buttons', async () => {
  renderCard()
  await userEvent.click(await screen.findByTestId('revoke-button'))

  const dialog = await screen.findByRole('dialog')
  expect(dialog).toHaveAttribute('aria-modal', 'true')

  const labelledBy = dialog.getAttribute('aria-labelledby') as string
  expect(document.getElementById(labelledBy)).toHaveTextContent('Thu hồi quyền chia sẻ?')
  const describedBy = dialog.getAttribute('aria-describedby') as string
  expect(document.getElementById(describedBy)).toHaveTextContent(/vẫn được giữ lại/)

  expect(screen.getByRole('button', { name: 'Thu hồi' })).toBeEnabled()
  expect(screen.getByRole('button', { name: 'Giữ quyền chia sẻ' })).toBeEnabled()
})

test('focus moves into the confirmation when it opens', async () => {
  renderCard()
  await userEvent.click(await screen.findByTestId('revoke-button'))

  const dialog = await screen.findByRole('dialog')
  await waitFor(() => expect(dialog.contains(document.activeElement)).toBe(true))
})

// ---------------------------------------------------------------------------
// Legacy / never-granted: the first grant
// ---------------------------------------------------------------------------

test('an eligible legacy consultation offers "Chia sẻ dữ liệu", not "Chia sẻ lại"', async () => {
  mockedGet.mockResolvedValue(neverGranted())

  renderCard()

  const button = await screen.findByTestId('share-button')
  expect(button).toHaveTextContent('Chia sẻ dữ liệu')
  // "Chia sẻ lại" would imply a previous grant that never existed.
  expect(screen.queryByTestId('reshare-button')).not.toBeInTheDocument()
  expect(screen.queryByTestId('revoke-button')).not.toBeInTheDocument()
})

test('an ineligible legacy consultation states the status but offers no action', async () => {
  mockedGet.mockResolvedValue(neverGranted({ consultation_status: 'COMPLETED', can_share: false }))

  renderCard()

  expect(await screen.findByTestId('session-ended')).toBeInTheDocument()
  expect(screen.queryByTestId('share-button')).not.toBeInTheDocument()
  expect(screen.queryByTestId('reshare-button')).not.toBeInTheDocument()
})

test('the first grant goes through the full consent dialog, never one tap', async () => {
  mockedGet.mockResolvedValue(neverGranted())

  renderCard()
  await userEvent.click(await screen.findByTestId('share-button'))

  // The server's current copy, verbatim — the same terms as booking.
  expect(await screen.findByText('Đoạn một.')).toBeInTheDocument()
  expect(screen.getByText('Đoạn hai.')).toBeInTheDocument()
  expect(mockedRestore).not.toHaveBeenCalled()
})

test('the first grant sends the rendered versions and every disclosed category', async () => {
  mockedGet.mockResolvedValue(neverGranted())

  renderCard()
  await userEvent.click(await screen.findByTestId('share-button'))
  mockedGet.mockResolvedValueOnce(sharing())
  await userEvent.click(await screen.findByRole('button', { name: POLICY.accept_label }))

  await waitFor(() => expect(mockedRestore).toHaveBeenCalledTimes(1))
  expect(mockedRestore).toHaveBeenCalledWith('c-1abc2def', {
    accepted: true,
    categories: CATEGORIES,
    consent_version: '1.0',
    policy_version: '1.1',
    source: 'web',
  })
  expect(await screen.findByTestId('sharing-status')).toHaveTextContent(/Đã chia sẻ|Đang chia sẻ/)
})

test('declining the first-grant dialog grants nothing', async () => {
  mockedGet.mockResolvedValue(neverGranted())

  renderCard()
  await userEvent.click(await screen.findByTestId('share-button'))
  await userEvent.click(await screen.findByRole('button', { name: POLICY.decline_label }))

  expect(mockedRestore).not.toHaveBeenCalled()
  expect(await screen.findByTestId('sharing-status')).toHaveTextContent('Chưa chia sẻ')
})

test('a failed first grant leaves the state never-granted and says so', async () => {
  mockedGet.mockResolvedValue(neverGranted())
  mockedRestore.mockRejectedValue(new ApiError(409, 'Consent version is out of date.'))

  renderCard()
  await userEvent.click(await screen.findByTestId('share-button'))
  await userEvent.click(await screen.findByRole('button', { name: POLICY.accept_label }))

  expect(await screen.findByText('Consent version is out of date.')).toBeInTheDocument()
  expect(screen.getByTestId('sharing-status')).toHaveTextContent('Chưa chia sẻ')
})

test('a needs-reconsent state is not reported as a withdrawal', async () => {
  // We moved the terms; the patient did nothing. Saying "đã thu hồi" here would
  // blame them for our version bump.
  mockedGet.mockResolvedValue(sharing({ state: 'NEEDS_RECONSENT' }))

  renderCard()

  expect(await screen.findByTestId('sharing-status')).toHaveTextContent(/Cần xác nhận lại/)
  expect(screen.queryByText(/Đã thu hồi/)).not.toBeInTheDocument()
})

test('an unavailable state is an error, never a statement about the patient', async () => {
  mockedGet.mockRejectedValue(new ApiError(502, 'gateway'))

  renderCard()

  expect(await screen.findByRole('alert')).toHaveTextContent(/Không tải được/)
  expect(screen.queryByTestId('sharing-status')).not.toBeInTheDocument()
  expect(screen.queryByText(/Chưa chia sẻ|Đã thu hồi|Đang chia sẻ/)).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Thử lại' })).toBeInTheDocument()
})

test('the first-grant action is reachable and labelled for assistive tech', async () => {
  mockedGet.mockResolvedValue(neverGranted())

  renderCard()

  const button = await screen.findByRole('button', { name: 'Chia sẻ dữ liệu' })
  expect(button).toBeEnabled()
  // The status line is a live region, so the state change is announced.
  expect(screen.getByTestId('sharing-status')).toHaveAttribute('aria-live', 'polite')
})
