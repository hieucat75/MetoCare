'use client'

import * as React from 'react'
import { FileText } from 'lucide-react'
import { PageHeader, Card, EmptyState, Alert } from '@/design-system'

export default function ClinicalNotesPage() {
  return (
    <div className="p-6 space-y-6">
      <PageHeader
        title="Ghi chú lâm sàng"
        subtitle="Ghi lại quan sát và quyết định điều trị cho bệnh nhân"
      />

      <Alert variant="info">
        Tính năng này sẽ có trong phiên bản tiếp theo.
      </Alert>

      <Card>
        <EmptyState
          icon={<FileText />}
          title="Chức năng ghi chú lâm sàng đang được phát triển"
          description="Ghi chú lâm sàng cho phép bác sĩ ghi lại quan sát và quyết định điều trị cho từng bệnh nhân."
          size="lg"
        />
      </Card>
    </div>
  )
}
