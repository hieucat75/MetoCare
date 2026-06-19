import type { Metadata } from 'next'

export const metadata: Metadata = { title: 'Tổng quan — MetoCare' }

export default function PatientDashboardPage() {
  return (
    <div className="p-4 lg:p-6">
      <div className="max-w-2xl">
        <div className="h-8 w-48 bg-secondary-100 rounded-md animate-pulse mb-2" />
        <div className="h-4 w-72 bg-secondary-100 rounded animate-pulse mb-8" />
        <div className="grid gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-24 bg-secondary-100 rounded-xl animate-pulse" />
          ))}
        </div>
      </div>
    </div>
  )
}
