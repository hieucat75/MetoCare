/**
 * ExplanationSection Tests — Claude Clinical Explanation Frontend Integration
 * Tests all 10 required cases for safety, rendering, and API contract.
 */
import * as React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import '@testing-library/jest-dom'
import { ExplanationSection, isSafe } from '../ExplanationSection'
import type { LabExplanation } from '@/lib/api/patient'

// ── Helpers ────────────────────────────────────────────────────────────────────

function makeExplanation(overrides: Partial<LabExplanation> = {}): LabExplanation {
  return {
    explanation: 'Đường huyết của bạn hơi cao so với mức bình thường.',
    why_it_matters: 'Mức đường huyết này có thể liên quan đến tiền tiểu đường.',
    what_to_monitor: 'Theo dõi chế độ ăn và vận động hàng ngày.',
    what_to_ask_doctor: 'Tôi có cần xét nghiệm thêm không?',
    next_step: 'Hẹn gặp bác sĩ trong 3 tháng.',
    source: 'claude',
    validated: true,
    ...overrides,
  }
}

// ── Test 1: renders explanation when validated=true ────────────────────────────

describe('test_explanation_renders_when_validated', () => {
  it('renders explanation text when validated=true', () => {
    render(
      <ExplanationSection
        explanation={makeExplanation()}
        loading={false}
        error={false}
        onRetry={() => {}}
        biomarkerStatus="high"
      />
    )
    expect(screen.getByText(/hơi cao so với mức bình thường/)).toBeInTheDocument()
  })

  it('renders all sub-sections when present', () => {
    render(
      <ExplanationSection
        explanation={makeExplanation()}
        loading={false}
        error={false}
        onRetry={() => {}}
        biomarkerStatus="high"
      />
    )
    expect(screen.getByText('Ý nghĩa')).toBeInTheDocument()
    expect(screen.getByText('Cần theo dõi gì')).toBeInTheDocument()
    expect(screen.getByText('Nên hỏi bác sĩ')).toBeInTheDocument()
    expect(screen.getByText('Bước tiếp theo')).toBeInTheDocument()
  })

  it('renders AI disclaimer for claude source', () => {
    render(
      <ExplanationSection
        explanation={makeExplanation({ source: 'claude' })}
        loading={false}
        error={false}
        onRetry={() => {}}
        biomarkerStatus="high"
      />
    )
    expect(screen.getByText(/tạo bởi AI/)).toBeInTheDocument()
  })

  it('does not render AI disclaimer for deterministic_fallback source', () => {
    render(
      <ExplanationSection
        explanation={makeExplanation({ source: 'deterministic_fallback' })}
        loading={false}
        error={false}
        onRetry={() => {}}
        biomarkerStatus="high"
      />
    )
    expect(screen.queryByText(/tạo bởi AI/)).not.toBeInTheDocument()
  })
})

// ── Test 2: hides and shows fallback when validated=false ─────────────────────

describe('test_unvalidated_explanation_shows_fallback', () => {
  it('shows fallback text when validated=false', () => {
    render(
      <ExplanationSection
        explanation={makeExplanation({ validated: false })}
        loading={false}
        error={false}
        onRetry={() => {}}
        biomarkerStatus="high"
      />
    )
    expect(screen.getByText(/Vui lòng tham khảo bác sĩ/)).toBeInTheDocument()
  })

  it('does not show explanation content when validated=false', () => {
    render(
      <ExplanationSection
        explanation={makeExplanation({ validated: false })}
        loading={false}
        error={false}
        onRetry={() => {}}
        biomarkerStatus="high"
      />
    )
    expect(screen.queryByText(/hơi cao so với mức bình thường/)).not.toBeInTheDocument()
  })
})

// ── Test 3: frontend safety check — hides dangerous text for normal status ─────

describe('test_dangerous_text_for_normal_status_hidden', () => {
  it('hides explanation containing danger phrase when status is normal', () => {
    const dangerousExplanation = makeExplanation({
      explanation: 'Kết quả này rất nguy hiểm và cần cấp cứu ngay.',
      validated: true,
    })
    render(
      <ExplanationSection
        explanation={dangerousExplanation}
        loading={false}
        error={false}
        onRetry={() => {}}
        biomarkerStatus="normal"
      />
    )
    // Should show safe fallback, not the dangerous text
    expect(screen.getByText(/Vui lòng tham khảo bác sĩ/)).toBeInTheDocument()
    expect(screen.queryByText(/rất nguy hiểm/)).not.toBeInTheDocument()
  })

  it('hides explanation with alarm phrase when status is normal', () => {
    const alarmingExplanation = makeExplanation({
      explanation: 'Chỉ số này bất thường và đáng lo ngại.',
      validated: true,
    })
    render(
      <ExplanationSection
        explanation={alarmingExplanation}
        loading={false}
        error={false}
        onRetry={() => {}}
        biomarkerStatus="normal"
      />
    )
    expect(screen.getByText(/Vui lòng tham khảo bác sĩ/)).toBeInTheDocument()
    expect(screen.queryByText(/bất thường/)).not.toBeInTheDocument()
  })

  it('isSafe returns false for normal status with danger phrase', () => {
    const expl = makeExplanation({ explanation: 'Rất nguy hiểm, cần cấp cứu ngay.' })
    expect(isSafe(expl, 'normal')).toBe(false)
  })

  it('isSafe returns true for high status with urgent language', () => {
    const expl = makeExplanation({ explanation: 'Rất nguy hiểm, cần điều trị ngay.' })
    expect(isSafe(expl, 'high')).toBe(true)
  })

  it('isSafe returns false for borderline_high status with danger phrase', () => {
    const expl = makeExplanation({ explanation: 'Mức này rất nguy hiểm và cần cấp cứu.' })
    expect(isSafe(expl, 'borderline_high')).toBe(false)
  })
})

// ── Test 4: loading skeleton shown while fetching ─────────────────────────────

describe('test_loading_skeleton', () => {
  it('shows loading skeleton when loading=true', () => {
    render(
      <ExplanationSection
        explanation={null}
        loading={true}
        error={false}
        onRetry={() => {}}
        biomarkerStatus="normal"
      />
    )
    expect(screen.getByRole('status')).toBeInTheDocument()
    expect(screen.getByLabelText(/Đang tải giải thích/)).toBeInTheDocument()
  })

  it('does not show explanation content while loading', () => {
    render(
      <ExplanationSection
        explanation={makeExplanation()}
        loading={true}
        error={false}
        onRetry={() => {}}
        biomarkerStatus="high"
      />
    )
    // Loading takes priority; no explanation text shown
    expect(screen.queryByText(/hơi cao/)).not.toBeInTheDocument()
  })
})

// ── Test 5: error state with retry button ─────────────────────────────────────

describe('test_error_state_shows_retry', () => {
  it('shows error message when error=true', () => {
    render(
      <ExplanationSection
        explanation={null}
        loading={false}
        error={true}
        onRetry={() => {}}
        biomarkerStatus="normal"
      />
    )
    expect(screen.getByText(/Không thể tải giải thích/)).toBeInTheDocument()
  })

  it('shows retry button when error=true', () => {
    render(
      <ExplanationSection
        explanation={null}
        loading={false}
        error={true}
        onRetry={() => {}}
        biomarkerStatus="normal"
      />
    )
    expect(screen.getByRole('button', { name: /Thử lại/ })).toBeInTheDocument()
  })

  it('calls onRetry when retry button is clicked', () => {
    const onRetry = jest.fn()
    render(
      <ExplanationSection
        explanation={null}
        loading={false}
        error={true}
        onRetry={onRetry}
        biomarkerStatus="normal"
      />
    )
    fireEvent.click(screen.getByRole('button', { name: /Thử lại/ }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })
})

// ── Test 6: null explanation renders nothing (silent) ─────────────────────────

describe('test_null_explanation_renders_nothing', () => {
  it('renders nothing when explanation is null', () => {
    const { container } = render(
      <ExplanationSection
        explanation={null}
        loading={false}
        error={false}
        onRetry={() => {}}
        biomarkerStatus="normal"
      />
    )
    expect(container.firstChild).toBeNull()
  })
})

// ── Test 7: no Anthropic import in frontend ───────────────────────────────────

describe('test_no_anthropic_import_in_frontend', () => {
  it('ExplanationSection does not import the @anthropic-ai SDK', () => {
    // Structural test: only check actual SDK imports/requires, not comments
    const fs = require('fs')
    const path = require('path')
    const componentSource = fs.readFileSync(
      path.resolve(__dirname, '../ExplanationSection.tsx'),
      'utf-8'
    )
    expect(componentSource).not.toMatch(/from ['"]@anthropic-ai/)
    expect(componentSource).not.toMatch(/require\(['"]@anthropic-ai/)
    expect(componentSource).not.toMatch(/api\.anthropic\.com/)
  })

  it('patient.ts does not import the @anthropic-ai SDK', () => {
    const fs = require('fs')
    const path = require('path')
    const patientSource = fs.readFileSync(
      path.resolve(__dirname, '../../../lib/api/patient.ts'),
      'utf-8'
    )
    expect(patientSource).not.toMatch(/from ['"]@anthropic-ai/)
    expect(patientSource).not.toMatch(/require\(['"]@anthropic-ai/)
    expect(patientSource).not.toMatch(/api\.anthropic\.com/)
  })
})

// ── Test 8: API client calls correct backend endpoint ─────────────────────────

describe('test_api_client_calls_backend_not_anthropic', () => {
  it('getLabResultExplanation constructs correct backend URL pattern', () => {
    // Structural test: verify endpoint format in source
    const fs = require('fs')
    const path = require('path')
    const patientSource = fs.readFileSync(
      path.resolve(__dirname, '../../../lib/api/patient.ts'),
      'utf-8'
    )
    // Must contain the backend explanation endpoint pattern
    expect(patientSource).toMatch(/patients.*lab-results.*explanation/)
    // Must NOT reference anthropic API URL
    expect(patientSource).not.toMatch(/api\.anthropic\.com/)
    // Must not import @anthropic-ai SDK
    expect(patientSource).not.toMatch(/from ['"]@anthropic-ai/)
  })

  it('API call uses api.get (backend client) not direct fetch to external AI', () => {
    const fs = require('fs')
    const path = require('path')
    const patientSource = fs.readFileSync(
      path.resolve(__dirname, '../../../lib/api/patient.ts'),
      'utf-8'
    )
    // Must use api.get somewhere in the file (routes through backend)
    expect(patientSource).toMatch(/api\.get/)
    // Function must exist
    expect(patientSource).toMatch(/getLabResultExplanation/)
    // URL must contain /explanation
    expect(patientSource).toMatch(/\/explanation/)
    // Must NOT call anthropic.com directly
    expect(patientSource).not.toMatch(/api\.anthropic\.com/)
  })
})

// ── Test 9: Glucose 5.7 borderline — explanation text does not say dangerous ──

describe('test_glucose_borderline_explanation_not_dangerous', () => {
  it('borderline glucose explanation shows without safety block for borderline_high status', () => {
    const borderlineExplanation = makeExplanation({
      explanation: 'Đường huyết 5.7 mmol/L hơi cao so với mức bình thường (3.9-5.6). Đây là mức tiền tiểu đường cần theo dõi.',
      why_it_matters: 'Cần theo dõi để phòng ngừa tiểu đường type 2.',
      next_step: 'Điều chỉnh chế độ ăn và tập thể dục.',
      source: 'claude',
      validated: true,
    })
    render(
      <ExplanationSection
        explanation={borderlineExplanation}
        loading={false}
        error={false}
        onRetry={() => {}}
        biomarkerStatus="borderline_high"
      />
    )
    // Should show explanation (not blocked)
    expect(screen.getByText(/hơi cao/)).toBeInTheDocument()
    // Must not contain dangerous language
    expect(screen.queryByText(/rất nguy hiểm/)).not.toBeInTheDocument()
    expect(screen.queryByText(/cần cấp cứu/)).not.toBeInTheDocument()
  })

  it('isSafe passes for borderline_high with appropriate language', () => {
    const expl = makeExplanation({
      explanation: 'Hơi cao, tiền tiểu đường, cần theo dõi.',
      why_it_matters: 'Mức này nằm trong vùng tiền tiểu đường.',
    })
    expect(isSafe(expl, 'borderline_high')).toBe(true)
  })
})

// ── Test 10: Glucose 502 critical — explanation allowed to say urgent ──────────

describe('test_glucose_critical_explanation_can_be_urgent', () => {
  it('critical glucose explanation with urgent language is allowed to show', () => {
    const criticalExplanation = makeExplanation({
      explanation: 'Đường huyết 502 mg/dL rất nguy hiểm. Cần khẩn cấp điều trị ngay.',
      why_it_matters: 'Mức này có thể gây hôn mê đái tháo đường.',
      next_step: 'Đến cơ sở y tế ngay lập tức.',
      source: 'claude',
      validated: true,
    })
    render(
      <ExplanationSection
        explanation={criticalExplanation}
        loading={false}
        error={false}
        onRetry={() => {}}
        biomarkerStatus="critical"
      />
    )
    // Critical status — urgent language is appropriate and should display
    expect(screen.getByText(/502 mg\/dL rất nguy hiểm/)).toBeInTheDocument()
  })

  it('isSafe returns true for critical status with urgent language', () => {
    const expl = makeExplanation({
      explanation: 'Rất nguy hiểm. Cần cấp cứu ngay. Khẩn cấp.',
    })
    // critical is not in nonCriticalStatuses, so danger phrases are allowed
    expect(isSafe(expl, 'critical')).toBe(true)
  })

  it('isSafe returns true for high status with urgent language', () => {
    const expl = makeExplanation({
      explanation: 'Mức triglyceride 502 mg/dL rất nguy hiểm cho tim mạch.',
    })
    expect(isSafe(expl, 'high')).toBe(true)
  })
})
