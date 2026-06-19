'use client'

import { Stethoscope } from 'lucide-react'
import { PageHeader, Alert, EmptyState } from '@/design-system'

export default function DoctorsPage() {
  return (
    <div className="p-6">
      <PageHeader
        title="Quản lý bác sĩ"
        subtitle="Danh sách và thông tin bác sĩ trong hệ thống"
      />

      <Alert variant="info" title="Tính năng đang phát triển" className="mb-6">
        Màn hình này đang được xây dựng và sẽ sớm ra mắt.
      </Alert>

      <EmptyState
        icon={<Stethoscope />}
        title="Chưa có dữ liệu bác sĩ"
        description="Quản lý thông tin bác sĩ, chứng chỉ hành nghề và phân công phòng khám."
        size="lg"
      />
    </div>
  )
}
