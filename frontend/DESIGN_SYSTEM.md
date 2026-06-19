# MetoCare Design System

## Quick Start

```ts
// Core components
import Button from '@/design-system/components/core/Button'
import { Badge, Alert, Card, Modal, Tabs } from '@/design-system/components/core'

// Layout
import { AppShell, Sidebar, TopNav, PageHeader } from '@/design-system/components/layout'

// Healthcare domain
import { PatientMetricCard, RiskLevelBadge, AISessionCard } from '@/design-system/components/healthcare'

// Tokens
import TOKENS, { CLINICAL_STATUS_MAP } from '@/design-system/tokens'
```

---

## Design Tokens

Source: `src/design-system/tokens/index.ts`

| Category | Key Values |
|---|---|
| **Primary** | `#1B4FD8` (default) / `#EFF4FF` (light) / `#1540B8` (hover) |
| **Secondary** | `#475569` (default) / `#F1F5F9` (light) |
| **Accent** | `#0891B2` clinical teal |
| **Success** | `#16A34A` / light `#DCFCE7` |
| **Warning** | `#D97706` / light `#FEF3C7` |
| **Danger** | `#DC2626` / light `#FEE2E2` |
| **Background** | `#F8FAFC` / surface `#FFFFFF` / border `#E2E8F0` |
| **Text** | `#0F172A` default / `#64748B` muted / `#94A3B8` subtle |
| **Font** | Inter (sans), JetBrains Mono (mono) |
| **Radius** | sm `4px` / md `8px` / lg `12px` / xl `16px` / full `9999px` |
| **Shadow focus** | `0 0 0 3px rgba(27,79,216,0.25)` |

---

## Component Index

### Core

| Component | Path | Variants / Sizes | Purpose |
|---|---|---|---|
| Button | `core/Button.tsx` | primary, secondary, ghost, outline, danger, link / xs sm md lg | Primary action element with spinner and icon slots |
| Badge | `core/Badge.tsx` | default, primary, success, warning, danger, info + 9 clinical / sm md | Inline status label; clinical variants auto-apply Vietnamese text |
| Alert | `core/Alert.tsx` | info, success, warning, danger, neutral | Left-bordered contextual alert with dismiss |
| Card | `core/Card.tsx` | default, outlined, elevated, ghost, flat / padding none sm md lg | Generic content container |
| Modal | `core/Modal.tsx` | sizes: sm md lg xl full | Accessible dialog (Radix Dialog) |
| Tabs | `core/Tabs.tsx` | line, pill, card | Tab navigation with badge counts (Radix Tabs) |
| Input / PasswordInput | `core/Input.tsx` | — | Text input with icon slots; PasswordInput adds show/hide |
| Textarea | `core/Textarea.tsx` | — | Multi-line input |
| Select | `core/Select.tsx` | — | Single-select dropdown (Radix Select) |
| Checkbox | `core/Checkbox.tsx` | — | Accessible checkbox with label/description |
| RadioGroup | `core/Radio.tsx` | horizontal / vertical | Radio group (Radix Radio) |
| Switch | `core/Switch.tsx` | — | Toggle switch (Radix Switch) |
| FormField | `core/FormField.tsx` | — | Label + hint + error wrapper for any input |
| Table | `core/Table.tsx` | — | Data table with column config, skeleton, row click |
| EmptyState | `core/EmptyState.tsx` | — | Zero-data placeholder with CTA |
| Spinner / Skeleton / PageLoading | `core/LoadingState.tsx` | — | Loading primitives |
| ErrorState | `core/ErrorState.tsx` | — | Error display with retry |

### Layout

| Component | Path | Purpose |
|---|---|---|
| AppShell | `layout/AppShell.tsx` | Top-level shell composing sidebar + top nav |
| Sidebar | `layout/Sidebar.tsx` | Role-aware vertical nav with nested items |
| TopNav | `layout/TopNav.tsx` | Horizontal bar with breadcrumbs and action slots |
| PageHeader | `layout/PageHeader.tsx` | Page-level title + breadcrumbs + action buttons |

### Healthcare Domain

| Component | Path | Purpose |
|---|---|---|
| PatientMetricCard | `healthcare/PatientMetricCard.tsx` | Single metabolic metric with value, unit, trend, risk |
| RiskLevelBadge | `healthcare/RiskLevelBadge.tsx` | Standalone high/medium/low risk pill |
| CarePlanCard | `healthcare/CarePlanCard.tsx` | Care plan summary with goal progress |
| MedicationCard | `healthcare/MedicationCard.tsx` | Medication detail with dosage and schedule |
| ConsentStatusCard | `healthcare/ConsentStatusCard.tsx` | Patient consent record with revoke action |
| AISessionCard | `healthcare/AISessionCard.tsx` | AI consultation session with status and review CTA |
| DoctorReviewQueueItem | `healthcare/DoctorReviewQueueItem.tsx` | Review queue row with priority and patient info |
| ClinicalRecommendationPanel | `healthcare/ClinicalRecommendationPanel.tsx` | AI recommendation list with accept/modify |
| ReviewDecisionPanel | `healthcare/ReviewDecisionPanel.tsx` | Doctor approve/reject/request-info controls |
| PatientSummaryHeader | `healthcare/PatientSummaryHeader.tsx` | Patient identity strip with demographics and risk |
| TimelineItem | `healthcare/TimelineItem.tsx` | Single event in vertical clinical timeline |

---

## Clinical Status Colors

| Status | Token Key | Background | Border | Text (hex) | Vietnamese Label |
|---|---|---|---|---|---|
| pending_review | `clinical.pendingReview` | `#FEF3C7` | `#FCD34D` | `#D97706` | Cho xet duyet |
| approved | `clinical.approved` | `#DCFCE7` | `#86EFAC` | `#16A34A` | Da duyet |
| rejected | `clinical.rejected` | `#FEE2E2` | `#FCA5A5` | `#DC2626` | Tu choi |
| request_info | `clinical.requestInfo` | `#DBEAFE` | `#93C5FD` | `#2563EB` | Yeu cau them thong tin |
| active | `clinical.active` | `#DCFCE7` | `#86EFAC` | `#16A34A` | Dang hoat dong |
| revoked | `clinical.revoked` | `#F3F4F6` | `#D1D5DB` | `#6B7280` | Da thu hoi |
| high_risk | `clinical.highRisk` | `#FEE2E2` | `#FCA5A5` | `#DC2626` | Nguy co cao |
| medium_risk | `clinical.mediumRisk` | `#FEF3C7` | `#FCD34D` | `#D97706` | Nguy co trung binh |
| low_risk | `clinical.lowRisk` | `#DCFCE7` | `#86EFAC` | `#16A34A` | Nguy co thap |

Use `CLINICAL_STATUS_MAP[status]` from `@/design-system/tokens` to resolve Tailwind class strings.  
Use `<Badge variant="pending_review" />` (no children) to auto-render the Vietnamese label.

---

## Accessibility

- All interactive components expose `focus-visible` rings using the `focus` shadow token (`rgba(27,79,216,0.25)`).
- Danger/destructive focus uses `focus-danger` (`rgba(220,38,38,0.25)`).
- Icon-only decorative elements carry `aria-hidden="true"`.
- Alert renders with `role="alert"`. Modal uses Radix Dialog which manages `aria-modal`, `aria-labelledby`, and focus trap.
- Loading buttons set `aria-busy={true}` and disable pointer events during `loading` state.
- Clinical Badge variants expose Vietnamese text as visible label for screen readers.

---

## Claude Design Sync

From the `frontend/` directory:

```bash
/design-sync
```

The manifest at `frontend/design-system.manifest.json` describes all tokens, component paths, variants, and clinical workflow statuses. Claude Design reads this file to sync the component gallery at `/design-system`.
