# Meto AI — Context Engine Specification

> **Phiên bản:** 1.0 | **Ngày:** 2026-06-30 | **Trạng thái:** Approved

---

## Tổng quan

Context Engine là thành phần backend chịu trách nhiệm **thu thập, lọc, và đóng gói thông tin cần thiết** trước mỗi lần Meto trả lời. Engine đảm bảo Meto luôn có đủ ngữ cảnh để trả lời đúng và an toàn, trong khi giữ token budget hợp lý và bảo vệ quyền riêng tư người dùng.

**File backend:** `app/ai/context_engine.py`

---

## 1. Danh sách 9 Context Blocks

### Block 1: `user_profile_summary`

| Thuộc tính | Giá trị |
|-----------|---------|
| Nguồn data | `users` table, `user_profiles` table |
| Token budget | ~150 tokens |
| Khi nào include | Luôn luôn (bắt buộc) |
| Staleness policy | 24 giờ, hoặc khi user cập nhật profile |

**Fields:**
```python
{
  "user_id": "uuid",          # internal only, không đưa vào prompt
  "display_name": "string",   # tên hiển thị
  "age": int,
  "gender": "male|female|other",
  "preferred_address": "anh|chị|bác|cô|chú|bạn",  # từ memory nếu có
  "language": "vi",
  "account_type": "patient|caregiver"
}
```

**Ví dụ JSON:**
```json
{
  "display_name": "Nguyễn Văn An",
  "age": 58,
  "gender": "male",
  "preferred_address": "anh",
  "language": "vi",
  "account_type": "patient"
}
```

---

### Block 2: `health_summary`

| Thuộc tính | Giá trị |
|-----------|---------|
| Nguồn data | `health_profiles` table, `diagnoses` table |
| Token budget | ~300 tokens |
| Khi nào include | Luôn luôn (nếu có consent) |
| Staleness policy | 12 giờ |

**Fields:**
```python
{
  "primary_conditions": ["string"],     # chẩn đoán chính
  "secondary_conditions": ["string"],   # bệnh nền phụ
  "allergies": ["string"],              # dị ứng đã biết
  "blood_type": "string",
  "chronic_conditions": ["string"],
  "last_updated": "ISO8601"
}
```

**Ví dụ JSON:**
```json
{
  "primary_conditions": ["Đái tháo đường type 2", "Tăng huyết áp"],
  "secondary_conditions": ["Rối loạn mỡ máu"],
  "allergies": ["Penicillin"],
  "blood_type": "O+",
  "chronic_conditions": ["Đái tháo đường type 2"],
  "last_updated": "2026-06-28T08:00:00Z"
}
```

---

### Block 3: `current_care_plan`

| Thuộc tính | Giá trị |
|-----------|---------|
| Nguồn data | `care_plans` table, `care_tasks` table |
| Token budget | ~250 tokens |
| Khi nào include | Dashboard, Care Plan screen; optional ở các màn khác |
| Staleness policy | 4 giờ |

**Fields:**
```python
{
  "plan_id": "uuid",
  "plan_name": "string",
  "active_tasks": [
    {
      "task_id": "uuid",
      "title": "string",
      "due_date": "ISO8601",
      "status": "pending|completed|overdue",
      "priority": "high|medium|low"
    }
  ],
  "completed_today": int,
  "total_today": int
}
```

**Ví dụ JSON:**
```json
{
  "plan_name": "Kiểm soát đường huyết tháng 6",
  "active_tasks": [
    {
      "title": "Đo đường huyết buổi sáng",
      "due_date": "2026-06-30T07:00:00Z",
      "status": "completed",
      "priority": "high"
    },
    {
      "title": "Uống Metformin 500mg buổi trưa",
      "due_date": "2026-06-30T12:00:00Z",
      "status": "pending",
      "priority": "high"
    }
  ],
  "completed_today": 1,
  "total_today": 3
}
```

---

### Block 4: `active_medications`

| Thuộc tính | Giá trị |
|-----------|---------|
| Nguồn data | `prescriptions` table, `medications` table |
| Token budget | ~300 tokens |
| Khi nào include | Luôn luôn (nếu có); bắt buộc ở Medications screen |
| Staleness policy | 6 giờ |

**Fields:**
```python
{
  "medications": [
    {
      "med_id": "uuid",
      "name": "string",
      "generic_name": "string",
      "dosage": "string",
      "frequency": "string",
      "route": "oral|injection|topical",
      "prescribed_by": "string",    # tên bác sĩ
      "start_date": "ISO8601",
      "next_dose_time": "ISO8601",
      "adherence_last_7d": float    # tỉ lệ tuân thủ 7 ngày gần nhất
    }
  ]
}
```

**Ví dụ JSON:**
```json
{
  "medications": [
    {
      "name": "Metformin",
      "generic_name": "Metformin HCl",
      "dosage": "500mg",
      "frequency": "2 lần/ngày",
      "route": "oral",
      "prescribed_by": "BS. Trần Minh Khoa",
      "start_date": "2026-01-15",
      "next_dose_time": "2026-06-30T12:00:00Z",
      "adherence_last_7d": 0.85
    }
  ]
}
```

---

### Block 5: `recent_labs`

| Thuộc tính | Giá trị |
|-----------|---------|
| Nguồn data | `lab_results` table |
| Token budget | ~350 tokens |
| Khi nào include | Luôn nếu có kết quả <30 ngày; bắt buộc ở Labs screen |
| Staleness policy | Real-time (load khi mở chat) |

**Fields:**
```python
{
  "labs": [
    {
      "test_name": "string",
      "value": "string",
      "unit": "string",
      "reference_range": "string",
      "status": "normal|high|low|critical",
      "collected_date": "ISO8601",
      "ordered_by": "string"
    }
  ],
  "most_recent_date": "ISO8601"
}
```

**Ví dụ JSON:**
```json
{
  "labs": [
    {
      "test_name": "HbA1c",
      "value": "7.8",
      "unit": "%",
      "reference_range": "< 7.0%",
      "status": "high",
      "collected_date": "2026-06-25",
      "ordered_by": "BS. Trần Minh Khoa"
    },
    {
      "test_name": "Glucose (fasting)",
      "value": "145",
      "unit": "mg/dL",
      "reference_range": "70–99 mg/dL",
      "status": "high",
      "collected_date": "2026-06-25"
    }
  ],
  "most_recent_date": "2026-06-25"
}
```

---

### Block 6: `recent_metrics`

| Thuộc tính | Giá trị |
|-----------|---------|
| Nguồn data | `health_metrics` table (blood pressure, glucose, weight, SpO2, v.v.) |
| Token budget | ~250 tokens |
| Khi nào include | Luôn nếu có metric <7 ngày; bắt buộc ở Metrics screen |
| Staleness policy | 30 phút (metrics thay đổi thường xuyên) |

**Fields:**
```python
{
  "metrics": [
    {
      "metric_type": "blood_pressure|glucose|weight|spo2|heart_rate|temperature",
      "latest_value": "string",
      "unit": "string",
      "reference_range": "string",
      "status": "normal|high|low|critical",
      "measured_at": "ISO8601",
      "trend": "improving|stable|worsening"
    }
  ]
}
```

**Ví dụ JSON:**
```json
{
  "metrics": [
    {
      "metric_type": "blood_pressure",
      "latest_value": "145/92",
      "unit": "mmHg",
      "reference_range": "< 130/80 mmHg",
      "status": "high",
      "measured_at": "2026-06-30T07:30:00Z",
      "trend": "stable"
    },
    {
      "metric_type": "glucose",
      "latest_value": "132",
      "unit": "mg/dL",
      "measured_at": "2026-06-30T07:15:00Z",
      "status": "high",
      "trend": "improving"
    }
  ]
}
```

---

### Block 7: `current_screen_context`

| Thuộc tính | Giá trị |
|-----------|---------|
| Nguồn data | Frontend (injected tại thời điểm gọi API) |
| Token budget | ~100 tokens |
| Khi nào include | Luôn luôn |
| Staleness policy | Real-time (mỗi lần gọi) |

**Fields:**
```python
{
  "screen_id": "dashboard|labs|medications|metrics|nutrition|care_plan|profile",
  "entity_id": "uuid|null",   # ID của item đang xem (vd: lab_result_id khi xem 1 kết quả)
  "entity_type": "string|null",
  "view_context": {}          # dữ liệu bổ sung từ màn hình hiện tại
}
```

**Ví dụ JSON:**
```json
{
  "screen_id": "labs",
  "entity_id": "lab-result-uuid-123",
  "entity_type": "lab_result",
  "view_context": {
    "test_name": "HbA1c",
    "value": "7.8",
    "status": "high"
  }
}
```

---

### Block 8: `today_context`

| Thuộc tính | Giá trị |
|-----------|---------|
| Nguồn data | `care_tasks`, `appointments`, `medication_logs` |
| Token budget | ~200 tokens |
| Khi nào include | Dashboard; optional ở các màn |
| Staleness policy | 30 phút |

**Fields:**
```python
{
  "date": "YYYY-MM-DD",
  "upcoming_appointments": [
    {
      "title": "string",
      "datetime": "ISO8601",
      "provider": "string",
      "location": "string"
    }
  ],
  "missed_medications_today": ["string"],  # tên thuốc bị bỏ qua
  "pending_tasks_count": int,
  "completed_tasks_count": int,
  "last_glucose_reading": "string|null"
}
```

**Ví dụ JSON:**
```json
{
  "date": "2026-06-30",
  "upcoming_appointments": [
    {
      "title": "Khám định kỳ đái tháo đường",
      "datetime": "2026-07-05T09:00:00Z",
      "provider": "BS. Trần Minh Khoa",
      "location": "Phòng khám Nội tiết, Bệnh viện 115"
    }
  ],
  "missed_medications_today": [],
  "pending_tasks_count": 2,
  "completed_tasks_count": 1,
  "last_glucose_reading": "132 mg/dL lúc 07:15"
}
```

---

### Block 9: `safety_flags`

| Thuộc tính | Giá trị |
|-----------|---------|
| Nguồn data | Rules engine chạy trên `recent_metrics` + `recent_labs` |
| Token budget | ~100 tokens |
| Khi nào include | Luôn luôn (bắt buộc) |
| Staleness policy | Real-time (tính lại mỗi lần) |

**Fields:**
```python
{
  "has_critical_values": bool,
  "critical_items": [
    {
      "type": "lab|metric",
      "name": "string",
      "value": "string",
      "severity": "high|critical"
    }
  ],
  "red_flag_symptoms": [],  # từ recent user input nếu có
  "escalation_required": bool
}
```

**Ví dụ JSON — không có critical:**
```json
{
  "has_critical_values": false,
  "critical_items": [],
  "red_flag_symptoms": [],
  "escalation_required": false
}
```

**Ví dụ JSON — có critical:**
```json
{
  "has_critical_values": true,
  "critical_items": [
    {
      "type": "metric",
      "name": "Glucose",
      "value": "350 mg/dL",
      "severity": "critical"
    }
  ],
  "red_flag_symptoms": [],
  "escalation_required": true
}
```

---

## 2. Context Assembly Logic — Màn nào include block nào

| Block | Dashboard | Labs | Medications | Metrics | Nutrition | Care Plan | Profile |
|-------|-----------|------|-------------|---------|-----------|-----------|---------|
| user_profile_summary | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| health_summary | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| current_care_plan | ✅ | ⭕ | ⭕ | ⭕ | ⭕ | ✅ | ⭕ |
| active_medications | ⭕ | ⭕ | ✅ | ⭕ | ✅ | ⭕ | ⭕ |
| recent_labs | ⭕ | ✅ | ⭕ | ⭕ | ⭕ | ⭕ | ⭕ |
| recent_metrics | ✅ | ⭕ | ⭕ | ✅ | ✅ | ⭕ | ⭕ |
| current_screen_context | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| today_context | ✅ | ⭕ | ✅ | ⭕ | ⭕ | ✅ | ⭕ |
| safety_flags | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

**Ký hiệu:** ✅ = Luôn include | ⭕ = Include nếu có data & relevant | ❌ = Không include

---

## 3. Token Budget

| Block | Budget (tokens) | Ghi chú |
|-------|----------------|---------|
| user_profile_summary | ~150 | Không thể giảm |
| health_summary | ~300 | Giới hạn tối đa 5 conditions |
| current_care_plan | ~250 | Chỉ lấy tasks hôm nay + overdue |
| active_medications | ~300 | Tối đa 10 thuốc |
| recent_labs | ~350 | Tối đa 10 lab gần nhất, <30 ngày |
| recent_metrics | ~250 | Tối đa 5 metric types, <7 ngày |
| current_screen_context | ~100 | Compact |
| today_context | ~200 | Chỉ ngày hôm nay |
| safety_flags | ~100 | Không giảm |
| **Total context** | **~2000** | Reserve ~2000 cho system prompt + ~6000 cho response |

**Tổng token budget mỗi request: ~10,000 tokens** (Claude Sonnet context window đủ)

---

## 4. Staleness Policy & Cache

```python
CACHE_TTL = {
    "user_profile_summary": 86400,   # 24 giờ
    "health_summary": 43200,          # 12 giờ
    "current_care_plan": 14400,       # 4 giờ
    "active_medications": 21600,      # 6 giờ
    "recent_labs": 0,                 # không cache (real-time)
    "recent_metrics": 1800,           # 30 phút
    "current_screen_context": 0,      # không cache (per-request)
    "today_context": 1800,            # 30 phút
    "safety_flags": 0,                # không cache (tính lại mỗi lần)
}
```

Cache backend: **Redis** (Azure Cache for Redis), key format: `meto:ctx:{user_id}:{block_name}`

---

## 5. Xử lý Missing Data

| Tình huống | Xử lý |
|-----------|-------|
| Block không có data | Include block với `{"available": false, "reason": "no_data"}` |
| Consent chưa được cấp | Exclude block, thêm note vào system prompt |
| Data quá cũ (> 2x staleness) | Include với cảnh báo `{"stale": true, "last_updated": "..."}` |
| API backend lỗi | Skip block, log error, không dừng toàn bộ request |
| User mới, chưa có data | Include empty arrays, Meto biết cách xử lý "chưa có thông tin" |

---

## 6. Context Isolation (Bảo mật)

### Nguyên tắc
**Tuyệt đối không** có trường hợp user A thấy data của user B.

### Implementation Requirements

```python
class ContextEngine:
    def __init__(self, user_id: str, request_user_id: str):
        # Bắt buộc: xác minh caller có quyền lấy data của user_id
        if user_id != request_user_id:
            raise ContextIsolationError("Cross-user context access denied")
        self.user_id = user_id

    async def get_block(self, block_name: str) -> dict:
        # Mọi query DB đều WHERE user_id = self.user_id
        # Không bao giờ dùng raw input từ request làm user_id trong query
        ...
```

### Database Query Requirements
- Mọi query phải có `WHERE user_id = :user_id` parameterized
- Không dùng string interpolation cho user_id
- Foreign key constraints đảm bảo data integrity
- Row-level security (RLS) ở PostgreSQL layer làm backup

---

## 7. Consent Gating Logic

```python
CONSENT_REQUIRED_BLOCKS = {
    "health_summary",
    "current_care_plan",
    "active_medications",
    "recent_labs",
    "recent_metrics",
    "today_context",
}

async def assemble_context(user_id: str, screen_id: str, consent: UserConsent) -> dict:
    context = {}

    # Luôn include (không cần consent)
    context["user_profile_summary"] = await get_user_profile(user_id)
    context["current_screen_context"] = get_screen_context(screen_id)
    context["safety_flags"] = await compute_safety_flags(user_id)

    # Chỉ include nếu user đã consent
    if consent.health_data_granted:
        for block in CONSENT_REQUIRED_BLOCKS:
            if should_include(block, screen_id):
                context[block] = await get_block(user_id, block)
    else:
        # Thêm note để Meto biết không có health data
        context["_consent_note"] = "User has not consented to health data access"

    return context
```

---

*Xem thêm: 03_PROMPT_POLICY.md (cách context được đưa vào prompt), 04_SAFETY_PRIVACY.md (audit logging, consent model)*
