import * as React from 'react'
import {
  ArrowLeft,
  User,
  Phone,
  MapPin,
  Stethoscope,
  Clock,
  ClipboardList,
  AlertCircle,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import Badge from '@/design-system/components/core/Badge'
import { RiskLevelBadge } from '@/design-system/components/healthcare/RiskLevelBadge'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface PatientProfile {
  id: string
  fullName: string
  /** Null when the patient has not recorded a date of birth. */
  dateOfBirth: string | null
  /** Null when the patient has not recorded a gender. */
  gender: 'male' | 'female' | 'other' | null
  phone?: string
  address?: string
  avatarUrl?: string
  riskLevel: 'high' | 'medium' | 'low' | 'unknown'
  riskScore?: number
  primaryDiagnosis?: string
  primaryDoctor?: string
  lastVisit?: string
  activePlanCount: number
  pendingReviewCount: number
}

export interface PatientSummaryHeaderProps {
  patient: PatientProfile
  onBack: () => void
  showBackButton?: boolean
  actions?: React.ReactNode
  compact?: boolean
  className?: string
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function calculateAge(dateOfBirth: string | null): number | null {
  if (!dateOfBirth) return null
  const dob = new Date(dateOfBirth)
  if (Number.isNaN(dob.getTime())) return null
  const today = new Date()
  let age = today.getFullYear() - dob.getFullYear()
  const monthDiff = today.getMonth() - dob.getMonth()
  if (monthDiff < 0 || (monthDiff === 0 && today.getDate() < dob.getDate())) {
    age -= 1
  }
  return age
}

const GENDER_LABEL: Record<'male' | 'female' | 'other', string> = {
  male: 'Nam',
  female: 'Nu',
  other: 'Khac',
}

/** Build the "gender · age" meta label, degrading to "Không rõ" when absent. */
function buildDemographics(gender: PatientProfile['gender'], age: number | null): string {
  const parts: string[] = []
  if (gender) parts.push(GENDER_LABEL[gender])
  if (age !== null) parts.push(`${age} tuoi`)
  return parts.length > 0 ? parts.join(' · ') : 'Khong ro'
}

function formatLastVisit(dateStr: string): string {
  return new Intl.DateTimeFormat('vi-VN', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  }).format(new Date(dateStr))
}

function getInitials(name: string): string {
  return name
    .split(' ')
    .filter(Boolean)
    .slice(-2)
    .map((w) => w[0].toUpperCase())
    .join('')
}

// ---------------------------------------------------------------------------
// PatientSummaryHeader
// ---------------------------------------------------------------------------

export function PatientSummaryHeader({
  patient,
  onBack,
  showBackButton = true,
  actions,
  compact = false,
  className,
}: PatientSummaryHeaderProps) {
  const age = calculateAge(patient.dateOfBirth)
  const demographics = buildDemographics(patient.gender, age)

  return (
    <div className={cn('bg-surface border-b border-border px-6 py-4', className)}>
      {/* Row 1: back button, name, gender+age badge, risk badge, actions */}
      <div className="flex items-start justify-between gap-4">
        {/* Left side */}
        <div className="flex items-start gap-3 min-w-0">
          {/* Back button */}
          {showBackButton && (
            <button
              type="button"
              onClick={onBack}
              aria-label="Quay lai"
              className={cn(
                'shrink-0 inline-flex items-center justify-center',
                'h-8 w-8 rounded-md text-text-muted',
                'hover:bg-secondary-100 hover:text-text transition-colors',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30',
                'mt-0.5'
              )}
            >
              <ArrowLeft className="h-4 w-4" aria-hidden="true" />
            </button>
          )}

          {/* Avatar + name block */}
          <div className="flex items-start gap-3 min-w-0">
            {/* Avatar */}
            {patient.avatarUrl ? (
              <img
                src={patient.avatarUrl}
                alt={patient.fullName}
                className="shrink-0 h-10 w-10 rounded-full object-cover border border-border"
              />
            ) : (
              <span
                className={cn(
                  'shrink-0 inline-flex items-center justify-center',
                  'h-10 w-10 rounded-full bg-primary-light text-primary-700',
                  'text-label-md font-semibold border border-primary-200'
                )}
                aria-hidden="true"
              >
                {getInitials(patient.fullName)}
              </span>
            )}

            {/* Name + badges */}
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-display-xs font-bold text-text leading-tight">
                  {patient.fullName}
                </h2>
                {/* Gender + age badge */}
                <Badge variant="default" size="sm">
                  <User className="h-3 w-3" aria-hidden="true" />
                  {demographics}
                </Badge>
                {/* Risk level badge */}
                <RiskLevelBadge
                  level={patient.riskLevel}
                  score={patient.riskScore}
                  showScore={patient.riskScore !== undefined}
                  size="sm"
                />
              </div>

              {/* Primary diagnosis — shown in both compact and full */}
              {patient.primaryDiagnosis && (
                <p className="mt-0.5 text-body-sm text-text-muted truncate">
                  {patient.primaryDiagnosis}
                </p>
              )}
            </div>
          </div>
        </div>

        {/* Right side: actions */}
        {actions && <div className="shrink-0 flex items-center gap-2 pt-0.5">{actions}</div>}
      </div>

      {/* Row 2 (not compact): meta info — phone, address, doctor, last visit */}
      {!compact && (
        <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-1.5 pl-[3.25rem]">
          {patient.phone && (
            <span className="inline-flex items-center gap-1.5 text-body-xs text-text-muted">
              <Phone className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              {patient.phone}
            </span>
          )}
          {patient.address && (
            <span className="inline-flex items-center gap-1.5 text-body-xs text-text-muted">
              <MapPin className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              <span className="max-w-[20ch] truncate">{patient.address}</span>
            </span>
          )}
          {patient.primaryDoctor && (
            <span className="inline-flex items-center gap-1.5 text-body-xs text-text-muted">
              <Stethoscope className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              {patient.primaryDoctor}
            </span>
          )}
          {patient.lastVisit && (
            <span className="inline-flex items-center gap-1.5 text-body-xs text-text-muted">
              <Clock className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              Kham lan cuoi: {formatLastVisit(patient.lastVisit)}
            </span>
          )}
        </div>
      )}

      {/* Row 3 (not compact): stat chips */}
      {!compact && (
        <div className="mt-3 flex flex-wrap items-center gap-2 pl-[3.25rem]">
          {/* Active plans count */}
          <span
            className={cn(
              'inline-flex items-center gap-1.5 text-body-xs font-medium',
              'px-2.5 py-1 rounded-full',
              'bg-clinical-active-light text-green-800 border border-clinical-active-border'
            )}
          >
            <ClipboardList className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            {patient.activePlanCount} ke hoach dang hoat dong
          </span>

          {/* Pending reviews count */}
          {patient.pendingReviewCount > 0 && (
            <span
              className={cn(
                'inline-flex items-center gap-1.5 text-body-xs font-medium',
                'px-2.5 py-1 rounded-full',
                'bg-clinical-pending-review-light text-amber-800 border border-clinical-pending-review-border'
              )}
            >
              <AlertCircle className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              {patient.pendingReviewCount} cho xet duyet
            </span>
          )}
        </div>
      )}
    </div>
  )
}

PatientSummaryHeader.displayName = 'PatientSummaryHeader'

export default PatientSummaryHeader
