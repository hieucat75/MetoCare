'use client'

import * as React from 'react'
import { FileText, Download, Clock, AlertCircle } from 'lucide-react'
import { useAuth } from '@/lib/auth/context'
import { NeuCard, NeuButton } from '@/components/patient/neu'

// ── Page ──────────────────────────────────────────────────────────────────────

export default function ReportPage() {
  const { user } = useAuth()
  const patientId = user?.patient_profile_id

  const [downloading, setDownloading] = React.useState(false)
  const [downloadError, setDownloadError] = React.useState<string | null>(null)
  const [downloadSuccess, setDownloadSuccess] = React.useState(false)

  async function handleDownloadPdf() {
    if (!patientId) return
    setDownloading(true)
    setDownloadError(null)
    setDownloadSuccess(false)

    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? ''
      const token = localStorage.getItem('access_token') ?? ''

      const response = await fetch(`${apiUrl}/api/v1/patients/${patientId}/summary.pdf`, {
        headers: { Authorization: `Bearer ${token}` },
      })

      if (!response.ok) {
        const text = await response.text().catch(() => '')
        throw new Error(text || `Lỗi ${response.status}: Không tải được báo cáo`)
      }

      const blob = await response.blob()
      const objectUrl = URL.createObjectURL(blob)

      const link = document.createElement('a')
      link.href = objectUrl
      link.download = `metocare-bao-cao-suc-khoe.pdf`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      URL.revokeObjectURL(objectUrl)

      setDownloadSuccess(true)
      setTimeout(() => setDownloadSuccess(false), 4000)
    } catch (err) {
      setDownloadError(
        err instanceof Error ? err.message : 'Không thể tải báo cáo. Vui lòng thử lại.'
      )
    } finally {
      setDownloading(false)
    }
  }

  if (!patientId) {
    return (
      <div className="p-4 max-w-md mx-auto mt-10">
        <NeuCard>
          <p className="text-[15px] text-neu-muted text-center">
            Không tìm thấy hồ sơ bệnh nhân. Vui lòng liên hệ hỗ trợ.
          </p>
        </NeuCard>
      </div>
    )
  }

  return (
    <div className="p-4 max-w-md mx-auto pb-28 space-y-5">
      {/* Header */}
      <header>
        <h1 className="text-[22px] font-extrabold tracking-[-0.02em] text-neu-text">
          Báo cáo sức khoẻ
        </h1>
        <p className="mt-1 text-[14px] text-neu-muted">
          Tải báo cáo tóm tắt sức khoẻ của bạn ở định dạng PDF
        </p>
      </header>

      {/* Success banner */}
      {downloadSuccess && (
        <div className="rounded-[14px] bg-[rgba(227,245,236,0.95)] border border-[rgba(15,156,110,0.25)] px-4 py-3 flex items-center gap-3">
          <FileText className="size-5 text-neu-green shrink-0" aria-hidden="true" />
          <p className="text-[14px] font-semibold text-[#0F9C6E]">
            Báo cáo đã được tải xuống thành công!
          </p>
        </div>
      )}

      {/* Main download card */}
      <NeuCard size="lg">
        <div className="flex flex-col items-center text-center gap-5 py-4">
          {/* Report icon */}
          <div
            className="size-20 rounded-[22px] flex items-center justify-center bg-gradient-to-br from-[rgba(15,156,110,0.15)] to-[rgba(15,156,110,0.05)]"
            style={{
              boxShadow:
                'inset 3px 3px 8px rgba(15,156,110,0.1), inset -2px -2px 5px rgba(255,255,255,0.95)',
            }}
          >
            <FileText className="size-9 text-neu-green" aria-hidden="true" />
          </div>

          <div className="space-y-1.5">
            <h2 className="text-[18px] font-bold text-neu-text">Báo cáo tóm tắt sức khoẻ</h2>
            <p className="text-[13.5px] text-neu-muted max-w-[28ch] mx-auto leading-relaxed">
              Bao gồm chỉ số sức khoẻ, kết quả xét nghiệm và lịch sử thuốc của bạn.
            </p>
          </div>

          {/* Error */}
          {downloadError && (
            <div className="w-full rounded-[12px] bg-[rgba(251,231,229,0.93)] border border-[rgba(217,45,32,0.2)] px-4 py-3 flex items-start gap-2.5 text-left">
              <AlertCircle className="size-4 text-[#D92D20] shrink-0 mt-0.5" aria-hidden="true" />
              <p className="text-[13px] text-[#D92D20]">{downloadError}</p>
            </div>
          )}

          <NeuButton
            className="!px-8 !w-auto flex items-center gap-2"
            onClick={handleDownloadPdf}
            disabled={downloading}
          >
            <Download className="size-4" aria-hidden="true" />
            {downloading ? 'Đang tải xuống...' : 'Tải xuống PDF'}
          </NeuButton>
        </div>
      </NeuCard>

      {/* Report history — coming soon */}
      <NeuCard className="!p-0">
        <div className="px-5 pt-4 pb-1">
          <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-neu-muted">
            Lịch sử báo cáo
          </p>
        </div>
        <div className="px-5 pb-5">
          <div className="flex items-center gap-3 py-4">
            <div className="shrink-0 size-10 rounded-[12px] bg-[rgba(16,48,44,0.05)] flex items-center justify-center">
              <Clock className="size-5 text-neu-muted" aria-hidden="true" />
            </div>
            <div>
              <p className="text-[14px] font-semibold text-neu-text">Sắp ra mắt</p>
              <p className="text-[13px] text-neu-muted">
                Lịch sử các báo cáo đã tải sẽ xuất hiện ở đây.
              </p>
            </div>
          </div>
        </div>
      </NeuCard>
    </div>
  )
}
