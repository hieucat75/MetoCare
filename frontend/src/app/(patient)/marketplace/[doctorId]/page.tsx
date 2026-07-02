'use client'

import * as React from 'react'
import { useParams, useRouter } from 'next/navigation'
import { ArrowLeft, Star, Building2, Clock, Languages, MessageSquare } from 'lucide-react'
import { NeuCard } from '@/components/patient/neu'
import { PatientErrorState, PatientSkeleton } from '@/components/patient/states'
import { formatVnd, formatDateTime, MarketplaceDisclaimer } from '@/components/marketplace'
import { getDoctorDetail, type DoctorDetailOut } from '@/lib/api/marketplace'

// Map raw consultation-method tokens → VN labels for display.
const METHOD_LABELS: Record<string, string> = {
  CHAT: 'Nhắn tin',
  VIDEO: 'Gọi video',
  IN_PERSON: 'Khám trực tiếp',
}

function parseMethods(raw?: string | null): string[] {
  if (!raw) return []
  return raw
    .split(/[,;]/)
    .map((s) => s.trim())
    .filter(Boolean)
}

export default function DoctorDetailPage() {
  const router = useRouter()
  const params = useParams<{ doctorId: string }>()
  const doctorId = params.doctorId

  const [doctor, setDoctor] = React.useState<DoctorDetailOut | null>(null)
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)

  const load = React.useCallback(() => {
    setLoading(true)
    setError(null)
    getDoctorDetail(doctorId)
      .then((d) => setDoctor(d))
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [doctorId])

  React.useEffect(() => {
    load()
  }, [load])

  const nextAvailable = doctor ? formatDateTime(doctor.next_available) : null
  const methods = doctor ? parseMethods(doctor.consultation_methods) : []
  const languages = doctor ? parseMethods(doctor.languages) : []

  return (
    <div className="p-4 max-w-md mx-auto pb-32 space-y-4">
      {/* ── Header ── */}
      <header className="flex items-center gap-3">
        <button
          type="button"
          aria-label="Quay lại"
          onClick={() => router.back()}
          className="neu-icon-btn !w-11 !h-11 !rounded-full text-neu-text"
        >
          <ArrowLeft className="size-5" />
        </button>
        <h1 className="text-[20px] font-extrabold tracking-[-0.02em] text-neu-text">Hồ sơ bác sĩ</h1>
      </header>

      {loading ? (
        <div className="space-y-3">
          <PatientSkeleton />
          <PatientSkeleton />
        </div>
      ) : error ? (
        <PatientErrorState
          title="Không thể tải hồ sơ bác sĩ"
          message={error}
          onRetry={load}
        />
      ) : doctor ? (
        <>
          {/* ── Identity ── */}
          <NeuCard className="!p-5">
            <div className="flex items-start gap-4">
              <DoctorAvatar name={doctor.full_name} avatarUrl={doctor.avatar_url} />
              <div className="min-w-0 flex-1">
                <h2 className="text-[20px] font-extrabold text-neu-text">{doctor.full_name}</h2>
                {doctor.specialty && (
                  <p className="text-[15px] font-semibold text-neu-green">{doctor.specialty}</p>
                )}
                {doctor.hospital_name && (
                  <p className="mt-1 flex items-center gap-1.5 text-[14px] text-neu-muted">
                    <Building2 className="size-4 shrink-0" aria-hidden="true" />
                    {doctor.hospital_name}
                  </p>
                )}
              </div>
            </div>

            {/* Rating + experience row */}
            <div className="mt-4 flex items-center gap-4">
              {doctor.rating_count > 0 ? (
                <span className="inline-flex items-center gap-1 text-[15px] font-semibold text-neu-text">
                  <Star className="size-4 fill-[#F5B547] text-[#F5B547]" aria-hidden="true" />
                  {doctor.rating_avg.toFixed(1)}
                  <span className="font-normal text-neu-muted">
                    ({doctor.rating_count} đánh giá)
                  </span>
                </span>
              ) : (
                <span className="text-[14px] text-neu-muted">Chưa có đánh giá</span>
              )}
              {doctor.years_experience != null && (
                <span className="text-[14px] text-neu-muted">
                  {doctor.years_experience} năm kinh nghiệm
                </span>
              )}
            </div>
          </NeuCard>

          {/* ── Bio ── */}
          {doctor.bio && (
            <NeuCard className="!p-5">
              <h3 className="text-[16px] font-bold text-neu-text">Giới thiệu</h3>
              <p className="mt-2 text-[15px] leading-relaxed text-neu-muted whitespace-pre-line">
                {doctor.bio}
              </p>
            </NeuCard>
          )}

          {/* ── Methods & languages ── */}
          {(methods.length > 0 || languages.length > 0) && (
            <NeuCard className="!p-5 space-y-4">
              {methods.length > 0 && (
                <div>
                  <p className="flex items-center gap-1.5 text-[14px] font-bold text-neu-text">
                    <MessageSquare className="size-4" aria-hidden="true" />
                    Hình thức tư vấn
                  </p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {methods.map((m) => (
                      <span
                        key={m}
                        className="rounded-full bg-[rgba(13,155,110,0.1)] px-3 py-1 text-[14px] font-semibold text-neu-green"
                      >
                        {METHOD_LABELS[m] ?? m}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {languages.length > 0 && (
                <div>
                  <p className="flex items-center gap-1.5 text-[14px] font-bold text-neu-text">
                    <Languages className="size-4" aria-hidden="true" />
                    Ngôn ngữ
                  </p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {languages.map((l) => (
                      <span
                        key={l}
                        className="rounded-full bg-[rgba(16,48,44,0.06)] px-3 py-1 text-[14px] font-semibold text-neu-muted"
                      >
                        {l}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </NeuCard>
          )}

          {/* ── Price + availability ── */}
          <NeuCard className="!p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-[13px] text-neu-muted">Phí tư vấn</p>
                <p className="text-[24px] font-extrabold text-neu-text">
                  {formatVnd(doctor.consultation_fee)}
                </p>
              </div>
              {nextAvailable && (
                <div className="text-right">
                  <p className="flex items-center justify-end gap-1 text-[13px] text-neu-muted">
                    <Clock className="size-3.5" aria-hidden="true" />
                    Lịch trống gần nhất
                  </p>
                  <p className="text-[15px] font-bold text-neu-green">{nextAvailable}</p>
                </div>
              )}
            </div>
          </NeuCard>

          <MarketplaceDisclaimer />
        </>
      ) : null}

      {/* ── Sticky CTA ── */}
      {doctor && (
        <div className="fixed inset-x-0 bottom-20 z-20 px-4">
          <div className="mx-auto max-w-md">
            <button
              type="button"
              onClick={() => router.push(`/marketplace/${doctorId}/book`)}
              className="neu-btn-primary w-full"
            >
              Đặt tư vấn
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function DoctorAvatar({ name, avatarUrl }: { name: string; avatarUrl?: string | null }) {
  if (avatarUrl) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img src={avatarUrl} alt="" className="size-16 shrink-0 rounded-[18px] object-cover" />
    )
  }
  return (
    <span
      className="grid size-16 shrink-0 place-items-center rounded-[18px] text-[18px] font-extrabold text-neu-green neu-icon-btn"
      aria-hidden="true"
    >
      {initials(name)}
    </span>
  )
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return '?'
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}
