import type { SourceRef } from '@/lib/api/clinicalCopilot'

const NO_DATE_LABEL = 'không rõ thời điểm'

/**
 * `date: null` is a real, meaningful state (the underlying record genuinely
 * has no date) — it must never read as if the data is current/fresh, so it
 * gets a distinct fallback rather than being blank or omitted.
 */
export function formatSourceDate(date?: string | null): string {
  return date ? date : NO_DATE_LABEL
}

/** Shared render of a `SourceRef[]` list — used everywhere sources are shown. */
export function SourceList({ sources }: { sources: SourceRef[] }) {
  return (
    <ul className="space-y-0.5">
      {sources.map((s) => (
        <li key={s.id} className="text-body-xs text-text-subtle">
          {s.label} · {formatSourceDate(s.date)}
        </li>
      ))}
    </ul>
  )
}
