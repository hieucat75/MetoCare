'use client'

import * as React from 'react'
import { Building2 } from 'lucide-react'
import { Select } from '@/design-system'
import { useClinic } from '@/lib/clinic/ClinicContext'

/**
 * Switches the *active branch* within the caller's single current clinic —
 * a distinct, explicit action from switching clinics (handled separately by
 * `ClinicRouteGuard`'s "must_select_clinic" state). Purely client-side today:
 * no Phase C0 endpoint accepts a branch filter, so this does not scope any
 * request yet (see `ClinicContext.tsx` for the rationale) — it just persists
 * the selection for C1 screens to read later.
 *
 * Hidden entirely when the caller's role can't read branches (Accountant,
 * RBAC_MATRIX.md M02 row) or when the clinic has 0-1 branches (nothing to
 * switch between).
 */
export function BranchSwitcher() {
  const { branches, activeBranchId, setActiveBranchId, capabilities } = useClinic()

  if (!capabilities.canViewBranches || branches.length < 2) return null

  const options = [
    { value: '__all__', label: 'Tất cả chi nhánh' },
    ...branches.map((b) => ({ value: b.id, label: b.name })),
  ]

  return (
    <div className="flex items-center gap-2 px-1">
      <Building2 className="h-4 w-4 shrink-0 text-text-muted" aria-hidden="true" />
      <Select
        value={activeBranchId ?? '__all__'}
        onValueChange={(value) => setActiveBranchId(value === '__all__' ? null : value)}
        options={options}
        fullWidth
      />
    </div>
  )
}
