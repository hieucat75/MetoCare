'use client'

import * as React from 'react'
import { ClinicProvider } from '@/lib/clinic/ClinicContext'
import { ClinicRouteGuard } from '@/components/clinic/ClinicRouteGuard'
import { ClinicShell } from '@/components/clinic/ClinicShell'

/**
 * Root layout for the Clinic Portal (`/clinic/*`, clinic staff — Owner,
 * Admin, Doctor, Nurse, Receptionist, Care Coordinator, Accountant). Distinct
 * from `/admin/*` (platform admins) and `/doctor/*` (marketplace doctors) —
 * neither of those shells is reused here.
 *
 * `ClinicProvider` resolves the active clinic + capability tier once for the
 * whole portal; `ClinicRouteGuard` blocks rendering of any protected content
 * until auth + membership are both resolved (no flash of protected UI).
 */
export default function ClinicPortalLayout({ children }: { children: React.ReactNode }) {
  return (
    <ClinicProvider>
      <ClinicRouteGuard>
        <ClinicShell>{children}</ClinicShell>
      </ClinicRouteGuard>
    </ClinicProvider>
  )
}
