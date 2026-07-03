# Doctor + Admin portal screenshots

Responsive mobile/desktop captures of the MetoCare doctor and admin portals,
generated with Playwright against a **fully mocked backend** (no live API).

## Files

| PNG | Page | Viewport |
| --- | --- | --- |
| `doctor-dashboard-mobile.png` | Doctor overview (KPI cards + review queue + consultations) | 390×844 |
| `doctor-dashboard-desktop.png` | Doctor overview | 1440×900 |
| `doctor-consultation-workspace-mobile.png` | Consultation workspace (`/doctor/consultations/c-1001`) | 390×844 |
| `doctor-consultation-workspace-desktop.png` | Consultation workspace | 1440×900 |
| `admin-overview-mobile.png` | Admin overview (`/admin/dashboard`) | 390×844 |
| `admin-overview-desktop.png` | Admin overview | 1440×900 |
| `admin-consultations-mobile.png` | Consultation monitoring (`/admin/consultations`) — responsive stacked cards | 390×844 |
| `admin-consultations-desktop.png` | Consultation monitoring — data table | 1440×900 |

Mobile shots show the `PortalShell` drawer top bar (hamburger) + the responsive
`DataTable` stacked-card view; desktop shots show the expanded sidebar + real
`<table>`.

## Regenerate

```bash
cd frontend
npx playwright install chromium   # once, if browsers are missing
npx playwright test               # runs both viewport projects → 8 PNGs
npx playwright test --project=mobile     # only mobile
npx playwright test --project=desktop    # only desktop
```

- Config: `frontend/playwright.config.ts` — boots `next dev` on an isolated port
  **3199** (so it never collides with a dev server already on the default 3099)
  and defines the `mobile` (390×844) / `desktop` (1440×900) projects.
- Specs: `frontend/e2e/screenshots.spec.ts`.
- Mock backend + seeded auth: `frontend/e2e/fixtures.ts`. `mockPortal(page, role)`
  seeds `meto_access` / `meto_refresh` into `localStorage` before load and routes
  every `**/api/v1/**` request to Vietnamese fixtures — `/auth/me` (doctor vs
  `internal_admin`), `/doctor/stats`, `/doctor/queue`, `/doctors/me/consultations`,
  `/consultations/:id(+/patient-summary,/notes)`, `/admin/stats`,
  `/admin/consultations(+/stats)`, `/admin/doctors`, `/admin/users`,
  `/admin/audit-logs` — so pages render populated, never error/empty states.
