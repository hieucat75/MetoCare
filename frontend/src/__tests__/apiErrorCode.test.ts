/**
 * Regression: the backend's error CODE and MESSAGE must survive the client.
 *
 * The password-policy handler answers `{code, message}` — not `detail`. The
 * client only read `detail`, so a policy rejection arrived as a bare
 * "Lỗi 422" with no code, and the register page's `422 === invalid phone`
 * assumption then told a real user their valid number was wrong.
 */

import { ApiError, apiFetch } from '@/lib/api/client'

function mockResponse(status: number, body: unknown) {
  global.fetch = jest.fn().mockResolvedValue({
    ok: false,
    status,
    json: async () => body,
  }) as unknown as typeof fetch
}

describe('apiFetch error parsing', () => {
  afterEach(() => jest.resetAllMocks())

  it('carries a PASSWORD_POLICY code and its message', async () => {
    mockResponse(422, {
      code: 'PASSWORD_POLICY',
      message: 'Mật khẩu phải có ít nhất 8 ký tự.',
    })

    await expect(apiFetch('/x', { skipAuth: true })).rejects.toMatchObject({
      status: 422,
      code: 'PASSWORD_POLICY',
      detail: 'Mật khẩu phải có ít nhất 8 ký tự.',
    })
  })

  it('still carries a plain detail string', async () => {
    mockResponse(422, { detail: 'Số điện thoại di động Việt Nam không hợp lệ.' })

    const err = (await apiFetch('/x', { skipAuth: true }).catch((e) => e)) as ApiError
    expect(err.detail).toContain('Số điện thoại')
    expect(err.code).toBeUndefined()
  })

  it('a password rejection is distinguishable from a phone rejection', async () => {
    // The whole point: both are 422, and a client must be able to tell them
    // apart without guessing.
    mockResponse(422, { code: 'PASSWORD_POLICY', message: 'Mật khẩu phải gồm cả chữ và số.' })
    const pw = (await apiFetch('/x', { skipAuth: true }).catch((e) => e)) as ApiError

    mockResponse(422, { detail: 'Số điện thoại di động Việt Nam không hợp lệ.' })
    const phone = (await apiFetch('/x', { skipAuth: true }).catch((e) => e)) as ApiError

    expect(pw.status).toBe(phone.status)
    expect(pw.code).not.toBe(phone.code)
    expect(pw.detail).not.toContain('Số điện thoại')
  })
})
