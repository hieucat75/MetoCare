/**
 * Drift guard: frontend legal versions must match the canonical root JSON.
 * Mirrors backend tests/test_legal_versions_sync.py. Runs in the full checkout
 * (repo root available), unlike the frontend-only Docker build.
 */
import { readFileSync } from 'fs'
import { resolve } from 'path'
import { TERMS_VERSION, PRIVACY_VERSION } from '@/lib/legal'

describe('legal versions', () => {
  it('match the canonical repo-root legal-versions.json', () => {
    const root = resolve(__dirname, '../../../legal-versions.json')
    const data = JSON.parse(readFileSync(root, 'utf-8')) as {
      terms_version: string
      privacy_version: string
    }
    expect(TERMS_VERSION).toBe(data.terms_version)
    expect(PRIVACY_VERSION).toBe(data.privacy_version)
  })
})
