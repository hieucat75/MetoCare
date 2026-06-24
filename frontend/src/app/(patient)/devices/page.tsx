'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import { ArrowLeft, Watch, Smartphone, Heart, Activity, Droplets, ChevronRight } from 'lucide-react'
import { NeuCard } from '@/components/patient/neu'

type DeviceSlug = 'smartwatch' | 'steps' | 'heart-rate' | 'blood-pressure' | 'glucose'

type DeviceConfig = {
  key: DeviceSlug
  name: string
  subtitle: string
  icon: React.ElementType
  iconColor: string
}

const DEVICES: DeviceConfig[] = [
  {
    key: 'smartwatch',
    name: 'Đồng hồ thông minh',
    subtitle: 'Apple Watch, Galaxy Watch, Garmin, Fitbit',
    icon: Watch,
    iconColor: '#0F9C6E',
  },
  {
    key: 'steps',
    name: 'Bộ đếm bước chân',
    subtitle: 'Cảm biến điện thoại / thiết bị đeo',
    icon: Smartphone,
    iconColor: '#2563EB',
  },
  {
    key: 'heart-rate',
    name: 'Máy đo nhịp tim',
    subtitle: 'Thiết bị đo nhịp tim chuyên dụng',
    icon: Heart,
    iconColor: '#D92D20',
  },
  {
    key: 'blood-pressure',
    name: 'Máy đo huyết áp',
    subtitle: 'Omron, Citizen và các thương hiệu khác',
    icon: Activity,
    iconColor: '#7C3AED',
  },
  {
    key: 'glucose',
    name: 'Máy đo đường huyết',
    subtitle: 'Accu-Chek, OneTouch, Freestyle Libre',
    icon: Droplets,
    iconColor: '#D97706',
  },
]

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

      {/* Coming-soon banner */}
      <div className="rounded-[14px] bg-[#EFF6FF] border border-[#BFDBFE] px-4 py-3">
        <p className="text-[13px] font-bold text-[#1D4ED8]">
          Kết nối tự động đang được phát triển
        </p>
        <p className="text-[12px] text-[#3B82F6] mt-0.5 leading-relaxed">
          Bạn có thể nhập chỉ số thủ công qua từng thiết bị trong khi chờ tính năng ra mắt.
        </p>
      </div>

      {/* Device list */}
      <section>
        <NeuCard className="!px-4 !py-1">
          {DEVICES.map(({ key, name, subtitle, icon: Icon, iconColor }, idx) => (
            <button
              key={key}
              type="button"
              onClick={() => router.push(`/devices/${key}`)}
              className={`flex w-full items-center gap-3 py-3.5 text-left${
                idx < DEVICES.length - 1 ? ' border-b border-[rgba(16,48,44,0.06)]' : ''
              }`}
            >
              <div
                className="size-9 rounded-[10px] flex items-center justify-center shrink-0"
                style={{ backgroundColor: `${iconColor}1A` }}
              >
                <Icon className="size-5" style={{ color: iconColor }} aria-hidden />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-[14.5px] font-semibold text-neu-text leading-tight">{name}</p>
                <p className="text-[12px] text-neu-muted mt-0.5 truncate">{subtitle}</p>
              </div>
              <span className="rounded-full bg-[#EFF6FF] px-2 py-0.5 text-[10px] font-bold text-[#2563EB] shrink-0">
                Sắp hỗ trợ
              </span>
              <ChevronRight className="size-[18px] text-neu-subtle shrink-0" aria-hidden />
            </button>
          ))}
        </NeuCard>
      </section>

      <p className="text-center text-[12px] text-neu-muted px-2">
        Khi ứng dụng di động ra mắt, thiết bị sẽ kết nối qua Bluetooth và HealthKit / Health
        Connect.
      </p>
    </div>
  )
}
