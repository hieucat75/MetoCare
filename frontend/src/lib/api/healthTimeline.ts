import { api } from './client'

export interface TimelineEvent {
  event_id: string
  event_type: string
  date: string        // YYYY-MM-DD
  title_vi: string
  summary_vi: string
  source: string
  importance: 'info' | 'watch' | 'warning' | 'urgent'
  related_markers: string[]
  metadata: Record<string, unknown>
  evidence_level: string
}

export interface TimelineSummary {
  improved_areas: string[]
  worsened_areas: string[]
  stable_areas: string[]
  biggest_change_vi: string
  missing_longitudinal_vi: string[]
  data_span_days: number
  total_events: number
}

export interface HealthTimelineResponse {
  timeline_events: TimelineEvent[]
  timeline_summary: TimelineSummary
  missing_sources: string[]
  generated_at: string
}

export async function fetchHealthTimeline(
  patientId: string,
  params?: {
    from_date?: string
    to_date?: string
    event_type?: string
    limit?: number
  }
): Promise<HealthTimelineResponse> {
  const query = new URLSearchParams()
  if (params?.from_date) query.set('from_date', params.from_date)
  if (params?.to_date) query.set('to_date', params.to_date)
  if (params?.event_type) query.set('event_type', params.event_type)
  if (params?.limit) query.set('limit', String(params.limit))
  const qs = query.toString() ? `?${query.toString()}` : ''
  return api.get<HealthTimelineResponse>(`/patients/${patientId}/health-timeline${qs}`)
}
