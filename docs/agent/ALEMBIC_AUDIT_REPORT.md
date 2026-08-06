# Alembic Migration Chain Audit

**Date:** 2026-07-07
**Alembic HEAD:** `t13_p0_note_draft_status`
**Total revisions:** 44
**Auditor:** Claude Code (read-only, no DB writes)

---

## Chain Status

```
SINGLE_HEAD ✅
```

`python -m alembic heads` returns exactly one head: `t13_p0_note_draft_status`. The chain resolves fully from head to a single base (`2c30ffd33627`). No orphan revisions detected.

---

## Revision List (ordered, head → base)

| # | revision_id | description | down_revision | status |
|---|---|---|---|---|
| 1 | `t13_p0_note_draft_status` | add draft/finalized status to consultation_notes | `t12_merge_p0_m1_heads` | **HEAD** |
| 2 | `t12_merge_p0_m1_heads` | merge t12_p0 + t12_m1 heads (no-op schema) | `(t12_p0_doctor_review_decisions, t12_m1_meto_conv_review)` | merge |
| 3 | `t12_p0_doctor_review_decisions` | doctor_review_decisions encrypted store | `t11_m1_health_metric_original` | branch |
| 4 | `t12_m1_meto_conv_review` | Meto conv admin-review columns | `t11_m1_health_metric_original` | branch |
| 5 | `t11_m1_health_metric_original` | add original_value/unit to health_metrics (P0) | `t10_m1_consultation_marketplace` | branchpoint |
| 6 | `t10_m1_consultation_marketplace` | Doctor Marketplace — consultation bounded context | `a1_terms_consents` | ok |
| 7 | `a1_terms_consents` | add terms_consents table | `1ec6f403fced` | ok |
| 8 | `1ec6f403fced` | add Meto AI tables | `t9_m2_drug_seed` | ok |
| 9 | `t9_m2_drug_seed` | seed drug_catalog reference table | `t9_m1_drug_cat` | ok |
| 10 | `t9_m1_drug_cat` | add drug_catalog reference table | `t8_m1_unitlen` | ok |
| 11 | `t8_m1_unitlen` | widen unit/reference_range columns | `t7_m1_dquality` | ok |
| 12 | `t7_m1_dquality` | add data_quality_flag/note to lab_results | `t6_m1_lieng` | ok |
| 13 | `t6_m1_lieng` | lab intelligence provenance columns | `t5_m2_ocase` | ok |
| 14 | `t5_m2_ocase` | add ocr_cases table | `t5_m1_lbatch` | ok |
| 15 | `t5_m1_lbatch` | add lab_upload_batches table | `t4_m11_orlb` | ok |
| 16 | `t4_m11_orlb` | add original_value/unit/ref_range to lab_results | `t4_m10_add_adhr` | ok |
| 17 | `t4_m10_add_adhr` | add medication adherence table | `hmbk_backfill` | ok |
| 18 | `hmbk_backfill` | backfill lab_results → health_metrics | `hm_source_ref` | ok |
| 19 | `hm_source_ref` | add health_metrics.source_ref for lab linkage | `pauth_user_phone` | ok |
| 20 | `pauth_user_phone` | add users.phone + make email nullable | `prf_notif_prefs` | ok |
| 21 | `prf_notif_prefs` | add notification preference columns | `prd_med_frequency` | ok |
| 22 | `prd_med_frequency` | add medications.frequency | `t27_uq_patient_profile_user_id` | ok |
| 23 | `t27_uq_patient_profile_user_id` | unique constraint patient_profiles.user_id | `t23_add_notifications` | ok |
| 24 | `t23_add_notifications` | add notifications table | `t21_add_booking` | ok |
| 25 | `t21_add_booking` | add doctor_availability + booking_appointments | `t19_add_triage_log` | ok |
| 26 | `t19_add_triage_log` | add triage_logs table | `t18_add_ntrl` | ok |
| 27 | `t18_add_ntrl` | add nutrition_logs table | `t4_m9_add_sdel` | ok |
| 28 | `t4_m9_add_sdel` | add soft delete columns | `t4_m8_ext_drcl` | ok |
| 29 | `t4_m8_ext_drcl` | extend doctor clinic fields | `t4_m7_add_junc` | ok |
| 30 | `t4_m7_add_junc` | add doctor clinic junction | `t4_m6_add_bksp` | ok |
| 31 | `t4_m6_add_bksp` | add booking health snapshot | `t4_m5_add_cpln` | ok |
| 32 | `t4_m5_add_cpln` | add care plan table | `t4_m4b_enc_fk` | ok |
| 33 | `t4_m4b_enc_fk` | add encounter FKs to ai_sessions (C5 fix) | `t4_m4_add_encs` | ok |
| 34 | `t4_m4_add_encs` | add encounter table | `t4_m3_add_recs` | ok |
| 35 | `t4_m3_add_recs` | add ai clinical recommendations | `t4_m2_ext_sess` | ok |
| 36 | `t4_m2_ext_sess` | extend ai session fields | `t4_m1_ren_conv` | ok |
| 37 | `t4_m1_ren_conv` | rename ai_conversations → ai_sessions | `t4_m0_role` | ok |
| 38 | `t4_m0_role` | add ai_service to userrole constraint (C6 fix) | `a1b2c3d4e5f6` | ok |
| 39 | `a1b2c3d4e5f6` | lab document pipeline status | `8e3134ab9679` | ok |
| 40 | `8e3134ab9679` | refresh token family and audit severity | `65849f86200f` | ok |
| 41 | `65849f86200f` | refresh tokens and MFA | `fad70c6f2d60` | ok |
| 42 | `fad70c6f2d60` | encrypt PHI fields | `85416e7ef0e9` | ok |
| 43 | `85416e7ef0e9` | timescaledb hypertable + continuous aggregate | `2c30ffd33627` | ok |
| 44 | `2c30ffd33627` | initial schema — 14 core entities | `None` | **BASE** |

---

## Gaps / Orphans Found

**NONE**

All 44 revision files form a fully connected DAG with exactly one head and one base. Every `down_revision` reference resolves to an existing file in `alembic/versions/`.

### Note on "missing" sprint numbers (T14–T17, T20, T22, T24–T26)

These sprint tickets did not produce schema-changing migrations — they were testing, API-only, or operational hardening tasks:

| Sprint | Type | Migration needed? |
|--------|------|------------------|
| T14 | Lab pipeline E2E tests | No |
| T15 | Symptom log + medication CRUD API | No (tables existed) |
| T16 | Care plan + encounter RBAC test coverage | No |
| T17 | Admin API tests + AI sessions coverage | No |
| T20 | Production hardening (health check, startup validation) | No |
| T22 | Doctor portal summary API | No |
| T24 | PDF report export | No |
| T25 | Admin user management endpoints | No |
| T26 | Pilot hardening + smoke test | No |

The numbering gaps are intentional and normal.

### Note on `t12_merge_p0_m1_heads` branching

The branch at `t11_m1_health_metric_original` (two children: `t12_p0` and `t12_m1`) is correctly resolved by the merge revision `t12_merge_p0_m1_heads`. This is well-documented in the migration comment. No action needed.

### Note on `alembic check` output

`alembic check` reported: `Target database is not up to date.`

This is expected for a **local SQLite dev DB** that has not been upgraded to `t13_p0_note_draft_status`. It does **not** indicate a chain issue — it only means the local dev database stamp is behind HEAD. The chain structure itself is valid.

---

## Risk Assessment

**LOW RISK.** The migration chain is structurally sound:

- ✅ Single head (`t13_p0_note_draft_status`)
- ✅ Single base (`2c30ffd33627`)
- ✅ No orphan revisions
- ✅ No broken `down_revision` references
- ✅ The only branch (`t11` → `t12_p0` + `t12_m1`) is properly resolved via merge revision
- ✅ All 44 files in `alembic/versions/` participate in the chain
- ✅ `t12_merge_p0_m1_heads` is a documented no-op schema merge (upgrade/downgrade are no-ops)
- ✅ Short slug revision IDs (`t13_p0_note_draft_status` = 26 chars) fit within the `alembic_version(32)` column limit

One minor operational note: the local SQLite dev DB is behind HEAD (needs `alembic upgrade head` on local to reach t13). This is a dev environment concern, not a chain integrity issue.

---

## Recommended Action

```
NONE_REQUIRED
```

The Alembic migration chain is clean and ready for production deployment. No migration fixes, merges, or rewrites are needed.

**For deploy pipeline:** `python -m alembic upgrade head` will apply any unapplied revisions in correct topological order and terminate at `t13_p0_note_draft_status`.
