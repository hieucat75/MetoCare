'use client'

import * as React from 'react'
import {
  getMyClinic,
  getMyMembership,
  listMyMemberships,
  listBranches,
  getClinicSubscription,
  type ClinicOut,
  type ClinicRole,
  type ClinicBranchOut,
  type ClinicSubscriptionDetailOut,
  type MyClinicMembershipOut,
} from '@/lib/api/clinics'
import { ApiError, toPageError, type PageError } from '@/lib/api/client'

// ---------------------------------------------------------------------------
// Capabilities — derived directly from the caller's own ClinicMembership.roles
// ---------------------------------------------------------------------------
//
// `GET /clinics/me/membership` (backend/app/api/v1/routes/clinics.py) returns
// the caller's real roles at their active clinic, resolved server-side via
// `TenantContext` (never guessed client-side). Capabilities below are a
// direct transcription of docs/clinic-saas/RBAC_MATRIX.md §3's Phase-C0 rows
// (Clinic config M01, Branches M02, Staff M03, Subscription M04, Services
// M05) — every capability still re-checks against the backend's own 403 on
// the actual write call (this object only controls what's *offered* in the
// UI, never the authorization decision itself).
export interface ClinicCapabilities {
  canManageClinic: boolean // M01 write — Owner/Admin
  canDeactivateClinic: boolean // Owner only (clinics.py: require_clinic_roles(OWNER))
  canViewStaff: boolean // M03 — Owner/Admin (GET /members is Owner/Admin-only, so view==manage in C0)
  canViewBranches: boolean // M02 read — everyone except Accountant
  canManageBranches: boolean // M02 write — Owner/Admin
  canManageServices: boolean // M05 write — Owner/Admin (read is universal, all 7 roles)
  canManageSubscription: boolean // M04 write — Owner only
  canViewSubscription: boolean // M04 read — Owner/Admin/Accountant
  canViewPatients: boolean // M06 read — Owner/Admin/Doctor/Nurse/Reception full, Care Coordinator narrow, Accountant excluded
  canManagePatients: boolean // M06 link/create — Owner/Admin/Reception
  canUpdatePatientRecord: boolean // M06 PATCH status/internal_notes — Owner/Admin/Reception
  canViewAppointments: boolean // M07 read — everyone except Accountant (RBAC_MATRIX.md Appointments row)
  canManageAppointments: boolean // M07 create/confirm/cancel/reschedule — Owner/Admin/Reception/Doctor (Doctor's own-only scoping is server-enforced, this is UX-only)
}

function capabilitiesForRoles(roles: ClinicRole[]): ClinicCapabilities {
  const has = (r: ClinicRole) => roles.includes(r)
  const ownerOrAdmin = has('owner') || has('admin')
  const isAccountantOnly = roles.length > 0 && roles.every((r) => r === 'accountant')
  return {
    canManageClinic: ownerOrAdmin,
    canDeactivateClinic: has('owner'),
    canViewStaff: ownerOrAdmin,
    canViewBranches: !isAccountantOnly,
    canManageBranches: ownerOrAdmin,
    canManageServices: ownerOrAdmin,
    canManageSubscription: has('owner'),
    canViewSubscription: ownerOrAdmin || has('accountant'),
    canViewPatients:
      ownerOrAdmin ||
      has('doctor') ||
      has('nurse') ||
      has('receptionist') ||
      has('care_coordinator'),
    canManagePatients: ownerOrAdmin || has('receptionist'),
    canUpdatePatientRecord: ownerOrAdmin || has('receptionist'),
    canViewAppointments: !isAccountantOnly,
    canManageAppointments: ownerOrAdmin || has('receptionist') || has('doctor'),
  }
}

// ---------------------------------------------------------------------------
// Context shape
// ---------------------------------------------------------------------------

export type ClinicStatusState =
  | 'loading'
  | 'ready'
  | 'no_membership'
  | 'must_select_clinic'
  | 'error'

export interface ClinicContextValue {
  status: ClinicStatusState
  error: PageError | null
  clinic: ClinicOut | null
  roles: ClinicRole[]
  capabilities: ClinicCapabilities
  subscription: ClinicSubscriptionDetailOut | null
  branches: ClinicBranchOut[]
  /** Every clinic the caller belongs to — real clinic-switcher data from
   * `GET /clinics/memberships/mine`, not a guess. Empty until loaded;
   * `status === 'must_select_clinic'` is exactly the case where the UI must
   * render this list and let the user pick (never silently default). */
  myMemberships: MyClinicMembershipOut[]
  /** Switch the active clinic — persists the choice and reloads. */
  switchClinic: (clinicId: string) => void
  /** Locally-selected active branch for this session — purely a client-side
   * UX concept today. None of the Phase C0 endpoints accept a branch filter,
   * so this does not scope any request yet; it exists so C1 (appointments/
   * queue, which will be branch-scoped) can read it without another
   * BranchSwitcher rebuild. */
  activeBranchId: string | null
  setActiveBranchId: (branchId: string | null) => void
  refresh: () => Promise<void>
}

const ClinicContext = React.createContext<ClinicContextValue | null>(null)

function branchStorageKey(clinicId: string): string {
  return `meto_clinic_active_branch:${clinicId}`
}

const ACTIVE_CLINIC_STORAGE_KEY = 'meto_clinic_active_clinic_id'

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

export function ClinicProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = React.useState<ClinicStatusState>('loading')
  const [error, setError] = React.useState<PageError | null>(null)
  const [clinic, setClinic] = React.useState<ClinicOut | null>(null)
  const [roles, setRoles] = React.useState<ClinicRole[]>([])
  const [subscription, setSubscription] = React.useState<ClinicSubscriptionDetailOut | null>(null)
  const [branches, setBranches] = React.useState<ClinicBranchOut[]>([])
  const [myMemberships, setMyMemberships] = React.useState<MyClinicMembershipOut[]>([])
  const [activeBranchId, setActiveBranchIdState] = React.useState<string | null>(null)

  const setActiveBranchId = React.useCallback(
    (branchId: string | null) => {
      setActiveBranchIdState(branchId)
      if (typeof window === 'undefined' || !clinic) return
      if (branchId) window.localStorage.setItem(branchStorageKey(clinic.id), branchId)
      else window.localStorage.removeItem(branchStorageKey(clinic.id))
    },
    [clinic]
  )

  const load = React.useCallback(async () => {
    setStatus('loading')
    setError(null)
    const selectedClinicId =
      typeof window === 'undefined'
        ? undefined
        : (window.localStorage.getItem(ACTIVE_CLINIC_STORAGE_KEY) ?? undefined)
    try {
      // `myMemberships` is always safe to fetch (never gated by which clinic
      // is active) — it's the source of truth for whether a switcher is even
      // needed, and the fallback when `X-Clinic-Id` alone can't resolve one.
      const membershipList = await listMyMemberships()
      setMyMemberships(membershipList.items)

      const [activeClinic, membership] = await Promise.all([
        getMyClinic(selectedClinicId),
        getMyMembership(selectedClinicId),
      ])
      setClinic(activeClinic)
      setRoles(membership.roles)

      const [subscriptionResult, branchesResult] = await Promise.allSettled([
        getClinicSubscription(activeClinic.id),
        listBranches(activeClinic.id, { limit: 200 }),
      ])
      setSubscription(subscriptionResult.status === 'fulfilled' ? subscriptionResult.value : null)
      setBranches(branchesResult.status === 'fulfilled' ? branchesResult.value.items : [])

      if (typeof window !== 'undefined') {
        window.localStorage.setItem(ACTIVE_CLINIC_STORAGE_KEY, activeClinic.id)
        const storedBranch = window.localStorage.getItem(branchStorageKey(activeClinic.id))
        setActiveBranchIdState(storedBranch)
      }

      setStatus('ready')
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 403) {
        setStatus('no_membership')
        setError(toPageError(err))
        return
      }
      if (err instanceof ApiError && err.status === 400) {
        setStatus('must_select_clinic')
        setError(toPageError(err))
        return
      }
      setStatus('error')
      setError(toPageError(err))
    }
  }, [])

  const switchClinic = React.useCallback(
    (clinicId: string) => {
      if (typeof window !== 'undefined') {
        window.localStorage.setItem(ACTIVE_CLINIC_STORAGE_KEY, clinicId)
      }
      void load()
    },
    [load]
  )

  React.useEffect(() => {
    void load()
  }, [load])

  const value = React.useMemo<ClinicContextValue>(
    () => ({
      status,
      error,
      clinic,
      roles,
      capabilities: capabilitiesForRoles(roles),
      subscription,
      branches,
      myMemberships,
      switchClinic,
      activeBranchId,
      setActiveBranchId,
      refresh: load,
    }),
    [
      status,
      error,
      clinic,
      roles,
      subscription,
      branches,
      myMemberships,
      switchClinic,
      activeBranchId,
      setActiveBranchId,
      load,
    ]
  )

  return <ClinicContext.Provider value={value}>{children}</ClinicContext.Provider>
}

export function useClinic(): ClinicContextValue {
  const ctx = React.useContext(ClinicContext)
  if (!ctx) throw new Error('useClinic must be used within ClinicProvider')
  return ctx
}
