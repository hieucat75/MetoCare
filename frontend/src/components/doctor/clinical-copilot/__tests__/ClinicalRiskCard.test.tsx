import { render, screen } from '@testing-library/react'
import { ClinicalRiskCard } from '../ClinicalRiskCard'
import type { ClinicalAnalysisOut, RiskFlag, CitedClaim } from '@/lib/api/clinicalCopilot'

function sourcedClaim(overrides: Partial<CitedClaim> = {}): CitedClaim {
  return {
    text: 'Kiểm soát đường huyết chưa ổn định',
    sources: [{ id: 'src-1', type: 'metric', label: 'HbA1c', date: '2026-07-01' }],
    basis: 'sourced',
    confidence: 'high',
    ...overrides,
  }
}

function sampleData(
  priorityOverrides: Partial<RiskFlag> = {},
  analysisOverrides: Partial<ClinicalAnalysisOut> = {}
): ClinicalAnalysisOut {
  return {
    priority: {
      level: 'monitor',
      label_vi: 'Theo dõi',
      findings: ['Huyết áp tăng nhẹ'],
      missing_data: [],
      sources: [{ id: 'src-bp', type: 'metric', label: 'Huyết áp', date: '2026-07-01' }],
      ...priorityOverrides,
    },
    key_issues: [sourcedClaim()],
    contradictions_or_gaps: [
      sourcedClaim({ text: 'Không có ghi nhận về tuân thủ thuốc', sources: [] }),
    ],
    differentials_to_exclude: [sourcedClaim({ text: 'Suy giáp' })],
    missing_data: [{ category: 'labs', label_vi: 'Chưa có xét nghiệm lipid gần đây' }],
    confidence: 'medium',
    confidence_note_vi: null,
    disclaimer: 'disc',
    ...analysisOverrides,
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
        missing_data: [],
        confidence: 'high',
        confidence_note_vi: null,
        disclaimer: 'disc',
      }}
    />
  )

  expect(screen.getAllByText('Không có dữ liệu.').length).toBeGreaterThan(0)
  expect(screen.queryByText('Nguồn')).not.toBeInTheDocument()
})

test('renders per-item sources (label + date) for a CitedClaim with basis "sourced"', () => {
  render(<ClinicalRiskCard data={sampleData()} />)

  expect(screen.getAllByText(/HbA1c · 2026-07-01/).length).toBeGreaterThan(0)
})

test('shows "Cần xác nhận thêm" for a CitedClaim with basis "needs_confirmation" and empty sources', () => {
  render(
    <ClinicalRiskCard
      data={sampleData(
        {},
        {
          key_issues: [
            {
              text: 'Nghi ngờ thiếu tuân thủ điều trị',
              sources: [],
              basis: 'needs_confirmation',
              confidence: 'low',
            },
          ],
        }
      )}
    />
  )

  expect(screen.getByText('Nghi ngờ thiếu tuân thủ điều trị')).toBeInTheDocument()
  expect(screen.getByText('Cần xác nhận thêm')).toBeInTheDocument()
})

test('renders the real missing_data list with the provided label_vi strings', () => {
  render(
    <ClinicalRiskCard
      data={sampleData(
        {},
        {
          missing_data: [
            { category: 'labs', label_vi: 'Chưa có xét nghiệm lipid gần đây' },
            { category: 'allergies', label_vi: 'Chưa ghi nhận dị ứng' },
          ],
        }
      )}
    />
  )

  expect(screen.getByText('Chưa có xét nghiệm lipid gần đây')).toBeInTheDocument()
  expect(screen.getByText('Chưa ghi nhận dị ứng')).toBeInTheDocument()
})

test('shows the low-confidence banner prominently when confidence is "low"', () => {
  render(
    <ClinicalRiskCard
      data={sampleData(
        {},
        {
          confidence: 'low',
          confidence_note_vi: 'Phân tích này dựa trên dữ liệu hạn chế, cần thận trọng khi sử dụng.',
        }
      )}
    />
  )

  const banner = screen.getByTestId('low-confidence-banner')
  expect(banner).toBeInTheDocument()
  expect(
    screen.getByText('Phân tích này dựa trên dữ liệu hạn chế, cần thận trọng khi sử dụng.')
  ).toBeInTheDocument()
})

test('a SourceRef with date: null renders "không rõ thời điểm", distinct from a real date', () => {
  render(
    <ClinicalRiskCard
      data={sampleData({
        sources: [
          { id: 'src-a', type: 'metric', label: 'Cân nặng', date: null },
          { id: 'src-b', type: 'metric', label: 'Chiều cao', date: '2026-06-01' },
        ],
      })}
    />
  )

  expect(screen.getByText(/Cân nặng · không rõ thời điểm/)).toBeInTheDocument()
  expect(screen.getByText(/Chiều cao · 2026-06-01/)).toBeInTheDocument()
  expect(screen.queryByText(/Cân nặng ·\s*$/)).not.toBeInTheDocument()
})
