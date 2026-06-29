import { formatLabValue } from '../formatLabValue'

describe('formatLabValue', () => {
  test('returns dash for null', () => {
    expect(formatLabValue(null)).toBe('—')
  })

  test('returns dash for undefined', () => {
    expect(formatLabValue(undefined)).toBe('—')
  })

  // mg/dL → integer
  test('mg/dL rounds floating-point artifact to integer', () => {
    expect(formatLabValue(174.48289999999997, 'mg/dL')).toBe('174')
  })

  test('mg/dL case-insensitive', () => {
    expect(formatLabValue(100.7, 'mg/dl')).toBe('101')
  })

  test('mg/dL integer stays integer', () => {
    expect(formatLabValue(92, 'mg/dL')).toBe('92')
  })

  // mmol/L → 1 decimal
  test('mmol/L gives 1 decimal', () => {
    expect(formatLabValue(5.7321, 'mmol/L')).toBe('5.7')
  })

  test('mmol/L keeps trailing zero', () => {
    expect(formatLabValue(1.009, 'mmol/L')).toBe('1.0')
  })

  // % → 1 decimal
  test('percentage gives 1 decimal', () => {
    expect(formatLabValue(6.234, '%')).toBe('6.2')
  })

  // µmol/L → integer
  test('µmol/L rounds to integer', () => {
    expect(formatLabValue(88.5678, 'µmol/L')).toBe('89')
  })

  test('umol/L ASCII variant rounds to integer', () => {
    expect(formatLabValue(88.3, 'umol/L')).toBe('88')
  })

  // mmHg → integer
  test('mmHg rounds to integer', () => {
    expect(formatLabValue(120.9, 'mmHg')).toBe('121')
  })

  // bpm → integer
  test('bpm rounds to integer', () => {
    expect(formatLabValue(72.6, 'bpm')).toBe('73')
  })

  // kg/m² → 1 decimal (BMI)
  test('kg/m² gives 1 decimal', () => {
    expect(formatLabValue(22.456, 'kg/m²')).toBe('22.5')
  })

  test('kg/m2 alternate notation gives 1 decimal', () => {
    expect(formatLabValue(22.456, 'kg/m2')).toBe('22.5')
  })

  // temperature → 1 decimal
  test('°C gives 1 decimal', () => {
    expect(formatLabValue(36.789, '°C')).toBe('36.8')
  })

  // eGFR → integer
  test('mL/min rounds to integer for eGFR', () => {
    expect(formatLabValue(67.89, 'mL/min/1.73m²')).toBe('68')
  })

  // enzyme units → integer
  test('U/L rounds to integer', () => {
    expect(formatLabValue(45.7, 'U/L')).toBe('46')
  })

  // weight → 1 decimal
  test('kg gives 1 decimal', () => {
    expect(formatLabValue(68.456, 'kg')).toBe('68.5')
  })

  // blood cell counts
  test('G/L gives 1 decimal for WBC', () => {
    expect(formatLabValue(7.23, 'G/L')).toBe('7.2')
  })

  test('T/L gives 1 decimal for RBC', () => {
    expect(formatLabValue(4.845, 'T/L')).toBe('4.8')
  })

  // string input
  test('numeric string is parsed and formatted', () => {
    expect(formatLabValue('174.9', 'mg/dL')).toBe('175')
  })

  test('non-numeric string (e.g. "<5") passes through unchanged', () => {
    expect(formatLabValue('<5', 'µmol/L')).toBe('<5')
  })

  // no unit fallback
  test('integer without unit has no decimals', () => {
    expect(formatLabValue(120)).toBe('120')
  })

  test('float without unit shows 1 decimal', () => {
    expect(formatLabValue(5.678)).toBe('5.7')
  })
})
