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
  xs: 32, // thinking indicator
  sm: 40, // chat header (thu nhỏ)
  md: 56, // floating button
  lg: 72, // empty state
  xl: 96, // splash / welcome screen
} as const

// ---------------------------------------------------------------------------
// Meto Aura Color tokens
// ---------------------------------------------------------------------------

const C = {
  mintPrimary: '#5ECBC8',
  mintLight: '#A8EDEA',
  mintDeep: '#3BB8B5',
  mintPale: '#E8F9F9',
  glowColor: 'rgba(94, 203, 200, 0.4)',
  glowStrong: 'rgba(94, 203, 200, 0.7)',
  glowSoft: 'rgba(94, 203, 200, 0.2)',
  // Facial features — deep teal ink for high contrast on the light mint bubble
  // AND on light app backgrounds (dashboard, floating button, sidebar).
  ink: '#0A4A47',
  inkSoft: 'rgba(10, 74, 71, 0.55)',
  eyeShine: 'rgba(255, 255, 255, 0.95)',
  blush: 'rgba(255, 138, 138, 0.4)',
}

// ---------------------------------------------------------------------------
// Emoji Face — SVG drawn at 0,0 → 100,100 viewBox, scaled by parent
// Face changes per state
// ---------------------------------------------------------------------------

function MetoFace({ state, sizePx }: { state: MetoState; sizePx: number }) {
  const faceSize = sizePx * 0.62 // 62% of bubble — a touch larger so features read
  const faceOffset = (sizePx - faceSize) / 2
  // Small sizes (sm 40px) drop fine detail (brows, thought dots, cheeks) so the
  // core eyes+nose+mouth stay crisp and instantly readable.
  const compact = sizePx < 56

  // Soft drop-shadow gives features depth so they pop on both light and mint.
  const faceShadow = 'drop-shadow(0 1px 1.2px rgba(6, 42, 40, 0.35))'

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
        style={{ width: '100%', height: '100%', overflow: 'visible', filter: faceShadow }}
      >
        {/* ---- IDLE: calm friendly face ---- */}
        {state === 'idle' && (
          <>
            {/* Eyes — dark, glossy */}
            <motion.ellipse
              cx="34"
              cy="44"
              rx="7"
              ry="8.5"
              fill={C.ink}
              animate={{ ry: [8.5, 1.2, 8.5] }}
              transition={{
                duration: 4,
                times: [0, 0.05, 0.1],
                repeat: Infinity,
                repeatDelay: 3.5,
              }}
            />
            <motion.ellipse
              cx="66"
              cy="44"
              rx="7"
              ry="8.5"
              fill={C.ink}
              animate={{ ry: [8.5, 1.2, 8.5] }}
              transition={{
                duration: 4,
                times: [0, 0.05, 0.1],
                repeat: Infinity,
                repeatDelay: 3.5,
              }}
            />
            {/* Eye shine */}
            <circle cx="31.5" cy="41" r="2.2" fill={C.eyeShine} />
            <circle cx="63.5" cy="41" r="2.2" fill={C.eyeShine} />
            {/* Nose */}
            <path
              d="M 47.5 54 Q 50 57 52.5 54"
              stroke={C.ink}
              strokeWidth="2.5"
              strokeLinecap="round"
              fill="none"
            />
            {/* Gentle smile */}
            <path
              d="M 34 65 Q 50 77 66 65"
              stroke={C.ink}
              strokeWidth="5"
              strokeLinecap="round"
              fill="none"
            />
            {/* Cheeks */}
            {!compact && (
              <>
                <ellipse cx="23" cy="61" rx="6" ry="4" fill={C.blush} />
                <ellipse cx="77" cy="61" rx="6" ry="4" fill={C.blush} />
              </>
            )}
          </>
        )}

        {/* ---- LISTENING: attentive, slightly raised brows ---- */}
        {state === 'listening' && (
          <>
            {!compact && (
              <>
                <path
                  d="M 25 30 Q 34 24 43 29"
                  stroke={C.ink}
                  strokeWidth="3"
                  strokeLinecap="round"
                  fill="none"
                />
                <path
                  d="M 57 29 Q 66 24 75 30"
                  stroke={C.ink}
                  strokeWidth="3"
                  strokeLinecap="round"
                  fill="none"
                />
              </>
            )}
            {/* Eyes wider */}
            <ellipse cx="34" cy="44" rx="7.5" ry="9" fill={C.ink} />
            <ellipse cx="66" cy="44" rx="7.5" ry="9" fill={C.ink} />
            <circle cx="31" cy="41" r="2.4" fill={C.eyeShine} />
            <circle cx="63" cy="41" r="2.4" fill={C.eyeShine} />
            {/* Nose */}
            <path
              d="M 47.5 55 Q 50 58 52.5 55"
              stroke={C.ink}
              strokeWidth="2.5"
              strokeLinecap="round"
              fill="none"
            />
            {/* Slight open mouth — attentive */}
            <path
              d="M 38 66 Q 50 74 62 66"
              stroke={C.ink}
              strokeWidth="4.5"
              strokeLinecap="round"
              fill="none"
            />
          </>
        )}

        {/* ---- THINKING: looking up-left, thoughtful ---- */}
        {state === 'thinking' && (
          <>
            {!compact && (
              <>
                <path
                  d="M 26 32 Q 35 28 42 33"
                  stroke={C.inkSoft}
                  strokeWidth="3"
                  strokeLinecap="round"
                  fill="none"
                />
                <path
                  d="M 58 33 Q 65 28 74 32"
                  stroke={C.inkSoft}
                  strokeWidth="3"
                  strokeLinecap="round"
                  fill="none"
                />
              </>
            )}
            {/* Eyes */}
            <ellipse cx="34" cy="45" rx="7" ry="8" fill={C.ink} />
            <ellipse cx="66" cy="45" rx="7" ry="8" fill={C.ink} />
            {/* Glance shine drifting up-left — thoughtful */}
            <motion.circle
              cx="31"
              cy="42"
              r="2.4"
              fill={C.eyeShine}
              animate={{ cx: [31, 30, 31], cy: [42, 41, 42] }}
              transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
            />
            <motion.circle
              cx="63"
              cy="42"
              r="2.4"
              fill={C.eyeShine}
              animate={{ cx: [63, 62, 63], cy: [42, 41, 42] }}
              transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
            />
            {/* Nose */}
            <path
              d="M 47.5 55 Q 50 57.5 52.5 55"
              stroke={C.ink}
              strokeWidth="2.3"
              strokeLinecap="round"
              fill="none"
            />
            {/* Thinking mouth — slight line */}
            <path
              d="M 40 67 Q 50 70 60 67"
              stroke={C.ink}
              strokeWidth="4"
              strokeLinecap="round"
              fill="none"
            />
            {/* Thought dots top-right */}
            {!compact && (
              <>
                <motion.circle
                  cx="78"
                  cy="20"
                  r="2.2"
                  fill={C.inkSoft}
                  animate={{ opacity: [0.3, 1, 0.3], scale: [0.8, 1.2, 0.8] }}
                  transition={{ duration: 1, repeat: Infinity, delay: 0 }}
                />
                <motion.circle
                  cx="86"
                  cy="12"
                  r="3"
                  fill={C.inkSoft}
                  animate={{ opacity: [0.2, 0.9, 0.2], scale: [0.8, 1.2, 0.8] }}
                  transition={{ duration: 1, repeat: Infinity, delay: 0.3 }}
                />
                <motion.circle
                  cx="94"
                  cy="4"
                  r="3.6"
                  fill={C.inkSoft}
                  animate={{ opacity: [0.1, 0.7, 0.1], scale: [0.8, 1.2, 0.8] }}
                  transition={{ duration: 1, repeat: Infinity, delay: 0.6 }}
                />
              </>
            )}
          </>
        )}

        {/* ---- ANSWERING: happy, talking ---- */}
        {state === 'answering' && (
          <>
            {/* Happy squint eyes */}
            <motion.path
              d="M 26 42 Q 34 35 42 42"
              stroke={C.ink}
              strokeWidth="4.5"
              strokeLinecap="round"
              fill="none"
              animate={{
                d: ['M 26 42 Q 34 35 42 42', 'M 27 43 Q 34 37 41 43', 'M 26 42 Q 34 35 42 42'],
              }}
              transition={{ duration: 1.5, repeat: Infinity, ease: 'easeInOut' }}
            />
            <motion.path
              d="M 58 42 Q 66 35 74 42"
              stroke={C.ink}
              strokeWidth="4.5"
              strokeLinecap="round"
              fill="none"
              animate={{
                d: ['M 58 42 Q 66 35 74 42', 'M 59 43 Q 66 37 73 43', 'M 58 42 Q 66 35 74 42'],
              }}
              transition={{ duration: 1.5, repeat: Infinity, ease: 'easeInOut' }}
            />
            {/* Nose */}
            <path
              d="M 47.5 52 Q 50 55 52.5 52"
              stroke={C.ink}
              strokeWidth="2.3"
              strokeLinecap="round"
              fill="none"
            />
            {/* Talking mouth — open/close */}
            <motion.path
              stroke={C.ink}
              strokeWidth="4"
              strokeLinecap="round"
              strokeLinejoin="round"
              fill="rgba(10,74,71,0.16)"
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
            {!compact && (
              <>
                <ellipse cx="22" cy="58" rx="7" ry="4.5" fill={C.blush} />
                <ellipse cx="78" cy="58" rx="7" ry="4.5" fill={C.blush} />
              </>
            )}
          </>
        )}

        {/* ---- COMPLETED: big smile, sparkle eyes ---- */}
        {state === 'completed' && (
          <>
            {/* Star eyes */}
            <motion.text
              x="28"
              y="51"
              fontSize="22"
              fontWeight="bold"
              textAnchor="middle"
              fill={C.ink}
              initial={{ scale: 0, opacity: 0 }}
              animate={{ scale: [0, 1.3, 1], opacity: 1 }}
              transition={{ duration: 0.4, delay: 0.1 }}
            >
              ✦
            </motion.text>
            <motion.text
              x="72"
              y="51"
              fontSize="22"
              fontWeight="bold"
              textAnchor="middle"
              fill={C.ink}
              initial={{ scale: 0, opacity: 0 }}
              animate={{ scale: [0, 1.3, 1], opacity: 1 }}
              transition={{ duration: 0.4, delay: 0.2 }}
            >
              ✦
            </motion.text>
            {/* Nose */}
            <path
              d="M 47.5 54 Q 50 57 52.5 54"
              stroke={C.ink}
              strokeWidth="2.3"
              strokeLinecap="round"
              fill="none"
            />
            {/* Big happy smile */}
            <motion.path
              d="M 28 63 Q 50 84 72 63"
              stroke={C.ink}
              strokeWidth="5"
              strokeLinecap="round"
              fill="none"
              initial={{ pathLength: 0 }}
              animate={{ pathLength: 1 }}
              transition={{ duration: 0.5, delay: 0.3, ease: 'easeOut' }}
            />
            {/* Rosy cheeks */}
            {!compact && (
              <>
                <motion.ellipse
                  cx="20"
                  cy="59"
                  rx="8"
                  ry="5"
                  fill={C.blush}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: 0.5 }}
                />
                <motion.ellipse
                  cx="80"
                  cy="59"
                  rx="8"
                  ry="5"
                  fill={C.blush}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: 0.5 }}
                />
              </>
            )}
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
  // Soft, blurred glow ONLY — no `0 0 0 Npx` hard spread (that created the
  // detached "plate / egg-on-a-dish" ring). Pure ambient + halo glow keeps the
  // liquid-glass feel as a single cohesive orb.
  const shadowByState: Record<MetoState, string[]> = {
    idle: [
      `0 4px 16px ${C.glowColor}, 0 0 14px ${C.glowSoft}`,
      `0 6px 24px ${C.glowColor}, 0 0 24px rgba(94,203,200,0.4)`,
      `0 4px 16px ${C.glowColor}, 0 0 14px ${C.glowSoft}`,
    ],
    listening: [
      `0 5px 20px ${C.glowColor}, 0 0 20px rgba(94,203,200,0.4)`,
      `0 8px 30px ${C.glowStrong}, 0 0 36px ${C.glowStrong}`,
      `0 5px 20px ${C.glowColor}, 0 0 20px rgba(94,203,200,0.4)`,
    ],
    thinking: [
      `0 3px 12px ${C.glowColor}, 0 0 10px ${C.glowSoft}`,
      `0 5px 18px ${C.glowColor}, 0 0 16px rgba(94,203,200,0.3)`,
      `0 3px 12px ${C.glowColor}, 0 0 10px ${C.glowSoft}`,
    ],
    answering: [
      `0 5px 20px ${C.glowColor}, 0 0 18px rgba(94,203,200,0.4)`,
      `0 8px 32px ${C.glowStrong}, 0 0 42px ${C.glowStrong}`,
      `0 5px 20px ${C.glowColor}, 0 0 18px rgba(94,203,200,0.4)`,
    ],
    completed: [`0 8px 30px ${C.glowStrong}, 0 0 40px ${C.glowStrong}`],
  }

  const scaleByState: Record<MetoState, number[]> = {
    idle: [1, 1.04, 1],
    listening: [1, 1.06, 1],
    thinking: [1, 1.02, 1],
    answering: [1, 1.03, 1],
    completed: [1, 1.1, 1.05],
  }

  const durationByState: Record<MetoState, number> = {
    idle: 3,
    listening: 1.5,
    thinking: 2,
    answering: 1.5,
    completed: 0.4,
  }

  const showFace = px >= 40 // only show face when large enough

  return (
    <div
      className={className}
      style={{
        position: 'relative',
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
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
