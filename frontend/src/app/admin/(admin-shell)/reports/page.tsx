'use client'

import { BarChart3 } from 'lucide-react'
import { PageHeader, Alert, EmptyState } from '@/design-system'

export default function ReportsPage() {
  return (
    <div className="p-6">
      <PageHeader
        title="Báo cáo & Thống kê"
        subtitle="Tổng hợp dữ liệu hoạt động và hiệu quả hệ thống"
      />

      <Alert variant="info" title="Tính năng đang phát triển" className="mb-6">
        Màn hình này đang được xây dựng và sẽ sớm ra mắt.
      </Alert>

      <EmptyState
        icon={<BarChart3 />}
        title="Chưa có báo cáo"
        description="Báo cáo tổng hợp về hoạt động của hệ thống, hiệu quả điều trị và an toàn AI."
        size="lg"
      />
    </div>
  )
}
