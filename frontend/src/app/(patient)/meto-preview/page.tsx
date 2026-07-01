'use client'

import * as React from 'react'
import { MetoAura, MetoState } from '@/components/patient/meto/MetoAura'

const STATES: MetoState[] = ['idle', 'listening', 'thinking', 'answering', 'completed']
const SIZES = ['xs', 'sm', 'md', 'lg', 'xl'] as const

export default function MetoPreviewPage() {
  const [liveState, setLiveState] = React.useState<MetoState>('idle')

  React.useEffect(() => {
    const cycle = [...STATES, ...STATES]
    let i = 0
    const id = setInterval(() => {
      i = (i + 1) % STATES.length
      setLiveState(STATES[i])
    }, 2500)
    return () => clearInterval(id)
  }, [])

  return (
    <div className="min-h-screen bg-gradient-to-br from-[#0d1117] to-[#1a2332] p-8 font-sans">
      <h1 className="text-white text-2xl font-bold mb-2">Meto Aura — Design Preview</h1>
      <p className="text-gray-400 text-sm mb-10">Liquid glass emoji with 5 animation states</p>

      {/* Live cycle demo */}
      <section className="mb-14 flex flex-col items-center gap-6">
        <div className="text-gray-300 text-xs uppercase tracking-widest">Live cycle</div>
        <MetoAura state={liveState} size="xl" />
        <div className="text-[#5ECBC8] text-sm font-mono">{liveState}</div>
      </section>

      {/* All states × size md */}
      <section className="mb-14">
        <div className="text-gray-400 text-xs uppercase tracking-widest mb-6">All states — size md (56px)</div>
        <div className="flex flex-wrap gap-12 items-end">
          {STATES.map((s) => (
            <div key={s} className="flex flex-col items-center gap-3">
              <MetoAura state={s} size="md" />
              <span className="text-gray-400 text-xs font-mono">{s}</span>
            </div>
          ))}
        </div>
      </section>

      {/* All sizes × idle */}
      <section className="mb-14">
        <div className="text-gray-400 text-xs uppercase tracking-widest mb-6">All sizes — idle state</div>
        <div className="flex flex-wrap gap-10 items-end">
          {SIZES.map((sz) => (
            <div key={sz} className="flex flex-col items-center gap-3">
              <MetoAura state="idle" size={sz} />
              <span className="text-gray-400 text-xs font-mono">{sz}</span>
            </div>
          ))}
        </div>
      </section>

      {/* Click to test */}
      <section className="mb-14">
        <div className="text-gray-400 text-xs uppercase tracking-widest mb-6">Tap to switch state</div>
        <div className="flex flex-wrap gap-4">
          {STATES.map((s) => (
            <button
              key={s}
              onClick={() => setLiveState(s)}
              className={`px-4 py-2 rounded-full text-sm font-mono transition-all ${
                liveState === s
                  ? 'bg-[#5ECBC8] text-black'
                  : 'bg-white/10 text-gray-300 hover:bg-white/20'
              }`}
            >
              {s}
            </button>
          ))}
        </div>
        <div className="mt-8">
          <MetoAura state={liveState} size="xl" />
        </div>
      </section>

      {/* Dark vs light bg */}
      <section>
        <div className="text-gray-400 text-xs uppercase tracking-widest mb-6">Dark vs light background</div>
        <div className="flex gap-0 rounded-2xl overflow-hidden">
          <div className="flex-1 bg-[#1a2332] flex items-center justify-center py-10">
            <MetoAura state="answering" size="lg" />
          </div>
          <div className="flex-1 bg-[#EAF7F2] flex items-center justify-center py-10">
            <MetoAura state="answering" size="lg" />
          </div>
          <div className="flex-1 bg-white flex items-center justify-center py-10">
            <MetoAura state="answering" size="lg" />
          </div>
        </div>
      </section>
    </div>
  )
}
