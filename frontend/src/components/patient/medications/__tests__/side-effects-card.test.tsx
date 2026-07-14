/**
 * SideEffectsCard (M4) — no side-effect data source exists yet; this
 * component must never imply otherwise or infer content from a drug name.
 *
 * Verifies the product decision this component encodes:
 *  - empty state text is exact and locked (criterion 3)
 *  - no sample/default data ever renders when groups=[] (criterion 4)
 *  - never claims "no side effects" / "safe" (criterion 2)
 *  - "urgent" (Dấu hiệu cần đi khám ngay) is visually distinguished from
 *    "common" but does not use alarm-red/scare wording
 *  - content is a pure function of props (criterion 1)
 *  - each group is its own accessible region with its own heading (criterion 6)
 */
import * as React from 'react'
import { render, screen } from '@testing-library/react'
import '@testing-library/jest-dom'
import { SideEffectsCard, SIDE_EFFECTS_EMPTY_STATE, type MedicationSideEffectGroup } from '../side-effects-card'

const FORBIDDEN_SAFETY_CLAIMS = ['không có tác dụng phụ', 'an toàn', 'không có nguy cơ']

describe('SideEffectsCard — empty state', () => {
  test('renders the exact required empty-state sentence when groups=[]', () => {
    render(<SideEffectsCard groups={[]} />)
    expect(screen.getByText(SIDE_EFFECTS_EMPTY_STATE)).toBeInTheDocument()
  })

  test('renders the empty state when all groups are present but have zero items', () => {
    const emptyGroups: MedicationSideEffectGroup[] = [
      { level: 'common', items: [] },
      { level: 'uncommon', items: [] },
      { level: 'urgent', items: [] },
    ]
    render(<SideEffectsCard groups={emptyGroups} />)
    expect(screen.getByText(SIDE_EFFECTS_EMPTY_STATE)).toBeInTheDocument()
  })

  test('never renders a "no side effects" / safety claim', () => {
    render(<SideEffectsCard groups={[]} />)
    const bodyText = (document.body.textContent ?? '').toLowerCase()
    for (const phrase of FORBIDDEN_SAFETY_CLAIMS) {
      expect(bodyText).not.toContain(phrase.toLowerCase())
    }
  })

  test('does not render any group heading when empty (no stray sample groups)', () => {
    render(<SideEffectsCard groups={[]} />)
    expect(screen.queryByRole('heading', { name: 'Thường gặp' })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Ít gặp' })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Dấu hiệu cần đi khám ngay' })).not.toBeInTheDocument()
  })
})

describe('SideEffectsCard — populated states', () => {
  const allThreeGroups: MedicationSideEffectGroup[] = [
    { level: 'common', items: ['Buồn nôn', 'Đau đầu nhẹ'] },
    { level: 'uncommon', items: ['Phát ban da'] },
    { level: 'urgent', items: ['Khó thở', 'Sưng mặt/môi/lưỡi'] },
  ]

  test('renders all 3 groups with their items under distinct headings', () => {
    render(<SideEffectsCard groups={allThreeGroups} />)
    expect(screen.getByRole('heading', { name: 'Thường gặp' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Ít gặp' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Dấu hiệu cần đi khám ngay' })).toBeInTheDocument()
    expect(screen.getByText('Buồn nôn')).toBeInTheDocument()
    expect(screen.getByText('Phát ban da')).toBeInTheDocument()
    expect(screen.getByText('Khó thở')).toBeInTheDocument()
  })

  test('each group is its own accessible region (distinct headings, distinct sections)', () => {
    render(<SideEffectsCard groups={allThreeGroups} />)
    const common = screen.getByRole('heading', { name: 'Thường gặp' })
    const urgent = screen.getByRole('heading', { name: 'Dấu hiệu cần đi khám ngay' })
    expect(common.id).not.toBe(urgent.id)
    expect(common.closest('section')).not.toBe(urgent.closest('section'))
  })

  test('"urgent" wording is prominent but not fear-inducing (no exclamation, no alarm words)', () => {
    render(<SideEffectsCard groups={allThreeGroups} />)
    const urgentHeading = screen.getByRole('heading', { name: 'Dấu hiệu cần đi khám ngay' })
    expect(urgentHeading.textContent).not.toMatch(/!|khẩn cấp|nguy hiểm|cấp cứu ngay/i)
  })

  test('merges multiple groups sharing the same level instead of dropping any (safety data must never be silently lost)', () => {
    const duplicateUrgent: MedicationSideEffectGroup[] = [
      { level: 'urgent', items: ['Khó thở'] },
      { level: 'urgent', items: ['Sưng mặt'] },
    ]
    render(<SideEffectsCard groups={duplicateUrgent} />)
    expect(screen.getByText('Khó thở')).toBeInTheDocument()
    expect(screen.getByText('Sưng mặt')).toBeInTheDocument()
  })

  test('merging preserves every distinct evidence label, not just the first (provenance must stay attributable)', () => {
    const duplicateUrgentWithSources: MedicationSideEffectGroup[] = [
      { level: 'urgent', items: ['Khó thở'], evidenceLabel: 'Nguồn A' },
      { level: 'urgent', items: ['Sưng mặt'], evidenceLabel: 'Nguồn B' },
    ]
    render(<SideEffectsCard groups={duplicateUrgentWithSources} />)
    expect(screen.getByText(/Nguồn A/)).toBeInTheDocument()
    expect(screen.getByText(/Nguồn B/)).toBeInTheDocument()
  })

  test('renders only the groups that have items (omits empty groups from the 3, no gap)', () => {
    const onlyUrgent: MedicationSideEffectGroup[] = [
      { level: 'common', items: [] },
      { level: 'uncommon', items: [] },
      { level: 'urgent', items: ['Khó thở'] },
    ]
    render(<SideEffectsCard groups={onlyUrgent} />)
    expect(screen.queryByRole('heading', { name: 'Thường gặp' })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Ít gặp' })).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Dấu hiệu cần đi khám ngay' })).toBeInTheDocument()
  })

  test('same items render identically regardless of any external medication context (no per-drug branching)', () => {
    const { unmount } = render(<SideEffectsCard groups={allThreeGroups} />)
    expect(screen.getByText('Buồn nôn')).toBeInTheDocument()
    unmount()
    render(<SideEffectsCard groups={allThreeGroups} />)
    expect(screen.getByText('Buồn nôn')).toBeInTheDocument()
  })

  test('handles a long list of items without crashing', () => {
    const many: MedicationSideEffectGroup[] = [
      { level: 'common', items: Array.from({ length: 20 }, (_, i) => `Triệu chứng ${i + 1}`) },
    ]
    render(<SideEffectsCard groups={many} />)
    expect(screen.getByText('Triệu chứng 20')).toBeInTheDocument()
  })
})

describe('SideEffectsCard — loading and error', () => {
  test('shows a loading indicator and no empty-state text while loading', () => {
    render(<SideEffectsCard groups={[]} loading />)
    expect(screen.getByLabelText('Đang tải dữ liệu tác dụng phụ')).toBeInTheDocument()
    expect(screen.queryByText(SIDE_EFFECTS_EMPTY_STATE)).not.toBeInTheDocument()
  })

  test('shows the error message via role=alert, not the empty state', () => {
    render(<SideEffectsCard groups={[]} error="Không thể tải dữ liệu." />)
    expect(screen.getByRole('alert')).toHaveTextContent('Không thể tải dữ liệu.')
    expect(screen.queryByText(SIDE_EFFECTS_EMPTY_STATE)).not.toBeInTheDocument()
  })
})
