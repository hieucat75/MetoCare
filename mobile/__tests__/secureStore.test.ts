import { secureStorage } from '../src/storage/secureStore'
import * as SecureStore from 'expo-secure-store'

describe('secureStorage adapter', () => {
  beforeEach(async () => {
    // Mock exposes the backing Map for cleanup between tests.
    ;(SecureStore as unknown as { __mem: Map<string, string> }).__mem.clear()
    jest.clearAllMocks()
  })

  it('sets and gets a raw string value', async () => {
    await secureStorage.setItem('k', 'v')
    expect(SecureStore.setItemAsync).toHaveBeenCalledWith('k', 'v')
    await expect(secureStorage.getItem('k')).resolves.toBe('v')
  })

  it('returns null for a missing key', async () => {
    await expect(secureStorage.getItem('missing')).resolves.toBeNull()
  })

  it('round-trips JSON via setJSON/getJSON', async () => {
    await secureStorage.setJSON('obj', { a: 1, b: 'two' })
    await expect(secureStorage.getJSON<{ a: number; b: string }>('obj')).resolves.toEqual({
      a: 1,
      b: 'two',
    })
  })

  it('returns null (not throw) when stored JSON is corrupt', async () => {
    await secureStorage.setItem('bad', '{not-json')
    await expect(secureStorage.getJSON('bad')).resolves.toBeNull()
  })

  it('removeItem never throws on a missing key', async () => {
    await expect(secureStorage.removeItem('nope')).resolves.toBeUndefined()
  })

  it('removeItem deletes an existing key', async () => {
    await secureStorage.setItem('k', 'v')
    await secureStorage.removeItem('k')
    await expect(secureStorage.getItem('k')).resolves.toBeNull()
  })

  it('reports availability', async () => {
    await expect(secureStorage.isAvailable()).resolves.toBe(true)
  })
})
