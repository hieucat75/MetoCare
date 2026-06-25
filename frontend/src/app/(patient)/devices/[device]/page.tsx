'use client'

import * as React from 'react'
import { useRouter, useParams } from 'next/navigation'
import {
  ArrowLeft,
  ArrowRight,
  AlertCircle,
  Clock,
  Watch,
  Smartphone,
  Activity,
  Scale,
  Droplets,
  Thermometer,
  Heart,
  BarChart2,
} from 'lucide-react'
import { NeuCard, NeuButton } from '@/components/patient/neu'

type DeviceStatus = 'manual' | 'coming-soon'

type ManualFallback = {
  label: string
  href: string
}

type DeviceInfo = {
  name: string
  subtitle: string
  description: string
  icon: React.ElementType
  iconColor: string
  status: DeviceStatus
  whyNative: string
  manualFallbacks: ManualFallback[]
}

const DEVICE_INFO: Record<string, DeviceInfo> = {
  // ── Health Platforms ──────────────────────────────────────────────────────
  'apple-health': {
    name: 'Apple Health',
    subtitle: 'iOS — HealthKit',
    description:
      'Đồng bộ tất cả chỉ số sức khỏe từ Apple Health: nhịp tim, SpO₂, bước chân, chu kỳ giấc ngủ và nhiều hơn nữa.',
    icon: Heart,
    iconColor: '#E03131',
    status: 'coming-soon',
    whyNative:
      'Apple Health yêu cầu quyền truy cập HealthKit — chỉ khả dụng trên ứng dụng iOS native, không hỗ trợ trên trình duyệt web.',
    manualFallbacks: [
      { label: 'Nhập nhịp tim thủ công', href: '/metrics/log/heart_rate' },
      { label: 'Nhập SpO₂ thủ công', href: '/metrics/log/spo2' },
    ],
  },
  'health-connect': {
    name: 'Google Health Connect',
    subtitle: 'Android — Health Connect API',
    description:
      'Kết nối với Health Connect để đồng bộ dữ liệu từ các ứng dụng sức khỏe Android: nhịp tim, bước chân, giấc ngủ, cân nặng.',
    icon: Activity,
    iconColor: '#1A73E8',
    status: 'coming-soon',
    whyNative:
      'Health Connect API yêu cầu quyền truy cập native trên Android — không hỗ trợ từ trình duyệt web.',
    manualFallbacks: [
      { label: 'Nhập nhịp tim thủ công', href: '/metrics/log/heart_rate' },
      { label: 'Nhập cân nặng thủ công', href: '/metrics/log/weight' },
    ],
  },
  'samsung-health': {
    name: 'Samsung Health',
    subtitle: 'Galaxy devices',
    description:
      'Đồng bộ dữ liệu từ Samsung Health trên điện thoại và đồng hồ Galaxy: nhịp tim, huyết áp, SpO₂, giấc ngủ.',
    icon: Smartphone,
    iconColor: '#1428A0',
    status: 'coming-soon',
    whyNative:
      'Samsung Health SDK yêu cầu ứng dụng Android native và tài khoản Samsung — không hỗ trợ trên web.',
    manualFallbacks: [
      { label: 'Nhập nhịp tim thủ công', href: '/metrics/log/heart_rate' },
      { label: 'Nhập huyết áp thủ công', href: '/metrics/log/blood_pressure_systolic' },
    ],
  },
  'huawei-health': {
    name: 'Huawei Health',
    subtitle: 'Huawei & Honor devices',
    description:
      'Tích hợp với Huawei Health Kit để lấy dữ liệu từ điện thoại và đồng hồ Huawei / Honor.',
    icon: Smartphone,
    iconColor: '#CF1322',
    status: 'coming-soon',
    whyNative:
      'Huawei Health Kit yêu cầu HMS Core và ứng dụng Android native — không hỗ trợ trên trình duyệt web.',
    manualFallbacks: [
      { label: 'Nhập nhịp tim thủ công', href: '/metrics/log/heart_rate' },
      { label: 'Nhập SpO₂ thủ công', href: '/metrics/log/spo2' },
    ],
  },

  // ── Wearables ─────────────────────────────────────────────────────────────
  'apple-watch': {
    name: 'Apple Watch',
    subtitle: 'Series 4 trở lên',
    description:
      'Đồng bộ nhịp tim, SpO₂, ECG, số bước chân và chu kỳ giấc ngủ từ Apple Watch qua HealthKit.',
    icon: Watch,
    iconColor: '#0F9C6E',
    status: 'coming-soon',
    whyNative:
      'Apple Watch giao tiếp qua HealthKit (iOS) — cần ứng dụng iOS native để nhận dữ liệu, không hỗ trợ trên web.',
    manualFallbacks: [
      { label: 'Nhập nhịp tim thủ công', href: '/metrics/log/heart_rate' },
      { label: 'Nhập SpO₂ thủ công', href: '/metrics/log/spo2' },
    ],
  },
  garmin: {
    name: 'Garmin',
    subtitle: 'Vivosmart, Forerunner, Fenix...',
    description:
      'Đồng bộ dữ liệu sức khỏe từ thiết bị Garmin: nhịp tim, SpO₂, bước chân, stress, giấc ngủ qua Garmin Connect API.',
    icon: Watch,
    iconColor: '#007CC3',
    status: 'coming-soon',
    whyNative:
      'Garmin Connect API yêu cầu OAuth 2.0 và có thể cần ứng dụng native để đồng bộ — tính năng sẽ có trong ứng dụng di động.',
    manualFallbacks: [
      { label: 'Nhập nhịp tim thủ công', href: '/metrics/log/heart_rate' },
      { label: 'Nhập SpO₂ thủ công', href: '/metrics/log/spo2' },
    ],
  },
  fitbit: {
    name: 'Fitbit',
    subtitle: 'Charge, Sense, Versa...',
    description:
      'Đồng bộ bước chân, nhịp tim, SpO₂, cân nặng và giấc ngủ từ thiết bị Fitbit qua Fitbit Web API.',
    icon: Watch,
    iconColor: '#00B0B9',
    status: 'coming-soon',
    whyNative:
      'Fitbit Web API cần xác thực OAuth qua ứng dụng — tính năng tích hợp sẽ được bổ sung cùng ứng dụng di động MetoCare.',
    manualFallbacks: [
      { label: 'Nhập nhịp tim thủ công', href: '/metrics/log/heart_rate' },
      { label: 'Nhập cân nặng thủ công', href: '/metrics/log/weight' },
    ],
  },

  // ── Bluetooth Medical Devices ─────────────────────────────────────────────
  'blood-pressure': {
    name: 'Máy đo huyết áp',
    subtitle: 'Omron, Citizen và các thương hiệu khác',
    description:
      'Kết nối máy đo huyết áp Bluetooth để ghi nhận huyết áp tâm thu và tâm trương tự động.',
    icon: Activity,
    iconColor: '#7C3AED',
    status: 'manual',
    whyNative:
      'Máy đo huyết áp dùng Bluetooth LE y tế — giao thức BLE cần quyền từ ứng dụng di động, không khả dụng trên web. Bạn có thể nhập kết quả thủ công ngay bây giờ.',
    manualFallbacks: [
      { label: 'Nhập huyết áp thủ công', href: '/metrics/log/blood_pressure_systolic' },
    ],
  },
  'smart-scale': {
    name: 'Cân thông minh',
    subtitle: 'Withings, Xiaomi Mi Scale...',
    description:
      'Đồng bộ cân nặng, BMI và tỷ lệ mỡ cơ thể từ cân thông minh Bluetooth.',
    icon: Scale,
    iconColor: '#2563EB',
    status: 'coming-soon',
    whyNative:
      'Cân thông minh dùng Bluetooth LE — kết nối cần quyền BLE từ ứng dụng di động, không hỗ trợ trên web.',
    manualFallbacks: [
      { label: 'Nhập cân nặng thủ công', href: '/metrics/log/weight' },
    ],
  },
  glucose: {
    name: 'Máy đo đường huyết',
    subtitle: 'Accu-Chek, OneTouch, Freestyle Libre',
    description:
      'Đồng bộ kết quả đường huyết từ máy đo hoặc cảm biến CGM liên tục.',
    icon: Droplets,
    iconColor: '#D97706',
    status: 'manual',
    whyNative:
      'Máy đo đường huyết yêu cầu tích hợp Bluetooth LE hoặc NFC đặc thù của từng thiết bị — chỉ khả dụng trên ứng dụng di động. Bạn có thể nhập kết quả thủ công ngay bây giờ.',
    manualFallbacks: [
      { label: 'Nhập đường huyết thủ công', href: '/metrics/log/fasting_glucose' },
    ],
  },
  'pulse-oximeter': {
    name: 'Máy đo SpO₂',
    subtitle: 'Pulse oximeter Bluetooth',
    description:
      'Đo độ bão hòa oxy trong máu (SpO₂) và nhịp tim từ máy đo xung Bluetooth.',
    icon: Heart,
    iconColor: '#D92D20',
    status: 'manual',
    whyNative:
      'Máy đo SpO₂ Bluetooth dùng giao thức BLE y tế — cần quyền native từ ứng dụng di động. Bạn có thể nhập kết quả thủ công ngay bây giờ.',
    manualFallbacks: [
      { label: 'Nhập SpO₂ thủ công', href: '/metrics/log/spo2' },
      { label: 'Nhập nhịp tim thủ công', href: '/metrics/log/heart_rate' },
    ],
  },
  thermometer: {
    name: 'Nhiệt kế thông minh',
    subtitle: 'iHealth, Braun, Omron...',
    description:
      'Ghi nhận nhiệt độ cơ thể từ nhiệt kế Bluetooth và theo dõi xu hướng theo thời gian.',
    icon: Thermometer,
    iconColor: '#E67E22',
    status: 'manual',
    whyNative:
      'Nhiệt kế Bluetooth dùng BLE — cần quyền native từ ứng dụng di động. Bạn có thể nhập kết quả thủ công ngay bây giờ.',
    manualFallbacks: [
      { label: 'Nhập nhiệt độ thủ công', href: '/metrics/log/temperature' },
    ],
  },
  ecg: {
    name: 'Máy đo ECG',
    subtitle: 'KardiaMobile, AliveCor...',
    description:
      'Ghi và phân tích điện tâm đồ (ECG) từ thiết bị đo chuyên dụng Bluetooth.',
    icon: BarChart2,
    iconColor: '#C0392B',
    status: 'coming-soon',
    whyNative:
      'Thiết bị ECG yêu cầu phần cứng chuyên dụng và giao thức Bluetooth đặc thù — cần ứng dụng di động với quyền BLE đặc biệt và pipeline xử lý tín hiệu y tế.',
    manualFallbacks: [],
  },
  'body-composition': {
    name: 'Máy phân tích cơ thể',
    subtitle: 'Withings Body+, InBody...',
    description:
      'Đo cân nặng, BMI, tỷ lệ mỡ, khối cơ và lượng nước trong cơ thể qua Bluetooth.',
    icon: Scale,
    iconColor: '#16A085',
    status: 'coming-soon',
    whyNative:
      'Thiết bị phân tích cơ thể dùng Bluetooth LE — kết nối cần quyền BLE từ ứng dụng di động. Bạn có thể nhập chỉ số cân nặng và BMI thủ công ngay bây giờ.',
    manualFallbacks: [
      { label: 'Nhập cân nặng thủ công', href: '/metrics/log/weight' },
      { label: 'Nhập BMI thủ công', href: '/metrics/log/bmi' },
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

  const device = DEVICE_INFO[slug]
  const Icon = device.icon
  const isManual = device.status === 'manual'

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
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <p className="text-[15px] font-bold text-neu-text">{device.name}</p>
              {isManual ? (
                <span className="rounded-full bg-[#ECFDF5] px-2 py-0.5 text-[10px] font-bold text-[#059669]">
                  Nhập thủ công
                </span>
              ) : (
                <span className="rounded-full bg-[#EFF6FF] px-2 py-0.5 text-[10px] font-bold text-[#2563EB]">
                  Sắp hỗ trợ
                </span>
              )}
            </div>
            <p className="text-[12px] text-neu-muted mt-0.5">{device.subtitle}</p>
          </div>
        </div>
        <p className="mt-3 text-[14px] text-neu-muted leading-relaxed">{device.description}</p>
      </NeuCard>

      {/* Status notice */}
      {isManual ? (
        <div className="rounded-[14px] bg-[#F0FDF4] border border-[#86EFAC] px-4 py-4">
          <div className="flex items-start gap-3">
            <Clock className="size-5 text-[#16A34A] shrink-0 mt-0.5" aria-hidden />
            <div>
              <p className="text-[13px] font-bold text-[#15803D]">
                Kết nối BLE tự động — sắp ra mắt
              </p>
              <p className="text-[12px] text-[#16A34A] mt-1 leading-relaxed">
                {device.whyNative}
              </p>
            </div>
          </div>
        </div>
      ) : (
        <div className="rounded-[14px] bg-[#EFF6FF] border border-[#BFDBFE] px-4 py-4">
          <div className="flex items-start gap-3">
            <AlertCircle className="size-5 text-[#2563EB] shrink-0 mt-0.5" aria-hidden />
            <div>
              <p className="text-[13px] font-bold text-[#1D4ED8]">Sắp hỗ trợ kết nối tự động</p>
              <p className="text-[12px] text-[#3B82F6] mt-1 leading-relaxed">{device.whyNative}</p>
            </div>
          </div>
        </div>
      )}

      {/* Manual fallback section */}
      {device.manualFallbacks.length > 0 && (
        <section>
          <p className="mb-2 px-1 text-[11px] font-semibold uppercase tracking-[0.06em] text-neu-muted">
            {isManual ? 'Nhập thủ công' : 'Nhập thủ công trong khi chờ'}
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
        <p className="text-[13px] text-neu-muted text-center leading-relaxed px-2">
          Tính năng ghi nhận thủ công cho thiết bị này sẽ được bổ sung cùng ứng dụng di động.
        </p>
      )}

      <NeuButton variant="secondary" onClick={() => router.push('/devices')}>
        Xem tất cả thiết bị
      </NeuButton>
    </div>
  )
}
