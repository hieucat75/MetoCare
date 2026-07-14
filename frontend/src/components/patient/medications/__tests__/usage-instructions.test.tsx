/**
 * UsageInstructionsCard (M3) — "Ghi chú của bạn" vs "Hướng dẫn sử dụng",
 * kept strictly apart. No AI, no medication-name-conditioned guidance.
 *
 * Verifies the product decision this component encodes:
 *  - note (real, user-authored) renders under its own "Ghi chú của bạn" heading
 *  - no note → no empty "Ghi chú của bạn" section at all
 *  - the guidance section always shows the fixed empty-state sentence,
 *    regardless of medication name/dose/frequency — proving nothing is
 *    hardcoded or hallucinated per-drug
 *  - the two sections are separate accessible regions (distinct headings),
 *    so a screen reader user can tell user content from system content
 */
import * as React from 'react'
import { render, screen } from '@testing-library/react'
import '@testing-library/jest-dom'
import { UsageInstructionsCard } from '../usage-instructions'

const REQUIRED_EMPTY_STATE = 'Hướng dẫn sử dụng chi tiết chưa có sẵn.'

// Phrases that would only appear if guidance content were hardcoded or
// hallucinated per-medication — none of these may ever render.
const FORBIDDEN_CLINICAL_PHRASES = [
  'trước ăn',
  'sau ăn',
  'phút',
  'lúc đói',
  'liều lượng',
  'không quá',
  'tương tác',
]

describe('UsageInstructionsCard', () => {
  test('shows the note under its own "Ghi chú của bạn" heading', () => {
    render(<UsageInstructionsCard note="Uống cùng nhiều nước theo lời dặn của bác sĩ" />)
    expect(screen.getByRole('heading', { name: 'Ghi chú của bạn' })).toBeInTheDocument()
    expect(
      screen.getByText('Uống cùng nhiều nước theo lời dặn của bác sĩ')
    ).toBeInTheDocument()
  })

  test('omits the note section entirely when there is no note (no empty gap)', () => {
    render(<UsageInstructionsCard note={null} />)
    expect(screen.queryByRole('heading', { name: 'Ghi chú của bạn' })).not.toBeInTheDocument()
  })

  test('always shows the fixed guidance empty-state sentence', () => {
    render(<UsageInstructionsCard note={null} />)
    expect(screen.getByRole('heading', { name: 'Hướng dẫn sử dụng' })).toBeInTheDocument()
    expect(screen.getByText(REQUIRED_EMPTY_STATE)).toBeInTheDocument()
  })

  test('guidance text is identical regardless of note content (never conditioned on it)', () => {
    const { rerender } = render(<UsageInstructionsCard note={null} />)
    expect(screen.getByText(REQUIRED_EMPTY_STATE)).toBeInTheDocument()

    rerender(<UsageInstructionsCard note="Uống trước khi ngủ" />)
    expect(screen.getByText(REQUIRED_EMPTY_STATE)).toBeInTheDocument()

    rerender(<UsageInstructionsCard note="Nhớ mang theo khi đi xa" />)
    expect(screen.getByText(REQUIRED_EMPTY_STATE)).toBeInTheDocument()
  })

  test('never renders hardcoded/hallucinated clinical guidance phrases', () => {
    render(<UsageInstructionsCard note="Metformin 500mg uống 2 lần/ngày" />)
    const bodyText = document.body.textContent ?? ''
    for (const phrase of FORBIDDEN_CLINICAL_PHRASES) {
      expect(bodyText).not.toContain(phrase)
    }
  })

  test('note and guidance are two separate accessible regions (screen-reader distinguishable)', () => {
    render(<UsageInstructionsCard note="Ghi chú thật của bệnh nhân" />)
    const noteHeading = screen.getByRole('heading', { name: 'Ghi chú của bạn' })
    const guidanceHeading = screen.getByRole('heading', { name: 'Hướng dẫn sử dụng' })
    // Each heading has its own id, referenced by a distinct aria-labelledby
    // section — a screen reader announces them as two separate regions.
    expect(noteHeading.id).not.toBe(guidanceHeading.id)
    expect(noteHeading.closest('section')).not.toBe(guidanceHeading.closest('section'))
  })

  test('does not use warning/danger styling classes (must not look like an alert card)', () => {
    const { container } = render(<UsageInstructionsCard note={null} />)
    expect(container.innerHTML).not.toMatch(/D92D20|FEF2F2|AlertTriangle|role="alert"/)
  })
})
