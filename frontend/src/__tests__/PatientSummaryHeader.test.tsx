import { render, screen } from '@testing-library/react'
import {
  PatientSummaryHeader,
  type PatientProfile,
} from '@/design-system/components/healthcare/PatientSummaryHeader'

const base: PatientProfile = {
  id: 'p1',
  fullName: 'Nguyen Van A',
  dateOfBirth: '1990-01-01',
  gender: 'male',
  riskLevel: 'low',
  activePlanCount: 0,
  pendingReviewCount: 0,
}

describe('PatientSummaryHeader demographics', () => {
  it('renders gender + age when both present', () => {
    render(<PatientSummaryHeader patient={base} onBack={() => {}} />)
    // "Nam · <age> tuoi"
    expect(screen.getByText(/Nam/)).toBeInTheDocument()
    expect(screen.getByText(/tuoi/)).toBeInTheDocument()
  })

  it('does NOT fabricate age/gender when dob and gender are null', () => {
    render(
      <PatientSummaryHeader
        patient={{ ...base, dateOfBirth: null, gender: null }}
        onBack={() => {}}
      />,
    )
    expect(screen.getByText('Khong ro')).toBeInTheDocument()
    expect(screen.queryByText(/tuoi/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Nam/)).not.toBeInTheDocument()
  })

  it('shows only gender when dob is null', () => {
    render(
      <PatientSummaryHeader
        patient={{ ...base, dateOfBirth: null }}
        onBack={() => {}}
      />,
    )
    expect(screen.getByText('Nam')).toBeInTheDocument()
    expect(screen.queryByText(/tuoi/)).not.toBeInTheDocument()
  })
})
