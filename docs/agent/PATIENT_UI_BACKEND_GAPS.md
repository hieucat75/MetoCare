# Patient UI — Backend Gaps Backlog

Tracked gaps discovered during the **V3 Decision-First UI replacement** (branch `feat/merge-design-into-patient`).
These are **not** implemented in the UI PR by design: the UI PR makes **no backend changes** and adds **no fake clinical content**. Each gap below is a backend contract that must be added before the corresponding spec feature can be fully wired.

Spec reference: `docs/product/METOCARE_PATIENT_APP_V1_DESIGN_SPEC.md`.

---

## Gap 1 — `MetricInsight` is missing `causes` + `expected_outcome`

**Spec:** §4 "Normalized Metric Detail Screen" requires two sections the API cannot supply:
- **NGUYÊN NHÂN CÓ THỂ** (possible causes)
- **KẾT QUẢ MONG ĐỢI** (expected outcome)

**Current frontend behavior**
- `GET /patients/{id}/insights/{metric_type}` → `MetricInsight` exposes only `meaning`, `risks[]`, `lifestyle[]`, `follow_up`, `trend`, `priority`, `disclaimer`.
- The metric detail screen (`(patient)/metrics/[metricType]/page.tsx`) renders Ý nghĩa / Nguy cơ / Khuyến nghị / Theo dõi + chart and **omits** Nguyên nhân and Kết quả mong đợi (a `// TODO(backend)` marks the spot). Nothing is hardcoded.

**Required backend contract**
- Add two fields to the `MetricInsight` schema (rules-first content, same engine as PA-11):
  - `causes: string[]` — behavioral/clinical/diet factors for the current value.
  - `expected_outcome: string` — what improves when the recommended action is followed.

**Suggested endpoint/schema** (extend existing, no new route)
```jsonc
// GET /patients/{id}/insights/{metric_type}  (MetricInsight, additive)
{
  "causes": ["Ăn nhiều tinh bột tinh chế", "Ít vận động"],
  "expected_outcome": "Đưa đường huyết đói về 4.0–5.5 mmol/L, giảm mệt mỏi."
}
```

**Why not implemented in UI PR:** would require changing the backend insight schema + rules content (out of UI-PR scope; "no backend changes"). Fabricating causes/outcome on the client would be fake clinical content (forbidden).

**Priority:** **P2** — detail screen is fully usable without it; additive enhancement to reach 100% spec §4.

---

## Gap 2 — AI Coach / "Xác nhận đã thực hiện" confirm-action loop has no endpoint

**Spec:** §5 (Contextual Coach) + §7.2 (`ConfirmButton`): the Action card's `[Xác nhận đã thực hiện]` button should record the action and return a positive coach message; the Coach sheet offers pre-defined option chips.

**Current frontend behavior**
- Dashboard Health Priority Engine shows the action + a primary CTA, but the CTA routes to the metric **detail** (read mode). There is **no** "confirm action taken" persistence and **no** AI coach sheet. The "Đã hiểu" button is a **local-only** dismiss (session state, no API).

**Required backend contract**
- An action-acknowledgement endpoint + (optionally) a contextual-coach reply.

**Suggested endpoint/schema**
```jsonc
// POST /patients/{id}/insights/{metric_type}/ack
//   body: { "action_id": "string", "acknowledged_at": "ISO-8601" }
//   200: { "coach_message": "Tuyệt vời bác An! ...", "streak": 3 }

// (optional) GET /patients/{id}/coach/chips?context=metric:{metric_type}
//   200: { "chips": ["Tôi thấy tim đập nhanh thì làm gì?", "Quên uống thuốc 1 ngày có sao không?"] }
```

**Why not implemented in UI PR:** no endpoint exists; a fake confirm/coach reply would be invented clinical content + false persistence (forbidden).

**Priority:** **P2** — nice-to-have engagement loop; dashboard decision flow works without it.

---

## Gap 3 — Medication adherence / "Đã uống" has no persistence API

**Spec:** §8 Screen 10 "Medications — Check off dosage" / dosage compliance coaching.

**Current frontend behavior**
- `(patient)/medications/page.tsx` renders a daily schedule with a **"Đã uống"** check affordance, but it is **local-only `useState`** (resets on reload), labeled in-UI "Đánh dấu chỉ để nhắc bạn trong phiên này — chưa được lưu lại." and flagged `// TODO(backend): adherence API`. CRUD (add/edit/delete medication) **is** fully wired to the existing API.

**Required backend contract**
- A medication-intake (adherence) log: record a dose taken, list today's intake status.

**Suggested endpoint/schema**
```jsonc
// POST /patients/{id}/medications/{med_id}/intake
//   body: { "taken_at": "ISO-8601", "slot": "morning|noon|evening|other" }
//   201: { "id": "uuid", "med_id": "uuid", "taken_at": "...", "slot": "morning" }

// GET /patients/{id}/medications/intake?date=YYYY-MM-DD
//   200: { "items": [ { "med_id": "uuid", "slot": "morning", "taken_at": "..." } ] }
```

**Why not implemented in UI PR:** no adherence table/endpoint; persisting locally only would imply saved data that isn't (avoided — labeled clearly instead).

**Priority:** **P1** — adherence is a core metabolic-care behavior; this is the most user-valuable of the three. Recommend scheduling first.

---

## Summary

| # | Gap | Frontend today | Backend needed | Priority |
|---|-----|----------------|----------------|----------|
| 1 | Insight `causes` + `expected_outcome` | sections omitted | additive `MetricInsight` fields | P2 |
| 2 | AI coach + confirm-action | local "Đã hiểu" dismiss only | `POST .../ack` (+ coach chips) | P2 |
| 3 | Medication adherence | local-only "Đã uống" | `POST/GET .../intake` | P1 |

None of these block the UI PR. They are the backend follow-ups required to reach 100% of `METOCARE_PATIENT_APP_V1_DESIGN_SPEC.md`.
