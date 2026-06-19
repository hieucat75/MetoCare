'use client'

import { Building2 } from 'lucide-react'
import { PageHeader, Alert, EmptyState } from '@/design-system'

export default function ClinicsPage() {
  return (
    <div className="p-6">
      <PageHeader
        title="Quản lý phòng khám"
        subtitle="Danh sách và cấu hình phòng khám trong hệ thống"
      />

      <Alert variant="info" title="Tính năng đang phát triển" className="mb-6">
        Màn hình này đang được xây dựng và sẽ sớm ra mắt.
      </Alert>

      <EmptyState
        icon={<Building2 />}
        title="Chưa có dữ liệu phòng khám"
        description="Quản lý danh sách phòng khám, bác sĩ liên kết và cấu hình hệ thống cho từng phòng khám."
        size="lg"
      />
    </div>
  )
}
