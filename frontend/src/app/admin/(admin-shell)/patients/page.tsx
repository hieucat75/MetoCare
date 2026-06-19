'use client'

import { UserCog } from 'lucide-react'
import { PageHeader, Alert, EmptyState } from '@/design-system'

export default function PatientsAdminPage() {
  return (
    <div className="p-6">
      <PageHeader
        title="Quản lý bệnh nhân"
        subtitle="Xem và quản lý thông tin bệnh nhân toàn hệ thống"
      />

      <Alert variant="info" title="Tính năng đang phát triển" className="mb-6">
        Màn hình này đang được xây dựng và sẽ sớm ra mắt.
      </Alert>

      <EmptyState
        icon={<UserCog />}
        title="Chưa có dữ liệu bệnh nhân"
        description="Xem và quản lý thông tin bệnh nhân trong toàn hệ thống (dành cho admin nội bộ)."
        size="lg"
      />
    </div>
  )
}
