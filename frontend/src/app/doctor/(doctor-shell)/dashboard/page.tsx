import type { Metadata } from 'next'

export const metadata: Metadata = { title: 'Tổng quan — MetoCare Bác sĩ' }

export default function DoctorDashboardPage() {
  return (
    <div className="p-6">
      <div className="h-8 w-48 bg-secondary-100 rounded-md animate-pulse mb-2" />
      <div className="h-4 w-72 bg-secondary-100 rounded animate-pulse mb-8" />
      <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="h-32 bg-secondary-100 rounded-xl animate-pulse" />
        ))}
      </div>
    </div>
  )
}
