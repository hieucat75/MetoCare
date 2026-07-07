import { render, screen } from '@testing-library/react'
import { SuggestedAdvice } from '../SuggestedAdvice'
import type { ClinicalAdviceOut } from '@/lib/api/clinicalCopilot'

function sampleData(): ClinicalAdviceOut {
  return {
    items: [
      { category: 'home_monitoring', text_vi: 'Đo đường huyết mỗi sáng trước ăn' },
      { category: 'explain_patient', text_vi: 'Giải thích ý nghĩa của chỉ số HbA1c' },
    ],
    confidence: 'medium',
    disclaimer: 'disc',
  }
}

test('groups advice items under Vietnamese category headings in the fixed order', () => {
  render(<SuggestedAdvice data={sampleData()} />)

  const headings = screen.getAllByText(/Giải thích cho bệnh nhân|Theo dõi tại nhà/)
  expect(headings.map((h) => h.textContent)).toEqual([
    'Giải thích cho bệnh nhân',
    'Theo dõi tại nhà',
  ])
  expect(screen.getByText('Đo đường huyết mỗi sáng trước ăn')).toBeInTheDocument()
  expect(screen.getByText('Giải thích ý nghĩa của chỉ số HbA1c')).toBeInTheDocument()
})

test('omits headings for categories with no items', () => {
  render(<SuggestedAdvice data={sampleData()} />)
  expect(screen.queryByText('Khi nào cần khám trực tiếp')).not.toBeInTheDocument()
  expect(screen.queryByText('Xét nghiệm/khám bổ sung (tham khảo)')).not.toBeInTheDocument()
})

test('renders "Không có dữ liệu." when there are no items', () => {
  render(<SuggestedAdvice data={{ items: [], confidence: 'low', disclaimer: 'disc' }} />)
  expect(screen.getByText('Không có dữ liệu.')).toBeInTheDocument()
})
