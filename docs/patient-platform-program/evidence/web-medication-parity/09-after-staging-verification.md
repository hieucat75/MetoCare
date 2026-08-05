# After — staging verification on the live URL

Deploy run `30964961627`, `azure-staging.yml` on `feat/patient-platform-journey2`,
**success 2026-08-05T01:03:35Z**, built from `c9bd98a`.

Verified at `https://app.metocare.me` (which is the staging Container App — see §1 of
`../../WEB-MEDICATION-PARITY-STATUS.md`). Driven as the seeded synthetic pilot
patient. No real PHI appears in any artifact here.

## Environment

| Check | Result |
|---|---|
| `GET /api/v1/health` | `{"status":"ok","db":"ok"}` |
| `GET /api/v1/info` | `env=staging`, `migration_version=j4_m8_consent_versioning`, `ocr=true`, `ai_assistant=true` |
| New route `GET /patients/{pid}/medications/{mid}/source` | **401** unauthenticated (route exists; was 404 before deploy) |
| Console errors on the medication detail page | **none** |

## Bundle changed

| | Before | After |
|---|---|---|
| Route chunk | `page-c45586326b373f44.js` | `page-28d1d13788f845bb.js` |
| sha256 | `6402410a…` | `8b55adfe…` |
| Bytes | 29,198 | 50,929 |

Marker diff (decoded from `\xNN` escapes):

| Capability | Before | After |
|---|---|---|
| structured schedule card | no | **yes** |
| next due dose | no | **yes** |
| dose-occurrence adherence | no | **yes** |
| "no fabricated 0%" wording | no | **yes** |
| skip-reason prompt | no | **yes** |
| adverse-event referral (clinical P0) | no | **yes** |
| doctor-stopped routing (P1) | no | **yes** |
| missed-dose referral (P1) | no | **yes** |
| provenance card | no | **yes** |
| corrected `source_type` label (P1) | no | **yes** |
| corrected `verification_status` label (P1) | no | **yes** |
| OCR "có thể sai" wording (P1) | no | **yes** |
| transcription-vs-canonical framing (P1) | no | **yes** |
| timezone-aware display | no | **yes** |
| stopped-schedule clarity (P1) | no | **yes** |
| relabelled legacy chip (P1) | no | **yes** |
| mandated interactions empty state | yes | **yes (preserved)** |

## Journey walked end-to-end

Two medications on the seeded patient: one `patient_manual`, one `ocr_confirmed`.

### Reads

```
GET /patients/{pid}/medications                  200  count=2
GET /patients/{pid}/reminders/due                200  delivered=1  due_now=1
GET /patients/{pid}/medications/{mid}/schedule   200  fixed_daily 08:00,20:00  tz=Asia/Ho_Chi_Minh
GET /patients/{pid}/schedules/{sid}/adherence    200  total=19 taken=1 skipped=0 missed=3 rate=0.25
```

### Actions

| Step | Result |
|---|---|
| `POST /doses/{id}/taken` | **200**, `state=taken`; adherence taken 1→2, rate 0.25→**0.40** |
| Re-submit the same dose as taken | **422** `"Liều đã được ghi nhận."` |
| Submit the same dose as skipped | **422** `"Liều đã được ghi nhận."` |

⇒ Confirms the already-recorded case is **422, not 409** — the client comment that
claimed 409 was wrong and has been corrected, with the 422 detail-passthrough tested.

### Skip with a structured reason, through the UI

Performed in the browser at `app.metocare.me`, not via curl:

1. `Bỏ qua` → prompt opens, rendered as `role="radiogroup"` with 5 `role="radio"` options.
2. Selected **`Tác dụng phụ`** → the referral appears:
   *"…hệ thống không tự báo cho bác sĩ. Nếu bạn thấy khó thở, phù, choáng, hạ đường
   huyết hoặc bất kỳ dấu hiệu bất thường nào, hãy liên hệ bác sĩ hoặc cơ sở y tế gần
   nhất ngay."*
3. Typed `buồn nôn nhiều` into the note field, then re-read the checked radio:

   ```
   document.querySelector('[role=radio][aria-checked=true]').textContent
   → "Tác dụng phụ"
   ```

   ⇒ **The clinical P0 is fixed on the live build.** Before, typing a note replaced the
   chip selection and the structured adverse-event classification was discarded.
4. `Xác nhận bỏ qua` → persisted. Adherence re-read from the backend:
   `taken=0 skipped=1 missed=0 rate=0.0`, and the card then rendered
   **"0% · Đã uống 0 · Bỏ qua 1 · Đã lỡ 0 · Tính trên 1 liều đã đến hạn kể từ 05/08/2026."**
   — the period statement (P1) rendering live.

### Provenance + consent

| Step | Result |
|---|---|
| `documents` consent **not** granted | `GET …/source` → **403** → card renders the actionable consent state, page keeps working |
| Consent granted | `GET …/source` → **200**, `has_document_source=true`, 1 prescription document |
| Consent revoked again | **403** (fail-closed re-verified live) |
| Consent re-granted | **200** |

The `ocr_confirmed` medication renders:

- **Nguồn:** `Máy đọc từ tài liệu, bạn đã duyệt` — the exact value that previously
  rendered as the raw English token `ocr_confirmed` under a green shield.
- **Trạng thái xác nhận:** `Bạn tự khai — chưa có bác sĩ xác nhận`
- OCR notice: *"…do máy đọc tự động từ ảnh tài liệu và **có thể sai**. Hãy đối chiếu
  với đơn/toa gốc trước khi dùng, đặc biệt là hàm lượng, liều và tần suất."*
- Framing: *"Nội dung trên tài liệu gốc (ghi lại từ ảnh — không phải liều đang áp dụng):"*
- Allowlisted fields only: `Hàm lượng`, `Dạng bào chế`, `Số lượng`, `Tần suất`,
  `Đường dùng`, `Hướng dẫn trên đơn`, plus `Cơ sở khám` / `Bác sĩ kê đơn` / `Ngày kê đơn`.
- Engine ids behind a `Chi tiết kỹ thuật` disclosure (`qa-fixture · mdi-1`).
- **`diagnosis` absent from the response body** (§1.9), asserted programmatically.

### Access-control probes

| Probe | Result |
|---|---|
| Foreign `patient_id` with a valid token | **403** |
| Unauthenticated | **401** |

## Screenshots

| File | What it shows |
|---|---|
| `01-detail-desktop-schedule-adherence.png` | Desktop two-column: schedule, timezone note, adherence with the qualifier ABOVE the figure, amber (not red) missed count, missed-dose referral |
| `02-detail-mobile-web.png` | Mobile-web single column (the mid-page nav bar is a `position:fixed` artifact of full-page capture) |
| `03-detail-desktop-provenance-ocr.png` | Provenance card with real OCR data and corrected labels |
| `04-skip-reason-prompt.png` | Skip prompt as a radiogroup |
| `05-skip-side-effect-referral.png` | Adverse-event referral (clinical P0) |
| `06-skip-structured-reason-plus-note.png` | Chip still selected with a note typed (clinical P0 fix) |
| `07-after-skip-adherence-updated.png` | Adherence after the skip, with the period statement |
| `08-provenance-mobile-web.png` | Provenance card on mobile-web |

## State changed on staging (synthetic account only)

Recorded for transparency; all on the seeded pilot patient:

- One dose marked **taken**, one dose marked **skipped** (`Tác dụng phụ — buồn nôn nhiều`).
- A `fixed_daily` schedule created on the OCR-sourced medication, then edited (which
  created a new version and stopped the previous one — visible in the card as
  `08:11 Đang áp dụng` + `06:00 Đã dừng`).
- `documents` consent left **granted** so the source card is viewable on manual review
  (it was ungranted before; commit `bfd6735` intended it granted for Journey A).
- Terms-of-service acceptance completed for the test account to pass the consent gate.

## Not exercised live

- **`Bác sĩ dặn ngừng` → discontinue routing.** Present in the deployed bundle
  (marker `Cập nhật trạng thái thuốc` confirmed) and covered by unit tests; not clicked
  live because no further dose was due after the skip.
