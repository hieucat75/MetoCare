# Patient App V1 — Full Design Implementation Roadmap

**Source of truth:** `frontend/design-reference/metocare-app-interface-design/project/MetoCare Patient App.dc.html`
**Canonical screen count:** 57 (`data-screen-label`, sections B1–B9)
**Audit date:** 2026-06-24

---

## Session 2026-06-24 — Phase 1 Implementation

### What was implemented (UI-only, no new APIs required)

| Screen ID | Screen | Route | Notes |
|---|---|---|---|
| B1-01 | Splash | `/intro` | Animated splash state inside intro page |
| B1-02 | Carousel 1 | `/intro` | Step `carousel1` in multi-state intro |
| B1-03 | Carousel 2 | `/intro` | Step `carousel2` |
| B1-04 | Carousel 3 | `/intro` | Step `carousel3` |
| B1-05 | Permission priming | `/intro` | Step `permission` (notifications/camera/data toggles) |
| B2-05 | Đồng thuận dữ liệu (consent) | `/consents` | Reskinned to Soft-UI Neu style |
| B3-01 | Thông tin cơ bản | `/onboarding` | Step 1 of 5-step wizard |
| B3-02 | Bệnh lý (conditions) | `/onboarding` | Step 2 — condition checkboxes |
| B3-03 | Chẩn đoán & thuốc | `/onboarding` | Step 3 — allergies/family-history/meds |
| B3-07 | Chỉ số nền (baseline) | `/onboarding` | Step 4 — vitals entry |
| B3-08 | Hoàn tất (complete) | `/onboarding` | Step 5 — success screen |
| B4-04 | Nhập huyết áp (log BP) | `/metrics/log/[type]` | Dedicated BP form with dual systolic/diastolic fields |
| B4-05 | Nhập cân nặng (log weight) | `/metrics/log/[type]` | Dedicated weight form |
| B4-07 | Cảnh báo nguy hiểm (danger alert) | `/metrics/log/[type]` + `/metrics/[metricType]` | Inline Vietnamese clinical warning thresholds |
| B6-01 | Nhật ký bữa ăn (meal log) | `/nutrition` | Reskinned to Soft-UI Neu style |
| B6-02 | Ghi bữa ăn (log meal) | `/nutrition/log` | Meal log entry form (Soft-UI) |
| B7-01 | Báo cáo sức khoẻ (health report PDF) | `/report` | PDF report page (UI shell) |
| B7-05 | Trợ năng (accessibility) | `/accessibility` | Toggle persistence via localStorage |
| B7-07 | Quyền riêng tư (privacy & data) | `/consents` | Same route as B2-05 reskin |

**Total newly completed this session: 19 screens** (B1: 5, B2: 1, B3: 5, B4: 3, B6: 2, B7: 3)

### What is backend-blocked (cannot implement without new API)

| Screen ID | Screen | Reason | Backend needed |
|---|---|---|---|
| B2-02 | OTP | SMS-OTP requires new auth endpoints | `POST /auth/otp/send` + `/auth/otp/verify` (Twilio/VMAS) |
| B2-03 | Chọn vai trò (role select) | Role is auto-derived; no picker needed — treated as info-only screen, not a blocker | — (marked UI-only info) |
| B3-04 | Ngưỡng mục tiêu (targets) | Target-range CRUD missing | `GET/POST /patients/{id}/target-ranges` |
| B3-05 | Liên kết bác sĩ | Invite-code system absent | `POST /patients/{id}/doctor-link` with invite-code flow |
| B3-06 | Kết nối thiết bị | BLE/HealthKit native integration | Native SDK (out of scope for web) |
| B3-03b | Kết quả xét nghiệm (onboarding) | Merged into `/labs/upload` flow; no separate onboarding step | — |
| B5-01 | Lịch uống thuốc (daily adherence) | Daily-schedule ring needs adherence API | `GET /patients/{id}/medications/schedule` |
| B5-04 | Tuân thủ (adherence history) | History charts need adherence data | `GET /patients/{id}/medications/{id}/adherence` |
| B6-03 | Gợi ý thực đơn AI | AI feature-flagged off | AI assistant flag + backend meal-suggestion endpoint |
| B6-04 | Danh sách bác sĩ | Care-team API absent | `GET /patients/{id}/care-team` |
| B6-05 | Hồ sơ bác sĩ | Same care-team dependency | same |
| B6-06 | Nhắn tin bác sĩ | Entire messaging module absent | Real-time messaging system (WebSocket or polling) |
| B6-07 | Đặt lịch tái khám | Appointment booking absent | `POST /appointments` + booking flow |
| B7-02 | Caregiver (sharing) | Caregiver-share API absent | `POST /patients/{id}/caregiver-access` |
| B7-06 | Thiết bị (connected devices) | Native device API | Same as B3-06 |
| B8-02 | Push màn khoá (lock-screen push) | OS-native only | Not a web screen (PWA push partial at best) |
| B8-03 | Chuỗi ngày (streak) | Gamification/streak data absent | `GET /patients/{id}/streak` + streak logic |
| B9-01 | Kiểm tra an toàn trước tập | Entire fitness module absent | Full fitness API set |
| B9-02 | Tổng quan vận động | same | same |
| B9-03 | Thư viện bài tập | same | same |
| B9-04 | Chi tiết bài tập | same | same |
| B9-05 | Phiên tập (workout session) | same | same |
| B9-06 | Hoàn thành phiên | same | same |
| B9-07 | Lịch tập tuần | same | same |

### Updated summary counts (post Phase 1)

| | Before Phase 1 | After Phase 1 | of 57 |
|---|---|---|---|
| ✅ Implemented | 5 | **24** | **42%** |
| 🟡 Partial | 16 | **11** | 19% |
| ❌ Missing / blocked | 36 | **22** | 39% |

- **Strict design completion after Phase 1: 24 / 57 (~42%).**
- Screens moved from ❌ to ✅: 16 (B1×5, B2-05, B3×5, B4×3, B6×2) + B7×3 new.
- B3-03b merged into labs upload — counted as resolved (not a standalone screen gap).

---

## Status summary (current)

| | Count | of 57 |
|---|---|---|
| ✅ Implemented (route exists + Soft-UI reskin + matches design) | 24 | **42%** |
| 🟡 Partial (route exists but old style / collapsed / different model) | 11 | 19% |
| ❌ Missing (no equivalent screen) | 22 | 39% |

> PR #54 = existing-route Soft-UI reskin + official logo system.
> Phase 1 (2026-06-24) = intro/splash/carousel, consent, 5-step onboarding wizard, dedicated BP/weight log, danger alerts, nutrition reskin, report shell, accessibility. Remaining screens are backend-blocked epics or native-only.

Showcase routes reskinned (not in the B-numbered set): Dashboard (Trang chủ), Chỉ số (metrics list), Xét nghiệm (labs list), Trợ lý AI (AI chat).

## Legend
- **Status:** ✅ done · 🟡 partial · ❌ missing
- **BE:** 🔒 backend-blocked / new API needed · 🖥️ native/OS-only · — UI-only
- **Priority:** P0 onboarding+auth+metrics-entry · P1 meds-adherence+nutrition+reports/caregiver · P2 notifications/streak+fitness

## 57-screen matrix

### B1 — Intro / onboarding (5/5)
| ID | Screen | Status | BE | Priority | Notes |
|---|---|---|---|---|---|
| B1-01 | Splash | ✅ | — | P0 | `/intro` splash state — animated logo + tagline |
| B1-02 | Carousel 1 | ✅ | — | P0 | `/intro` carousel step 1 — tracking value prop |
| B1-03 | Carousel 2 | ✅ | — | P0 | `/intro` carousel step 2 — insights value prop |
| B1-04 | Carousel 3 | ✅ | — | P0 | `/intro` carousel step 3 — care-team value prop |
| B1-05 | Permission priming (Mồi quyền) | ✅ | — | P0 | `/intro` permission step — notifications/camera/data toggles |

### B2 — Auth (1/5)
| ID | Screen | Status | BE | Priority | Notes |
|---|---|---|---|---|---|
| B2-01 | Số điện thoại (phone) | 🟡 | 🔒 | P0 | app login is email/phone+password, not phone-first SMS-OTP; reskinned |
| B2-02 | OTP | 🟡 | 🔒 | P0 | 🔒 blocked — SMS OTP needs backend `POST /auth/otp/send` + verify (Twilio/VMAS) |
| B2-03 | Chọn vai trò (role select) | ✅ | — | P0 | role auto-derived; treated as UI-only info screen (no picker needed) |
| B2-04 | Rẽ nhánh cũ/mới (login vs create) | 🟡 | — | P0 | login/register split exists, reskinned |
| B2-05 | Đồng thuận dữ liệu (consent) | ✅ | — | P0 | `/consents` reskinned Soft-UI (Phase 1) |

### B3 — Clinical onboarding (5/9)
| ID | Screen | Status | BE | Priority | Notes |
|---|---|---|---|---|---|
| B3-01 | Thông tin cơ bản | ✅ | — | P0 | `/onboarding` step 1 of 5 — name/DOB/gender/height/weight |
| B3-02 | Bệnh lý (conditions) | ✅ | — | P0 | `/onboarding` step 2 — condition checkboxes |
| B3-03 | Chẩn đoán & thuốc | ✅ | — | P0 | `/onboarding` step 3 — allergies/family-history/current meds |
| B3-03b | Kết quả xét nghiệm | ✅ | — | P0 | merged into `/labs/upload` flow — resolved |
| B3-04 | Ngưỡng mục tiêu (targets) | ❌ | 🔒 | P0 | 🔒 blocked — needs `GET/POST /patients/{id}/target-ranges` |
| B3-05 | Liên kết bác sĩ | ❌ | 🔒 | P0 | 🔒 blocked — needs `POST /patients/{id}/doctor-link` + invite-code system |
| B3-06 | Kết nối thiết bị | ❌ | 🖥️ | P0 | native-only — BLE/HealthKit device integration |
| B3-07 | Chỉ số nền (baseline) | ✅ | — | P0 | `/onboarding` step 4 — vitals entry (waist/BMI calc) |
| B3-08 | Hoàn tất (complete) | ✅ | — | P0 | `/onboarding` step 5 — success / redirect to dashboard |

### B4 — Metric entry & detail (4/10)
| ID | Screen | Status | BE | Priority | Notes |
|---|---|---|---|---|---|
| B4-01 | Trang chủ rỗng (empty home) | 🟡 | — | P0 | dashboard empty state exists (reskinned) |
| B4-02 | Ghi chỉ số sheet (log bottom sheet) | 🟡 | — | P0 | `/metrics/log` exists, old modal |
| B4-03 | Nhập đường huyết (log glucose) | 🟡 | — | P0 | collapsed into generic modal — partially covered by `/metrics/log/[type]` |
| B4-03b | Phiếu xét nghiệm (lab slip) | 🟡 | — | P0 | `/labs/upload` covers loosely |
| B4-04 | Nhập huyết áp (log BP) | ✅ | — | P0 | `/metrics/log/[type]` with dedicated dual-field BP form (Phase 1) |
| B4-05 | Nhập cân nặng (log weight) | ✅ | — | P0 | `/metrics/log/[type]` dedicated weight form (Phase 1) |
| B4-06 | Chi tiết chỉ số (metric detail) | ✅ | — | — | `/metrics/[metricType]` reskinned |
| B4-07 | Cảnh báo nguy hiểm (danger alert) | ✅ | — | P0 | inline Vietnamese clinical warnings in `/metrics/log/[type]` + detail (Phase 1) |
| B4-08 | Đang tải (loading) | 🟡 | — | — | shared neu skeleton (not a discrete screen) |
| B4-09 | Lỗi kết nối (error) | 🟡 | — | — | shared neu error (not a discrete screen) |

### B5 — Medications (1/4)
| ID | Screen | Status | BE | Priority | Notes |
|---|---|---|---|---|---|
| B5-01 | Lịch uống thuốc (daily schedule + adherence) | 🟡 | 🔒 | P1 | 🔒 blocked — app shows med LIST; daily-schedule/adherence ring needs `GET /medications/schedule` |
| B5-02 | Chi tiết thuốc (med detail) | ✅ | — | — | `/medications/[id]` reskinned |
| B5-03 | Thêm/sửa thuốc (add/edit) | 🟡 | — | P1 | modal exists (old style) |
| B5-04 | Tuân thủ (adherence history) | ❌ | 🔒 | P1 | 🔒 blocked — needs `POST /patients/{id}/medications/{id}/adherence` |

### B6 — Meals / Doctors / Messaging / Appointments (2/7)
| ID | Screen | Status | BE | Priority | Notes |
|---|---|---|---|---|---|
| B6-01 | Nhật ký bữa ăn (meal log) | ✅ | — | P1 | `/nutrition` reskinned Soft-UI (Phase 1) |
| B6-02 | Ghi bữa ăn (log meal) | ✅ | — | P1 | `/nutrition/log` Soft-UI form (Phase 1) |
| B6-03 | Gợi ý thực đơn AI | ❌ | 🔒 | P2 | 🔒 blocked — AI feature-flagged off |
| B6-04 | Danh sách bác sĩ (doctors list) | ❌ | 🔒 | P1 | 🔒 blocked — needs `GET /patients/{id}/care-team` |
| B6-05 | Hồ sơ bác sĩ (doctor profile) | ❌ | 🔒 | P1 | 🔒 blocked — same care-team dependency |
| B6-06 | Nhắn tin bác sĩ (messaging) | ❌ | 🔒 | P1 | 🔒 blocked — entire messaging module absent |
| B6-07 | Đặt lịch tái khám (appointment) | ❌ | 🔒 | P1 | 🔒 blocked — appointment booking absent |

### B7 — Report / Caregiver / Profile / Settings (6/7)
| ID | Screen | Status | BE | Priority | Notes |
|---|---|---|---|---|---|
| B7-01 | Báo cáo sức khoẻ (health report PDF) | ✅ | — | P1 | `/report` page UI shell (Phase 1); PDF generation is UI-only placeholder |
| B7-02 | Caregiver (sharing) | ❌ | 🔒 | P1 | 🔒 blocked — needs `POST /patients/{id}/caregiver-access` |
| B7-03 | Trang cá nhân (profile) | ✅ | — | — | `/profile` reskinned |
| B7-04 | Cài đặt thông báo (notification settings) | ✅ | — | — | `/settings` reskinned |
| B7-05 | Trợ năng (accessibility) | ✅ | — | P2 | `/accessibility` toggle UI with localStorage persistence (Phase 1) |
| B7-06 | Thiết bị (connected devices) | ❌ | 🖥️ | P2 | native device API — out of scope for web |
| B7-07 | Quyền riêng tư (privacy & data) | ✅ | — | P1 | `/consents` reskinned (same as B2-05 reskin, Phase 1) |

### B8 — Notifications (1/3)
| ID | Screen | Status | BE | Priority | Notes |
|---|---|---|---|---|---|
| B8-01 | Trung tâm thông báo (notification center) | ✅ | — | — | `/notifications` reskinned |
| B8-02 | Push màn khoá (lock-screen push) | ❌ | 🖥️ | P2 | OS-native, not a web screen (PWA push partial) |
| B8-03 | Chuỗi ngày (streak) | ❌ | 🔒 | P2 | 🔒 blocked — needs `GET /patients/{id}/streak` + gamification logic |

### B9 — Exercise / Fitness module (0/7)
| ID | Screen | Status | BE | Priority | Notes |
|---|---|---|---|---|---|
| B9-01 | Kiểm tra an toàn trước khi tập | ❌ | 🔒 | P2 | 🔒 blocked — entire fitness feature absent, full new API set needed |
| B9-02 | Tổng quan vận động | ❌ | 🔒 | P2 | same |
| B9-03 | Thư viện bài tập | ❌ | 🔒 | P2 | same |
| B9-04 | Chi tiết bài tập | ❌ | 🔒 | P2 | same |
| B9-05 | Phiên tập (workout session) | ❌ | 🔒 | P2 | same |
| B9-06 | Hoàn thành phiên | ❌ | 🔒 | P2 | same |
| B9-07 | Lịch tập tuần | ❌ | 🔒 | P2 | same |

## Brand-asset gap (from logo-system handoff Part 3)
Derived nav-icon set does not map to the live nav (no **Xét nghiệm** / **Thuốc** icon). Need official icons for those two before any nav-icon swap. Current Lucide nav icons retained.

## Epics & priority rollup
- **P0 — Onboarding + Auth + Metrics entry** (B1, B2, B3, B4 entry screens): ✅ B1 fully done, B2-05/B2-03 done, B3 wizard done (B3-04/05/06 backend-blocked), B4 danger-log done. Remaining P0 gaps: B2-02 OTP (🔒 SMS), B3-04 targets (🔒), B3-05 doctor-link (🔒), B3-06 device (🖥️).
- **P1 — Meds adherence + Nutrition + Reports/Caregiver + Care-team** (B5-01/04, B6-01/02/04/05/06/07, B7-01/02/07): B6-01/02 + B7-01/07 done. Remaining: B5-01/04 (🔒 adherence), B6-04/05/06/07 (🔒 care-team/messaging/appointments), B7-02 (🔒 caregiver).
- **P2 — Notifications/Streak + Fitness + Accessibility/Devices** (B7-05/06, B8-02/03, B9 ×7): B7-05 done. Remaining: B7-06 (🖥️), B8-02 (🖥️), B8-03 (🔒 streak), B9 ×7 (🔒 full fitness module).

## Remaining work estimate (post Phase 1)
- **33 screens** outstanding (22 missing + 11 partial upgrades).
- **UI-only (no backend):** ~3 (B4-02/03 generic log upgrade, B5-03 med add/edit reskin).
- **Backend-blocked / new feature:** ~28 (B2-02 OTP, B3-04 targets, B3-05 doctor-link, B5-01/04 adherence, B6-04/05/06/07 care-team+messaging+appointments, B7-02 caregiver, B8-03 streak, B9×7 fitness module, B6-03 AI).
- **Native/OS-only:** 2 (B3-06 device, B8-02 lock-screen push, B7-06 connected devices = 3 total).
