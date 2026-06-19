import Link from 'next/link'

export default function NotFound() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-4">
      <div className="text-center max-w-sm">
        <div className="w-16 h-16 rounded-2xl bg-primary-50 flex items-center justify-center mx-auto mb-6">
          <span className="text-3xl font-bold text-primary">M</span>
        </div>
        <h1 className="text-display-xs font-bold text-text mb-2">404</h1>
        <p className="text-body-md text-text-muted mb-6">Trang bạn tìm không tồn tại.</p>
        <Link
          href="/dashboard"
          className="inline-flex items-center justify-center h-10 px-6 rounded-md bg-primary text-white text-body-sm font-medium hover:bg-primary-hover transition-colors"
        >
          Về trang chủ
        </Link>
      </div>
    </div>
  )
}
