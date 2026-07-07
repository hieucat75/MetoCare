import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SuggestedQuestions } from '../SuggestedQuestions'
import type { ClinicalQuestionsOut } from '@/lib/api/clinicalCopilot'

function sampleData(): ClinicalQuestionsOut {
  return {
    questions: [
      {
        group: 'current_symptoms',
        question_vi: 'Anh/chị có thấy khát nước nhiều hơn bình thường không?',
        reason_vi: 'Đánh giá triệu chứng tăng đường huyết',
      },
      {
        group: 'medication_adherence',
        question_vi: 'Anh/chị có uống thuốc đều đặn mỗi ngày không?',
        reason_vi: 'Đánh giá tuân thủ điều trị',
      },
    ],
    missing_data: [],
    confidence: 'medium',
    confidence_note_vi: null,
    disclaimer: 'disc',
  }
}

test('groups questions under Vietnamese group headings in the fixed order', () => {
  render(<SuggestedQuestions data={sampleData()} />)

  const headings = screen.getAllByText(/Triệu chứng hiện tại|Thuốc và tuân thủ điều trị/)
  expect(headings.map((h) => h.textContent)).toEqual([
    'Triệu chứng hiện tại',
    'Thuốc và tuân thủ điều trị',
  ])
  expect(
    screen.getByText('Anh/chị có thấy khát nước nhiều hơn bình thường không?')
  ).toBeInTheDocument()
  expect(screen.getByText('Đánh giá tuân thủ điều trị')).toBeInTheDocument()
})

test('marking a question "Đã hỏi" strikes it through, and toggling off restores it', async () => {
  const user = userEvent.setup()
  render(<SuggestedQuestions data={sampleData()} />)

  const question = screen.getByText('Anh/chị có thấy khát nước nhiều hơn bình thường không?')
  const askedButtons = screen.getAllByRole('button', { name: 'Đã hỏi' })

  await user.click(askedButtons[0])
  expect(question).toHaveClass('line-through')

  await user.click(askedButtons[0])
  expect(question).not.toHaveClass('line-through')
})

test('marking a question "Bỏ qua" greys it out', async () => {
  const user = userEvent.setup()
  render(<SuggestedQuestions data={sampleData()} />)

  const skipButtons = screen.getAllByRole('button', { name: 'Bỏ qua' })
  await user.click(skipButtons[0])

  expect(skipButtons[0]).toHaveAttribute('aria-pressed', 'true')
})

test('renders "Không có dữ liệu." when there are no questions', () => {
  render(
    <SuggestedQuestions
      data={{ questions: [], missing_data: [], confidence: 'low', disclaimer: 'disc' }}
    />
  )
  expect(screen.getByText('Không có dữ liệu.')).toBeInTheDocument()
})

test('shows the low-confidence note prominently when confidence is "low"', () => {
  render(
    <SuggestedQuestions
      data={{
        ...sampleData(),
        confidence: 'low',
        confidence_note_vi: 'Gợi ý này dựa trên dữ liệu hạn chế.',
      }}
    />
  )

  expect(screen.getByTestId('low-confidence-banner')).toBeInTheDocument()
  expect(screen.getByText('Gợi ý này dựa trên dữ liệu hạn chế.')).toBeInTheDocument()
})
