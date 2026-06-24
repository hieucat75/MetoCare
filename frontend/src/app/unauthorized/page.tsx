'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import { ShieldOff } from 'lucide-react'
import { useAuth } from '@/lib/auth/context'
import { NeuButton } from '@/components/patient/neu'

export default function UnauthorizedPage() {
  const { user, logout } = useAuth()
  const router = useRouter()

  const handleLogout = async () => {
    await logout()
    router.replace('/login')
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-4">
      <div className="max-w-sm w-full text-center">
        <div className="w-16 h-16 rounded-2xl bg-danger-light flex items-center justify-center mx-auto mb-6">
          <ShieldOff className="w-8 h-8 text-danger" aria-hidden="true" />
        </div>
        <h1 className="text-display-xs font-bold text-text mb-2">Không có quyền truy cập</h1>
        <p className="text-body-md text-text-muted mb-2">
          Trang này không dành cho tài khoản của bạn.
        </p>
        {user && (
          <p className="text-body-sm text-text-subtle mb-8">
            Đang đăng nhập với: <span className="font-medium text-text">{user.email}</span>
          </p>
        )}
        <div className="flex flex-col gap-3">
          <NeuButton onClick={() => router.back()}>Quay lại</NeuButton>
          <NeuButton variant="secondary" onClick={handleLogout}>
            Đăng xuất
          </NeuButton>
        </div>
      </div>
    </div>
  )
}
