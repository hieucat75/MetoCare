import enum
import os

from dotenv import load_dotenv

# Populate os.environ from .env so os.getenv() calls below see local-dev overrides.
# load_dotenv() never overrides existing OS env vars — safe in production.
load_dotenv()


class FeatureFlag(enum.StrEnum):
    AI_TRIAGE = "ai_triage"  # DISABLED until Medical Board approval
    AI_LAB_INTERPRET = "ai_lab_interpret"  # DISABLED until Medical Board approval
    AI_CARE_PLAN_DRAFT = "ai_care_plan_draft"  # DISABLED until Medical Board approval
    AI_SAFETY_LAYER = "ai_safety_layer"  # DISABLED until Medical Board approval
    DOCTOR_REVIEW_GATE = "doctor_review_gate"  # ENABLED (mandatory)
    CONSENT_GATE = "consent_gate"  # ENABLED (mandatory)
    # T5 / C3: AI session feature flags — default OFF (fail-closed)
    AI_SESSION_ENABLED = "ai_session_enabled"  # Gates AISession creation
    AI_CLINICAL_RECS_ENABLED = "ai_clinical_recs_enabled"  # Gates viewing/acting on recs
    AI_ESCALATION_ENABLED = "ai_escalation_enabled"  # Gates escalation workflows
    # PR-B: patient-facing AI/OCR surfaces — default OFF (no real AI for MVP)
    AI_ASSISTANT = "ai_assistant"  # Gates /ai/chat + /ai/explain
    OCR = "ocr"  # Gates lab OCR (process/interpret)
    AI_RECOMMENDATION = "ai_recommendation"  # Gates AI recommendation surfaces
    # OCR Lab Upload track: cloud OCR is an OPT-IN fallback. Default OFF so medical
    # images are NEVER sent to a third party unless explicitly enabled with a key.
    OCR_CLOUD_FALLBACK = "ocr_cloud_fallback"  # Gates cloud OCR fallback (anthropic|azure)
    # PA-11: Clinical Insight Engine — rules-first patient guidance.
    CLINICAL_INSIGHT = "clinical_insight"  # Gates insight + health-summary endpoints
    CLINICAL_INSIGHT_AI = "clinical_insight_ai"  # Gates OPTIONAL LLM rephrasing of rules text


_DEFAULTS = {
    FeatureFlag.AI_TRIAGE: False,
    FeatureFlag.AI_LAB_INTERPRET: False,
    FeatureFlag.AI_CARE_PLAN_DRAFT: False,
    FeatureFlag.AI_SAFETY_LAYER: False,
    FeatureFlag.DOCTOR_REVIEW_GATE: True,
    FeatureFlag.CONSENT_GATE: True,
    # T5 / C3: new flags — default OFF (fail-closed)
    FeatureFlag.AI_SESSION_ENABLED: False,
    FeatureFlag.AI_CLINICAL_RECS_ENABLED: False,
    FeatureFlag.AI_ESCALATION_ENABLED: False,
    # PR-B: patient-facing AI/OCR — default OFF
    FeatureFlag.AI_ASSISTANT: False,
    FeatureFlag.OCR: False,
    FeatureFlag.AI_RECOMMENDATION: False,
    FeatureFlag.OCR_CLOUD_FALLBACK: False,  # opt-in only; never silently send images out
    # PA-11: rules-first insight is deterministic + guardrail-checked → safe ON by default.
    FeatureFlag.CLINICAL_INSIGHT: True,
    FeatureFlag.CLINICAL_INSIGHT_AI: False,  # LLM rephrasing OFF in v1 (rules-only)
}


def is_enabled(flag: FeatureFlag | str) -> bool:
    """Check if a feature flag is enabled.

    Guards must fail closed (unknown flag = disabled).
    Reads from environment variables: FEATURE_<FLAG_NAME> or the MCP-prefixed
    alias MCP_FEATURE_<FLAG_NAME> (e.g. MCP_FEATURE_OCR=false), =true|false.
    """
    try:
        if isinstance(flag, str):
            flag_enum = FeatureFlag(flag)
        else:
            flag_enum = flag
    except ValueError:
        return False  # fail closed on unknown flag

    if flag_enum not in FeatureFlag:
        return False

    truthy = ("true", "1", "yes", "on", "t")
    # FEATURE_<NAME> takes precedence; MCP_FEATURE_<NAME> is an accepted alias.
    for env_var_name in (f"FEATURE_{flag_enum.name}", f"MCP_FEATURE_{flag_enum.name}"):
        env_val = os.getenv(env_var_name)
        if env_val is not None:
            return env_val.lower() in truthy

    return _DEFAULTS.get(flag_enum, False)
