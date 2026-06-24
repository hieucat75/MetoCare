'use client'

import * as React from 'react'
import { useRouter, useParams } from 'next/navigation'
import {
  ArrowLeft,
  Watch,
  Smartphone,
  Heart,
  Activity,
  Droplets,
  AlertCircle,
  ArrowRight,
} from 'lucide-react'
import { NeuCard, NeuButton } from '@/components/patient/neu'

type DeviceSlug = 'smartwatch' | 'steps' | 'heart-rate' | 'blood-pressure' | 'glucose'

type ManualFallback = { label: string; href: string }

type DeviceInfo = {
  name: string
  subtitle: string
  description: string
  icon: React.ElementType
  iconColor: string
  whyNative: string
  manualFallbacks: ManualFallback[]
}

const DEVICE_INFO: Record<DeviceSlug, DeviceInfo> = {
  smartwatch: {
    name: 'Đồng hồ thông minh',
    subtitle: 'Apple Watch, Galaxy Watch, Garmin, Fitbit',
    description: 'Đồng bộ nhịp tim, SpO₂ và số bước chân từ đồng hồ thông minh của bạn.',
    icon: Watch,
    iconColor: '#0F9C6E',
    whyNative:
      'Kết nối đồng hồ thông minh cần quyền truy cập HealthKit (iOS) hoặc Health Connect (Android) — chỉ khả dụng trên ứng dụng di động, không hỗ trợ trên trình duyệt web.',
    manualFallbacks: [
      { label: 'Nhập nhịp tim thủ công', href: '/metrics/log/heart_rate' },
      { label: 'Nhập SpO₂ thủ công', href: '/metrics/log/spo2' },
    ],
  },
  steps: {
    name: 'Bộ đếm bước chân',
    subtitle: 'Cảm biến điện thoại / thiết bị đeo',
    description: 'Theo dõi số bước chân hằng ngày qua điện thoại hoặc vòng đeo tay thông minh.',
    icon: Smartphone,
    iconColor: '#2563EB',
    whyNative:
      'Đếm bước chân cần quyền truy cập cảm biến chuyển động (pedometer) của điện thoại — tính năng này sẽ được bổ sung trong ứng dụng di động.',
    manualFallbacks: [],
  },
  'heart-rate': {
    name: 'Máy đo nhịp tim',
    subtitle: 'Thiết bị đo nhịp tim chuyên dụng',
    description: 'Kết nối máy đo nhịp tim Bluetooth để ghi nhận và theo dõi tự động.',
    icon: Heart,
    iconColor: '#D92D20',
    whyNative:
      'Máy đo nhịp tim sử dụng giao thức Bluetooth Low Energy (BLE) y tế — không hỗ trợ kết nối trực tiếp từ trình duyệt web. Tính năng sẽ có trong ứng dụng di động.',
    manualFallbacks: [{ label: 'Nhập nhịp tim thủ công', href: '/metrics/log/heart_rate' }],
  },
  'blood-pressure': {
    name: 'Máy đo huyết áp',
    subtitle: 'Omron, Citizen và các thương hiệu khác',
    description:
      'Kết nối máy đo huyết áp Bluetooth để ghi nhận huyết áp tâm thu và tâm trương tự động.',
    icon: Activity,
    iconColor: '#7C3AED',
    whyNative:
      'Máy đo huyết áp dùng Bluetooth LE y tế — giao thức này cần quyền BLE từ ứng dụng di động, không khả dụng trên web.',
    manualFallbacks: [
      { label: 'Nhập huyết áp thủ công', href: '/metrics/log/blood_pressure_systolic' },
    ],
  },
  glucose: {
    name: 'Máy đo đường huyết',
    subtitle: 'Accu-Chek, OneTouch, Freestyle Libre',
    description: 'Đồng bộ kết quả đường huyết từ máy đo hoặc cảm biến CGM liên tục.',
    icon: Droplets,
    iconColor: '#D97706',
    whyNative:
      'Kết nối máy đo đường huyết yêu cầu tích hợp Bluetooth LE hoặc NFC đặc thù của từng thiết bị — chỉ khả dụng trên ứng dụng di động.',
    manualFallbacks: [
      { label: 'Nhập đường huyết thủ công', href: '/metrics/log/fasting_glucose' },
    ],
  },
}

const VALID_SLUGS = new Set(Object.keys(DEVICE_INFO))

export default function DeviceDetailPage() {
  const router = useRouter()
  const params = useParams()
  const slug = typeof params.device === 'string' ? params.device : ''

  if (!VALID_SLUGS.has(slug)) {
    return (
      <div className="p-4 max-w-md mx-auto mt-10">
        <div
          role="alert"
          className="rounded-[14px] bg-[#FEF9EC] border border-[#E0A92E]/30 p-4 text-[14px]"
        >
          <p className="font-bold text-[#8B6400]">Thiết bị không tồn tại</p>
          <button
            type="button"
            onClick={() => router.back()}
            className="mt-2 text-[13px] text-[#0F9C6E] font-semibold"
          >
            ← Quay lại
          </button>
        </div>
      </div>
    )
  }

  const device = DEVICE_INFO[slug as DeviceSlug]
  const Icon = device.icon

  return (
    <div className="p-4 max-w-md mx-auto pb-28 space-y-5">
      <header className="flex items-center gap-3">
        <button
          type="button"
          aria-label="Quay lại"
          onClick={() => router.back()}
          className="neu-icon-btn !h-11 !w-11 !rounded-full text-neu-text"
        >
          <ArrowLeft className="size-5" />
        </button>
        <h1 className="text-[20px] font-extrabold tracking-[-0.02em] text-neu-text">
          {device.name}
        </h1>
      </header>

      {/* Device summary card */}
      <NeuCard>
        <div className="flex items-center gap-4">
          <div
            className="size-14 rounded-[16px] flex items-center justify-center shrink-0"
            style={{ backgroundColor: `${device.iconColor}1A` }}
          >
            <Icon className="size-8" style={{ color: device.iconColor }} aria-hidden />
          </div>
          <div>
            <p className="text-[15px] font-bold text-neu-text">{device.name}</p>
            <p className="text-[12px] text-neu-muted">{device.subtitle}</p>
          </div>
        </div>
        <p className="mt-3 text-[14px] text-neu-muted leading-relaxed">{device.description}</p>
      </NeuCard>

      {/* Honest coming-soon notice — explains web limitation clearly */}
      <div className="rounded-[14px] bg-[#EFF6FF] border border-[#BFDBFE] px-4 py-4">
        <div className="flex items-start gap-3">
          <AlertCircle className="size-5 text-[#2563EB] shrink-0 mt-0.5" aria-hidden />
          <div>
            <p className="text-[13px] font-bold text-[#1D4ED8]">Sắp hỗ trợ kết nối tự động</p>
            <p className="text-[12px] text-[#3B82F6] mt-1 leading-relaxed">{device.whyNative}</p>
          </div>
        </div>
      </div>

      {/* Manual fallback section — only rendered when metric types exist */}
      {device.manualFallbacks.length > 0 && (
        <section>
          <p className="mb-2 px-1 text-[11px] font-semibold uppercase tracking-[0.06em] text-neu-muted">
            Nhập thủ công trong khi chờ
          </p>
          <NeuCard className="!px-4 !py-1">
            {device.manualFallbacks.map(({ label, href }, idx) => (
              <button
                key={href}
                type="button"
                onClick={() => router.push(href)}
                className={`flex w-full items-center gap-3 py-3.5 text-left${
                  idx < device.manualFallbacks.length - 1
                    ? ' border-b border-[rgba(16,48,44,0.06)]'
                    : ''
                }`}
              >
                <span className="flex-1 text-[14px] font-semibold text-neu-text">{label}</span>
                <ArrowRight className="size-[18px] text-neu-subtle" aria-hidden />
              </button>
            ))}
          </NeuCard>
          <p className="mt-2 px-1 text-[12px] text-neu-muted leading-relaxed">
            Chỉ số nhập thủ công sẽ được lưu vào hồ sơ và hiển thị trên biểu đồ.
          </p>
        </section>
      )}

      {device.manualFallbacks.length === 0 && (
        <p className="text-[13px] text-neu-muted text-center leading-relaxed">
          Tính năng ghi nhận thủ công cho chỉ số này sẽ được bổ sung cùng ứng dụng di động.
        </p>
      )}

      <NeuButton variant="secondary" onClick={() => router.push('/devices')}>
        Xem tất cả thiết bị
      </NeuButton>
    </div>
  )
}
