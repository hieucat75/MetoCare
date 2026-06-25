'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import {
  ArrowLeft,
  ChevronRight,
  Smartphone,
  Watch,
  Activity,
  Scale,
  Droplets,
  Thermometer,
  Heart,
  BarChart2,
} from 'lucide-react'
import { NeuCard } from '@/components/patient/neu'

type DeviceStatus = 'manual' | 'coming-soon'

type DeviceEntry = {
  slug: string
  name: string
  subtitle: string
  icon: React.ElementType
  iconColor: string
  status: DeviceStatus
}

type DeviceCategory = {
  id: string
  title: string
  devices: DeviceEntry[]
}

const CATEGORIES: DeviceCategory[] = [
  {
    id: 'platforms',
    title: 'Nền tảng sức khỏe',
    devices: [
      {
        slug: 'apple-health',
        name: 'Apple Health',
        subtitle: 'iOS — HealthKit',
        icon: Heart,
        iconColor: '#E03131',
        status: 'coming-soon',
      },
      {
        slug: 'health-connect',
        name: 'Google Health Connect',
        subtitle: 'Android — Health Connect API',
        icon: Activity,
        iconColor: '#1A73E8',
        status: 'coming-soon',
      },
      {
        slug: 'samsung-health',
        name: 'Samsung Health',
        subtitle: 'Galaxy devices',
        icon: Smartphone,
        iconColor: '#1428A0',
        status: 'coming-soon',
      },
      {
        slug: 'huawei-health',
        name: 'Huawei Health',
        subtitle: 'Huawei & Honor devices',
        icon: Smartphone,
        iconColor: '#CF1322',
        status: 'coming-soon',
      },
    ],
  },
  {
    id: 'wearables',
    title: 'Thiết bị đeo',
    devices: [
      {
        slug: 'apple-watch',
        name: 'Apple Watch',
        subtitle: 'Series 4 trở lên',
        icon: Watch,
        iconColor: '#0F9C6E',
        status: 'coming-soon',
      },
      {
        slug: 'garmin',
        name: 'Garmin',
        subtitle: 'Vivosmart, Forerunner, Fenix...',
        icon: Watch,
        iconColor: '#007CC3',
        status: 'coming-soon',
      },
      {
        slug: 'fitbit',
        name: 'Fitbit',
        subtitle: 'Charge, Sense, Versa...',
        icon: Watch,
        iconColor: '#00B0B9',
        status: 'coming-soon',
      },
    ],
  },
  {
    id: 'bluetooth-medical',
    title: 'Thiết bị y tế Bluetooth',
    devices: [
      {
        slug: 'blood-pressure',
        name: 'Máy đo huyết áp',
        subtitle: 'Omron, Citizen và các thương hiệu khác',
        icon: Activity,
        iconColor: '#7C3AED',
        status: 'manual',
      },
      {
        slug: 'smart-scale',
        name: 'Cân thông minh',
        subtitle: 'Withings, Xiaomi Mi Scale...',
        icon: Scale,
        iconColor: '#2563EB',
        status: 'coming-soon',
      },
      {
        slug: 'glucose',
        name: 'Máy đo đường huyết',
        subtitle: 'Accu-Chek, OneTouch, Freestyle Libre',
        icon: Droplets,
        iconColor: '#D97706',
        status: 'manual',
      },
      {
        slug: 'pulse-oximeter',
        name: 'Máy đo SpO₂',
        subtitle: 'Pulse oximeter Bluetooth',
        icon: Heart,
        iconColor: '#D92D20',
        status: 'manual',
      },
      {
        slug: 'thermometer',
        name: 'Nhiệt kế thông minh',
        subtitle: 'iHealth, Braun, Omron...',
        icon: Thermometer,
        iconColor: '#E67E22',
        status: 'manual',
      },
      {
        slug: 'ecg',
        name: 'Máy đo ECG',
        subtitle: 'KardiaMobile, AliveCor...',
        icon: BarChart2,
        iconColor: '#C0392B',
        status: 'coming-soon',
      },
      {
        slug: 'body-composition',
        name: 'Máy phân tích cơ thể',
        subtitle: 'Withings Body+, InBody...',
        icon: Scale,
        iconColor: '#16A085',
        status: 'coming-soon',
      },
    ],
  },
]

function StatusBadge({ status }: { status: DeviceStatus }) {
  if (status === 'manual') {
    return (
      <span className="rounded-full bg-[#ECFDF5] px-2 py-0.5 text-[10px] font-bold text-[#059669] shrink-0">
        Nhập thủ công
      </span>
    )
  }
  return (
    <span className="rounded-full bg-[#EFF6FF] px-2 py-0.5 text-[10px] font-bold text-[#2563EB] shrink-0">
      Sắp hỗ trợ
    </span>
  )
}

export default function DevicesPage() {
  const router = useRouter()

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
          Kết nối thiết bị
        </h1>
      </header>

      {/* Informational banner */}
      <div className="rounded-[14px] bg-[#EFF6FF] border border-[#BFDBFE] px-4 py-3">
        <p className="text-[13px] font-bold text-[#1D4ED8]">Kết nối tự động đang được phát triển</p>
        <p className="text-[12px] text-[#3B82F6] mt-0.5 leading-relaxed">
          Thiết bị có nhãn <span className="font-semibold text-[#059669]">Nhập thủ công</span> đã có
          thể ghi chỉ số ngay bây giờ. Các thiết bị khác sẽ hỗ trợ khi ứng dụng di động ra mắt.
        </p>
      </div>

      {/* Device categories */}
      {CATEGORIES.map((category) => (
        <section key={category.id} className="space-y-2">
          <p className="px-1 text-[11px] font-semibold uppercase tracking-[0.06em] text-neu-muted">
            {category.title}
          </p>
          <NeuCard className="!px-4 !py-1">
            {category.devices.map(
              ({ slug, name, subtitle, icon: Icon, iconColor, status }, idx) => (
                <button
                  key={slug}
                  type="button"
                  onClick={() => router.push(`/devices/${slug}`)}
                  className={`flex w-full items-center gap-3 py-3.5 text-left${
                    idx < category.devices.length - 1
                      ? ' border-b border-[rgba(16,48,44,0.06)]'
                      : ''
                  }`}
                >
                  <div
                    className="size-9 rounded-[10px] flex items-center justify-center shrink-0"
                    style={{ backgroundColor: `${iconColor}1A` }}
                  >
                    <Icon className="size-5" style={{ color: iconColor }} aria-hidden />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-[14.5px] font-semibold text-neu-text leading-tight">
                      {name}
                    </p>
                    <p className="text-[12px] text-neu-muted mt-0.5 truncate">{subtitle}</p>
                  </div>
                  <StatusBadge status={status} />
                  <ChevronRight className="size-[18px] text-neu-subtle shrink-0" aria-hidden />
                </button>
              )
            )}
          </NeuCard>
        </section>
      ))}

      <p className="text-center text-[12px] text-neu-muted px-2">
        Khi ứng dụng di động ra mắt, thiết bị sẽ kết nối qua Bluetooth và HealthKit / Health
        Connect.
      </p>
    </div>
  )
}
