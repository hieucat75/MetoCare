/**
 * MedicationNameAutocomplete — drug library autocomplete (name lookup only).
 *
 * Verifies the spec's frontend acceptance points:
 *  - typing 2+ chars calls the suggest endpoint (debounced)
 *  - suggestions render with primary + secondary text
 *  - selecting a suggestion fills the input (onChange) and reports the item
 *  - free-text entry is always allowed
 *  - empty result and API error keep the input usable
 *  - prescription tag shows; NO prescribing/dose copy appears
 */
import * as React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom'
import { MedicationNameAutocomplete, MEDICATION_SAFETY_NOTICE } from '../MedicationNameAutocomplete'
import type { DrugSuggestItem } from '@/lib/api/patient'
import * as patientApi from '@/lib/api/patient'

jest.mock('@/lib/api/patient', () => ({
  __esModule: true,
  suggestMedications: jest.fn(),
}))

const mockSuggest = patientApi.suggestMedications as jest.MockedFunction<
  typeof patientApi.suggestMedications
>

function makeItem(overrides: Partial<DrugSuggestItem> = {}): DrugSuggestItem {
  return {
    id: 'metformin',
    display_name: 'Metformin',
    generic_name: 'metformin',
    matched_name: 'metformin',
    brand_names: ['Glucophage'],
    drug_class: 'biguanide',
    metric_groups: ['diabetes'],
    prescription_required: true,
    caution_flags: [],
    confidence_score: 95,
    safety_notice: MEDICATION_SAFETY_NOTICE,
    ...overrides,
  }
}

function resolveWith(items: DrugSuggestItem[]) {
  mockSuggest.mockResolvedValue({
    query: 'q',
    metric_group: null,
    results: items,
    total: items.length,
  })
}

/** Controlled harness mirroring how the modal owns `name` state. */
function Harness({
  onSelect,
  initial = '',
}: {
  onSelect?: (item: DrugSuggestItem) => void
  initial?: string
}) {
  const [value, setValue] = React.useState(initial)
  return (
    <MedicationNameAutocomplete
      value={value}
      onChange={setValue}
      onSelect={onSelect}
      placeholder="VD: Metformin"
    />
  )
}

beforeEach(() => {
  mockSuggest.mockReset()
})

describe('MedicationNameAutocomplete', () => {
  it('does not call the suggest endpoint for fewer than 2 characters', async () => {
    resolveWith([])
    render(<Harness />)
    const input = screen.getByPlaceholderText('VD: Metformin')
    fireEvent.change(input, { target: { value: 'm' } })
    // Wait past the debounce window
    await new Promise((r) => setTimeout(r, 400))
    expect(mockSuggest).not.toHaveBeenCalled()
  })

  it('calls the suggest endpoint after typing 2+ characters and renders results', async () => {
    resolveWith([
      makeItem(),
      makeItem({
        id: 'gliclazide',
        display_name: 'Gliclazide',
        generic_name: 'gliclazide',
        prescription_required: true,
      }),
    ])
    render(<Harness />)
    const input = screen.getByPlaceholderText('VD: Metformin')
    fireEvent.change(input, { target: { value: 'met' } })

    expect(await screen.findByText('Metformin')).toBeInTheDocument()
    expect(mockSuggest).toHaveBeenCalledWith('met', expect.objectContaining({ limit: 10 }))
  })

  it('shows the "Thuốc kê đơn" tag for prescription drugs and a generic/class subtitle', async () => {
    resolveWith([
      makeItem({ display_name: 'Crestor', generic_name: 'rosuvastatin', drug_class: 'statin' }),
    ])
    render(<Harness />)
    fireEvent.change(screen.getByPlaceholderText('VD: Metformin'), {
      target: { value: 'crestor' },
    })

    expect(await screen.findByText('Crestor')).toBeInTheDocument()
    expect(screen.getByText('Thuốc kê đơn')).toBeInTheDocument()
    expect(screen.getByText(/rosuvastatin/)).toBeInTheDocument()
  })

  it('fills the input with display_name and reports the item when a suggestion is selected', async () => {
    const item = makeItem({ display_name: 'Crestor', generic_name: 'rosuvastatin' })
    resolveWith([item])
    const onSelect = jest.fn()
    render(<Harness onSelect={onSelect} />)
    const input = screen.getByPlaceholderText('VD: Metformin') as HTMLInputElement
    fireEvent.change(input, { target: { value: 'crestor' } })

    const option = await screen.findByText('Crestor')
    fireEvent.mouseDown(option)

    await waitFor(() => expect(input.value).toBe('Crestor'))
    expect(onSelect).toHaveBeenCalledWith(item)
  })

  it('always allows free-text entry (typing updates the value without a selection)', async () => {
    resolveWith([])
    render(<Harness />)
    const input = screen.getByPlaceholderText('VD: Metformin') as HTMLInputElement
    fireEvent.change(input, { target: { value: 'Thuốc nam gia truyền' } })
    expect(input.value).toBe('Thuốc nam gia truyền')
  })

  it('shows an empty-result message and keeps the input usable', async () => {
    resolveWith([])
    render(<Harness />)
    const input = screen.getByPlaceholderText('VD: Metformin') as HTMLInputElement
    fireEvent.change(input, { target: { value: 'zzzzz' } })

    expect(await screen.findByText(/Không tìm thấy thuốc phù hợp/)).toBeInTheDocument()
    // Input still editable
    fireEvent.change(input, { target: { value: 'zzzzz x' } })
    expect(input.value).toBe('zzzzz x')
  })

  it('handles an API error gracefully and keeps free-text usable', async () => {
    mockSuggest.mockRejectedValue(new Error('500'))
    render(<Harness />)
    const input = screen.getByPlaceholderText('VD: Metformin') as HTMLInputElement
    fireEvent.change(input, { target: { value: 'met' } })

    expect(await screen.findByText(/Không tải được gợi ý/)).toBeInTheDocument()
    fireEvent.change(input, { target: { value: 'metf' } })
    expect(input.value).toBe('metf')
  })

  it('never renders dosing or prescribing recommendation copy in suggestions', async () => {
    resolveWith([makeItem({ display_name: 'Metformin', generic_name: 'metformin' })])
    render(<Harness />)
    fireEvent.change(screen.getByPlaceholderText('VD: Metformin'), { target: { value: 'met' } })
    await screen.findByText('Metformin')

    const banned = [/nên dùng/i, /liều/i, /\bmg\b/i, /ngày \d+ lần/i, /khuyến nghị/i, /bắt đầu/i]
    for (const re of banned) {
      expect(screen.queryByText(re)).not.toBeInTheDocument()
    }
  })

  it('exports a safety notice with no prescribing directive', () => {
    expect(MEDICATION_SAFETY_NOTICE).toMatch(/chỉ để nhận diện tên thuốc/)
    expect(MEDICATION_SAFETY_NOTICE).not.toMatch(/nên dùng/i)
  })
})
