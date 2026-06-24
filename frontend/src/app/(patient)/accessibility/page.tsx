'use client'

import * as React from 'react'
import { Type, Contrast, Zap, MonitorSpeaker, ExternalLink } from 'lucide-react'
import { NeuCard } from '@/components/patient/neu'

// ── Types ─────────────────────────────────────────────────────────────────────

type A11ySettings = {
  largeText: boolean
  highContrast: boolean
  reduceMotion: boolean
}

// ── Constants ─────────────────────────────────────────────────────────────────

const LS_LARGE_TEXT = 'a11y_large_text'
const LS_CONTRAST = 'a11y_contrast'
const LS_REDUCE_MOTION = 'a11y_reduce_motion'

// ── Custom toggle ─────────────────────────────────────────────────────────────

function NeuToggle({
  checked,
  onChange,
  id,
}: {
  checked: boolean
  onChange: (value: boolean) => void
  id: string
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      id={id}
      onClick={() => onChange(!checked)}
      className={[
        'relative h-7 w-12 rounded-full transition-all duration-200 shrink-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0F9C6E]/40',
        checked
          ? 'bg-gradient-to-b from-[#13b37e] to-[#0F9C6E] shadow-[0_4px_12px_-4px_rgba(15,156,110,0.55)]'
          : 'neu-pressed',
      ].join(' ')}
    >
      <span
        className={[
          'absolute top-1 size-5 rounded-full bg-white transition-all duration-200',
          checked ? 'left-6 shadow-[0_2px_8px_rgba(15,156,110,0.35)]' : 'left-1 shadow-sm',
        ].join(' ')}
      />
    </button>
  )
}

// ── Setting row ───────────────────────────────────────────────────────────────

function SettingRow({
  icon,
  iconColor,
  title,
  description,
  toggleId,
  checked,
  onChange,
}: {
  icon: React.ReactNode
  iconColor: string
  title: string
  description: string
  toggleId: string
  checked: boolean
  onChange: (value: boolean) => void
}) {
  return (
    <div className="flex items-center gap-4 py-4 border-b border-[#C8D8D4] last:border-0">
      {/* Icon */}
      <div
        className="shrink-0 size-10 rounded-[12px] flex items-center justify-center"
        style={{ background: iconColor + '22', color: iconColor }}
      >
        {icon}
      </div>

      {/* Text */}
      <label
        htmlFor={toggleId}
        className="flex-1 min-w-0 cursor-pointer"
      >
        <p className="text-[15px] font-semibold text-neu-text">{title}</p>
        <p className="text-[13px] text-neu-muted mt-0.5 leading-snug">{description}</p>
      </label>

      {/* Toggle */}
      <NeuToggle checked={checked} onChange={onChange} id={toggleId} />
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

function readStoredBool(key: string): boolean {
  if (typeof window === 'undefined') return false
  return localStorage.getItem(key) === 'true'
}

export default function AccessibilityPage() {
  const [settings, setSettings] = React.useState<A11ySettings>({
    largeText: false,
    highContrast: false,
    reduceMotion: false,
  })

  // Hydrate from localStorage on mount
  React.useEffect(() => {
    setSettings({
      largeText: readStoredBool(LS_LARGE_TEXT),
      highContrast: readStoredBool(LS_CONTRAST),
      reduceMotion: readStoredBool(LS_REDUCE_MOTION),
    })
  }, [])

  // Apply large text: add/remove class on <body>
  React.useEffect(() => {
    if (settings.largeText) {
      document.body.classList.add('text-lg-mode')
    } else {
      document.body.classList.remove('text-lg-mode')
    }
    localStorage.setItem(LS_LARGE_TEXT, String(settings.largeText))
  }, [settings.largeText])

  // Apply high contrast
  React.useEffect(() => {
    if (settings.highContrast) {
      document.body.classList.add('high-contrast-mode')
    } else {
      document.body.classList.remove('high-contrast-mode')
    }
    localStorage.setItem(LS_CONTRAST, String(settings.highContrast))
  }, [settings.highContrast])

  // Apply reduce motion
  React.useEffect(() => {
    if (settings.reduceMotion) {
      document.body.classList.add('reduce-motion-mode')
    } else {
      document.body.classList.remove('reduce-motion-mode')
    }
    localStorage.setItem(LS_REDUCE_MOTION, String(settings.reduceMotion))
  }, [settings.reduceMotion])

  function update<K extends keyof A11ySettings>(key: K, value: boolean) {
    setSettings((prev) => ({ ...prev, [key]: value }))
  }

  return (
    <div className="p-4 max-w-md mx-auto pb-28 space-y-5">
      {/* Header */}
      <header>
        <h1 className="text-[22px] font-extrabold tracking-[-0.02em] text-neu-text">Trợ năng</h1>
        <p className="mt-1 text-[14px] text-neu-muted">
          Tuỳ chỉnh để ứng dụng dễ sử dụng hơn với bạn.
        </p>
      </header>

      {/* Toggleable settings */}
      <NeuCard className="!p-0">
        <div className="px-5 pt-4 pb-1">
          <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-neu-muted">
            Hiển thị
          </p>
        </div>
        <div className="px-5 pb-4">
          <SettingRow
            icon={<Type className="size-5" />}
            iconColor="#0F9C6E"
            title="Chữ lớn"
            description="Tăng kích thước văn bản trong toàn bộ ứng dụng."
            toggleId="a11y-large-text"
            checked={settings.largeText}
            onChange={(v) => update('largeText', v)}
          />
          <SettingRow
            icon={<Contrast className="size-5" />}
            iconColor="#2563EB"
            title="Độ tương phản cao"
            description="Làm nổi bật màu sắc để dễ đọc hơn."
            toggleId="a11y-contrast"
            checked={settings.highContrast}
            onChange={(v) => update('highContrast', v)}
          />
          <SettingRow
            icon={<Zap className="size-5" />}
            iconColor="#C77A06"
            title="Giảm chuyển động"
            description="Tắt hoạt ảnh và hiệu ứng chuyển tiếp."
            toggleId="a11y-reduce-motion"
            checked={settings.reduceMotion}
            onChange={(v) => update('reduceMotion', v)}
          />
        </div>
      </NeuCard>

      {/* Screen reader informational section */}
      <NeuCard>
        <div className="flex items-start gap-3">
          <div className="shrink-0 size-10 rounded-[12px] bg-[rgba(109,63,190,0.12)] flex items-center justify-center">
            <MonitorSpeaker className="size-5 text-[#6D3FBE]" aria-hidden="true" />
          </div>
          <div className="flex-1">
            <p className="text-[15px] font-semibold text-neu-text">Đọc màn hình</p>
            <p className="mt-1 text-[13px] text-neu-muted leading-relaxed">
              Ứng dụng MetoCare hỗ trợ trình đọc màn hình của điện thoại bạn (VoiceOver trên iOS,
              TalkBack trên Android). Bật tính năng này trong phần Cài đặt điện thoại.
            </p>
            <a
              href="https://support.apple.com/vi-vn/111794"
              target="_blank"
              rel="noopener noreferrer"
              className="mt-2.5 inline-flex items-center gap-1 text-[13px] font-semibold text-neu-green"
            >
              Hướng dẫn bật VoiceOver (iOS)
              <ExternalLink className="size-3.5" aria-hidden="true" />
            </a>
          </div>
        </div>
      </NeuCard>
    </div>
  )
}
