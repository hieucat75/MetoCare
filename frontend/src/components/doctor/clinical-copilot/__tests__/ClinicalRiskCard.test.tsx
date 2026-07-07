import { render, screen } from '@testing-library/react'
import { ClinicalRiskCard } from '../ClinicalRiskCard'
import type { ClinicalAnalysisOut, RiskFlag } from '@/lib/api/clinicalCopilot'

function sampleData(priorityOverrides: Partial<RiskFlag> = {}): ClinicalAnalysisOut {
  return {
    priority: {
      level: 'monitor',
      label_vi: 'Theo dõi',
      findings: ['Huyết áp tăng nhẹ'],
      missing_data: ['Chưa có xét nghiệm lipid gần đây'],
      sources: [{ type: 'metric', label: 'Huyết áp', date: '2026-07-01' }],
      ...priorityOverrides,
    },
    key_issues: ['Kiểm soát đường huyết chưa ổn định'],
    contradictions_or_gaps: ['Không có ghi nhận về tuân thủ thuốc'],
    differentials_to_exclude: ['Suy giáp'],
    confidence: 'medium',
    disclaimer: 'disc',
  }
}

test('renders findings, key issues, contradictions, and differentials', () => {
  render(<ClinicalRiskCard data={sampleData()} />)

  expect(screen.getByText('Huyết áp tăng nhẹ')).toBeInTheDocument()
  expect(screen.getByText('Kiểm soát đường huyết chưa ổn định')).toBeInTheDocument()
  expect(screen.getByText('Không có ghi nhận về tuân thủ thuốc')).toBeInTheDocument()
  expect(screen.getByText('Suy giáp')).toBeInTheDocument()
})

test('urgent level renders the emergency banner unconditionally, above the rest of the card', () => {
  render(<ClinicalRiskCard data={sampleData({ level: 'urgent', label_vi: 'Cần khám ngay' })} />)

  const banner = screen.getByTestId('urgent-risk-banner')
  expect(banner).toBeInTheDocument()
  expect(banner).toHaveAttribute('role', 'alert')
  expect(screen.getByText('Cảnh báo cấp cứu')).toBeInTheDocument()

  // The banner must be the first rendered element inside the card, not
  // collapsible or reorderable behind other insights.
  const card = banner.parentElement as HTMLElement
  expect(card.firstElementChild).toBe(banner)
})

test('non-urgent levels (monitor, see_doctor_soon, normal) never render the emergency banner', () => {
  for (const level of ['normal', 'monitor', 'see_doctor_soon'] as const) {
    const { unmount } = render(<ClinicalRiskCard data={sampleData({ level })} />)
    expect(screen.queryByTestId('urgent-risk-banner')).not.toBeInTheDocument()
    unmount()
  }
})

test('does not crash and shows "Không có dữ liệu." for every empty list field', () => {
  render(
    <ClinicalRiskCard
      data={{
        priority: {
          level: 'normal',
          label_vi: 'Bình thường',
          findings: [],
          missing_data: [],
          sources: [],
        },
        key_issues: [],
        contradictions_or_gaps: [],
        differentials_to_exclude: [],
        confidence: 'high',
        disclaimer: 'disc',
      }}
    />
  )

  expect(screen.getAllByText('Không có dữ liệu.').length).toBeGreaterThan(0)
  expect(screen.queryByText('Nguồn')).not.toBeInTheDocument()
})
