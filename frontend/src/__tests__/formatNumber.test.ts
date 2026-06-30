/**
 * Tests for shared number formatter — @/lib/formatNumber
 *
 * Covers:
 *  - Each unit type from the spec table
 *  - Edge cases: NaN, null, undefined, 0, very large, very small
 *  - Unknown unit / default fallback
 *  - Case-insensitive unit matching
 *  - String input (numeric + non-numeric pass-through)
 *  - formatLabDisplay with and without unit
 */

import { formatLabValue, formatLabDisplay } from '../lib/formatNumber'

// ── formatLabValue ────────────────────────────────────────────────────────────

describe('formatLabValue — missing / invalid values', () => {
  test('returns "—" for null', () => {
    expect(formatLabValue(null)).toBe('—')
  })

  test('returns "—" for undefined', () => {
    expect(formatLabValue(undefined)).toBe('—')
  })

  test('returns "—" for NaN', () => {
    expect(formatLabValue(NaN)).toBe('—')
  })

  test('returns "—" for +Infinity', () => {
    expect(formatLabValue(Infinity)).toBe('—')
  })

  test('returns "—" for -Infinity', () => {
    expect(formatLabValue(-Infinity)).toBe('—')
  })
})

describe('formatLabValue — mg/dL (integer)', () => {
  test('rounds floating-point artifact to integer', () => {
    expect(formatLabValue(174.48289999999997, 'mg/dL')).toBe('174')
  })

  test('case-insensitive: mg/dl', () => {
    expect(formatLabValue(100.7, 'mg/dl')).toBe('101')
  })

  test('case-insensitive: MG/DL', () => {
    expect(formatLabValue(100.7, 'MG/DL')).toBe('101')
  })

  test('integer input stays integer', () => {
    expect(formatLabValue(92, 'mg/dL')).toBe('92')
  })

  test('zero', () => {
    expect(formatLabValue(0, 'mg/dL')).toBe('0')
  })

  test('very large value', () => {
    expect(formatLabValue(9999.9, 'mg/dL')).toBe('10000')
  })
})

describe('formatLabValue — mmol/L (1 decimal)', () => {
  test('1 decimal', () => {
    expect(formatLabValue(5.7321, 'mmol/L')).toBe('5.7')
  })

  test('keeps trailing zero', () => {
    expect(formatLabValue(1.009, 'mmol/L')).toBe('1.0')
  })

  test('case-insensitive: MMOL/L', () => {
    expect(formatLabValue(5.7321, 'MMOL/L')).toBe('5.7')
  })
})

describe('formatLabValue — % (1 decimal)', () => {
  test('HbA1c percentage', () => {
    expect(formatLabValue(6.234, '%')).toBe('6.2')
  })

  test('exactly 1 decimal', () => {
    expect(formatLabValue(6.1, '%')).toBe('6.1')
  })
})

describe('formatLabValue — BMI kg/m² (1 decimal)', () => {
  test('kg/m² gives 1 decimal', () => {
    expect(formatLabValue(22.456, 'kg/m²')).toBe('22.5')
  })

  test('kg/m2 alternate notation', () => {
    expect(formatLabValue(22.456, 'kg/m2')).toBe('22.5')
  })
})

describe('formatLabValue — mmHg / BP (integer)', () => {
  test('systolic', () => {
    expect(formatLabValue(120.9, 'mmHg')).toBe('121')
  })

  test('diastolic', () => {
    expect(formatLabValue(79.3, 'mmHg')).toBe('79')
  })

  test('case-insensitive: MMHG', () => {
    expect(formatLabValue(120.9, 'MMHG')).toBe('121')
  })
})

describe('formatLabValue — eGFR mL/min (integer)', () => {
  test('eGFR with extended unit', () => {
    expect(formatLabValue(67.89, 'mL/min/1.73m²')).toBe('68')
  })

  test('bare mL/min', () => {
    expect(formatLabValue(89.2, 'mL/min')).toBe('89')
  })
})

describe('formatLabValue — µmol/L (integer)', () => {
  test('unicode µmol/L', () => {
    expect(formatLabValue(88.5678, 'µmol/L')).toBe('89')
  })

  test('ASCII umol/L', () => {
    expect(formatLabValue(88.3, 'umol/L')).toBe('88')
  })

  test('alternate μmol/L', () => {
    expect(formatLabValue(44.7, 'μmol/L')).toBe('45')
  })
})

describe('formatLabValue — g/dL (2 decimals)', () => {
  test('haemoglobin 2 decimals', () => {
    expect(formatLabValue(14.5, 'g/dL')).toBe('14.50')
  })

  test('trailing zeros preserved', () => {
    expect(formatLabValue(14.00001, 'g/dL')).toBe('14.00')
  })

  test('case-insensitive: G/DL', () => {
    expect(formatLabValue(14.5, 'G/DL')).toBe('14.50')
  })
})

describe('formatLabValue — IU/L (integer)', () => {
  test('enzyme units U/L', () => {
    expect(formatLabValue(45.7, 'U/L')).toBe('46')
  })

  test('IU/L variant', () => {
    expect(formatLabValue(32.4, 'IU/L')).toBe('32')
  })
})

describe('formatLabValue — mIU/L (2 decimals)', () => {
  test('TSH mIU/L typical value', () => {
    expect(formatLabValue(2.543, 'mIU/L')).toBe('2.54')
  })

  test('TSH mIU/L very small value (0.03 must not collapse to 0.0)', () => {
    expect(formatLabValue(0.03, 'mIU/L')).toBe('0.03')
  })

  test('case-insensitive miu/l', () => {
    expect(formatLabValue(2.543, 'miu/l')).toBe('2.54')
  })
})

describe('formatLabValue — default / unknown unit', () => {
  test('small float with unknown unit → 2 decimals', () => {
    expect(formatLabValue(1.234, 'foobar')).toBe('1.23')
  })

  test('large float (≥10) with unknown unit → 1 decimal', () => {
    expect(formatLabValue(12.34, 'xyz')).toBe('12.3')
  })

  test('integer with unknown unit → 0 decimals', () => {
    expect(formatLabValue(42, 'xyz')).toBe('42')
  })

  test('no unit, integer → 0 decimals', () => {
    expect(formatLabValue(120)).toBe('120')
  })

  test('no unit, float → 1 decimal', () => {
    expect(formatLabValue(5.678)).toBe('5.7')
  })
})

describe('formatLabValue — string input', () => {
  test('numeric string parsed and formatted', () => {
    expect(formatLabValue('174.9', 'mg/dL')).toBe('175')
  })

  test('non-numeric string passes through unchanged', () => {
    expect(formatLabValue('<5', 'µmol/L')).toBe('<5')
  })

  test('non-numeric "negative" passes through', () => {
    expect(formatLabValue('negative', 'mg/dL')).toBe('negative')
  })

  test('empty string: parseFloat returns NaN → pass through', () => {
    // parseFloat('') === NaN, so the string is returned as-is
    expect(formatLabValue('')).toBe('')
  })
})

describe('formatLabValue — very small values', () => {
  test('0.001 with unknown unit → 2 decimals', () => {
    expect(formatLabValue(0.001, 'abc')).toBe('0.00')
  })

  test('0 with mg/dL → "0"', () => {
    expect(formatLabValue(0, 'mg/dL')).toBe('0')
  })
})

// ── formatLabDisplay ──────────────────────────────────────────────────────────

describe('formatLabDisplay', () => {
  test('appends unit after formatted value', () => {
    expect(formatLabDisplay(174.48289999999997, 'mg/dL')).toBe('174 mg/dL')
  })

  test('mmol/L', () => {
    expect(formatLabDisplay(5.7321, 'mmol/L')).toBe('5.7 mmol/L')
  })

  test('returns "—" for null (no unit suffix)', () => {
    expect(formatLabDisplay(null, 'mg/dL')).toBe('—')
  })

  test('returns "—" for undefined', () => {
    expect(formatLabDisplay(undefined, 'mg/dL')).toBe('—')
  })

  test('no unit → no suffix', () => {
    expect(formatLabDisplay(120, '')).toBe('120')
  })

  test('null unit → no suffix', () => {
    expect(formatLabDisplay(120, null)).toBe('120')
  })

  test('whitespace unit trimmed', () => {
    expect(formatLabDisplay(120, '  mmHg  ')).toBe('120 mmHg')
  })

  test('g/dL with 2 decimals + unit', () => {
    expect(formatLabDisplay(14.5, 'g/dL')).toBe('14.50 g/dL')
  })
})
