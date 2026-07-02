/**
 * Tests for MetoAura component (Framer Motion liquid-glass redesign).
 * Component uses Framer Motion animations — no CSS animation classes.
 * Verifies correct rendering across states and sizes.
 */
import * as React from 'react'
import { render } from '@testing-library/react'
import { MetoAura, type MetoState } from '@/components/patient/meto/MetoAura'

// Mock framer-motion to avoid animation issues in JSDOM
jest.mock('framer-motion', () => {
  const actual = jest.requireActual('framer-motion')
  return {
    ...actual,
    motion: new Proxy(
      {},
      {
        get: (_: unknown, tag: string) =>
          // eslint-disable-next-line react/display-name
          React.forwardRef(({ children, ...props }: React.HTMLAttributes<HTMLElement> & { children?: React.ReactNode }, ref: React.Ref<HTMLElement>) =>
            React.createElement(tag, { ...props, ref }, children)
          ),
      }
    ),
    AnimatePresence: ({ children }: { children: React.ReactNode }) => <>{children}</>,
    useReducedMotion: () => false,
  }
})

describe('MetoAura', () => {
  it('renders without crashing', () => {
    const { container } = render(<MetoAura />)
    expect(container.firstChild).toBeTruthy()
  })

  it('renders idle state', () => {
    const { container } = render(<MetoAura state="idle" />)
    expect(container.firstChild).toBeTruthy()
  })

  it('renders thinking state', () => {
    const { container } = render(<MetoAura state="thinking" />)
    expect(container.firstChild).toBeTruthy()
  })

  it('renders answering state', () => {
    const { container } = render(<MetoAura state="answering" />)
    expect(container.firstChild).toBeTruthy()
  })

  it('renders listening state', () => {
    const { container } = render(<MetoAura state="listening" />)
    expect(container.firstChild).toBeTruthy()
  })

  it('renders completed state', () => {
    const { container } = render(<MetoAura state="completed" />)
    expect(container.firstChild).toBeTruthy()
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

  it('renders with lg size (72px)', () => {
    const { container } = render(<MetoAura size="lg" />)
    const el = container.firstChild as HTMLElement
    expect(el.style.width).toBe('72px')
    expect(el.style.height).toBe('72px')
  })

  it('renders with xl size (96px)', () => {
    const { container } = render(<MetoAura size="xl" />)
    const el = container.firstChild as HTMLElement
    expect(el.style.width).toBe('96px')
    expect(el.style.height).toBe('96px')
  })

  it('renders with xs size (32px)', () => {
    const { container } = render(<MetoAura size="xs" />)
    const el = container.firstChild as HTMLElement
    expect(el.style.width).toBe('32px')
    expect(el.style.height).toBe('32px')
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
