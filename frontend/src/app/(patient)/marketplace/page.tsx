'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import { ArrowLeft, Search, Star, Stethoscope, Building2 } from 'lucide-react'
import { NeuCard } from '@/components/patient/neu'
import { PatientErrorState, PatientSkeleton, PatientEmptyState } from '@/components/patient/states'
import { formatVnd } from '@/components/marketplace'
import { browseDoctors, type DoctorCardOut } from '@/lib/api/marketplace'

// ── Filter option constants ───────────────────────────────────────────────────

const METHOD_OPTIONS = [
  { key: '', label: 'Tất cả' },
  { key: 'CHAT', label: 'Nhắn tin' },
  { key: 'VIDEO', label: 'Video' },
  { key: 'IN_PERSON', label: 'Trực tiếp' },
] as const

const PRICE_OPTIONS = [
  { key: 'all', label: 'Mọi mức giá', min: undefined, max: undefined },
  { key: 'lt300', label: 'Dưới 300k', min: undefined, max: 300_000 },
  { key: '300-600', label: '300k–600k', min: 300_000, max: 600_000 },
  { key: 'gt600', label: 'Trên 600k', min: 600_000, max: undefined },
] as const

type PriceKey = (typeof PRICE_OPTIONS)[number]['key']

// ── Page ──────────────────────────────────────────────────────────────────────

export default function MarketplacePage() {
  const router = useRouter()

  const [name, setName] = React.useState('')
  const [specialty, setSpecialty] = React.useState('')
  const [method, setMethod] = React.useState<string>('')
  const [priceKey, setPriceKey] = React.useState<PriceKey>('all')

  const [doctors, setDoctors] = React.useState<DoctorCardOut[]>([])
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)

  const load = React.useCallback(() => {
    setLoading(true)
    setError(null)
    const price = PRICE_OPTIONS.find((p) => p.key === priceKey)
    browseDoctors({
      name: name.trim() || undefined,
      specialty: specialty.trim() || undefined,
      method: method || undefined,
      min_price: price?.min,
      max_price: price?.max,
    })
      .then((items) => setDoctors(items))
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [name, specialty, method, priceKey])

  // Re-fetch on filter change, debounced for the free-text inputs.
  React.useEffect(() => {
    const id = setTimeout(load, 300)
    return () => clearTimeout(id)
  }, [load])

  return (
    <div className="p-4 max-w-md mx-auto pb-28 space-y-4">
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
        <div className="min-w-0">
          <h1 className="text-[24px] font-extrabold tracking-[-0.02em] text-neu-text">
            Tư vấn bác sĩ
          </h1>
          <p className="text-[14px] text-neu-muted">Chọn bác sĩ phù hợp để đặt tư vấn</p>
        </div>
      </header>

      {/* ── Search + filters ── */}
      <div className="space-y-3">
        <label className="flex items-center gap-2.5 rounded-[16px] bg-white px-4 py-3 neu-card !shadow-none border border-[rgba(16,48,44,0.08)]">
          <Search className="size-5 shrink-0 text-neu-muted" aria-hidden="true" />
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Tìm theo tên bác sĩ"
            className="min-w-0 flex-1 bg-transparent text-[16px] text-neu-text outline-none placeholder:text-neu-muted"
            aria-label="Tìm theo tên bác sĩ"
          />
        </label>

        <input
          value={specialty}
          onChange={(e) => setSpecialty(e.target.value)}
          placeholder="Chuyên khoa (vd: Nội tiết, Tim mạch)"
          className="w-full rounded-[16px] bg-white px-4 py-3 text-[16px] text-neu-text outline-none neu-card !shadow-none border border-[rgba(16,48,44,0.08)] placeholder:text-neu-muted"
          aria-label="Lọc theo chuyên khoa"
        />

        {/* Method chips */}
        <div className="flex flex-wrap gap-2">
          {METHOD_OPTIONS.map((m) => {
            const active = method === m.key
            return (
              <button
                key={m.key || 'all'}
                type="button"
                onClick={() => setMethod(m.key)}
                className={
                  active
                    ? 'rounded-full bg-neu-green px-3.5 py-1.5 text-[14px] font-semibold text-white'
                    : 'rounded-full bg-white px-3.5 py-1.5 text-[14px] font-semibold text-neu-muted border border-[rgba(16,48,44,0.1)]'
                }
              >
                {m.label}
              </button>
            )
          })}
        </div>

        {/* Price chips */}
        <div className="flex flex-wrap gap-2">
          {PRICE_OPTIONS.map((p) => {
            const active = priceKey === p.key
            return (
              <button
                key={p.key}
                type="button"
                onClick={() => setPriceKey(p.key)}
                className={
                  active
                    ? 'rounded-full bg-neu-green px-3.5 py-1.5 text-[14px] font-semibold text-white'
                    : 'rounded-full bg-white px-3.5 py-1.5 text-[14px] font-semibold text-neu-muted border border-[rgba(16,48,44,0.1)]'
                }
              >
                {p.label}
              </button>
            )
          })}
        </div>
      </div>

      {/* ── Results ── */}
      {loading ? (
        <div className="space-y-3">
          <PatientSkeleton />
          <PatientSkeleton />
        </div>
      ) : error ? (
        <PatientErrorState title="Không thể tải danh sách bác sĩ" message={error} onRetry={load} />
      ) : doctors.length === 0 ? (
        <PatientEmptyState
          icon={Stethoscope}
          title="Chưa tìm thấy bác sĩ"
          description="Thử điều chỉnh bộ lọc hoặc xoá từ khoá tìm kiếm để xem thêm bác sĩ."
        />
      ) : (
        <div className="space-y-3">
          {doctors.map((doc) => (
            <DoctorCard
              key={doc.id}
              doctor={doc}
              onClick={() => router.push(`/marketplace/${doc.id}`)}
            />
          ))}
        </div>
      )}
    </div>
  )
}

// ── Doctor card ───────────────────────────────────────────────────────────────

function DoctorCard({ doctor, onClick }: { doctor: DoctorCardOut; onClick: () => void }) {
  const experience =
    doctor.years_experience != null ? `${doctor.years_experience} năm kinh nghiệm` : null

  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full text-left transition-transform active:scale-[0.99]"
    >
      <NeuCard className="!p-4">
        <div className="flex items-start gap-3.5">
          <DoctorAvatar name={doctor.full_name} avatarUrl={doctor.avatar_url} />
          <div className="min-w-0 flex-1">
            <p className="text-[17px] font-bold text-neu-text truncate">{doctor.full_name}</p>
            {doctor.specialty && (
              <p className="text-[14px] text-neu-green font-semibold">{doctor.specialty}</p>
            )}
            {doctor.hospital_name && (
              <p className="mt-0.5 flex items-center gap-1 text-[13px] text-neu-muted truncate">
                <Building2 className="size-3.5 shrink-0" aria-hidden="true" />
                <span className="truncate">{doctor.hospital_name}</span>
              </p>
            )}
            {experience && <p className="text-[13px] text-neu-muted">{experience}</p>}

            <div className="mt-2 flex items-center gap-3">
              <RatingPill avg={doctor.rating_avg} count={doctor.rating_count} />
              <span className="text-[16px] font-extrabold text-neu-text">
                {formatVnd(doctor.consultation_fee)}
              </span>
            </div>
          </div>
        </div>
      </NeuCard>
    </button>
  )
}

function DoctorAvatar({ name, avatarUrl }: { name: string; avatarUrl?: string | null }) {
  if (avatarUrl) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={avatarUrl}
        alt=""
        className="size-14 shrink-0 rounded-[16px] object-cover"
      />
    )
  }
  return (
    <span
      className="grid size-14 shrink-0 place-items-center rounded-[16px] text-[16px] font-extrabold text-neu-green neu-icon-btn"
      aria-hidden="true"
    >
      {initials(name)}
    </span>
  )
}

function RatingPill({ avg, count }: { avg: number; count: number }) {
  if (!count) {
    return <span className="text-[13px] text-neu-muted">Chưa có đánh giá</span>
  }
  return (
    <span className="inline-flex items-center gap-1 text-[14px] font-semibold text-neu-text">
      <Star className="size-4 fill-[#F5B547] text-[#F5B547]" aria-hidden="true" />
      {avg.toFixed(1)}
      <span className="font-normal text-neu-muted">({count})</span>
    </span>
  )
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return '?'
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}
