# Meto AI — Future Roadmap (24 Tháng)

> **Phiên bản:** 1.0 | **Ngày:** 2026-06-30 | **Trạng thái:** Approved

---

## Tổng quan

Tài liệu này định nghĩa roadmap 24 tháng cho Meto AI Platform — từ nền tảng chat ban đầu đến AI Health Companion Platform đầy đủ tính năng. Mỗi phase có gate criteria rõ ràng: phase sau không bắt đầu cho đến khi phase trước đạt tất cả gates.

**Triết lý phát triển:**
- **User value first:** Mỗi phase phải cải thiện rõ ràng trải nghiệm người dùng
- **Safety before features:** Không ship features mới nếu safety metrics xấu đi
- **Measure everything:** Mỗi phase có KPIs cụ thể để đo thành công
- **Medical caution:** Features liên quan y tế cần review bổ sung trước ship

**Status hôm nay:** Phase 1 đã được thiết kế (tài liệu 00–13). Bắt đầu implementation tháng 7/2026.

---

## Phase 1 — Foundation (Tháng 1–2)
### Chủ đề: Chat + Context

**Business Value:**
Đặt nền tảng cho toàn bộ platform. Người dùng MetoCare lần đầu có thể trò chuyện với AI hiểu hoàn toàn hồ sơ sức khỏe của họ — không phải chatbot generic.

**Deliverables:**

| Feature | Complexity | Priority |
|---------|-----------|---------|
| Core chatbot (text Q&A) | M | P0 |
| 9 context blocks (Context Engine) | L | P0 |
| Meto Aura UI (floating button, chat panel) | M | P0 |
| Quick prompts per screen | S | P0 |
| Safety guardrails + red flag detection | M | P0 |
| Audit logging (metadata only) | S | P0 |
| Consent modal + consent gating | S | P0 |
| SSE streaming responses | M | P0 |
| AI provider abstraction (Claude primary, OpenAI fallback) | M | P0 |
| Conversation persistence (DB) | S | P1 |
| Basic conversation history UI | S | P1 |
| Staging deploy (Azure Container Apps) | M | P0 |
| Smoke tests + safety test suite | M | P0 |

**Technical Dependencies:**
- PostgreSQL schema finalized
- Redis deployed (Azure Cache for Redis)
- Claude API key configured
- OpenAI API key configured (fallback)
- Azure Container Apps environment ready
- JWT auth working for all AI endpoints

**Estimated Complexity:** L (2 engineers, 8 weeks)

**Risks:**
| Rủi ro | Mức độ | Mitigation |
|-------|-------|-----------|
| Context assembly performance | HIGH | Cache strategy (Redis), load test trước ship |
| Claude rate limits | MEDIUM | Fallback to OpenAI, honor Retry-After |
| Safety guardrails miss edge cases | HIGH | Extensive test suite, conservative approach |
| User không trust AI health info | MEDIUM | Clear disclaimer, bác sĩ escalation luôn visible |
| Data leak qua cross-user context | CRITICAL | RLS + parameterized queries + security audit |

**Success Metrics:**
- [ ] 1,000 conversations trong tuần đầu (nếu GA)
- [ ] Session completion rate > 80%
- [ ] Zero cross-user data access incidents
- [ ] P95 TTFT < 3,000ms
- [ ] Safety escalation rate: detects 100% of test red flags

**Gate Criteria (Sang Phase 2):**
- [ ] Session completion rate > 80% duy trì 2 tuần
- [ ] Error rate < 1% trong 7 ngày liên tiếp
- [ ] Zero severity-1 security incidents
- [ ] CSAT > 70% (minimum viable satisfaction)
- [ ] P95 TTFT < 3,000ms duy trì 7 ngày
- [ ] Safety test suite: 100% pass rate
- [ ] Code review hoàn chỉnh cho toàn bộ AI codebase
- [ ] Load test: 100 concurrent users không degradation

---

## Phase 2 — Intelligence (Tháng 3–4)
### Chủ đề: Tools + Memory

**Business Value:**
Nâng Meto từ "AI trả lời câu hỏi" lên "AI thực hiện hành động". Người dùng không chỉ được tư vấn — Meto có thể tạo nhắc nhở, ghi chỉ số, cập nhật care plan ngay trong chat. Memory giúp Meto nhớ người dùng qua các session.

**Deliverables:**

| Feature | Complexity | Priority |
|---------|-----------|---------|
| Tool Engine (registry, dispatcher, executor) | L | P0 |
| 12 tools (theo 09_TOOLS_AND_ACTIONS.md) | XL | P0 |
| Tool consent UI (per-action confirmation) | S | P0 |
| Tool audit logging | S | P0 |
| Memory Engine (3 tiers) | L | P0 |
| Memory extraction từ sessions | M | P0 |
| Memory prompt injection | M | P0 |
| Memory injection prevention (sanitizer) | M | P0 |
| Memory UI (xem, sửa, xóa) | M | P1 |
| Conversation summarization | M | P1 |
| Long conversation compression | M | P1 |
| Analytics v1 (core events, dashboards) | M | P1 |
| A/B testing infrastructure | M | P2 |

**Technical Dependencies:**
- Phase 1 gate criteria all met
- Tool permission model approved
- Memory encryption key management (Azure Key Vault)
- Memory storage schema migrated
- Analytics pipeline (Azure Event Hubs + ADX)

**Estimated Complexity:** XL (2-3 engineers, 8 weeks)

**Risks:**
| Rủi ro | Mức độ | Mitigation |
|-------|-------|-----------|
| Tool execution race conditions | MEDIUM | Proper async handling, tool_call_id tracking |
| Memory injection attack via user messages | HIGH | Sanitizer implemented + tested |
| Tool rate limit abuse | MEDIUM | Per-tool rate limiting |
| Memory extraction accuracy (AI extracting wrong info) | MEDIUM | confidence threshold 0.7+, user can correct |
| Conversation compression losing important context | MEDIUM | Lossless for safety/medical content |
| Analytics pipeline delays | LOW | Acceptable up to 30s for non-alerting metrics |

**Success Metrics:**
- [ ] Tool action rate > 15% of sessions use ≥1 tool
- [ ] Memory opt-in rate > 60%
- [ ] Tool success rate > 95% per tool
- [ ] Memory injection attack: 0 successful injections in security testing
- [ ] Conversation summarization quality: CSAT of summarized sessions ≥ non-summarized
- [ ] Analytics dashboards: < 5 minute lag from event to dashboard

**Gate Criteria (Sang Phase 3):**
- [ ] All 12 tools functional + tested
- [ ] Memory Engine: memories persisted correctly across sessions (verified by test)
- [ ] Tool audit log: 100% coverage verified
- [ ] Memory sanitizer: passes all injection test vectors
- [ ] CSAT >= Phase 1 CSAT (không xấu đi)
- [ ] Session completion rate maintained >= Phase 1 baseline
- [ ] Analytics dashboards operational với < 30s lag
- [ ] Medical team review: all health-related tool responses reviewed

---

## Phase 3 — Voice + Vision (Tháng 5–6)
### Chủ đề: Multimodal Input

**Business Value:**
Mở rộng cách người dùng tương tác với Meto. Người lớn tuổi (55+) thích nói chuyện hơn gõ. Người đang cầm đơn thuốc có thể chụp ảnh thay vì gõ lại. Đây là bước quan trọng để Meto tiếp cận đối tượng rộng hơn.

**Deliverables:**

| Feature | Complexity | Priority |
|---------|-----------|---------|
| Voice input (speech-to-text, Vietnamese) | L | P0 |
| Voice waveform UI (Meto Aura voice state) | M | P0 |
| Noise filtering + confidence threshold | M | P1 |
| OCR: chụp ảnh đơn thuốc | L | P0 |
| OCR: chụp ảnh kết quả xét nghiệm | L | P0 |
| Image understanding: ảnh bữa ăn → dinh dưỡng | XL | P1 |
| Health summary generation (full document) | M | P0 |
| Summary export (PDF) | S | P1 |
| Multimodal input routing (voice/image/text) | M | P0 |

**Technical Dependencies:**
- Phase 2 gate criteria all met
- STT provider: Azure Cognitive Services Speech hoặc OpenAI Whisper
- Vision model: Claude Vision hoặc GPT-4V
- OCR pipeline: Azure Form Recognizer
- File upload handling (image → blob storage → processing)
- Vietnamese language model quality assessment

**Estimated Complexity:** XL (3 engineers, 8 weeks)

**Risks:**
| Rủi ro | Mức độ | Mitigation |
|-------|-------|-----------|
| Vietnamese STT accuracy | HIGH | Evaluate multiple providers, set minimum accuracy threshold |
| OCR errors on handwritten prescriptions | HIGH | Confidence display, user correction UI |
| Image privacy (user uploads health images) | HIGH | Process and delete immediately, no persistent storage of raw images |
| Nutrition estimation from food photo inaccuracy | MEDIUM | Always present as estimate, user correction possible |
| Voice latency (STT → text → AI → response) | MEDIUM | Target < 5 seconds total |
| Image abuse (non-health content upload) | MEDIUM | Content filtering before processing |

**Success Metrics:**
- [ ] Voice recognition accuracy: > 90% for Vietnamese health vocabulary
- [ ] OCR prescription reading: > 85% accuracy for printed text
- [ ] Voice session completion rate: >= text-only benchmark
- [ ] Feature adoption: > 20% of users try voice in first month
- [ ] Health summary generation: user satisfaction > 80%

**Gate Criteria (Sang Phase 4):**
- [ ] Voice STT accuracy > 90% (tested on Vietnamese health vocabulary dataset)
- [ ] OCR accuracy > 85% (printed prescriptions)
- [ ] Image privacy: no images stored after processing (verified)
- [ ] Multimodal CSAT >= text-only CSAT
- [ ] Load test: multimodal requests không impact text response latency
- [ ] Zero content moderation incidents với image uploads

---

## Phase 4 — AI Coach (Tháng 7–9)
### Chủ đề: Proactive Intelligence

**Business Value:**
Chuyển Meto từ reactive (chờ user hỏi) sang proactive (chủ động hỗ trợ). Đây là bước quan trọng nhất về business value — Meto trở thành AI Coach thực sự, không chỉ là chatbot.

**Deliverables:**

| Feature | Complexity | Priority |
|---------|-----------|---------|
| Predictive reminders (ML-based timing) | XL | P0 |
| Medication adherence prediction | L | P0 |
| Behavior coaching engine | XL | P0 |
| Positive reinforcement system | M | P0 |
| Trend analysis (health metrics over time) | L | P0 |
| Anomaly detection (unusual metric values) | L | P0 |
| Proactive check-in messaging | M | P1 |
| Weekly health summary digest | M | P1 |
| Goal tracking + milestone celebration | M | P1 |
| Push notification integration với AI context | M | P0 |

**Technical Dependencies:**
- Phase 3 gate criteria all met
- ML pipeline: Azure ML hoặc lightweight custom model
- Push notification infrastructure
- Historical metrics data volume sufficient for ML (min 3 months)
- Behavior coaching content library (medical review required)
- Notification consent model (separate from AI consent)

**Estimated Complexity:** XL (3-4 engineers, 12 weeks)

**Risks:**
| Rủi ro | Mức độ | Mitigation |
|-------|-------|-----------|
| Predictive model accuracy | HIGH | Conservative approach, clear confidence display to user |
| Proactive notifications becoming annoying | HIGH | Smart frequency capping, user control |
| Behavior coaching medical accuracy | CRITICAL | Medical professional review of all coaching content |
| ML model bias (certain demographics) | HIGH | Bias testing across age/gender segments |
| Over-reliance on AI coaching vs medical care | HIGH | Always reference healthcare provider |
| Push notification opt-out rate | MEDIUM | Granular notification controls |

**Success Metrics:**
- [ ] Medication adherence improvement: +10% vs baseline for coached users
- [ ] Predictive reminder accuracy: > 70% (user confirms they forgot)
- [ ] Proactive check-in response rate: > 30%
- [ ] Weekly digest open rate: > 40%
- [ ] Behavior coaching satisfaction: CSAT > 75%
- [ ] Notification opt-out rate: < 20%

**Gate Criteria (Sang Phase 5):**
- [ ] Medication adherence improvement demonstrated (statistical significance)
- [ ] Proactive message frequency: avg < 2/day per user (not annoying)
- [ ] All coaching content medical review completed
- [ ] ML model bias testing passed (no significant demographic disparities)
- [ ] Push notification opt-out rate < 20%
- [ ] DAU Meto growth: > 20% increase from Phase 3 baseline
- [ ] Zero medical safety incidents from proactive features

---

## Phase 5 — Ecosystem (Tháng 10–12)
### Chủ đề: Connected Health

**Business Value:**
Meto trở thành hub kết nối toàn bộ ecosystem sức khỏe của người dùng — thiết bị đo, gia đình, và bác sĩ. Đây là lợi thế cạnh tranh dài hạn mà chatbot thông thường không thể có.

**Deliverables:**

| Feature | Complexity | Priority |
|---------|-----------|---------|
| Doctor Copilot (bác sĩ view Meto summary) | XL | P0 |
| Doctor Copilot consent model | M | P0 |
| Family Companion (người thân với consent) | L | P1 |
| Family alert system | M | P1 |
| Wearables: Apple Watch (HealthKit) | L | P0 |
| Wearables: Garmin Connect | M | P1 |
| Wearables: Omron blood pressure | M | P1 |
| Wearables: Fitbit (Health Connect Android) | M | P1 |
| MCP integration (expose Meto tools as MCP) | L | P0 |
| MCP server deployment | M | P0 |
| Real-time metric streaming từ wearables | L | P1 |

**Technical Dependencies:**
- Phase 4 gate criteria all met
- Apple HealthKit integration agreement
- Google Health Connect integration
- HIPAA/healthcare data sharing compliance review (for Doctor Copilot)
- MCP server infrastructure
- Family invite + consent flow
- Doctor portal (separate UI or existing MetoCare doctor app)

**Estimated Complexity:** XL (3-4 engineers, 12 weeks)

**Risks:**
| Rủi ro | Mức độ | Mitigation |
|-------|-------|-----------|
| Doctor Copilot consent complexity | HIGH | Separate explicit consent flow, user can revoke anytime |
| Wearable data accuracy variance | MEDIUM | Display device source, confidence indicators |
| Family access privacy concerns | HIGH | Granular permissions, user always in control |
| MCP protocol instability | MEDIUM | Version pin, fallback to native tools |
| Wearable API deprecation risk | MEDIUM | Abstraction layer per device |
| Real-time metric flood (continuous monitoring) | MEDIUM | Throttle to meaningful events only |

**Success Metrics:**
- [ ] Doctor Copilot adoption: > 30% of users share summary with doctor
- [ ] Wearable connection rate: > 25% of iOS users connect Apple Watch
- [ ] Family Companion: > 10% of users enable family access
- [ ] MCP: ≥3 external integrations using Meto MCP in first quarter
- [ ] Real-time metric alerts: < 5% false positive rate

**Gate Criteria (Sang Phase 6):**
- [ ] Doctor Copilot: security audit passed
- [ ] Family consent model: legal review approved
- [ ] Wearable data: sync accuracy > 95% (vs manual entry)
- [ ] MCP server: passing MCP compliance test suite
- [ ] Zero consent violations in ecosystem features
- [ ] Wearable integration: does not degrade core chat performance

---

## Phase 6 — Platform (Tháng 13–24)
### Chủ đề: AI Health Companion Platform

**Business Value:**
Meto không còn là tính năng trong MetoCare — Meto trở thành platform. Các clinic, đối tác B2B, và nhà phát triển bên thứ ba có thể build trên Meto. Đây là foundation cho tăng trưởng dài hạn và moat cạnh tranh.

**Sub-phases:**

### Phase 6A — Agent Ecosystem (Tháng 13–15)

| Feature | Complexity | Priority |
|---------|-----------|---------|
| Agent orchestration framework | XL | P0 |
| Specialist agents (Lab Agent, Medication Agent, Nutrition Agent) | XL | P0 |
| Agent-to-agent communication | L | P0 |
| Agent marketplace (internal) | L | P1 |
| Long-running task execution | L | P1 |
| Agent audit trail | M | P0 |

**Architecture Vision:**
```
User Query
    │
    ▼
Meto Orchestrator (decides which agents to invoke)
    │
    ├──▶ Lab Analysis Agent (specialized in lab interpretation)
    ├──▶ Medication Safety Agent (specialized in drug interactions)
    ├──▶ Nutrition Agent (specialized in dietary guidance)
    └──▶ Care Coordination Agent (appointment, care plan)
    │
    ▼
Synthesized Response → User
```

**Gate Criteria:**
- [ ] Agent communication protocol stable (no breaking changes planned)
- [ ] Agent isolation: agents cannot access each other's user data
- [ ] Orchestrator decision quality: correct agent selection > 90%
- [ ] Agent latency: multi-agent response < 8 seconds P95

---

### Phase 6B — Research Mode (Tháng 16–18)

| Feature | Complexity | Priority |
|---------|-----------|---------|
| Research consent model (explicit, granular) | L | P0 |
| Anonymized data aggregation pipeline | XL | P0 |
| Population health insights | L | P1 |
| Clinical data export (for authorized researchers) | L | P1 |
| De-identification pipeline | XL | P0 |
| Research portal | M | P1 |

**Privacy Requirements:**
- All research data: de-identified (k-anonymity k≥5)
- Explicit separate research consent required
- IRB approval required before any research data use
- Audit trail for all research data access
- User can withdraw from research at any time (retroactive)

**Gate Criteria:**
- [ ] IRB approval obtained
- [ ] De-identification audit: third-party verified
- [ ] Research consent: legal review completed
- [ ] Zero re-identification risk (k-anonymity verified)

---

### Phase 6C — Multilingual (Tháng 19–21)

| Feature | Complexity | Priority |
|---------|-----------|---------|
| English language support | L | P0 |
| Khmer language support | XL | P1 |
| Thai language support | L | P1 |
| Language detection (auto-switch) | S | P0 |
| Medical translation quality assurance | M | P0 |
| RTL layout support (if needed) | M | P2 |
| Localized medical references (by country) | L | P1 |

**Risks:**
- Medical translation errors: critical — native medical reviewer required per language
- Vietnamese → English: high quality expected (existing Vietnamese LLM quality is good)
- Vietnamese → Khmer: limited Khmer medical training data for LLMs

**Gate Criteria:**
- [ ] English: medical translation accuracy > 95% (reviewed by medical professional)
- [ ] Khmer: minimum viable quality threshold met (TBD based on LLM capability)
- [ ] Thai: same as Khmer
- [ ] CSAT per language >= Vietnamese baseline

---

### Phase 6D — Offline & Local Model (Tháng 22–24)

| Feature | Complexity | Priority |
|---------|-----------|---------|
| Offline mode (cached responses for common queries) | L | P1 |
| Local model fallback (on-device, lightweight) | XL | P1 |
| Sync when reconnected | M | P1 |
| Local model privacy (no data leaves device) | M | P0 |
| Progressive web app (PWA) support | M | P2 |

**Technical Approach:**
```
Normal mode: Cloud API (Claude/OpenAI)
         ↓ (no internet)
Offline mode: Local LLM (Phi-3 mini or similar)
         → Limited capabilities, basic Q&A only
         → Safety guardrails still enforced locally
         → Sync conversation when reconnected
```

**Gate Criteria:**
- [ ] Offline model: safety guardrails pass 100% of test cases
- [ ] Offline model accuracy: > 70% of cloud quality for common queries
- [ ] Battery impact: < 5% additional drain per hour
- [ ] Sync conflict resolution: no data loss

---

### Phase 6E — B2B & Clinic Integration (Parallel track, Tháng 13–24)

| Feature | Complexity | Priority |
|---------|-----------|---------|
| Clinic API (embed Meto in clinic software) | XL | P0 |
| White-label Meto (clinic branding) | L | P1 |
| Clinic admin dashboard | M | P0 |
| Patient population management | L | P1 |
| Integration with EHR systems (basic) | XL | P1 |
| B2B pricing + billing | M | P0 |
| Clinic-specific prompt customization | M | P1 |
| HIPAA compliance documentation | M | P0 |

**Business Model:**
- B2C: Integrated in MetoCare app (current)
- B2B Clinic: Per-patient-month licensing
- B2B Enterprise: Custom deployment + support

**Gate Criteria:**
- [ ] HIPAA compliance: audit completed
- [ ] Clinic API: 3 pilot clinics signed and using
- [ ] B2B CSAT: clinic admin satisfaction > 80%
- [ ] EHR integration: at least 1 major Vietnamese EHR system

---

## Phase Summary Table

| Phase | Timeline | Theme | Complexity | Priority | Key Deliverable |
|-------|---------|-------|-----------|---------|----------------|
| **1** | T1–2 | Foundation | L | P0 | Core chat + context |
| **2** | T3–4 | Intelligence | XL | P0 | Tools + Memory |
| **3** | T5–6 | Voice + Vision | XL | P0 | Multimodal input |
| **4** | T7–9 | AI Coach | XL | P0 | Proactive AI |
| **5** | T10–12 | Ecosystem | XL | P1 | Connected health |
| **6A** | T13–15 | Agent | XL | P1 | Multi-agent |
| **6B** | T16–18 | Research | XL | P2 | Data platform |
| **6C** | T19–21 | Multilingual | L | P1 | English + Khmer + Thai |
| **6D** | T22–24 | Offline | XL | P2 | Local model |
| **6E** | T13–24 | B2B | XL | P1 | Clinic integration |

---

## Cross-cutting Concerns (All Phases)

### Security
- Security audit mỗi phase trước GA
- Penetration testing: Phase 1, 3, 5, 6 (major milestones)
- Dependency vulnerability scanning: automated, weekly

### Medical Safety
- Medical professional review: mọi feature ảnh hưởng đến clinical content
- Red flag detection: phải pass 100% test cases mỗi phase
- Escalation paths: luôn available bất kể feature additions

### Performance
- P95 TTFT target: < 3,000ms (core chat, maintained tất cả phases)
- Session completion rate: không được giảm qua các phases
- Load target tăng theo phases: 1K concurrent (P1) → 10K (P3) → 50K (P5) → 100K (P6)

### Privacy
- GDPR compliance: maintained tất cả phases
- Data minimization: review per phase
- User rights: always available (view, export, delete)

### Accessibility
- WCAG 2.1 AA: UI components mỗi phase
- Voice UI: accessible design
- Large text support: maintained

---

## Resource Planning

### Phase 1–2 (Months 1–4)
```
Engineering: 2 senior engineers
Design: 1 UX designer (part-time)
Medical advisor: 1 (consulting)
PM: 1
```

### Phase 3–4 (Months 5–9)
```
Engineering: 3 engineers (add ML/AI specialist)
Design: 1 UX designer
Medical advisor: 1-2 (consulting)
PM: 1
Data: 1 data engineer (analytics)
```

### Phase 5–6 (Months 10–24)
```
Engineering: 4-6 engineers
Design: 2 designers
Medical: 1 medical director (part-time)
PM: 2 (product + growth)
Data: 1-2 data engineers
Legal: 1 (for B2B, HIPAA)
```

---

## Risk Register — Long-term

| Rủi ro chiến lược | Mức độ | Timeline | Mitigation |
|------------------|-------|---------|-----------|
| Regulatory changes (AI in healthcare) | HIGH | Ongoing | Legal monitoring, conservative approach |
| LLM provider cost increase | MEDIUM | Any time | Multiple providers, token optimization |
| Competitor releases similar product | HIGH | 6-12 months | Accelerate ecosystem moat (Phase 5) |
| Medical error scandal | CRITICAL | Any time | Aggressive safety guardrails, audit trails |
| Data breach | CRITICAL | Any time | Defense in depth, regular audits |
| LLM quality regression | MEDIUM | Any time | Automated quality regression tests |
| Vietnamese language LLM quality | MEDIUM | Phase 3+ | Evaluate models regularly |
| User trust erosion | HIGH | Ongoing | Transparency, user control, CSAT monitoring |

---

## Success Vision — Month 24

Sau 24 tháng, Meto AI Platform đạt được:

**User Metrics:**
- > 100,000 monthly active users
- > 60% of MetoCare app users use Meto monthly
- D30 Meto retention > 40%
- CSAT > 85%

**Business Metrics:**
- B2B: > 10 clinic partners
- Revenue from Meto: measurable contribution to MetoCare revenue
- Cost per conversation: < $0.05 (via token optimization + local model)

**Health Impact:**
- Medication adherence improvement: +15% for coached users
- User-reported health understanding: significantly improved (survey)
- Doctor appointment preparation rate: measurable increase

**Platform Metrics:**
- > 5 external integrations via MCP
- Multi-language: Vietnamese + English + Khmer live
- Agent ecosystem: > 5 specialist agents
- Zero Severity-1 medical safety incidents

---

*Tài liệu này là living document. Cập nhật quarterly sau mỗi phase review. Thay đổi scope phải được PM + Tech Lead + Medical Advisor phê duyệt trước khi commit vào roadmap.*
