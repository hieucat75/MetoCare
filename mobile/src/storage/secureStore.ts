import * as SecureStore from 'expo-secure-store'

/**
 * Thin async adapter over expo-secure-store (iOS Keychain / Android Keystore).
 *
 * All token + install-identity material MUST go through here — never
 * AsyncStorage — so at-rest secrets are hardware-backed. The adapter adds:
 *  - typed JSON helpers (getJSON/setJSON) with safe parse,
 *  - null-on-miss semantics,
 *  - a resilient delete that never throws on a missing key.
 *
 * Note: native Keychain/Keystore behaviour is logic-tested via an in-memory
 * mock; real device at-rest encryption is native-runtime pending.
 */

export interface SecureStorageAdapter {
  getItem(key: string): Promise<string | null>
  setItem(key: string, value: string): Promise<void>
  removeItem(key: string): Promise<void>
  getJSON<T>(key: string): Promise<T | null>
  setJSON<T>(key: string, value: T): Promise<void>
  isAvailable(): Promise<boolean>
}

async function getItem(key: string): Promise<string | null> {
  return SecureStore.getItemAsync(key)
}

async function setItem(key: string, value: string): Promise<void> {
  await SecureStore.setItemAsync(key, value)
}

async function removeItem(key: string): Promise<void> {
  try {
    await SecureStore.deleteItemAsync(key)
  } catch {
    // Deleting a non-existent key is a no-op — never surface as an error.
  }
}

async function getJSON<T>(key: string): Promise<T | null> {
  const raw = await getItem(key)
  if (raw == null) return null
  try {
    return JSON.parse(raw) as T
  } catch {
    // Corrupt payload: treat as absent rather than crash the caller.
    return null
  }
}

async function setJSON<T>(key: string, value: T): Promise<void> {
  await setItem(key, JSON.stringify(value))
}

async function isAvailable(): Promise<boolean> {
  try {
    return await SecureStore.isAvailableAsync()
  } catch {
    return false
  }
}

export const secureStorage: SecureStorageAdapter = {
  getItem,
  setItem,
  removeItem,
  getJSON,
  setJSON,
  isAvailable,
}
