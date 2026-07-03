'use client'

import * as React from 'react'
import Link from 'next/link'
import { Plus } from 'lucide-react'

/**
 * Shared primary action FAB for patient screens (the "+" button).
 *
 * Owns the ONE canonical position/size/shape so the FAB never drifts across
 * pages or collides with the Meto FAB (stacked 16px above at bottom-[184px])
 * or the bottom nav. Pages supply only behavior (onClick / href), an
 * accessible label, and — when needed — a custom icon or skin.
 */

// Single source of truth for FAB placement. bottom-28 (112px) clears the
// bottom nav; the Meto FAB sits at bottom-[184px] — keep the two in sync.
const FAB_LAYOUT =
  'fixed bottom-28 right-5 z-30 flex size-14 items-center justify-center rounded-full text-white'

// Default visual skin — the shared neumorphic green used by most pages.
const DEFAULT_SKIN = 'neu-btn-primary !min-h-0 !p-0'

type PatientPrimaryFabProps = {
  ariaLabel: string
  onClick?: () => void
  href?: string
  icon?: React.ReactNode
  /** Replaces the default neu-btn-primary skin (positioning is always applied). */
  className?: string
  style?: React.CSSProperties
}

export function PatientPrimaryFab({
  ariaLabel,
  onClick,
  href,
  icon,
  className,
  style,
}: PatientPrimaryFabProps) {
  const content = icon ?? <Plus className="size-7" aria-hidden="true" />
  const classes = `${FAB_LAYOUT} ${className ?? DEFAULT_SKIN}`

  if (href) {
    return (
      <Link href={href} aria-label={ariaLabel} className={classes} style={style}>
        {content}
      </Link>
    )
  }

  return (
    <button
      type="button"
      aria-label={ariaLabel}
      onClick={onClick}
      className={classes}
      style={style}
    >
      {content}
    </button>
  )
}
