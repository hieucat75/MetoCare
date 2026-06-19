import type { Metadata } from 'next'

export const metadata: Metadata = { title: 'Tổng quan — MetoCare Admin' }

export default function AdminDashboardPage() {
  return (
    <div className="p-6">
      <div className="h-8 w-48 bg-secondary-100 rounded-md animate-pulse mb-2" />
      <div className="h-4 w-72 bg-secondary-100 rounded animate-pulse mb-8" />
      <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="h-28 bg-secondary-100 rounded-xl animate-pulse" />
        ))}
      </div>
    </div>
  )
}
