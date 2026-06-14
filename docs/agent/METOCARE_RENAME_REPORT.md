# MetoCare Rename Report (Task: METOCARE-RENAME-1)

> Tác giả: Claude Code · Ngày: 2026-06-14 · Branch: `chore/metocare-rename` (từ `main`)
> Phạm vi: **chỉ rename references trong docs**. KHÔNG đụng code, package, DB tables, imports.

---

## 1. Files updated (with line refs)

| File | Line(s) | Before → After |
|------|---------|----------------|
| `README.md` | 1 | `# Metabolic Care Platform (MCP)` → `# MetoCare` |
| `README.md` | (mới, sau badge) | + product definition (verbatim, xem §2) |
| `docs/AI_Safety_Guardrail.md` | 1 | `# AI Safety Guardrail — Metabolic Care Platform` → `# AI Safety Guardrail — MetoCare` |
| `docs/Architecture_Doctrine.md` | 1 | `# Architecture Doctrine — Metabolic Care Platform (MCP)` → `# Architecture Doctrine — MetoCare (MCP)` |
| `docs/Architecture_Doctrine.md` | 9 | `...cho Metabolic Care Platform — nền tảng...` → `...cho MetoCare — nền tảng...` |
| `docs/BRD.md` | 1 | `... (BRD) — Metabolic Care Platform` → `... (BRD) — MetoCare` |
| `docs/Data_Model_Overview.md` | 1 | `Data Model Overview — Metabolic Care Platform` → `... — MetoCare` |
| `docs/DevEnv_Hardening_Plan.md` | 1 | `DevEnv Hardening Plan — Metabolic Care Platform` → `... — MetoCare` |
| `docs/MVP_Scope_and_Roadmap.md` | 1 | `MVP Scope & Roadmap — Metabolic Care Platform` → `... — MetoCare` |
| `docs/Product_Module_Map.md` | 1 | `Product Module Map — Metabolic Care Platform` → `... — MetoCare` |
| `docs/Security_Compliance_Framework.md` | 1 | `Security & Compliance Framework — Metabolic Care Platform` → `... — MetoCare` |
| `docs/Sprint0_Execution_Blueprint.md` | 1 | `Sprint 0 Execution Blueprint — Metabolic Care Platform` → `... — MetoCare` |
| `docs/Technical_Architecture.md` | 1 | `Technical Architecture — Metabolic Care Platform` → `... — MetoCare` |
| `docs/Technical_Architecture.md` | 27 | mermaid node `SYS[Metabolic Care Platform]` → `SYS[MetoCare]` |

**Tổng: 12 file, 14 vị trí (13 thay tên + 1 thêm product definition).**

## 2. Product definition added (README, verbatim)

> MetoCare is an AI-assisted metabolic health care platform connecting personal health data, lab interpretation, medical safety guardrails, and doctor/clinic workflows.

## 3. References changed (tóm tắt)

- Title (H1) của README + 10 design docs hiện hành → "MetoCare".
- 1 intro line (Architecture_Doctrine §9) và 1 mermaid label (Technical_Architecture) → "MetoCare".
- Cấu trúc kỹ thuật, nội dung body, sơ đồ khác giữ nguyên (no cosmetic rewrite).

## 4. References intentionally NOT changed

| Mục | Lý do |
|-----|-------|
| `app/`, `backend/`, module paths | Yêu cầu: KHÔNG rename package/module (tránh break imports). |
| DB tables, model class names | Yêu cầu: KHÔNG rename DB tables. |
| `docs/agent/*` (Sprint 0, P1, P2 handoffs, discovery, execution plan) | Historical reports — phản ánh trạng thái lúc viết; không sửa lịch sử. |
| `docs/AI_Safety_Guardrail.md:137` | Đây là **bản mirror nguyên văn** của `SYSTEM_SAFETY_PROMPT_VI` trong `app/domain/policies.py`. Đổi tên trong doc mà không đổi code sẽ gây phân kỳ doc↔code, và đổi prompt là **thay đổi code/medical-safety** (ngoài scope docs-only). → Giữ nguyên, đồng bộ với code. |
| Viết tắt "MCP" (xuyên suốt body docs) | Giữ làm shorthand nội bộ (tránh mass rewrite). Không phải tên hiển thị sản phẩm. |
| `app_name` setting / API title trong code | Là code — ngoài scope Task 1 (docs-only). |

## 5. Import / package rename decision

**NONE.** Toàn bộ package/module paths, imports, class names, DB tables, code giữ nguyên 100%.
Đây là rename **chỉ ở tầng tài liệu hiển thị**. Đổi tên code/brand trong `app_name`, system prompt,
API title → đề xuất làm ở task code riêng nếu PTH muốn brand đồng bộ vào runtime.

## 6. Test results sau rename (actual output)

```
pytest:                 130 passed, 1 skipped, 1 warning   (không đổi — docs-only)
ruff check:             All checks passed!
compileall:             OK
docker-compose config:  VALID
```
Docs-only → không ảnh hưởng code/test; chạy đầy đủ để xác nhận không có regression.

## 7. Limitations / Notes

- Brand "MetoCare" hiện chỉ ở docs hiển thị; **runtime/code vẫn dùng "Metabolic Care Platform"** (app_name,
  system safety prompt, API description). Đồng bộ brand vào code là task riêng (cần đụng code + cân nhắc
  medical-safety prompt) — chưa làm trong Task 1.
- "MCP" abbreviation giữ nguyên trong docs body.
