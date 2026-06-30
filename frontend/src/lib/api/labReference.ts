'use client'

import * as React from 'react'
import { api } from './client'

// ── Catalog types (mirror backend app/data/lab_reference.json) ───────────────

export interface LabUnit {
  key: string
  label: string
  ref_range: { low: number; high: number }
  is_primary?: boolean
}

export interface LabBiomarker {
  name_vn: string
  name_en: string
  category: string
  units: LabUnit[]
  value_precision: number
  notes: string
  higher_is_better: boolean | null
}

export interface LabCategory {
  key: string
  name: string
  biomarkers: string[]
}

export interface LabCatalog {
  version: string
  categories: LabCategory[]
  biomarkers: Record<string, LabBiomarker>
}

// ── Fetch + 24h in-memory cache (no React Query in this project) ─────────────

let _cache: LabCatalog | null = null
let _inflight: Promise<LabCatalog> | null = null

export async function getLabReference(): Promise<LabCatalog> {
  if (_cache) return _cache
  if (!_inflight) {
    _inflight = api
      .get<LabCatalog>('/lab-reference')
      .then((c) => {
        _cache = c
        return c
      })
      .finally(() => {
        _inflight = null
      })
  }
  return _inflight
}

/** Returns the catalog (or null while loading / on error). */
export function useLabReference(): LabCatalog | null {
  const [catalog, setCatalog] = React.useState<LabCatalog | null>(_cache)
  React.useEffect(() => {
    if (_cache) {
      setCatalog(_cache)
      return
    }
    let alive = true
    getLabReference()
      .then((c) => alive && setCatalog(c))
      .catch(() => alive && setCatalog(null))
    return () => {
      alive = false
    }
  }, [])
  return catalog
}

// ── Status classification from a value + the selected unit's reference range ──

export type LabStatusKey = 'normal' | 'low' | 'high' | 'very_low' | 'very_high'

export interface LabStatus {
  key: LabStatusKey
  label: string
  tone: 'mint' | 'warning' | 'danger'
  /** Implausible (>5× the upper bound, or far below a positive lower bound). */
  implausible: boolean
}

const STATUS_LABEL: Record<LabStatusKey, string> = {
  normal: 'Bình thường',
  low: 'Thấp',
  high: 'Cao',
  very_low: 'Rất thấp',
  very_high: 'Rất cao',
}
const STATUS_TONE: Record<LabStatusKey, 'mint' | 'warning' | 'danger'> = {
  normal: 'mint',
  low: 'warning',
  high: 'warning',
  very_low: 'danger',
  very_high: 'danger',
}

export function classifyLabValue(
  value: number,
  unit: LabUnit,
  higherIsBetter: boolean | null,
): LabStatus {
  const { low, high } = unit.ref_range
  let key: LabStatusKey = 'normal'

  if (higherIsBetter === true) {
    // Only a LOW value is a concern (e.g. HDL, eGFR).
    if (value < low * 0.6) key = 'very_low'
    else if (value < low) key = 'low'
  } else if (higherIsBetter === false) {
    // Both high AND low values are concerns.
    if (value > high * 1.5) key = 'very_high'
    else if (value > high) key = 'high'
    else if (low > 0 && value < low * 0.6) key = 'very_low'
    else if (low > 0 && value < low) key = 'low'
  } else {
    // null = context-dependent (e.g. Thyroglobulin surveillance after thyroidectomy).
    // Low values are not penalised — only flag genuinely HIGH values.
    if (value > high * 1.5) key = 'very_high'
    else if (value > high) key = 'high'
  }

  const implausible =
    value > high * 5 || (low > 0 && value > 0 && value < low * 0.2) || value < 0

  return { key, label: STATUS_LABEL[key], tone: STATUS_TONE[key], implausible }
}

/** Human-readable reference range for a unit, respecting one-sided bounds. */
export function formatRefRange(unit: LabUnit, higherIsBetter: boolean | null): string {
  const { low, high } = unit.ref_range
  if (higherIsBetter === true) return `≥ ${low} ${unit.label}`
  if (low <= 0) return `≤ ${high} ${unit.label}`
  return `${low}–${high} ${unit.label}`
}

export function primaryUnit(b: LabBiomarker): LabUnit {
  return b.units.find((u) => u.is_primary) ?? b.units[0]
}
