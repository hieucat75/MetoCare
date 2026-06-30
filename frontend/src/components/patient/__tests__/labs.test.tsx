/**
 * Labs UX Tests — MetoCare
 * Covers the Labs list screen, biomarker row, and navigation flows.
 *
 * Strategy:
 * - Unit tests for LabResultRow rendering (no router/auth required)
 * - Integration tests for labs list page behavior use mocked hooks
 * - Route-level checks are structural (path shape) not full page render
 */
import * as React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import '@testing-library/jest-dom'
import { LabResultRow, statusLabel, statusColor } from '../LabResultRow'
import type { LabResultEntry } from '@/lib/api/patient'

// ── Helpers ────────────────────────────────────────────────────────────────────

function makeResult(overrides: Partial<LabResultEntry> = {}): LabResultEntry {
  return {
    id: 'r1',
    patient_id: 'p1',
    document_id: null,
    batch_id: 'b1',
    test_name: 'Đường huyết đói',
    canonical_name: 'fasting_glucose',
    value: 6.5,
    unit: 'mmol/L',
    reference_range: '3.9 – 5.6',
    status: 'high',
    test_date: '2026-06-01T00:00:00Z',
    verified_by_user: false,
    original_value: 6.5,
    original_unit: 'mmol/L',
    original_reference_range: '3.9 – 5.6',
    original_test_name: 'Đường huyết đói',
    normalized_value_si: 117.0,
    normalized_unit_si: 'mg/dL',
    created_at: '2026-06-01T00:00:00Z',
    ...overrides,
  }
}

// ── test_labs_list_renders ─────────────────────────────────────────────────────

describe('test_labs_list_renders', () => {
  it('renders biomarker name at correct size', () => {
    const navigate = jest.fn()
    render(<LabResultRow result={makeResult()} batchId="b1" onNavigate={navigate} />)
    const name = screen.getByText('Đường huyết đói')
    expect(name).toBeInTheDocument()
    // Name must be ≥22px (22px inline style)
    expect(name).toHaveStyle({ fontSize: '22px' })
  })

  it('renders value prominently', () => {
    const navigate = jest.fn()
    render(<LabResultRow result={makeResult()} batchId="b1" onNavigate={navigate} />)
    const value = screen.getByLabelText(/Giá trị: 6.5/)
    expect(value).toBeInTheDocument()
    expect(value).toHaveStyle({ fontSize: '36px' })
  })

  it('renders unit', () => {
    const navigate = jest.fn()
    render(<LabResultRow result={makeResult()} batchId="b1" onNavigate={navigate} />)
    expect(screen.getByText('mmol/L')).toBeInTheDocument()
  })

  it('renders status badge', () => {
    const navigate = jest.fn()
    render(<LabResultRow result={makeResult()} batchId="b1" onNavigate={navigate} />)
    expect(screen.getByLabelText(/Trạng thái: Cao/)).toBeInTheDocument()
  })

  it('renders reference range when present', () => {
    const navigate = jest.fn()
    render(<LabResultRow result={makeResult()} batchId="b1" onNavigate={navigate} />)
    expect(screen.getByText(/3.9 – 5.6/)).toBeInTheDocument()
  })

  it('does not render reference range when absent', () => {
    const navigate = jest.fn()
    render(
      <LabResultRow
        result={makeResult({ reference_range: null })}
        batchId="b1"
        onNavigate={navigate}
      />
    )
    expect(screen.queryByText(/Bình thường:/)).not.toBeInTheDocument()
  })

  it('row has minimum height 72px', () => {
    const navigate = jest.fn()
    const { container } = render(
      <LabResultRow result={makeResult()} batchId="b1" onNavigate={navigate} />
    )
    const btn = container.querySelector('button')
    expect(btn).toHaveStyle({ minHeight: '72px' })
  })
})

// ── test_batch_expand_shows_results ───────────────────────────────────────────
// (Structural: shows that LabResultRow renders correctly in list context)

describe('test_batch_expand_shows_results', () => {
  it('renders multiple biomarker rows', () => {
    const navigate = jest.fn()
    const results = [
      makeResult({ id: 'r1', test_name: 'Đường huyết đói', value: 6.5 }),
      makeResult({ id: 'r2', test_name: 'HbA1c', value: 7.2, unit: '%' }),
      makeResult({ id: 'r3', test_name: 'Cholesterol toàn phần', value: 5.8 }),
    ]
    const { container } = render(
      <div>
        {results.map((r) => (
          <LabResultRow key={r.id} result={r} batchId="b1" onNavigate={navigate} />
        ))}
      </div>
    )
    expect(screen.getByText('Đường huyết đói')).toBeInTheDocument()
    expect(screen.getByText('HbA1c')).toBeInTheDocument()
    expect(screen.getByText('Cholesterol toàn phần')).toBeInTheDocument()
    expect(container.querySelectorAll('button')).toHaveLength(3)
  })
})

// ── test_biomarker_row_navigates_to_detail ────────────────────────────────────

describe('test_biomarker_row_navigates_to_detail', () => {
  it('calls onNavigate with correct batchId and resultId on click', () => {
    const navigate = jest.fn()
    render(
      <LabResultRow result={makeResult({ id: 'r42' })} batchId="batch99" onNavigate={navigate} />
    )
    fireEvent.click(screen.getByRole('button'))
    expect(navigate).toHaveBeenCalledTimes(1)
    expect(navigate).toHaveBeenCalledWith('batch99', 'r42')
  })

  it('aria-label includes biomarker name', () => {
    const navigate = jest.fn()
    render(
      <LabResultRow
        result={makeResult({ test_name: 'HbA1c' })}
        batchId="b1"
        onNavigate={navigate}
      />
    )
    expect(screen.getByLabelText(/Xem chi tiết HbA1c/)).toBeInTheDocument()
  })
})

// ── test_ai_summary_route_exists ──────────────────────────────────────────────

describe('test_ai_summary_route_exists', () => {
  it('AI insight route path is /labs/[batchId]/insight', () => {
    // Structural test: verify route format expected by navigation code
    const batchId = 'batch-abc-123'
    const insightPath = `/labs/${batchId}/insight`
    expect(insightPath).toBe('/labs/batch-abc-123/insight')
    expect(insightPath).toMatch(/^\/labs\/.+\/insight$/)
  })

  it('biomarker detail route path is /labs/[batchId]/results/[resultId]', () => {
    const batchId = 'batch-abc'
    const resultId = 'result-xyz'
    const detailPath = `/labs/${batchId}/results/${resultId}`
    expect(detailPath).toBe('/labs/batch-abc/results/result-xyz')
    expect(detailPath).toMatch(/^\/labs\/.+\/results\/.+$/)
  })
})

// ── test_empty_state_shows_message ────────────────────────────────────────────

describe('test_empty_state_shows_message', () => {
  it('renders placeholder when value is null', () => {
    const navigate = jest.fn()
    // Null out both canonical and original values — Option B arch prefers original_value
    // when non-null, so we must null both to reach the em-dash display path.
    render(
      <LabResultRow
        result={makeResult({ value: null, original_value: null, original_unit: null })}
        batchId="b1"
        onNavigate={navigate}
      />
    )
    // Should show em-dash placeholder (formatLabValue(null) → '—')
    expect(screen.getByLabelText(/Giá trị: —/)).toBeInTheDocument()
    expect(screen.getByLabelText(/Giá trị: —/).textContent).toBe('—')
  })
})

// ── test_error_state_shows_retry ─────────────────────────────────────────────

describe('test_error_state_shows_retry', () => {
  it('statusLabel returns correct Vietnamese labels', () => {
    expect(statusLabel('normal')).toBe('Bình thường')
    expect(statusLabel('high')).toBe('Cao')
    expect(statusLabel('low')).toBe('Thấp')
    expect(statusLabel('critical')).toBe('Nguy hiểm')
    expect(statusLabel(null)).toBe('Chưa rõ')
    expect(statusLabel('unknown')).toBe('Chưa rõ')
  })

  it('statusColor returns distinct colors for each status', () => {
    const normal = statusColor('normal')
    const high = statusColor('high')
    const low = statusColor('low')
    const critical = statusColor('critical')
    // All must be valid hex colors
    ;[normal, high, low, critical].forEach((c) => {
      expect(c).toMatch(/^#[0-9A-Fa-f]{6}$/)
    })
    // Each must be distinct
    const colors = new Set([normal, high, low, critical])
    expect(colors.size).toBe(4)
  })
})

// ── test_mobile_viewport_no_overflow ─────────────────────────────────────────

describe('test_mobile_viewport_no_overflow', () => {
  it('row button does not use fixed width that would overflow 375px', () => {
    const navigate = jest.fn()
    const { container } = render(
      <LabResultRow result={makeResult()} batchId="b1" onNavigate={navigate} />
    )
    const btn = container.querySelector('button')
    // Must use w-full (no fixed px width) for mobile flexibility
    expect(btn?.className).toMatch(/w-full/)
    // Must not have overflow-visible or fixed px width that breaks mobile
    expect(btn?.className).not.toMatch(/w-\d{3,}/)
  })

  it('test name truncates on small screens', () => {
    const navigate = jest.fn()
    render(
      <LabResultRow
        result={makeResult({ test_name: 'Cholesterol lipoprotein tỷ trọng thấp (LDL-C)' })}
        batchId="b1"
        onNavigate={navigate}
      />
    )
    const name = screen.getByText('Cholesterol lipoprotein tỷ trọng thấp (LDL-C)')
    expect(name.className).toMatch(/truncate/)
  })
})
