"""NarrativeInput builder.

Distills PatientInsightReport (Rule Engine output) into a compact JSON
that Claude receives. Claude never sees raw DB objects, OCR text, or
unclassified values.

The distillation:
- Removes internal fields (patient_id, generated_at, ai_draft_contract)
- Flattens nested dataclasses to plain dicts
- Limits list sizes (max 5 insights, max 3 priorities, max 2 patterns)
- Only includes fields needed for narrative generation
"""
from __future__ import annotations

from typing import Any

MAX_NARRATIVE_TOKENS_ESTIMATE = 6000  # Safety: keep input under ~6k tokens


def _get(obj: Any, attr: str, default: Any = None) -> Any:
    """Get attribute from dataclass or dict."""
    if isinstance(obj, dict):
        return obj.get(attr, default)
    return getattr(obj, attr, default)


def build_narrative_input(report: Any, language: str = "vi") -> dict:
    """Build compact dict from PatientInsightReport for Claude.

    Parameters
    ----------
    report : PatientInsightReport (or dict if already asdict'd)
    language : ISO language code

    Returns
    -------
    dict — safe to serialize to JSON and pass to Claude
    """
    # Urgent alerts
    urgent_alerts_raw = _get(report, "urgent_alerts", []) or []
    urgent_alerts = [
        {
            "title": _get(a, "title_vi", ""),
            "detail": _get(a, "detail_vi", ""),
        }
        for a in urgent_alerts_raw[:3]
    ]

    # Top insights
    insights_raw = _get(report, "insights", []) or []
    top_insights = [
        {
            "title": _get(c, "title_vi", ""),
            "importance": _get(c, "importance", ""),
            "severity": _get(c, "severity_label", ""),
            "trend": _get(c, "trend", ""),
            "rationale": _get(c, "rationale_vi", ""),
            "evidence_level": _get(c, "evidence_level", ""),
            "urgency": _get(c, "urgency_vi", ""),
        }
        for c in insights_raw[:5]
    ]

    # Clinical patterns
    patterns_raw = _get(report, "patterns_v3", []) or []
    clinical_patterns = [
        _get(p, "name_vi", str(p)) if not isinstance(p, str) else p
        for p in patterns_raw[:3]
    ]

    # Preventive domains — exclude low_concern
    domains_raw = _get(report, "preventive_risk_domains", []) or []
    preventive_domains = [
        {
            "domain": _get(d, "domain_id", ""),
            "level": _get(d, "level", ""),
            "level_vi": _get(d, "level_vi", ""),
            "description": _get(d, "description_vi", ""),
        }
        for d in domains_raw[:5]
        if _get(d, "level", "") != "low_concern"
    ]

    # Next best action
    next_best_action_raw = _get(report, "next_best_action", None)
    next_best_action = None
    if next_best_action_raw is not None:
        next_best_action = {
            "title": _get(next_best_action_raw, "title_vi", ""),
            "why": _get(next_best_action_raw, "why_vi", ""),
            "benefit": _get(next_best_action_raw, "expected_benefit_vi", ""),
            "timeframe": _get(next_best_action_raw, "timeframe_vi", ""),
        }

    # Priorities
    priorities_raw = _get(report, "priorities", []) or []
    top_priorities = [
        {
            "title": _get(p, "title_vi", str(p)) if not isinstance(p, str) else p,
            "explanation": _get(p, "explanation_vi", "") if not isinstance(p, str) else "",
        }
        for p in priorities_raw[:3]
    ]

    # Positive areas
    positive_raw = _get(report, "positive_reinforcement", []) or []
    positive_areas: list[str] = []
    for item in positive_raw[:3]:
        if isinstance(item, str):
            positive_areas.append(item)
        else:
            msg = _get(item, "message_vi", "")
            if msg:
                positive_areas.append(msg)

    return {
        "language": language,
        "overall_status": _get(report, "overall_status", ""),
        "overall_summary": _get(report, "overall_status_text_vi", ""),
        "urgent_alerts": urgent_alerts,
        "top_insights": top_insights,
        "clinical_patterns": clinical_patterns,
        "preventive_domains": preventive_domains,
        "next_best_action": next_best_action,
        "missing_context": (_get(report, "missing_context", []) or [])[:5],
        "context_completeness": round(_get(report, "context_completeness", 0.0) or 0.0, 2),
        "positive_areas": positive_areas,
        "top_priorities": top_priorities,
    }
