## Codex Review — T24 PDF Report Export

**Result:** APPROVE

**P0 Blockers:** 0
**P1 Blockers:** 0
**P2 Warnings:** 1
**Security:** PASS
**Test Results:** 502 passed, 1 skipped (7 T24-specific tests: all green)
**Acceptance Criteria:** 10/10 met

---

### Acceptance Criteria — Detailed

| # | Criterion | Status | Notes |
|---|-----------|--------|-------|
| AC1 | Route RBAC: DOCTOR+consent→200; PATIENT→403; AI_SERVICE→403; ADMIN→200 | ✅ PASS | All 4 RBAC branches verified by tests 1, 4, 5, 6 |
| AC2 | Content-Type: `application/pdf` | ✅ PASS | Route sets `media_type="application/pdf"` on `Response`; test 1 + 6 assert it |
| AC3 | PDF body starts with `%PDF` | ✅ PASS | Mock returns `b"%PDF-1.4 test"`; test 2 asserts `r.content.startswith(b"%PDF")` |
| AC4 | Content-Disposition: `attachment; filename=patient_{id}_summary.pdf` | ✅ PASS | Route sets header exactly; test 3 checks `attachment`, `filename=`, and patient_id presence |
| AC5 | Unauthenticated → 401 | ✅ PASS | Test 7 calls without bearer token; suite-wide `current_user` dep returns 401 |
| AC6 | PDF generation mocked in tests | ✅ PASS | All rendering tests use `patch("app.services.pdf_report.generate_patient_summary_pdf", return_value=_PDF_MOCK_BYTES)`; RBAC tests (4, 5, 7) do not invoke mock at all |
| AC7 | Ruff clean | ✅ PASS | `ruff check .` → "All checks passed!" |
| AC8 | Suite green: 502+ passed | ✅ PASS | `502 passed, 1 skipped in 7.14s` (baseline was 495+1; 7 new T24 tests account for delta) |
| AC9 | reportlab lazy import | ✅ PASS | All `reportlab.*` imports are **inside** `generate_patient_summary_pdf()` body — zero top-level import cost; app startup unaffected if reportlab is absent |
| AC10 | No code duplication | ✅ PASS | `get_patient_summary_pdf` calls `summary_svc.build_summary()` then `summary.model_dump()` — identical data path to the JSON summary endpoint; no separate query chains |

---

### P2 Warnings

**P2-1 — No `ImportError` fallback in `generate_patient_summary_pdf`**

`reportlab` imports are lazy (inside the function — satisfies AC9 startup cost concern), but there is no `try/except ImportError` guard. If `reportlab` is somehow absent from the environment at call time, the caller receives an unhandled `ImportError` rather than a clean HTTP 500 with a diagnostic message.

```python
# Current (no guard)
def generate_patient_summary_pdf(...) -> bytes:
    from reportlab.lib import colors
    ...

# Suggested improvement
def generate_patient_summary_pdf(...) -> bytes:
    try:
        from reportlab.lib import colors
        ...
    except ImportError as exc:
        raise RuntimeError(
            "reportlab is required for PDF generation. "
            "Install it with: pip install 'reportlab>=4.0'"
        ) from exc
```

Since `reportlab>=4.0` is declared in `requirements.txt` and is already installed in the venv, this is a minor hardening concern — not a blocker.

---

### Summary

T24 is a clean, focused implementation. The new `GET /{patient_id}/summary.pdf` endpoint correctly reuses the existing `patient_summary.build_summary()` aggregation service (no data duplication), enforces the same RBAC pattern established across the patient routes, and delegates PDF rendering entirely to the new `pdf_report` service. The reportlab imports are properly lazy, keeping server startup fast and decoupled from the PDF library.

All 7 new tests cover the required scenarios — RBAC gating (DOCTOR+consent, PATIENT block, AI_SERVICE block, ADMIN bypass), content-type, PDF header signature, Content-Disposition filename format, and unauthenticated access. The mock-based approach correctly isolates RBAC from rendering.

The single P2 warning (no `ImportError` catch in the service function) is a minor hardening suggestion with no impact on the current environment. No security issues identified.

**APPROVE — T24 may proceed to merge.**

---

*Reviewed by:* Codex (read-only)
*Branch:* `feature/t24-pdf-export`
*Reviewed at:* 2026-06-18
*Test run:* `python -m pytest tests/ -p no:warnings` → 502 passed, 1 skipped
