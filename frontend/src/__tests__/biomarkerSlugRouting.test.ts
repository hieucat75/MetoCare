/**
 * Tests for AI Copilot biomarker slug routing.
 *
 * Verifies:
 * - SLUG_TO_KEY correctly normalises URL slugs to mockBiomarkers keys
 * - METRIC_TYPE_TO_SLUG maps backend metric types to URL slugs
 * - resolveSlug returns the slug itself when no mapping exists (no 404 on unknown)
 * - All 18 required slugs resolve to an entry in mockBiomarkers
 */

import { describe, test, expect } from '@jest/globals'
import { SLUG_TO_KEY, METRIC_TYPE_TO_SLUG, resolveSlug } from '@/lib/ai-copilot/slugMap'
import { mockBiomarkers } from '@/lib/mock/aiCopilotData'

// The 18 required slugs from the spec
const REQUIRED_SLUGS = [
  'tsh',
  'ft4',
  'thyroglobulin',
  'fasting-glucose',
  'hba1c',
  'ldl',
  'hdl',
  'triglyceride',
  'total-cholesterol',
  'alt',
  'ast',
  'ggt',
  'creatinine',
  'egfr',
  'vitamin-d',
  'ferritin',
  'b12',
  'hs-crp',
]

describe('resolveSlug', () => {
  test('returns original slug when no mapping exists', () => {
    expect(resolveSlug('unknown-slug-xyz')).toBe('unknown-slug-xyz')
  })

  test('normalises fasting-glucose to glucose', () => {
    expect(resolveSlug('fasting-glucose')).toBe('glucose')
  })

  test('normalises triglyceride to tg', () => {
    expect(resolveSlug('triglyceride')).toBe('tg')
  })

  test('normalises vitamin-d to vitd', () => {
    expect(resolveSlug('vitamin-d')).toBe('vitd')
  })

  test('passes through tsh unchanged', () => {
    expect(resolveSlug('tsh')).toBe('tsh')
  })

  test('passes through hs-crp unchanged', () => {
    expect(resolveSlug('hs-crp')).toBe('hs-crp')
  })

  test('passes through total-cholesterol unchanged', () => {
    expect(resolveSlug('total-cholesterol')).toBe('total-cholesterol')
  })
})

describe('SLUG_TO_KEY', () => {
  test('glucose key resolves directly', () => {
    expect(SLUG_TO_KEY['glucose']).toBe('glucose')
  })

  test('tg key resolves directly', () => {
    expect(SLUG_TO_KEY['tg']).toBe('tg')
  })

  test('vitd key resolves directly', () => {
    expect(SLUG_TO_KEY['vitd']).toBe('vitd')
  })
})

describe('METRIC_TYPE_TO_SLUG', () => {
  test('fasting_glucose maps to fasting-glucose', () => {
    expect(METRIC_TYPE_TO_SLUG['fasting_glucose']).toBe('fasting-glucose')
  })

  test('hba1c maps to hba1c', () => {
    expect(METRIC_TYPE_TO_SLUG['hba1c']).toBe('hba1c')
  })

  test('triglyceride maps to triglyceride', () => {
    expect(METRIC_TYPE_TO_SLUG['triglyceride']).toBe('triglyceride')
  })

  test('tsh maps to tsh', () => {
    expect(METRIC_TYPE_TO_SLUG['tsh']).toBe('tsh')
  })

  test('hs_crp maps to hs-crp', () => {
    expect(METRIC_TYPE_TO_SLUG['hs_crp']).toBe('hs-crp')
  })
})

describe('All 18 required slugs resolve to mockBiomarkers entries', () => {
  test.each(REQUIRED_SLUGS)('slug "%s" resolves to a valid mockBiomarkers entry', (slug) => {
    const key = resolveSlug(slug)
    expect(mockBiomarkers).toHaveProperty(key)
    const bio = mockBiomarkers[key]
    expect(bio.key).toBe(key)
    expect(bio.name.length).toBeGreaterThan(0)
    expect(bio.doesWhat.length).toBeGreaterThan(0)
    expect(bio.doctorQs.length).toBeGreaterThan(0)
  })
})

describe('mockBiomarkers completeness', () => {
  const ALL_EXPECTED_KEYS = [
    'glucose',
    'hba1c',
    'ldl',
    'hdl',
    'tg',
    'vitd',
    'tsh',
    'ft4',
    'thyroglobulin',
    'total-cholesterol',
    'alt',
    'ast',
    'ggt',
    'creatinine',
    'egfr',
    'ferritin',
    'b12',
    'hs-crp',
  ]

  test.each(ALL_EXPECTED_KEYS)('mockBiomarkers has entry for key "%s"', (key) => {
    expect(mockBiomarkers).toHaveProperty(key)
  })

  test('every entry has required fields', () => {
    for (const [key, bio] of Object.entries(mockBiomarkers)) {
      expect(bio.key).toBe(key)
      expect(typeof bio.name).toBe('string')
      expect(bio.name.length).toBeGreaterThan(0)
      expect(typeof bio.conclusion).toBe('string')
      expect(bio.conclusion.length).toBeGreaterThan(0)
      expect(typeof bio.doesWhat).toBe('string')
      expect(bio.doesWhat.length).toBeGreaterThan(0)
      expect(Array.isArray(bio.doctorQs)).toBe(true)
    }
  })
})
