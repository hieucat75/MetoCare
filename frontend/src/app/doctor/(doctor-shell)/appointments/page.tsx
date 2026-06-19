'use client'

import * as React from 'react'
import { Calendar } from 'lucide-react'
import { PageHeader, Card, EmptyState, Alert } from '@/design-system'

export default function AppointmentsPage() {
  return (
    <div className="p-6 space-y-6">
      <PageHeader
        title="Lịch hẹn"
        subtitle="Quản lý lịch hẹn với bệnh nhân"
      />

      <Alert variant="info">
        Tính năng này sẽ được ra mắt trong phiên bản tiếp theo.
      </Alert>

      <Card>
        <EmptyState
          icon={<Calendar />}
          title="Tính năng lịch hẹn đang được phát triển"
          description="Chức năng đặt và quản lý lịch hẹn sẽ sớm ra mắt. Vui lòng theo dõi các cập nhật tiếp theo."
          size="lg"
        />
      </Card>

      <Card>
        <div className="px-2 py-1 space-y-1">
          <p className="text-body-sm font-semibold text-text">Liên hệ bệnh nhân</p>
          <p className="text-body-sm text-text-muted">
            Hiện tại, vui lòng liên hệ bệnh nhân qua hệ thống tin nhắn.
          </p>
        </div>
      </Card>
    </div>
  )
}
