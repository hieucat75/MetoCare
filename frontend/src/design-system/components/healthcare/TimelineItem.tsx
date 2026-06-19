import * as React from 'react'
import {
  Microscope,
  Bot,
  Stethoscope,
  ClipboardList,
  Pill,
  Shield,
  Settings,
} from 'lucide-react'
import { cn } from '@/lib/utils'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type TimelineEventType =
  | 'lab_result'
  | 'ai_session'
  | 'doctor_visit'
  | 'care_plan'
  | 'medication'
  | 'consent'
  | 'system'

export interface TimelineEvent {
  id: string
  date: string
  type: TimelineEventType
  title: string
  description: string
  actor?: string
  actorRole?: string
  status?: string
  metadata?: Record<string, string>
}

export interface TimelineItemProps {
  event: TimelineEvent
  isLast?: boolean
  onClick?: () => void
}

// ---------------------------------------------------------------------------
// Config per event type
// ---------------------------------------------------------------------------

interface TypeConfig {
  icon: React.ReactNode
  /** Tailwind classes for the icon container circle */
  iconWrapperClass: string
  /** Tailwind classes for the icon itself */
  iconClass: string
}

const TYPE_CONFIG: Record<TimelineEventType, TypeConfig> = {
  lab_result: {
    icon: <Microscope className="h-3.5 w-3.5" aria-hidden="true" />,
    iconWrapperClass: 'bg-info-light border-info-border',
    iconClass: 'text-info',
  },
  ai_session: {
    icon: <Bot className="h-3.5 w-3.5" aria-hidden="true" />,
    iconWrapperClass: 'bg-purple-50 border-purple-200',
    iconClass: 'text-purple-600',
  },
  doctor_visit: {
    icon: <Stethoscope className="h-3.5 w-3.5" aria-hidden="true" />,
    iconWrapperClass: 'bg-primary-light border-primary-200',
    iconClass: 'text-primary',
  },
  care_plan: {
    icon: <ClipboardList className="h-3.5 w-3.5" aria-hidden="true" />,
    iconWrapperClass: 'bg-success-light border-success-border',
    iconClass: 'text-success',
  },
  medication: {
    icon: <Pill className="h-3.5 w-3.5" aria-hidden="true" />,
    iconWrapperClass: 'bg-warning-light border-warning-border',
    iconClass: 'text-warning',
  },
  consent: {
    icon: <Shield className="h-3.5 w-3.5" aria-hidden="true" />,
    iconWrapperClass: 'bg-secondary-100 border-secondary-300',
    iconClass: 'text-secondary-600',
  },
  system: {
    icon: <Settings className="h-3.5 w-3.5" aria-hidden="true" />,
    iconWrapperClass: 'bg-secondary-50 border-secondary-200',
    iconClass: 'text-text-muted',
  },
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatEventDate(dateStr: string): { date: string; time: string } {
  const d = new Date(dateStr)
  const date = new Intl.DateTimeFormat('vi-VN', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  }).format(d)
  const time = new Intl.DateTimeFormat('vi-VN', {
    hour: '2-digit',
    minute: '2-digit',
  }).format(d)
  return { date, time }
}

// ---------------------------------------------------------------------------
// TimelineItem
// ---------------------------------------------------------------------------

export function TimelineItem({ event, isLast = false, onClick }: TimelineItemProps) {
  const config = TYPE_CONFIG[event.type]
  const { date, time } = formatEventDate(event.date)
  const hasMetadata = event.metadata && Object.keys(event.metadata).length > 0
  const isClickable = typeof onClick === 'function'

  return (
    <div
      className={cn(
        'relative flex gap-4',
        // Extra bottom padding to give room for the connector line between items
        !isLast && 'pb-6',
      )}
    >
      {/* Left column: connector line + icon circle */}
      <div className="relative flex flex-col items-center">
        {/* Icon circle */}
        <span
          className={cn(
            'relative z-10 inline-flex shrink-0 items-center justify-center',
            'h-7 w-7 rounded-full border',
            config.iconWrapperClass,
            config.iconClass,
          )}
          aria-hidden="true"
        >
          {config.icon}
        </span>

        {/* Vertical connector line below the circle, hidden for last item */}
        {!isLast && (
          <span
            className="mt-1 flex-1 w-px bg-border"
            aria-hidden="true"
          />
        )}
      </div>

      {/* Right column: content */}
      <div
        className={cn(
          'flex-1 min-w-0 pt-0.5',
          isClickable && [
            'cursor-pointer rounded-md -mx-2 px-2 py-1',
            'hover:bg-secondary-50 transition-colors',
          ],
        )}
        role={isClickable ? 'button' : undefined}
        tabIndex={isClickable ? 0 : undefined}
        onClick={isClickable ? onClick : undefined}
        onKeyDown={
          isClickable
            ? (e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  onClick()
                }
              }
            : undefined
        }
      >
        {/* Date + time */}
        <p className="text-body-xs text-text-muted mb-0.5">
          {date}
          <span className="mx-1 text-text-subtle" aria-hidden="true">&middot;</span>
          {time}
        </p>

        {/* Title */}
        <p className="text-body-sm font-medium text-text leading-snug">
          {event.title}
        </p>

        {/* Description */}
        <p className="mt-0.5 text-body-xs text-text-muted leading-relaxed">
          {event.description}
        </p>

        {/* Actor + role */}
        {event.actor && (
          <p className="mt-1 text-body-xs text-text-muted">
            <span className="font-medium text-text">{event.actor}</span>
            {event.actorRole && (
              <span className="ml-1 text-text-subtle">({event.actorRole})</span>
            )}
          </p>
        )}

        {/* Status chip */}
        {event.status && (
          <span
            className={cn(
              'mt-1.5 inline-flex items-center',
              'text-body-xs font-medium px-2 py-0.5 rounded-full',
              'bg-secondary-100 text-secondary-700',
            )}
          >
            {event.status}
          </span>
        )}

        {/* Metadata chips */}
        {hasMetadata && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {Object.entries(event.metadata!).map(([key, value]) => (
              <span
                key={key}
                className={cn(
                  'inline-flex items-center gap-1 text-body-xs',
                  'px-2 py-0.5 rounded-full',
                  'bg-secondary-50 border border-border text-text-muted',
                )}
              >
                <span className="font-medium text-text-subtle">{key}:</span>
                {value}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

TimelineItem.displayName = 'TimelineItem'

export default TimelineItem
