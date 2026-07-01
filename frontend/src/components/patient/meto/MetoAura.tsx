'use client'

import * as React from 'react'
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type MetoState = 'idle' | 'listening' | 'thinking' | 'answering' | 'completed'

type Props = {
  state?: MetoState
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl'
  className?: string
}

// ---------------------------------------------------------------------------
// Size system (matches 05_UI_UX_SPEC.md §1.3)
// ---------------------------------------------------------------------------

const SIZE_MAP = {
  xs: 32,  // thinking indicator
  sm: 40,  // chat header (thu nhỏ)
  md: 56,  // floating button
  lg: 72,  // empty state
  xl: 96,  // splash / welcome screen
} as const

// ---------------------------------------------------------------------------
// Meto Aura Color tokens
// ---------------------------------------------------------------------------

const C = {
  mintPrimary: '#5ECBC8',
  mintLight:   '#A8EDEA',
  mintDeep:    '#3BB8B5',
  mintPale:    '#E8F9F9',
  glowColor:   'rgba(94, 203, 200, 0.4)',
  glowStrong:  'rgba(94, 203, 200, 0.7)',
  glowSoft:    'rgba(94, 203, 200, 0.2)',
}

// ---------------------------------------------------------------------------
// Emoji Face — SVG drawn at 0,0 → 100,100 viewBox, scaled by parent
// Face changes per state
// ---------------------------------------------------------------------------

function MetoFace({ state, sizePx }: { state: MetoState; sizePx: number }) {
  const scale = sizePx / 100
  const faceSize = sizePx * 0.56   // 56% of bubble
  const faceOffset = (sizePx - faceSize) / 2

  return (
    <div
      style={{
        position: 'absolute',
        left: faceOffset,
        top: faceOffset,
        width: faceSize,
        height: faceSize,
        pointerEvents: 'none',
      }}
    >
      <svg
        viewBox="0 0 100 100"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        style={{ width: '100%', height: '100%', overflow: 'visible' }}
      >
        {/* ---- IDLE: calm friendly face ---- */}
        {state === 'idle' && (
          <>
            {/* Eyes */}
            <motion.ellipse
              cx="34" cy="42" rx="6" ry="7"
              fill="rgba(255,255,255,0.9)"
              animate={{ ry: [7, 1, 7] }}
              transition={{ duration: 4, times: [0, 0.05, 0.1], repeat: Infinity, repeatDelay: 3.5 }}
            />
            <motion.ellipse
              cx="66" cy="42" rx="6" ry="7"
              fill="rgba(255,255,255,0.9)"
              animate={{ ry: [7, 1, 7] }}
              transition={{ duration: 4, times: [0, 0.05, 0.1], repeat: Infinity, repeatDelay: 3.5 }}
            />
            {/* Pupils */}
            <circle cx="36" cy="44" r="3" fill={C.mintDeep} />
            <circle cx="68" cy="44" r="3" fill={C.mintDeep} />
            {/* Gentle smile */}
            <path
              d="M 35 65 Q 50 77 65 65"
              stroke="rgba(255,255,255,0.9)" strokeWidth="4"
              strokeLinecap="round" fill="none"
            />
          </>
        )}

        {/* ---- LISTENING: attentive, slightly raised brows ---- */}
        {state === 'listening' && (
          <>
            {/* Eyebrows slightly raised */}
            <path d="M 26 30 Q 35 25 44 30" stroke="rgba(255,255,255,0.8)" strokeWidth="3" strokeLinecap="round" fill="none" />
            <path d="M 56 30 Q 65 25 74 30" stroke="rgba(255,255,255,0.8)" strokeWidth="3" strokeLinecap="round" fill="none" />
            {/* Eyes wider */}
            <ellipse cx="34" cy="43" rx="7" ry="8" fill="rgba(255,255,255,0.9)" />
            <ellipse cx="66" cy="43" rx="7" ry="8" fill="rgba(255,255,255,0.9)" />
            <circle cx="36" cy="45" r="3.5" fill={C.mintDeep} />
            <circle cx="68" cy="45" r="3.5" fill={C.mintDeep} />
            {/* Highlight dots */}
            <circle cx="38" cy="42" r="1.5" fill="white" />
            <circle cx="70" cy="42" r="1.5" fill="white" />
            {/* Slight open mouth — attentive */}
            <path d="M 38 66 Q 50 74 62 66" stroke="rgba(255,255,255,0.9)" strokeWidth="3.5" strokeLinecap="round" fill="none" />
          </>
        )}

        {/* ---- THINKING: looking up-left, thoughtful ---- */}
        {state === 'thinking' && (
          <>
            {/* Brow furrow */}
            <path d="M 27 32 Q 36 28 43 33" stroke="rgba(255,255,255,0.7)" strokeWidth="3" strokeLinecap="round" fill="none" />
            <path d="M 57 33 Q 64 28 73 32" stroke="rgba(255,255,255,0.7)" strokeWidth="3" strokeLinecap="round" fill="none" />
            {/* Eyes shifted up-left slightly */}
            <ellipse cx="34" cy="44" rx="6.5" ry="7.5" fill="rgba(255,255,255,0.9)" />
            <ellipse cx="66" cy="44" rx="6.5" ry="7.5" fill="rgba(255,255,255,0.9)" />
            <motion.circle
              cx="32" cy="41" r="3.5" fill={C.mintDeep}
              animate={{ cx: [32, 31, 32], cy: [41, 40, 41] }}
              transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
            />
            <motion.circle
              cx="64" cy="41" r="3.5" fill={C.mintDeep}
              animate={{ cx: [64, 63, 64], cy: [41, 40, 41] }}
              transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
            />
            {/* Thinking mouth — slight line */}
            <path d="M 38 67 Q 50 70 62 67" stroke="rgba(255,255,255,0.8)" strokeWidth="3" strokeLinecap="round" fill="none" />
            {/* Thought dots top-right */}
            <motion.circle cx="76" cy="22" r="2" fill="rgba(255,255,255,0.5)"
              animate={{ opacity: [0.3, 1, 0.3], scale: [0.8, 1.2, 0.8] }}
              transition={{ duration: 1, repeat: Infinity, delay: 0 }}
            />
            <motion.circle cx="83" cy="14" r="2.8" fill="rgba(255,255,255,0.4)"
              animate={{ opacity: [0.2, 0.9, 0.2], scale: [0.8, 1.2, 0.8] }}
              transition={{ duration: 1, repeat: Infinity, delay: 0.3 }}
            />
            <motion.circle cx="90" cy="6" r="3.5" fill="rgba(255,255,255,0.3)"
              animate={{ opacity: [0.1, 0.7, 0.1], scale: [0.8, 1.2, 0.8] }}
              transition={{ duration: 1, repeat: Infinity, delay: 0.6 }}
            />
          </>
        )}

        {/* ---- ANSWERING: happy, talking ---- */}
        {state === 'answering' && (
          <>
            {/* Happy squint eyes */}
            <motion.path
              d="M 26 40 Q 34 34 42 40"
              stroke="rgba(255,255,255,0.95)" strokeWidth="4" strokeLinecap="round" fill="none"
              animate={{ d: ['M 26 40 Q 34 34 42 40', 'M 27 42 Q 34 36 41 42', 'M 26 40 Q 34 34 42 40'] }}
              transition={{ duration: 1.5, repeat: Infinity, ease: 'easeInOut' }}
            />
            <motion.path
              d="M 58 40 Q 66 34 74 40"
              stroke="rgba(255,255,255,0.95)" strokeWidth="4" strokeLinecap="round" fill="none"
              animate={{ d: ['M 58 40 Q 66 34 74 40', 'M 59 42 Q 66 36 73 42', 'M 58 40 Q 66 34 74 40'] }}
              transition={{ duration: 1.5, repeat: Infinity, ease: 'easeInOut' }}
            />
            {/* Talking mouth — open/close */}
            <motion.path
              stroke="rgba(255,255,255,0.95)" strokeWidth="3.5" strokeLinecap="round" fill="rgba(255,255,255,0.15)"
              animate={{
                d: [
                  'M 35 64 Q 50 72 65 64 Q 50 68 35 64',
                  'M 35 64 Q 50 76 65 64 Q 50 72 35 64',
                  'M 35 64 Q 50 70 65 64 Q 50 66 35 64',
                  'M 35 64 Q 50 76 65 64 Q 50 72 35 64',
                  'M 35 64 Q 50 72 65 64 Q 50 68 35 64',
                ],
              }}
              transition={{ duration: 1.2, repeat: Infinity, ease: 'easeInOut' }}
            />
            {/* Cheek blush */}
            <ellipse cx="22" cy="58" rx="8" ry="5" fill="rgba(255,180,180,0.25)" />
            <ellipse cx="78" cy="58" rx="8" ry="5" fill="rgba(255,180,180,0.25)" />
          </>
        )}

        {/* ---- COMPLETED: big smile, sparkle eyes ---- */}
        {state === 'completed' && (
          <>
            {/* Star eyes */}
            <motion.text
              x="28" y="52" fontSize="18" textAnchor="middle"
              fill="rgba(255,255,255,0.95)"
              initial={{ scale: 0, opacity: 0 }}
              animate={{ scale: [0, 1.3, 1], opacity: 1 }}
              transition={{ duration: 0.4, delay: 0.1 }}
            >✦</motion.text>
            <motion.text
              x="72" y="52" fontSize="18" textAnchor="middle"
              fill="rgba(255,255,255,0.95)"
              initial={{ scale: 0, opacity: 0 }}
              animate={{ scale: [0, 1.3, 1], opacity: 1 }}
              transition={{ duration: 0.4, delay: 0.2 }}
            >✦</motion.text>
            {/* Big happy smile */}
            <motion.path
              d="M 28 64 Q 50 84 72 64"
              stroke="rgba(255,255,255,0.95)" strokeWidth="4.5"
              strokeLinecap="round" fill="none"
              initial={{ pathLength: 0 }}
              animate={{ pathLength: 1 }}
              transition={{ duration: 0.5, delay: 0.3, ease: 'easeOut' }}
            />
            {/* Rosy cheeks */}
            <motion.ellipse cx="20" cy="60" rx="9" ry="6" fill="rgba(255,160,160,0.3)"
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.5 }}
            />
            <motion.ellipse cx="80" cy="60" rx="9" ry="6" fill="rgba(255,160,160,0.3)"
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.5 }}
            />
          </>
        )}
      </svg>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Thinking ripple rings
// ---------------------------------------------------------------------------

function ThinkingRipples({ sizePx }: { sizePx: number }) {
  return (
    <>
      {[0, 1, 2].map((i) => (
        <motion.div
          key={i}
          style={{
            position: 'absolute',
            inset: 0,
            borderRadius: '50%',
            border: `2px solid ${C.mintLight}`,
            pointerEvents: 'none',
          }}
          animate={{ scale: [1, 1.8, 2.4], opacity: [0.6, 0.3, 0] }}
          transition={{
            duration: 1.6,
            ease: 'easeOut',
            repeat: Infinity,
            delay: i * 0.4,
          }}
        />
      ))}
    </>
  )
}

// ---------------------------------------------------------------------------
// Completed burst particles + floating hearts
// ---------------------------------------------------------------------------

function CompletedBurst({ sizePx }: { sizePx: number }) {
  const particles = Array.from({ length: 6 }, (_, i) => ({
    angle: i * 60,
    delay: i * 0.06,
  }))
  const r = sizePx * 0.7

  return (
    <>
      {particles.map(({ angle, delay }) => {
        const rad = (angle * Math.PI) / 180
        const tx = Math.cos(rad) * r
        const ty = Math.sin(rad) * r
        return (
          <motion.div
            key={angle}
            style={{
              position: 'absolute',
              top: '50%',
              left: '50%',
              width: 6,
              height: 6,
              borderRadius: '50%',
              background: C.mintLight,
              marginTop: -3,
              marginLeft: -3,
              pointerEvents: 'none',
            }}
            initial={{ x: 0, y: 0, opacity: 1, scale: 1 }}
            animate={{ x: tx, y: ty, opacity: 0, scale: 0.3 }}
            transition={{ duration: 0.6, delay, ease: 'easeOut' }}
          />
        )
      })}
      {/* Floating heart */}
      <motion.div
        style={{
          position: 'absolute',
          top: '10%',
          right: '5%',
          fontSize: sizePx * 0.22,
          pointerEvents: 'none',
        }}
        initial={{ y: 0, opacity: 0, scale: 0 }}
        animate={{ y: -sizePx * 0.6, opacity: [0, 1, 0], scale: [0, 1.2, 0.8] }}
        transition={{ duration: 0.9, delay: 0.2, ease: 'easeOut' }}
      >
        💚
      </motion.div>
    </>
  )
}

// ---------------------------------------------------------------------------
// Main MetoAura component
// ---------------------------------------------------------------------------

export function MetoAura({ state = 'idle', size = 'md', className = '' }: Props) {
  const px = SIZE_MAP[size]
  const shouldReduceMotion = useReducedMotion()

  // ---- Core bubble background ----
  const bubbleBackground = `radial-gradient(
    circle at 35% 35%,
    rgba(255, 255, 255, 0.6) 0%,
    ${C.mintLight} 30%,
    ${C.mintPrimary} 60%,
    ${C.mintDeep} 100%
  )`

  // ---- Per-state box shadow glow ----
  const shadowByState: Record<MetoState, string[]> = {
    idle: [
      `0 0 0 8px ${C.glowSoft}, 0 8px 32px ${C.glowColor}`,
      `0 0 0 12px rgba(94,203,200,0.3), 0 8px 32px ${C.glowColor}`,
      `0 0 0 8px ${C.glowSoft}, 0 8px 32px ${C.glowColor}`,
    ],
    listening: [
      `0 0 0 10px rgba(94,203,200,0.3), 0 8px 32px ${C.glowColor}`,
      `0 0 0 18px rgba(94,203,200,0.5), 0 8px 40px ${C.glowStrong}`,
      `0 0 0 10px rgba(94,203,200,0.3), 0 8px 32px ${C.glowColor}`,
    ],
    thinking: [
      `0 0 0 6px ${C.glowSoft}, 0 4px 20px ${C.glowColor}`,
      `0 0 0 10px rgba(94,203,200,0.25), 0 4px 20px ${C.glowColor}`,
      `0 0 0 6px ${C.glowSoft}, 0 4px 20px ${C.glowColor}`,
    ],
    answering: [
      `0 0 0 8px rgba(94,203,200,0.3), 0 0 20px ${C.glowColor}`,
      `0 0 0 14px rgba(94,203,200,0.5), 0 0 36px ${C.glowStrong}`,
      `0 0 0 8px rgba(94,203,200,0.3), 0 0 20px ${C.glowColor}`,
    ],
    completed: [
      `0 0 0 12px rgba(94,203,200,0.4), 0 0 40px ${C.glowStrong}`,
    ],
  }

  const scaleByState: Record<MetoState, number[]> = {
    idle:      [1, 1.04, 1],
    listening: [1, 1.06, 1],
    thinking:  [1, 1.02, 1],
    answering: [1, 1.03, 1],
    completed: [1, 1.1, 1.05],
  }

  const durationByState: Record<MetoState, number> = {
    idle: 3, listening: 1.5, thinking: 2, answering: 1.5, completed: 0.4,
  }

  const showFace = px >= 40  // only show face when large enough

  return (
    <div
      className={className}
      style={{ position: 'relative', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}
    >
      {/* ---- Thinking ripples (behind bubble) ---- */}
      {!shouldReduceMotion && state === 'thinking' && (
        <div style={{ position: 'absolute', inset: 0, borderRadius: '50%' }}>
          <ThinkingRipples sizePx={px} />
        </div>
      )}

      {/* ---- Main bubble ---- */}
      <motion.div
        style={{
          width: px,
          height: px,
          borderRadius: '50%',
          background: bubbleBackground,
          backdropFilter: 'blur(12px)',
          WebkitBackdropFilter: 'blur(12px)',
          border: '1px solid rgba(255, 255, 255, 0.4)',
          position: 'relative',
          overflow: 'visible',
          flexShrink: 0,
        }}
        animate={
          shouldReduceMotion
            ? { opacity: 1 }
            : {
                scale: scaleByState[state],
                boxShadow: shadowByState[state],
              }
        }
        transition={
          shouldReduceMotion
            ? {}
            : {
                duration: durationByState[state],
                ease: 'easeInOut',
                repeat: state === 'completed' ? 0 : Infinity,
              }
        }
        aria-hidden="true"
      >
        {/* Glass highlight */}
        <div
          style={{
            position: 'absolute',
            inset: 0,
            borderRadius: '50%',
            background:
              'radial-gradient(circle at 35% 25%, rgba(255,255,255,0.55) 0%, rgba(255,255,255,0.1) 50%, transparent 75%)',
            pointerEvents: 'none',
          }}
        />

        {/* Emoji face */}
        {showFace && <MetoFace state={state} sizePx={px} />}

        {/* Answering glow filter overlay */}
        {!shouldReduceMotion && state === 'answering' && (
          <motion.div
            style={{
              position: 'absolute',
              inset: -4,
              borderRadius: '50%',
              background: `radial-gradient(circle, ${C.glowColor} 0%, transparent 70%)`,
              pointerEvents: 'none',
            }}
            animate={{ opacity: [0.4, 0.9, 0.4] }}
            transition={{ duration: 1.5, repeat: Infinity, ease: 'easeInOut' }}
          />
        )}
      </motion.div>

      {/* ---- Completed burst (above bubble) ---- */}
      <AnimatePresence>
        {!shouldReduceMotion && state === 'completed' && (
          <motion.div
            key="burst"
            style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}
            initial={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            <CompletedBurst sizePx={px} />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

export default MetoAura
