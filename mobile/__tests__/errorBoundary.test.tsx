import React from 'react'
import { Text } from 'react-native'
import { fireEvent, render } from '@testing-library/react-native'

const mockCapture = jest.fn()
jest.mock('../src/lib/monitor', () => ({
  captureException: (...args: unknown[]) => mockCapture(...args),
}))

import { ErrorBoundary } from '../src/components/ErrorBoundary'

function Boom(): React.ReactElement {
  throw new Error('render exploded for user@example.com')
}

describe('ErrorBoundary', () => {
  beforeEach(() => mockCapture.mockClear())

  it('renders children when there is no error', async () => {
    const view = await render(
      <ErrorBoundary>
        <Text>Nội dung</Text>
      </ErrorBoundary>,
    )
    expect(view.getByText('Nội dung')).toBeTruthy()
    expect(view.queryByText('Đã xảy ra sự cố')).toBeNull()
  })

  it('shows a safe fallback (no raw error text) and reports the crash', async () => {
    const spy = jest.spyOn(console, 'error').mockImplementation(() => {})
    const view = await render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>,
    )
    expect(view.getByText('Đã xảy ra sự cố')).toBeTruthy()
    // The raw error message / PHI-looking content is never shown to the user.
    expect(view.queryByText(/render exploded/)).toBeNull()
    expect(view.queryByText(/user@example.com/)).toBeNull()
    expect(mockCapture).toHaveBeenCalledTimes(1)
    expect(mockCapture.mock.calls[0][1]).toMatchObject({ fatal: true })
    spy.mockRestore()
  })

  it('retry clears the error state so recovered children render', async () => {
    const spy = jest.spyOn(console, 'error').mockImplementation(() => {})

    function Flaky({ crash }: { crash: boolean }): React.ReactElement {
      if (crash) throw new Error('boom')
      return <Text>Đã phục hồi</Text>
    }

    const view = await render(
      <ErrorBoundary>
        <Flaky crash />
      </ErrorBoundary>,
    )
    expect(view.getByText('Đã xảy ra sự cố')).toBeTruthy()

    // Fix the underlying condition, then retry → subtree re-mounts and renders.
    await view.rerender(
      <ErrorBoundary>
        <Flaky crash={false} />
      </ErrorBoundary>,
    )
    await fireEvent.press(view.getByText('Thử lại'))
    expect(view.getByText('Đã phục hồi')).toBeTruthy()
    spy.mockRestore()
  })
})
