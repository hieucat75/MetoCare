/**
 * MedicationOverflowMenu (M2) — Hero action-sheet consolidating
 * Tạm ngưng/Tiếp tục uống, Ngừng thuốc, Sửa, Xoá.
 *
 * Verifies the product decision this component encodes:
 *  - active meds offer Tạm ngưng; paused meds offer Tiếp tục uống instead
 *  - on_hold/terminal meds offer nothing (doctor-locked or history-only —
 *    matches the pre-existing MedRow restriction this consolidates)
 *  - Escape closes the sheet (a11y, matches DiscontinueModal/MedModal)
 *  - selecting an item closes the sheet and fires its handler
 */
import * as React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import '@testing-library/jest-dom'
import { MedicationOverflowMenu } from '../overflow-menu'
import type { Medication } from '@/lib/api/patient'

function makeMedication(overrides: Partial<Medication> = {}): Medication {
  return {
    id: 'med-1',
    patient_id: 'patient-1',
    name: 'Metformin',
    dose: '500mg',
    frequency: '2 lần/ngày',
    note: null,
    created_at: '2026-01-01T00:00:00Z',
    lifecycle_status: 'active',
    verification_status: 'unverified',
    source_type: 'patient_reported',
    medication_category: 'prescription',
    status_reason: null,
    ...overrides,
  }
}

function noop() {}

describe('MedicationOverflowMenu', () => {
  test('renders nothing when closed', () => {
    const { container } = render(
      <MedicationOverflowMenu
        open={false}
        onClose={noop}
        med={makeMedication()}
        busy={false}
        onTogglePause={noop}
        onDiscontinue={noop}
        onEdit={noop}
        onDelete={noop}
      />
    )
    expect(container).toBeEmptyDOMElement()
  })

  test('active medication offers Tạm ngưng, Ngừng thuốc, Sửa, Xoá', () => {
    render(
      <MedicationOverflowMenu
        open
        onClose={noop}
        med={makeMedication({ lifecycle_status: 'active' })}
        busy={false}
        onTogglePause={noop}
        onDiscontinue={noop}
        onEdit={noop}
        onDelete={noop}
      />
    )
    expect(screen.getByText('Tạm ngưng')).toBeInTheDocument()
    expect(screen.getByText('Ngừng thuốc')).toBeInTheDocument()
    expect(screen.getByText('Sửa')).toBeInTheDocument()
    expect(screen.getByText('Xoá')).toBeInTheDocument()
    expect(screen.queryByText('Tiếp tục uống')).not.toBeInTheDocument()
  })

  test('paused medication offers Tiếp tục uống instead of Tạm ngưng', () => {
    render(
      <MedicationOverflowMenu
        open
        onClose={noop}
        med={makeMedication({ lifecycle_status: 'paused' })}
        busy={false}
        onTogglePause={noop}
        onDiscontinue={noop}
        onEdit={noop}
        onDelete={noop}
      />
    )
    expect(screen.getByText('Tiếp tục uống')).toBeInTheDocument()
    expect(screen.getByText('Ngừng thuốc')).toBeInTheDocument()
    expect(screen.getByText('Sửa')).toBeInTheDocument()
    expect(screen.getByText('Xoá')).toBeInTheDocument()
    expect(screen.queryByText('Tạm ngưng')).not.toBeInTheDocument()
  })

  test('on_hold medication offers no management actions (doctor-locked)', () => {
    render(
      <MedicationOverflowMenu
        open
        onClose={noop}
        med={makeMedication({ lifecycle_status: 'on_hold' })}
        busy={false}
        onTogglePause={noop}
        onDiscontinue={noop}
        onEdit={noop}
        onDelete={noop}
      />
    )
    expect(screen.queryByText('Tạm ngưng')).not.toBeInTheDocument()
    expect(screen.queryByText('Tiếp tục uống')).not.toBeInTheDocument()
    expect(screen.queryByText('Ngừng thuốc')).not.toBeInTheDocument()
    expect(screen.queryByText('Sửa')).not.toBeInTheDocument()
    expect(screen.queryByText('Xoá')).not.toBeInTheDocument()
    // Only the close affordance remains
    expect(screen.getByText('Đóng')).toBeInTheDocument()
  })

  test('terminal medication (discontinued) offers no management actions', () => {
    render(
      <MedicationOverflowMenu
        open
        onClose={noop}
        med={makeMedication({ lifecycle_status: 'discontinued' })}
        busy={false}
        onTogglePause={noop}
        onDiscontinue={noop}
        onEdit={noop}
        onDelete={noop}
      />
    )
    expect(screen.queryByText('Sửa')).not.toBeInTheDocument()
    expect(screen.queryByText('Xoá')).not.toBeInTheDocument()
  })

  test('selecting an item closes the sheet and fires its handler', () => {
    const onClose = jest.fn()
    const onEdit = jest.fn()
    render(
      <MedicationOverflowMenu
        open
        onClose={onClose}
        med={makeMedication()}
        busy={false}
        onTogglePause={noop}
        onDiscontinue={noop}
        onEdit={onEdit}
        onDelete={noop}
      />
    )
    fireEvent.click(screen.getByText('Sửa'))
    expect(onClose).toHaveBeenCalledTimes(1)
    expect(onEdit).toHaveBeenCalledTimes(1)
  })

  test('Escape key closes the sheet', () => {
    const onClose = jest.fn()
    render(
      <MedicationOverflowMenu
        open
        onClose={onClose}
        med={makeMedication()}
        busy={false}
        onTogglePause={noop}
        onDiscontinue={noop}
        onEdit={noop}
        onDelete={noop}
      />
    )
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  test('Tab wraps from the last item back to the first (focus trap)', () => {
    render(
      <MedicationOverflowMenu
        open
        onClose={noop}
        med={makeMedication()}
        busy={false}
        onTogglePause={noop}
        onDiscontinue={noop}
        onEdit={noop}
        onDelete={noop}
      />
    )
    const buttons = screen.getAllByRole('button')
    const last = buttons[buttons.length - 1]
    const first = buttons[0]
    last.focus()
    expect(document.activeElement).toBe(last)
    fireEvent.keyDown(window, { key: 'Tab' })
    expect(document.activeElement).toBe(first)
  })

  test('Shift+Tab wraps from the first item back to the last (focus trap)', () => {
    render(
      <MedicationOverflowMenu
        open
        onClose={noop}
        med={makeMedication()}
        busy={false}
        onTogglePause={noop}
        onDiscontinue={noop}
        onEdit={noop}
        onDelete={noop}
      />
    )
    const buttons = screen.getAllByRole('button')
    const last = buttons[buttons.length - 1]
    const first = buttons[0]
    first.focus()
    expect(document.activeElement).toBe(first)
    fireEvent.keyDown(window, { key: 'Tab', shiftKey: true })
    expect(document.activeElement).toBe(last)
  })

  test('disables all action items while busy', () => {
    render(
      <MedicationOverflowMenu
        open
        onClose={noop}
        med={makeMedication()}
        busy
        onTogglePause={noop}
        onDiscontinue={noop}
        onEdit={noop}
        onDelete={noop}
      />
    )
    expect(screen.getByText('Tạm ngưng').closest('button')).toBeDisabled()
    expect(screen.getByText('Sửa').closest('button')).toBeDisabled()
  })
})
