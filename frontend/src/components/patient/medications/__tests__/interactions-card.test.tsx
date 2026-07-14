/**
 * InteractionsCard (M4) — highest clinical-risk surface in this sprint.
 * No interaction engine exists; this component must never imply otherwise.
 *
 * Verifies the product decision this component encodes:
 *  - empty state text is exact and locked (criterion 3)
 *  - no sample/default data ever renders when interactions=[] (criterion 4)
 *  - never claims "no interactions" / "safe" / "0 tương tác" (criterion 2)
 *  - "low" severity never uses green (would imply safety with no evidence)
 *  - content is a pure function of props — no medication-name-based
 *    inference, no hardcoded clinical facts (criterion 1)
 *  - severity + heading are screen-reader accessible (criterion 6)
 */
import * as React from 'react'
import { render, screen } from '@testing-library/react'
import '@testing-library/jest-dom'
import { InteractionsCard, INTERACTIONS_EMPTY_STATE, type MedicationInteraction } from '../interactions-card'

const FORBIDDEN_SAFETY_CLAIMS = [
  '0 tương tác',
  'không có tương tác',
  'không có nguy cơ',
  'an toàn',
  'không tương tác',
]

// The exact example the product owner explicitly banned from ever appearing
// as if it were real staging data.
const BANNED_SAMPLE_EXAMPLE = /Levothyroxine.{0,20}Canxi|Canxi.{0,20}Levothyroxine/i

describe('InteractionsCard — empty state', () => {
  test('renders the exact required empty-state sentence when interactions=[]', () => {
    render(<InteractionsCard medicationName="Metformin" interactions={[]} />)
    expect(screen.getByText(INTERACTIONS_EMPTY_STATE)).toBeInTheDocument()
  })

  test('never renders any "no interactions found" / safety claim', () => {
    render(<InteractionsCard medicationName="Metformin" interactions={[]} />)
    const bodyText = document.body.textContent ?? ''
    for (const phrase of FORBIDDEN_SAFETY_CLAIMS) {
      expect(bodyText.toLowerCase()).not.toContain(phrase.toLowerCase())
    }
  })

  test('never renders the banned Levothyroxine–Canxi sample as if real, regardless of medication name', () => {
    render(<InteractionsCard medicationName="Levothyroxine" interactions={[]} />)
    expect(document.body.textContent ?? '').not.toMatch(BANNED_SAMPLE_EXAMPLE)
  })

  test('does not render a list when interactions is empty (no stray sample rows)', () => {
    render(<InteractionsCard medicationName="Metformin" interactions={[]} />)
    expect(screen.queryByRole('list')).not.toBeInTheDocument()
  })
})

describe('InteractionsCard — populated states', () => {
  const oneInteraction: MedicationInteraction[] = [
    {
      severity: 'high',
      interactingSubstance: 'Warfarin',
      mechanism: 'Ức chế enzyme chuyển hoá',
      effect: 'Tăng nguy cơ chảy máu',
      recommendation: 'Trao đổi với bác sĩ trước khi dùng chung',
      evidenceLabel: 'Nguồn dữ liệu thử nghiệm',
    },
  ]

  test('renders a single interaction with medication name, substance, and severity', () => {
    render(<InteractionsCard medicationName="Metformin" interactions={oneInteraction} />)
    expect(
      screen.getByRole('heading', { name: 'Metformin tương tác với Warfarin' })
    ).toBeInTheDocument()
    expect(screen.getByText('Ức chế enzyme chuyển hoá')).toBeInTheDocument()
    expect(screen.getByText('Tăng nguy cơ chảy máu')).toBeInTheDocument()
    expect(screen.getByText('Trao đổi với bác sĩ trước khi dùng chung')).toBeInTheDocument()
  })

  test('renders multiple severities with distinct, non-green styling for every tier', () => {
    const multi: MedicationInteraction[] = [
      { severity: 'high', interactingSubstance: 'Warfarin' },
      { severity: 'moderate', interactingSubstance: 'Aspirin' },
      { severity: 'low', interactingSubstance: 'Vitamin C' },
    ]
    render(<InteractionsCard medicationName="Metformin" interactions={multi} />)
    expect(screen.getByLabelText('Mức độ tương tác: Mức độ cao')).toBeInTheDocument()
    expect(screen.getByLabelText('Mức độ tương tác: Mức độ trung bình')).toBeInTheDocument()
    expect(screen.getByLabelText('Mức độ tương tác: Mức độ thấp')).toBeInTheDocument()
    // "low" must not use the app's green/accent color, which reads as "safe".
    const lowBadge = screen.getByLabelText('Mức độ tương tác: Mức độ thấp')
    expect(lowBadge).toHaveStyle({ color: '#2563EB' })
  })

  test('same interaction data renders identically across different medicationName props (no per-drug branching)', () => {
    const { unmount } = render(
      <InteractionsCard medicationName="Metformin" interactions={oneInteraction} />
    )
    expect(screen.getByText('Ức chế enzyme chuyển hoá')).toBeInTheDocument()
    unmount()

    render(<InteractionsCard medicationName="Levothyroxine" interactions={oneInteraction} />)
    expect(screen.getByText('Ức chế enzyme chuyển hoá')).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { name: 'Levothyroxine tương tác với Warfarin' })
    ).toBeInTheDocument()
  })

  test('handles long mechanism/recommendation text without crashing', () => {
    const long = 'X'.repeat(400)
    render(
      <InteractionsCard
        medicationName="Metformin"
        interactions={[{ severity: 'moderate', interactingSubstance: 'Aspirin', mechanism: long }]}
      />
    )
    expect(screen.getByText(long)).toBeInTheDocument()
  })
})

describe('InteractionsCard — loading and error', () => {
  test('shows a loading indicator and no empty-state text while loading', () => {
    render(<InteractionsCard medicationName="Metformin" interactions={[]} loading />)
    expect(screen.getByLabelText('Đang tải dữ liệu tương tác thuốc')).toBeInTheDocument()
    expect(screen.queryByText(INTERACTIONS_EMPTY_STATE)).not.toBeInTheDocument()
  })

  test('shows the error message via role=alert, not the empty state', () => {
    render(
      <InteractionsCard medicationName="Metformin" interactions={[]} error="Không thể tải dữ liệu." />
    )
    expect(screen.getByRole('alert')).toHaveTextContent('Không thể tải dữ liệu.')
    expect(screen.queryByText(INTERACTIONS_EMPTY_STATE)).not.toBeInTheDocument()
  })
})
