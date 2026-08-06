import {
  getOrCreateInstallId,
  unlinkInstallId,
  peekInstallId,
  INSTALL_ID_KEY,
  INSTALL_MARKER_KEY,
  type AsyncKV,
} from '../src/storage/installId'
import type { SecureStorageAdapter } from '../src/storage/secureStore'

/** Minimal in-memory KV usable as both the secure + async fakes. */
function makeKV() {
  const mem = new Map<string, string>()
  return {
    mem,
    getItem: jest.fn(async (k: string) => (mem.has(k) ? mem.get(k)! : null)),
    setItem: jest.fn(async (k: string, v: string) => {
      mem.set(k, v)
    }),
    removeItem: jest.fn(async (k: string) => {
      mem.delete(k)
    }),
  }
}

function makeSecure(): SecureStorageAdapter & { mem: Map<string, string> } {
  const kv = makeKV()
  return {
    mem: kv.mem,
    getItem: kv.getItem,
    setItem: kv.setItem,
    removeItem: kv.removeItem,
    getJSON: async () => null,
    setJSON: async () => {},
    isAvailable: async () => true,
  }
}

describe('installId (ADR-03)', () => {
  let uuidN = 0
  const generateUUID = jest.fn(() => `uuid-${++uuidN}`)

  beforeEach(() => {
    uuidN = 0
    generateUUID.mockClear()
  })

  it('generates a UUID and marker on first install', async () => {
    const secure = makeSecure()
    const async: AsyncKV = makeKV()

    const id = await getOrCreateInstallId({ secure, async, generateUUID })

    expect(id).toBe('uuid-1')
    expect(secure.mem.get(INSTALL_ID_KEY)).toBe('uuid-1')
    expect((async as ReturnType<typeof makeKV>).mem.get(INSTALL_MARKER_KEY)).toBe('1')
    expect(generateUUID).toHaveBeenCalledTimes(1)
  })

  it('is idempotent within the same install', async () => {
    const secure = makeSecure()
    const async: AsyncKV = makeKV()

    const first = await getOrCreateInstallId({ secure, async, generateUUID })
    const second = await getOrCreateInstallId({ secure, async, generateUUID })

    expect(first).toBe(second)
    expect(generateUUID).toHaveBeenCalledTimes(1)
  })

  it('RESETS on reinstall: Keychain UUID persists but AsyncStorage marker is wiped', async () => {
    // Simulate: SecureStore (Keychain) survives reinstall, AsyncStorage does not.
    const secure = makeSecure()
    const asyncBefore = makeKV()
    const idBefore = await getOrCreateInstallId({ secure, async: asyncBefore, generateUUID })
    expect(idBefore).toBe('uuid-1')

    // Reinstall: fresh (empty) AsyncStorage, SAME secure store still holding uuid-1.
    const asyncAfter = makeKV()
    const idAfter = await getOrCreateInstallId({ secure, async: asyncAfter, generateUUID })

    expect(idAfter).toBe('uuid-2')
    expect(idAfter).not.toBe(idBefore)
    expect(secure.mem.get(INSTALL_ID_KEY)).toBe('uuid-2')
    expect(asyncAfter.mem.get(INSTALL_MARKER_KEY)).toBe('1')
  })

  it('regenerates if marker present but UUID missing (corruption recovery)', async () => {
    const secure = makeSecure()
    const async = makeKV()
    await async.setItem(INSTALL_MARKER_KEY, '1') // marker set, no secure UUID

    const id = await getOrCreateInstallId({ secure, async, generateUUID })

    expect(id).toBe('uuid-1')
    expect(secure.mem.get(INSTALL_ID_KEY)).toBe('uuid-1')
  })

  it('unlink clears both secure UUID and marker → next boot mints fresh id', async () => {
    const secure = makeSecure()
    const async = makeKV()
    await getOrCreateInstallId({ secure, async, generateUUID })

    await unlinkInstallId({ secure, async })
    expect(secure.mem.has(INSTALL_ID_KEY)).toBe(false)
    expect(async.mem.has(INSTALL_MARKER_KEY)).toBe(false)
    await expect(peekInstallId({ secure })).resolves.toBeNull()

    const fresh = await getOrCreateInstallId({ secure, async, generateUUID })
    expect(fresh).toBe('uuid-2')
  })

  it('never returns a hardware identifier — value is exactly the generated UUID', async () => {
    const secure = makeSecure()
    const async = makeKV()
    const id = await getOrCreateInstallId({ secure, async, generateUUID })
    expect(id).toMatch(/^uuid-\d+$/)
  })
})
