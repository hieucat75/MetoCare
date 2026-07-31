/**
 * expo-router can hand back a route param as `string | string[]` (repeated query
 * keys). Screens that feed a param straight into an API call — especially the
 * payment-adjacent booking flow — must narrow it to a single value first, so a
 * malformed URL can never create a consultation against the wrong/undefined id.
 */
export function firstParam(value: string | string[] | undefined): string {
  if (Array.isArray(value)) return value[0] ?? ''
  return value ?? ''
}
