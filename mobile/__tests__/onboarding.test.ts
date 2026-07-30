import {
  createOnboardingStore,
  ONBOARDING_KEY,
} from '../src/storage/onboarding'
import type { AsyncKV } from '../src/storage/installId'

/** Minimal in-memory AsyncKV fake (mirrors installId.test.ts). */
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

/** AsyncKV that always throws — simulates unavailable/failing storage. */
function makeFailingKV(): AsyncKV {
  const boom = async (): Promise<never> => {
    throw new Error('storage unavailable')
  }
  return { getItem: boom, setItem: boom, removeItem: boom }
}

describe('onboardingStore (first-run gate)', () => {
  it('reports not complete before onboarding has been finished', async () => {
    const kv = makeKV()
    const store = createOnboardingStore(kv)

    await expect(store.isComplete()).resolves.toBe(false)
  })

  it('persists completion and reports complete afterwards', async () => {
    const kv = makeKV()
    const store = createOnboardingStore(kv)

    await store.complete()

    expect(kv.mem.get(ONBOARDING_KEY)).toBe('1')
    await expect(store.isComplete()).resolves.toBe(true)
  })

  it('persists across store instances sharing the same storage', async () => {
    const kv = makeKV()
    await createOnboardingStore(kv).complete()

    // A fresh store (e.g. next app launch) reads the same backing store.
    const nextLaunch = createOnboardingStore(kv)
    await expect(nextLaunch.isComplete()).resolves.toBe(true)
  })

  it('reset clears completion so the gate re-shows onboarding', async () => {
    const kv = makeKV()
    const store = createOnboardingStore(kv)
    await store.complete()
    await expect(store.isComplete()).resolves.toBe(true)

    await store.reset()

    expect(kv.mem.has(ONBOARDING_KEY)).toBe(false)
    await expect(store.isComplete()).resolves.toBe(false)
  })

  describe('safe fallback when storage is unavailable', () => {
    it('isComplete degrades to false instead of throwing', async () => {
      const store = createOnboardingStore(makeFailingKV())
      await expect(store.isComplete()).resolves.toBe(false)
    })

    it('complete is best-effort and never rejects', async () => {
      const store = createOnboardingStore(makeFailingKV())
      await expect(store.complete()).resolves.toBeUndefined()
    })

    it('reset is best-effort and never rejects', async () => {
      const store = createOnboardingStore(makeFailingKV())
      await expect(store.reset()).resolves.toBeUndefined()
    })
  })
})
