import { render, screen } from '@testing-library/react'
import { PatientSummaryCard } from '../PatientSummaryCard'
import type { ClinicalSummaryOut } from '@/lib/api/clinicalCopilot'

function sampleData(overrides: Partial<ClinicalSummaryOut> = {}): ClinicalSummaryOut {
  return {
    as_of: '2026-07-07T00:00:00Z',
    conditions: ['Đái tháo đường type 2'],
    allergies: ['Penicillin'],
    medications: [{ name: 'Metformin', dosage: '500mg', frequency: '2 lần/ngày' }],
    abnormal_findings: [
      {
        metric_type: 'hba1c',
        label: 'HbA1c',
        status: 'high',
        value_display: '8.2%',
        trend_label: 'Tăng so với lần trước',
        priority: 'cao',
      },
    ],
    notable_changes: ['Cân nặng giảm 2kg'],
    sources: [{ type: 'lab', label: 'Xét nghiệm HbA1c', date: '2026-07-01' }],
    confidence: 'high',
    disclaimer: 'disc',
    ...overrides,
  }
}

test('renders conditions, medications, abnormal findings, and sources', () => {
  render(<PatientSummaryCard data={sampleData()} />)

  expect(screen.getByText('Đái tháo đường type 2')).toBeInTheDocument()
  expect(screen.getByText('Metformin')).toBeInTheDocument()
  expect(screen.getByText('500mg · 2 lần/ngày')).toBeInTheDocument()
  expect(screen.getByText('HbA1c')).toBeInTheDocument()
  expect(screen.getByText('Tăng so với lần trước · cao')).toBeInTheDocument()
  expect(screen.getByText(/Xét nghiệm HbA1c · 2026-07-01/)).toBeInTheDocument()
})

test('shows confidence as a subtle label, never prominent', () => {
  render(<PatientSummaryCard data={sampleData({ confidence: 'low' })} />)
  expect(screen.getByText('Độ tin cậy: thấp')).toBeInTheDocument()
})

test('does not crash and shows "Không có dữ liệu." for every empty list field', () => {
  render(
    <PatientSummaryCard
      data={sampleData({
        conditions: [],
        allergies: [],
        medications: [],
        abnormal_findings: [],
        notable_changes: [],
        sources: [],
      })}
    />
  )

  expect(screen.getAllByText('Không có dữ liệu.').length).toBeGreaterThan(0)
  expect(screen.queryByText('Nguồn')).not.toBeInTheDocument()
})
