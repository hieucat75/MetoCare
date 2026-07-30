import AsyncStorage from '@react-native-async-storage/async-storage'
import * as Crypto from 'expo-crypto'
import { secureStorage, type SecureStorageAdapter } from './secureStore'

/**
 * App installation UUID (ADR-03).
 *
 * A random per-install UUID — NEVER a hardware identifier — that must be:
 *   1. generated at first install,
 *   2. RESET on reinstall,
 *   3. RESET on account unlink.
 *
 * The reinstall-reset is the subtle part. On iOS the Keychain (backing
 * SecureStore) PERSISTS across app deletion + reinstall, so a UUID stored
 * only in SecureStore would survive a reinstall and violate requirement (2).
 *
 * Fix: gate regeneration on an AsyncStorage "install marker". AsyncStorage IS
 * wiped when the app is uninstalled. On boot:
 *   - marker present  → same install, reuse the SecureStore UUID.
 *   - marker absent   → fresh install (AsyncStorage was wiped). Regenerate a
 *                       new UUID even if a stale one lingers in the Keychain,
 *                       then (re)write the marker.
 *
 * The UUID itself lives in SecureStore (hardware-backed at rest); the marker
 * in AsyncStorage is a non-secret presence flag only.
 */

export const INSTALL_ID_KEY = 'meto_install_id'
export const INSTALL_MARKER_KEY = 'meto_install_marker'
const INSTALL_MARKER_VALUE = '1'

export interface AsyncKV {
  getItem(key: string): Promise<string | null>
  setItem(key: string, value: string): Promise<void>
  removeItem(key: string): Promise<void>
}

export interface InstallIdDeps {
  secure?: SecureStorageAdapter
  async?: AsyncKV
  generateUUID?: () => string
}

function resolve(deps: InstallIdDeps = {}) {
  return {
    secure: deps.secure ?? secureStorage,
    async: deps.async ?? AsyncStorage,
    generateUUID: deps.generateUUID ?? (() => Crypto.randomUUID()),
  }
}

/**
 * Returns the current install UUID, generating (and resetting on reinstall) as
 * needed. Idempotent within a single install lifetime.
 */
export async function getOrCreateInstallId(deps: InstallIdDeps = {}): Promise<string> {
  const { secure, async: kv, generateUUID } = resolve(deps)

  const marker = await kv.getItem(INSTALL_MARKER_KEY)
  if (marker === INSTALL_MARKER_VALUE) {
    // Same install — trust the stored UUID if present.
    const existing = await secure.getItem(INSTALL_ID_KEY)
    if (existing) return existing
    // Marker present but UUID missing (rare corruption) — regenerate.
  }

  // Fresh install (marker wiped) OR recovery — mint a NEW id, overwriting any
  // stale Keychain-persisted value so reinstall genuinely resets identity.
  const id = generateUUID()
  await secure.setItem(INSTALL_ID_KEY, id)
  await kv.setItem(INSTALL_MARKER_KEY, INSTALL_MARKER_VALUE)
  return id
}

/** Read the install id without creating one (null if none yet). */
export async function peekInstallId(deps: InstallIdDeps = {}): Promise<string | null> {
  const { secure } = resolve(deps)
  return secure.getItem(INSTALL_ID_KEY)
}

/**
 * Clear the install identity on account unlink. Removes BOTH the SecureStore
 * UUID and the AsyncStorage marker so the next boot mints a fresh id.
 */
export async function unlinkInstallId(deps: InstallIdDeps = {}): Promise<void> {
  const { secure, async: kv } = resolve(deps)
  await secure.removeItem(INSTALL_ID_KEY)
  await kv.removeItem(INSTALL_MARKER_KEY)
}
