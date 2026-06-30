/**
 * Tests for MetoAura component.
 * Verifies correct rendering across states and sizes.
 */
import * as React from 'react'
import { render, screen } from '@testing-library/react'
import { MetoAura, type MetoState } from '@/components/patient/meto/MetoAura'

describe('MetoAura', () => {
  it('renders without crashing', () => {
    render(<MetoAura />)
    // The component renders as aria-hidden so we verify via container
    const { container } = render(<MetoAura />)
    expect(container.firstChild).toBeTruthy()
  })

  it('applies idle state animation class by default', () => {
    const { container } = render(<MetoAura state="idle" />)
    const el = container.firstChild as HTMLElement
    expect(el.className).toContain('meto-breathe')
  })

  it('applies thinking state animation class', () => {
    const { container } = render(<MetoAura state="thinking" />)
    const el = container.firstChild as HTMLElement
    expect(el.className).toContain('meto-pulse')
  })

  it('applies answering state animation class', () => {
    const { container } = render(<MetoAura state="answering" />)
    const el = container.firstChild as HTMLElement
    expect(el.className).toContain('meto-glow')
  })

  it('applies listening state animation class', () => {
    const { container } = render(<MetoAura state="listening" />)
    const el = container.firstChild as HTMLElement
    expect(el.className).toContain('meto-pulse')
  })

  it('renders with sm size (40px)', () => {
    const { container } = render(<MetoAura size="sm" />)
    const el = container.firstChild as HTMLElement
    expect(el.style.width).toBe('40px')
    expect(el.style.height).toBe('40px')
  })

  it('renders with md size (56px)', () => {
    const { container } = render(<MetoAura size="md" />)
    const el = container.firstChild as HTMLElement
    expect(el.style.width).toBe('56px')
    expect(el.style.height).toBe('56px')
  })

  it('renders with lg size (80px)', () => {
    const { container } = render(<MetoAura size="lg" />)
    const el = container.firstChild as HTMLElement
    expect(el.style.width).toBe('80px')
    expect(el.style.height).toBe('80px')
  })

  it('is aria-hidden (decorative element)', () => {
    const { container } = render(<MetoAura />)
    const el = container.firstChild as HTMLElement
    expect(el.getAttribute('aria-hidden')).toBe('true')
  })

  it('passes extra className', () => {
    const { container } = render(<MetoAura className="my-custom-class" />)
    const el = container.firstChild as HTMLElement
    expect(el.className).toContain('my-custom-class')
  })

  const states: MetoState[] = ['idle', 'listening', 'thinking', 'answering', 'completed']
  states.forEach((state) => {
    it(`renders without crashing for state="${state}"`, () => {
      const { container } = render(<MetoAura state={state} />)
      expect(container.firstChild).toBeTruthy()
    })
  })
})
