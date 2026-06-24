/**
 * Canonical MetoCare brand artwork — IMAGE ONLY (MetoCare Logo System).
 *
 * Single source of truth for rendering the brand. Uses the official transparent
 * PNG artwork from the approved logo-system handoff — NEVER recreated with text,
 * fonts, CSS, SVG, or icon libraries. Do not recolor/reshape/trace/vectorize.
 *
 *   BrandLogo → full lockup (symbol + wordmark)
 *     tone="color" → /brand/metocare-logo.png        (metocare-lockup.png)
 *     tone="white" → /brand/metocare-logo-white.png  (metocare-lockup-white.png, for dark bg)
 *   BrandMark → icon-only mark
 *     tone="color" → /brand/metocare-mark.png        (metocare-mark.png)
 *     tone="white" → /brand/metocare-mark-white.png  (metocare-mark-white.png, for dark bg)
 *
 * Assets are transparent, so they sit cleanly on any background — no plates.
 */

type Tone = 'color' | 'white'

type Props = {
  className?: string
  alt?: string
  /** Use "white" on dark surfaces (inverts teal strokes to white, keeps green leaf). */
  tone?: Tone
}

/** Full MetoCare logo (symbol + wordmark). Exact image; aspect preserved. */
export function BrandLogo({ className = 'h-12 w-auto', alt = 'MetoCare', tone = 'color' }: Props) {
  const src = tone === 'white' ? '/brand/metocare-logo-white.png' : '/brand/metocare-logo.png'
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={src} alt={alt} className={className} />
}

/** Icon-only MetoCare mark. Exact image; aspect preserved. */
export function BrandMark({
  className = 'h-9 w-9 object-contain',
  alt = 'MetoCare',
  tone = 'color',
}: Props) {
  const src = tone === 'white' ? '/brand/metocare-mark-white.png' : '/brand/metocare-mark.png'
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={src} alt={alt} className={className} />
}
