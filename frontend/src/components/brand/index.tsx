/**
 * Canonical MetoCare brand artwork — IMAGE ONLY.
 *
 * These are the single source of truth for rendering the brand. The artwork is
 * the approved PNG asset; it is NEVER recreated with text, fonts, CSS, SVG, or
 * icon libraries. Do not recolor, reshape, trace, or vectorize.
 *
 *   BrandLogo → full logo (symbol + wordmark)  = public/brand/metocare-logo.png  (logo.png)
 *   BrandMark → icon-only mark                  = public/brand/metocare-mark.png  (mark-test.png)
 */

type Props = {
  className?: string
  alt?: string
}

/** Full MetoCare logo (symbol + wordmark). Exact image; aspect preserved. */
export function BrandLogo({ className = 'h-12 w-auto', alt = 'MetoCare' }: Props) {
  // eslint-disable-next-line @next/next/no-img-element
  return <img src="/brand/metocare-logo.png" alt={alt} className={className} />
}

/** Icon-only MetoCare mark. Exact image; aspect preserved. */
export function BrandMark({ className = 'h-9 w-9 object-contain', alt = 'MetoCare' }: Props) {
  // eslint-disable-next-line @next/next/no-img-element
  return <img src="/brand/metocare-mark.png" alt={alt} className={className} />
}
