'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { Activity, TrendingUp, Users, Bell, Camera, Database, ChevronRight } from 'lucide-react'
import { NeuCard, NeuButton } from '@/components/patient/neu'

type Step = 'splash' | 'carousel1' | 'carousel2' | 'carousel3' | 'permission'

const DOT_INDEX: Record<Step, number> = {
  carousel1: 0,
  carousel2: 1,
  carousel3: 2,
  splash: -1,
  permission: -1,
}

type PermissionKey = 'notifications' | 'camera' | 'data'

interface PermissionState {
  notifications: boolean
  camera: boolean
  data: boolean
}

function DotPagination({ active }: { active: number }) {
  return (
    <div className="flex items-center justify-center gap-2 mt-6">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="block rounded-full transition-all duration-300"
          style={{
            width: i === active ? '24px' : '8px',
            height: '8px',
            backgroundColor: i === active ? '#0F9C6E' : '#B0C4C0',
          }}
        />
      ))}
    </div>
  )
}

function SplashScreen() {
  return (
    <div
      className="flex flex-col items-center justify-center min-h-screen w-full px-8"
      style={{ background: 'linear-gradient(160deg,#17AE7B,#0B6B4D)' }}
    >
      <div className="flex flex-col items-center gap-6">
        <div className="relative">
          <div
            className="w-24 h-24 rounded-3xl flex items-center justify-center"
            style={{ backgroundColor: 'rgba(255,255,255,0.2)', backdropFilter: 'blur(12px)' }}
          >
            <svg width="52" height="52" viewBox="0 0 52 52" fill="none" aria-label="MetoCare logo">
              <path
                d="M26 8C16.059 8 8 16.059 8 26s8.059 18 18 18 18-8.059 18-18S35.941 8 26 8zm0 4a14 14 0 1 1 0 28 14 14 0 0 1 0-28z"
                fill="white"
                fillOpacity="0.9"
              />
              <path
                d="M18 26l5 5 11-11"
                stroke="white"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </div>
          <div
            className="absolute inset-0 rounded-3xl animate-ping"
            style={{ backgroundColor: 'rgba(255,255,255,0.15)', animationDuration: '2s' }}
          />
        </div>

        <div className="text-center">
          <h1 className="text-4xl font-bold text-white tracking-tight">MetoCare</h1>
          <p className="mt-3 text-lg text-white/80 font-medium">
            Quản lý chuyển hoá của bạn
          </p>
        </div>
      </div>

      <div className="mt-16 flex gap-1.5">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="block w-2 h-2 rounded-full bg-white/40 animate-pulse"
            style={{ animationDelay: `${i * 200}ms` }}
          />
        ))}
      </div>
    </div>
  )
}

interface CarouselScreenProps {
  step: 'carousel1' | 'carousel2' | 'carousel3'
  onNext: () => void
  onSkip: () => void
}

const CAROUSEL_CONTENT = {
  carousel1: {
    icon: <Activity size={48} strokeWidth={1.5} color="#0F9C6E" />,
    title: 'Theo dõi chỉ số',
    description:
      'Ghi lại và theo dõi các chỉ số chuyển hoá quan trọng như đường huyết, lipid máu, cân nặng — mọi lúc, mọi nơi.',
    isLast: false,
  },
  carousel2: {
    icon: <TrendingUp size={48} strokeWidth={1.5} color="#0F9C6E" />,
    title: 'Phân tích thông minh',
    description:
      'Hệ thống phân tích xu hướng sức khoẻ của bạn và đưa ra gợi ý phù hợp với mục tiêu điều trị cá nhân.',
    isLast: false,
  },
  carousel3: {
    icon: <Users size={48} strokeWidth={1.5} color="#0F9C6E" />,
    title: 'Kết nối bác sĩ',
    description:
      'Chia sẻ dữ liệu sức khoẻ với bác sĩ của bạn để được tư vấn kịp thời và điều chỉnh phác đồ điều trị hiệu quả.',
    isLast: true,
  },
} as const

function CarouselScreen({ step, onNext, onSkip }: CarouselScreenProps) {
  const { icon, title, description, isLast } = CAROUSEL_CONTENT[step]
  const dotIndex = DOT_INDEX[step]

  return (
    <div className="flex flex-col min-h-screen bg-[#E8EEE8] max-w-md mx-auto">
      <div className="flex justify-end px-4 pt-12 pb-2">
        <button
          type="button"
          onClick={onSkip}
          className="text-sm font-medium text-[#2B4040]/60 px-3 py-1.5 rounded-full hover:bg-[#2B4040]/10 transition-colors"
        >
          Bỏ qua
        </button>
      </div>

      <div className="flex-1 flex flex-col items-center justify-center px-6 pb-8">
        <NeuCard className="w-full text-center">
          <div className="flex items-center justify-center mb-6">
            <div
              className="w-24 h-24 rounded-2xl flex items-center justify-center"
              style={{ backgroundColor: '#E8EEE8', boxShadow: '6px 6px 12px #c8d4c8,-6px -6px 12px #ffffff' }}
            >
              {icon}
            </div>
          </div>

          <h2 className="text-2xl font-bold text-[#2B4040] mb-3">{title}</h2>
          <p className="text-[#2B4040]/70 leading-relaxed text-[15px]">{description}</p>

          <DotPagination active={dotIndex} />
        </NeuCard>

        <div className="w-full mt-8">
          <NeuButton onClick={onNext} className="flex items-center justify-center gap-2">
            {isLast ? 'Bắt đầu' : 'Tiếp theo'}
            <ChevronRight size={18} />
          </NeuButton>
        </div>
      </div>
    </div>
  )
}

const PERMISSION_ITEMS: Array<{ key: PermissionKey; icon: React.ReactNode; label: string; description: string }> = [
  {
    key: 'notifications',
    icon: <Bell size={22} color="#0F9C6E" strokeWidth={1.5} />,
    label: 'Thông báo',
    description: 'Nhắc nhở uống thuốc và kiểm tra chỉ số',
  },
  {
    key: 'camera',
    icon: <Camera size={22} color="#0F9C6E" strokeWidth={1.5} />,
    label: 'Camera',
    description: 'Chụp và tải lên kết quả xét nghiệm',
  },
  {
    key: 'data',
    icon: <Database size={22} color="#0F9C6E" strokeWidth={1.5} />,
    label: 'Dữ liệu sức khoẻ',
    description: 'Đồng bộ với ứng dụng sức khoẻ của thiết bị',
  },
]

interface PermissionRowProps {
  icon: React.ReactNode
  label: string
  description: string
  enabled: boolean
  onToggle: () => void
}

function PermissionRow({ icon, label, description, enabled, onToggle }: PermissionRowProps) {
  return (
    <div className="flex items-center gap-4 py-3">
      <div
        className="w-11 h-11 rounded-xl flex items-center justify-center flex-shrink-0"
        style={{ backgroundColor: '#E8EEE8', boxShadow: '3px 3px 8px #c8d4c8,-3px -3px 8px #ffffff' }}
      >
        {icon}
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-[#2B4040] font-semibold text-sm">{label}</p>
        <p className="text-[#2B4040]/60 text-xs mt-0.5 truncate">{description}</p>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={enabled}
        onClick={onToggle}
        className="relative flex-shrink-0 w-12 h-7 rounded-full transition-colors duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#0F9C6E]"
        style={{ backgroundColor: enabled ? '#0F9C6E' : '#B0C4C0' }}
      >
        <span
          className="absolute top-1 left-1 w-5 h-5 rounded-full bg-white shadow-sm transition-transform duration-200"
          style={{ transform: enabled ? 'translateX(20px)' : 'translateX(0)' }}
        />
      </button>
    </div>
  )
}

interface PermissionScreenProps {
  onContinue: () => void
}

function PermissionScreen({ onContinue }: PermissionScreenProps) {
  const [permissions, setPermissions] = useState<PermissionState>({
    notifications: true,
    camera: false,
    data: false,
  })

  const handleToggle = (key: PermissionKey) => {
    setPermissions((prev) => ({ ...prev, [key]: !prev[key] }))
  }

  return (
    <div className="flex flex-col min-h-screen bg-[#E8EEE8] max-w-md mx-auto">
      <div className="flex-1 flex flex-col justify-center px-6 pb-8 pt-16">
        <div className="mb-8">
          <h2 className="text-2xl font-bold text-[#2B4040]">
            Để ứng dụng hoạt động tốt hơn
          </h2>
          <p className="text-[#2B4040]/60 mt-2 text-sm leading-relaxed">
            Chọn quyền bạn muốn cho phép. Bạn có thể thay đổi trong Cài đặt bất kỳ lúc nào.
          </p>
        </div>

        <NeuCard className="w-full">
          <div className="divide-y divide-[#2B4040]/10">
            {PERMISSION_ITEMS.map(({ key, icon, label, description }) => (
              <PermissionRow
                key={key}
                icon={icon}
                label={label}
                description={description}
                enabled={permissions[key]}
                onToggle={() => handleToggle(key)}
              />
            ))}
          </div>
        </NeuCard>

        <div className="mt-8">
          <NeuButton onClick={onContinue}>Tiếp tục</NeuButton>
        </div>
      </div>
    </div>
  )
}

export default function IntroPage() {
  const router = useRouter()
  const [step, setStep] = useState<Step>('splash')

  useEffect(() => {
    if (step !== 'splash') return
    const timer = setTimeout(() => setStep('carousel1'), 2500)
    return () => clearTimeout(timer)
  }, [step])

  const handleNext = () => {
    if (step === 'carousel1') setStep('carousel2')
    else if (step === 'carousel2') setStep('carousel3')
    else if (step === 'carousel3') setStep('permission')
  }

  const handleSkip = () => {
    localStorage.setItem('intro_seen', '1')
    router.replace('/login')
  }

  const handleContinue = () => {
    localStorage.setItem('intro_seen', '1')
    router.replace('/login')
  }

  if (step === 'splash') return <SplashScreen />

  if (step === 'carousel1' || step === 'carousel2' || step === 'carousel3') {
    return (
      <CarouselScreen
        step={step}
        onNext={handleNext}
        onSkip={handleSkip}
      />
    )
  }

  return <PermissionScreen onContinue={handleContinue} />
}
