/**
 * formatLabValue.ts — backward-compat re-export shim.
 *
 * The canonical implementation has moved to `@/lib/formatNumber`.
 * This file re-exports everything so existing imports continue to work
 * without any changes.
 *
 * @see @/lib/formatNumber
 */
export { formatLabValue, formatLabDisplay } from '@/lib/formatNumber'
