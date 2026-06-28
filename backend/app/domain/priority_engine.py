"""Engine 4 — Priority Engine.

Ranks health issues by clinical significance × patient context.
Returns list[PriorityIssue] sorted by rank (1=most urgent).

Rules:
- Urgent alerts → always rank 1
- Context multipliers: CVD history, diabetes, CKD → raise severity of related patterns
- Patterns > isolated findings (multi-marker > single)
- Worsening trend > stable at same severity level
- Max 5 priorities returned
"""
from __future__ import annotations

from dataclasses import dataclass

from app.domain.patient_context import PatientContext


@dataclass
class PriorityIssue:
    rank: int
    issue_id: str                # card_id or pattern_id
    title_vi: str
    priority_reason_vi: str      # Why this rank — context-aware
    urgency: str                 # "routine" | "1_month" | "soon" | "immediately"
    urgency_vi: str
    linked_card_id: str | None = None


_URGENCY_SCORE = {
    "immediately": 4,
    "soon": 3,
    "1_month": 2,
    "routine": 1,
}

_URGENCY_VI = {
    "immediately": "Gặp bác sĩ ngay",
    "soon": "Gặp bác sĩ sớm",
    "1_month": "Tái khám trong 1 tháng",
    "routine": "Theo dõi định kỳ",
}

# Context multipliers — which patterns get boosted for which conditions
_CONTEXT_BOOSTS: dict[str, dict[str, int]] = {
    # pattern_id: {condition_flag: boost_score}
    "atherogenic_cholesterol": {"has_cvd_history": 3, "has_diabetes": 2},
    "insulin_resistance": {"has_diabetes": 2, "is_overweight": 1},
    "metabolic_syndrome": {"has_diabetes": 2, "has_cvd_history": 2},
    "kidney_risk": {"has_ckd": 3, "has_diabetes": 2, "has_hypertension": 1},
    "hepatic_metabolic": {"has_fatty_liver": 2, "is_overweight": 1},
    "inflammatory_process": {"has_cvd_history": 2},
    "hypertriglyceridemia_low_hdl": {"has_diabetes": 1, "is_overweight": 1},
}

_PATTERN_REASON_TEMPLATES: dict[str, str] = {
    "atherogenic_cholesterol": "Tăng cholesterol sinh xơ vữa là yếu tố nguy cơ tim mạch hàng đầu — đặc biệt khi có tiền sử hoặc nguy cơ cao.",
    "insulin_resistance": "Kháng insulin là nền tảng của nhiều rối loạn chuyển hóa — ưu tiên vì tác động dây chuyền lên đường huyết, lipid và cân nặng.",
    "metabolic_syndrome": "Hội chứng chuyển hóa tăng nguy cơ tiểu đường và tim mạch đồng thời — cần xử lý đa yếu tố.",
    "kidney_risk": "Suy giảm chức năng thận ảnh hưởng đến toàn thân — phát hiện và kiểm soát sớm giúp làm chậm tiến triển.",
    "hepatic_metabolic": "Tổn thương gan chuyển hóa thường âm thầm — ưu tiên vì gan ảnh hưởng đến toàn bộ chuyển hóa.",
    "inflammatory_process": "Viêm mạn tính là yếu tố nguy cơ độc lập — cần xác định nguyên nhân để kiểm soát.",
    "hypertriglyceridemia_low_hdl": "Mẫu hình TG/HDL bất lợi liên quan đến nguy cơ tim mạch và kháng insulin.",
    "thyroid_dysfunction": "Rối loạn tuyến giáp ảnh hưởng nhiều cơ quan — cần đánh giá và điều trị sớm.",
    "insulin_resistance_pattern": "Dấu hiệu kháng insulin cần can thiệp sớm bằng thay đổi lối sống.",
}

_SEVERITY_URGENCY = {
    "urgent": "immediately",
    "warning": "1_month",
    "watch": "routine",
    "info": "routine",
}


def _context_flag(ctx: PatientContext, flag: str) -> bool:
    if flag == "is_overweight":
        return ctx.is_overweight()
    return bool(getattr(ctx, flag, False))


class PriorityEngine:
    """Rank health issues by clinical importance × patient context."""

    def rank(
        self,
        insight_cards: list,          # list[InsightCard]
        patterns: list,               # list[ClinicalPattern]
        urgent_alerts: list,          # list[UrgentAlert]
        ctx: PatientContext,
    ) -> list[PriorityIssue]:

        scored: list[tuple[int, str, str, str, str, str | None]] = []
        # (score, issue_id, title_vi, urgency, reason_vi, linked_card_id)

        # Urgent alerts → always top
        for alert in urgent_alerts:
            scored.append((
                100,
                alert.alert_id,
                alert.title_vi,
                "immediately",
                "Cảnh báo khẩn — cần xử lý ngay lập tức.",
                None,
            ))

        # Patterns (multi-marker > single)
        for p in patterns:
            base_score = {"urgent": 50, "warning": 30, "watch": 15, "info": 5}.get(p.severity, 10)
            ctx_boost = sum(
                boost for flag, boost in _CONTEXT_BOOSTS.get(p.pattern_id, {}).items()
                if _context_flag(ctx, flag)
            )
            # Boost very-high-risk patients overall
            if ctx.cv_risk_category == "very_high":
                ctx_boost += 5
            elif ctx.cv_risk_category == "high":
                ctx_boost += 2

            urgency = _SEVERITY_URGENCY.get(p.severity, "routine")
            if ctx.cv_risk_category in ("very_high", "high") and urgency == "routine":
                urgency = "1_month"

            reason = _PATTERN_REASON_TEMPLATES.get(p.pattern_id, f"Mẫu hình {p.display_name_vi} cần theo dõi.")
            # Add context-specific note
            if ctx.has_cvd_history and p.pattern_id in ("atherogenic_cholesterol", "inflammatory_process"):
                reason += " Tiền sử bệnh tim mạch làm tăng mức ưu tiên này lên mức cao nhất."
            elif ctx.has_diabetes and p.pattern_id in ("insulin_resistance", "kidney_risk"):
                reason += " Tiểu đường làm tăng nguy cơ biến chứng liên quan — cần kiểm soát sớm."

            scored.append((base_score + ctx_boost, p.pattern_id, p.display_name_vi, urgency, reason, None))

        # Individual insight cards (single-marker, lower base score)
        for card in insight_cards:
            # Skip if already covered by a pattern
            covered = any(card.card_id.endswith(f"_{p.pattern_id}") or p.pattern_id in card.card_id for p in patterns)
            if covered:
                continue
            base_score = {"high": 20, "medium": 10, "low": 3}.get(card.importance, 5)
            urgency = getattr(card, "urgency_label", "routine") or "routine"
            reason = f"{card.title_vi} — chỉ số đơn lẻ cần theo dõi."

            scored.append((base_score, card.card_id, card.title_vi, urgency, reason, card.card_id))

        # Sort descending by score
        scored.sort(key=lambda x: -x[0])

        # Deduplicate and limit to 5
        seen: set[str] = set()
        priorities: list[PriorityIssue] = []
        rank = 1
        for _score, issue_id, title_vi, urgency, reason, linked in scored:
            if issue_id in seen:
                continue
            seen.add(issue_id)
            priorities.append(PriorityIssue(
                rank=rank,
                issue_id=issue_id,
                title_vi=title_vi,
                priority_reason_vi=reason,
                urgency=urgency,
                urgency_vi=_URGENCY_VI.get(urgency, "Theo dõi định kỳ"),
                linked_card_id=linked,
            ))
            rank += 1
            if rank > 5:
                break

        return priorities
