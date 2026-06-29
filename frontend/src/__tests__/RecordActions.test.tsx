/**
 * RecordActions component tests — P0 Health Record Edit & Delete
 *
 * Tests:
 *  1. Renders a trigger button (three-dot menu)
 *  2. Clicking the trigger opens the dropdown
 *  3. "Sửa" menu item calls onEdit callback
 *  4. "Xóa" menu item calls onDelete callback
 *  5. DeleteConfirmDialog opens on delete click (via parent wiring)
 *  6. DeleteConfirmDialog confirm button calls onConfirm
 *  7. DeleteConfirmDialog cancel button calls onCancel
 *  8. Trigger button has accessible aria-label
 */

import * as React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom'
import { RecordActions } from '@/components/records/RecordActions'
import { DeleteConfirmDialog } from '@/components/records/DeleteConfirmDialog'

// ── Helpers ───────────────────────────────────────────────────────────────────

function renderActions(
  onEdit: () => void = jest.fn(),
  onDelete: () => void = jest.fn(),
  label = 'mg/dL',
) {
  return render(<RecordActions onEdit={onEdit} onDelete={onDelete} label={label} />)
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('RecordActions', () => {
  test('renders a trigger button', () => {
    renderActions()
    // The MoreHorizontal icon trigger should be in the DOM
    const trigger = screen.getByRole('button')
    expect(trigger).toBeInTheDocument()
  })

  test('trigger button has an accessible aria-label', () => {
    renderActions(jest.fn(), jest.fn(), 'mg/dL')
    const trigger = screen.getByRole('button')
    expect(trigger).toHaveAttribute('aria-label')
    expect(trigger.getAttribute('aria-label')).toContain('mg/dL')
  })

  test('clicking trigger opens dropdown with Sửa and Xóa', async () => {
    renderActions()
    const trigger = screen.getByRole('button')
    fireEvent.click(trigger)
    await waitFor(() => {
      expect(screen.getByText('Sửa')).toBeInTheDocument()
      expect(screen.getByText('Xóa')).toBeInTheDocument()
    })
  })

  test('clicking Sửa calls onEdit callback', async () => {
    const onEdit = jest.fn()
    renderActions(onEdit)
    const trigger = screen.getByRole('button')
    fireEvent.click(trigger)
    await waitFor(() => screen.getByText('Sửa'))
    fireEvent.click(screen.getByText('Sửa'))
    expect(onEdit).toHaveBeenCalledTimes(1)
  })

  test('clicking Xóa calls onDelete callback', async () => {
    const onDelete = jest.fn()
    renderActions(jest.fn(), onDelete)
    const trigger = screen.getByRole('button')
    fireEvent.click(trigger)
    await waitFor(() => screen.getByText('Xóa'))
    fireEvent.click(screen.getByText('Xóa'))
    expect(onDelete).toHaveBeenCalledTimes(1)
  })

  test('renders without label prop', () => {
    const { container } = render(
      <RecordActions onEdit={jest.fn()} onDelete={jest.fn()} />
    )
    expect(container.querySelector('button')).toBeInTheDocument()
  })
})

// ── DeleteConfirmDialog tests ─────────────────────────────────────────────────

describe('DeleteConfirmDialog', () => {
  test('does not render when isOpen=false', () => {
    render(
      <DeleteConfirmDialog
        isOpen={false}
        onConfirm={jest.fn()}
        onCancel={jest.fn()}
      />
    )
    expect(screen.queryByText('Xóa bản ghi sức khỏe này?')).not.toBeInTheDocument()
  })

  test('renders title and description when isOpen=true', () => {
    render(
      <DeleteConfirmDialog
        isOpen
        onConfirm={jest.fn()}
        onCancel={jest.fn()}
      />
    )
    expect(screen.getByText('Xóa bản ghi sức khỏe này?')).toBeInTheDocument()
    expect(screen.getByText('Thao tác này không thể hoàn tác.')).toBeInTheDocument()
  })

  test('custom title and description are shown', () => {
    render(
      <DeleteConfirmDialog
        isOpen
        onConfirm={jest.fn()}
        onCancel={jest.fn()}
        title="Xóa kết quả xét nghiệm?"
        description="Không thể khôi phục."
      />
    )
    expect(screen.getByText('Xóa kết quả xét nghiệm?')).toBeInTheDocument()
    expect(screen.getByText('Không thể khôi phục.')).toBeInTheDocument()
  })

  test('clicking Xóa confirm button calls onConfirm', () => {
    const onConfirm = jest.fn()
    render(
      <DeleteConfirmDialog
        isOpen
        onConfirm={onConfirm}
        onCancel={jest.fn()}
      />
    )
    // Find the danger red button
    const buttons = screen.getAllByRole('button')
    const confirmBtn = buttons.find((b) => b.textContent === 'Xóa')
    expect(confirmBtn).toBeDefined()
    fireEvent.click(confirmBtn!)
    expect(onConfirm).toHaveBeenCalledTimes(1)
  })

  test('clicking Huỷ cancel button calls onCancel', () => {
    const onCancel = jest.fn()
    render(
      <DeleteConfirmDialog
        isOpen
        onConfirm={jest.fn()}
        onCancel={onCancel}
      />
    )
    const cancelBtn = screen.getByText('Huỷ')
    fireEvent.click(cancelBtn)
    expect(onCancel).toHaveBeenCalledTimes(1)
  })

  test('loading state disables buttons and shows spinner', () => {
    render(
      <DeleteConfirmDialog
        isOpen
        onConfirm={jest.fn()}
        onCancel={jest.fn()}
        loading
      />
    )
    const buttons = screen.getAllByRole('button')
    for (const btn of buttons) {
      expect(btn).toBeDisabled()
    }
    // Spinner should be present (animate-spin class)
    expect(document.querySelector('.animate-spin')).toBeInTheDocument()
  })
})
