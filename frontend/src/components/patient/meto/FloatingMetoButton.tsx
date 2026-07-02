'use client'
import * as React from 'react'
import { MetoAura } from './MetoAura'
import { ChatSheet } from './ChatSheet'

type Props = {
  screenId: string
  entityId?: string
  entityType?: string
}

export function FloatingMetoButton({ screenId, entityId, entityType }: Props) {
  const [open, setOpen] = React.useState(false)

  return (
    <>
      {/*
        Meto FAB is stacked ABOVE the page primary "+" FAB (which sits at
        bottom-28=112px, 56px tall → tops at 168px). bottom-[184px] leaves a
        clean 16px gap in the same right column (right-5) so the two never
        overlap. z-50 keeps Meto above the bottom nav (z-40) and the "+" (z-30).
      */}
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="Hỏi Meto"
        className="fixed bottom-[184px] right-5 z-50 flex items-center justify-center w-14 h-14 rounded-full transition-transform active:scale-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0F9C6E]/50"
        style={{
          boxShadow: '0 8px 24px -8px rgba(15,156,110,0.55), 0 2px 8px rgba(0,0,0,0.12)',
        }}
      >
        {/* md fills the 56px button edge-to-edge — no white gap ring / "disc" */}
        <MetoAura state="idle" size="md" />
      </button>

      <ChatSheet
        open={open}
        onClose={() => setOpen(false)}
        screenId={screenId}
        entityId={entityId}
        entityType={entityType}
      />
    </>
  )
}
