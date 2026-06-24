# Patient App V1 — Full Design Implementation Roadmap

**Source of truth:** `frontend/design-reference/metocare-app-interface-design/project/MetoCare Patient App.dc.html`
**Canonical screen count:** 57 (`data-screen-label`, sections B1–B9)
**Audit date:** 2026-06-24

## Status summary (by design screen)

| | Count | of 57 |
|---|---|---|
| ✅ Implemented (route exists + Soft-UI reskin + matches design) | 5 | **9%** |
| 🟡 Partial (route exists but old style / collapsed / different model) | 16 | 28% |
| ❌ Missing (no equivalent screen) | 36 | 63% |

- **Strict design completion: 5 / 57 (~9%).**
- With the 4 reskinned "showcase" routes counted as screens: **9 / 61 (~15%)**.
- Weighted (partials at 50%): **~23%**.

> ⚠️ PR #54 = **existing-route Soft-UI reskin + official logo system**, NOT "Patient App V1 design complete". Batches 1–9 were route reskins of a subset; they did not implement the full 57-screen design. Remaining screens are **future epics, many backend-blocked**.

Showcase routes reskinned (not in the B-numbered set): Dashboard (Trang chủ), Chỉ số (metrics list), Xét nghiệm (labs list), Trợ lý AI (AI chat).

## Legend
- **Status:** ✅ done · 🟡 partial · ❌ missing
- **BE:** 🔒 backend-blocked / new API needed · 🖥️ native/OS-only · — UI-only
- **Priority:** P0 onboarding+auth+metrics-entry · P1 meds-adherence+nutrition+reports/caregiver · P2 notifications/streak+fitness

## 57-screen matrix

### B1 — Intro / onboarding (0/5)
| ID | Screen | Status | BE | Priority | Notes |
|---|---|---|---|---|---|
| B1-01 | Splash | ❌ | — | P0 | no splash route |
| B1-02 | Carousel 1 | ❌ | — | P0 | intro carousel not built |
| B1-03 | Carousel 2 | ❌ | — | P0 | |
| B1-04 | Carousel 3 | ❌ | — | P0 | |
| B1-05 | Permission priming (Mồi quyền) | ❌ | — | P0 | |

### B2 — Auth (0/5)
| ID | Screen | Status | BE | Priority | Notes |
|---|---|---|---|---|---|
| B2-01 | Số điện thoại (phone) | 🟡 | 🔒 | P0 | app login is email/phone+password, not phone-first SMS-OTP; reskinned |
| B2-02 | OTP | 🟡 | 🔒 | P0 | app has TOTP MFA, not SMS OTP; SMS OTP needs backend |
| B2-03 | Chọn vai trò (role select) | ❌ | — | P0 | role derived from account; no picker |
| B2-04 | Rẽ nhánh cũ/mới (login vs create) | 🟡 | — | P0 | login/register split exists, reskinned |
| B2-05 | Đồng thuận dữ liệu (consent) | 🟡 | — | P0 | `/consents` exists, NOT reskinned (old style) |

### B3 — Clinical onboarding (0/9)
| ID | Screen | Status | BE | Priority | Notes |
|---|---|---|---|---|---|
| B3-01 | Thông tin cơ bản | 🟡 | — | P0 | `/onboarding` (single page, old) collects some of this |
| B3-02 | Bệnh lý (conditions) | ❌ | — | P0 | |
| B3-03 | Chẩn đoán & thuốc | ❌ | — | P0 | |
| B3-03b | Kết quả xét nghiệm | ❌ | — | P0 | |
| B3-04 | Ngưỡng mục tiêu (targets) | ❌ | 🔒 | P0 | target-range API |
| B3-05 | Liên kết bác sĩ | ❌ | 🔒 | P0 | doctor-link API |
| B3-06 | Kết nối thiết bị | ❌ | 🔒 | P0 | device integration — none |
| B3-07 | Chỉ số nền (baseline) | ❌ | — | P0 | |
| B3-08 | Hoàn tất (complete) | ❌ | — | P0 | |

### B4 — Metric entry & detail (1/10)
| ID | Screen | Status | BE | Priority | Notes |
|---|---|---|---|---|---|
| B4-01 | Trang chủ rỗng (empty home) | 🟡 | — | P0 | dashboard empty state exists (reskinned) |
| B4-02 | Ghi chỉ số sheet (log bottom sheet) | 🟡 | — | P0 | `/metrics/log` exists, old modal |
| B4-03 | Nhập đường huyết (log glucose) | 🟡 | — | P0 | collapsed into one generic modal |
| B4-03b | Phiếu xét nghiệm (lab slip) | 🟡 | — | P0 | `/labs/upload` covers loosely |
| B4-04 | Nhập huyết áp (log BP) | ❌ | — | P0 | no dedicated per-metric screen |
| B4-05 | Nhập cân nặng (log weight) | ❌ | — | P0 | |
| B4-06 | Chi tiết chỉ số (metric detail) | ✅ | — | — | `/metrics/[metricType]` reskinned |
| B4-07 | Cảnh báo nguy hiểm (danger alert) | ❌ | — | P0 | |
| B4-08 | Đang tải (loading) | 🟡 | — | — | shared neu skeleton (not a screen) |
| B4-09 | Lỗi kết nối (error) | 🟡 | — | — | shared neu error (not a screen) |

### B5 — Medications (1/4)
| ID | Screen | Status | BE | Priority | Notes |
|---|---|---|---|---|---|
| B5-01 | Lịch uống thuốc (daily schedule + adherence) | 🟡 | 🔒 | P1 | app shows med LIST; daily-schedule/adherence ring needs adherence API |
| B5-02 | Chi tiết thuốc (med detail) | ✅ | — | — | `/medications/[id]` reskinned |
| B5-03 | Thêm/sửa thuốc (add/edit) | 🟡 | — | P1 | modal (old style) |
| B5-04 | Tuân thủ (adherence history) | ❌ | 🔒 | P1 | adherence API — none |

### B6 — Meals / Doctors / Messaging / Appointments (0/7)
| ID | Screen | Status | BE | Priority | Notes |
|---|---|---|---|---|---|
| B6-01 | Nhật ký bữa ăn (meal log) | 🟡 | — | P1 | `/nutrition` exists, NOT reskinned |
| B6-02 | Ghi bữa ăn (log meal) | 🟡 | — | P1 | |
| B6-03 | Gợi ý thực đơn AI | ❌ | 🔒 | P2 | AI gated off |
| B6-04 | Danh sách bác sĩ (doctors list) | ❌ | 🔒 | P1 | care-team API |
| B6-05 | Hồ sơ bác sĩ (doctor profile) | ❌ | 🔒 | P1 | |
| B6-06 | Nhắn tin bác sĩ (messaging) | ❌ | 🔒 | P1 | patient↔doctor messaging — none |
| B6-07 | Đặt lịch tái khám (appointment) | ❌ | 🔒 | P1 | appointment booking — none |

### B7 — Report / Caregiver / Profile / Settings (2/7)
| ID | Screen | Status | BE | Priority | Notes |
|---|---|---|---|---|---|
| B7-01 | Báo cáo sức khoẻ (health report PDF) | ❌ | 🔒 | P1 | report generation |
| B7-02 | Caregiver (sharing) | ❌ | 🔒 | P1 | caregiver-share API |
| B7-03 | Trang cá nhân (profile) | ✅ | — | — | `/profile` reskinned |
| B7-04 | Cài đặt thông báo (notification settings) | ✅ | — | — | `/settings` reskinned |
| B7-05 | Trợ năng (accessibility) | ❌ | — | P2 | toggles need persistence backend |
| B7-06 | Thiết bị (connected devices) | ❌ | 🔒 | P2 | device integration |
| B7-07 | Quyền riêng tư (privacy & data) | 🟡 | — | P1 | `/consents` exists, NOT reskinned |

### B8 — Notifications (1/3)
| ID | Screen | Status | BE | Priority | Notes |
|---|---|---|---|---|---|
| B8-01 | Trung tâm thông báo (notification center) | ✅ | — | — | `/notifications` reskinned |
| B8-02 | Push màn khoá (lock-screen push) | ❌ | 🖥️ | P2 | OS-native, not a web screen |
| B8-03 | Chuỗi ngày (streak) | ❌ | 🔒 | P2 | streak/gamification data |

### B9 — Exercise / Fitness module (0/7)
| ID | Screen | Status | BE | Priority | Notes |
|---|---|---|---|---|---|
| B9-01 | Kiểm tra an toàn trước khi tập | ❌ | 🔒 | P2 | entire fitness feature absent |
| B9-02 | Tổng quan vận động | ❌ | 🔒 | P2 | |
| B9-03 | Thư viện bài tập | ❌ | 🔒 | P2 | |
| B9-04 | Chi tiết bài tập | ❌ | 🔒 | P2 | |
| B9-05 | Phiên tập (workout session) | ❌ | 🔒 | P2 | |
| B9-06 | Hoàn thành phiên | ❌ | 🔒 | P2 | |
| B9-07 | Lịch tập tuần | ❌ | 🔒 | P2 | |

## Brand-asset gap (from logo-system handoff Part 3)
Derived nav-icon set does not map to the live nav (no **Xét nghiệm** / **Thuốc** icon). Need official icons for those two before any nav-icon swap. Current Lucide nav icons retained.

## Epics & priority rollup
- **P0 — Onboarding + Auth + Metrics entry** (B1, B2, B3, B4 entry screens): ~24 screens. Mostly UI; some 🔒 (SMS-OTP, targets, doctor-link, devices).
- **P1 — Meds adherence + Nutrition + Reports/Caregiver + Care-team** (B5-01/04, B6-01/02/04/05/06/07, B7-01/02/07): ~12 screens. Heavily 🔒 (adherence, messaging, appointments, report, caregiver APIs).
- **P2 — Notifications/Streak + Fitness + Accessibility/Devices** (B7-05/06, B8-02/03, B9 ×7): ~11 screens. Mostly 🔒 / native; B9 is a whole new feature module.

## Remaining work estimate
- **52 screens** outstanding (36 missing + 16 partial upgrades).
- **UI-only (no backend):** ~10 (B2 consent/role, B3 flow, B4 per-metric log + danger, B6-01/02 nutrition, B7-07 consents).
- **Backend-blocked / new feature:** ~35 (B5 adherence, B6 care-team/messaging/appointments, B7 report/caregiver/devices, B8 streak, B9 fitness, B6-03 AI, B3 device/doctor-link).
- **Native/OS:** 1 (B8-02 push).
