import enum
import os


class FeatureFlag(enum.StrEnum):
    AI_TRIAGE          = "ai_triage"            # DISABLED until Medical Board approval
    AI_LAB_INTERPRET   = "ai_lab_interpret"     # DISABLED until Medical Board approval
    AI_CARE_PLAN_DRAFT = "ai_care_plan_draft"   # DISABLED until Medical Board approval
    AI_SAFETY_LAYER    = "ai_safety_layer"      # DISABLED until Medical Board approval
    DOCTOR_REVIEW_GATE = "doctor_review_gate"   # ENABLED (mandatory)
    CONSENT_GATE       = "consent_gate"         # ENABLED (mandatory)
    # T5 / C3: AI session feature flags — default OFF (fail-closed)
    AI_SESSION_ENABLED      = "ai_session_enabled"       # Gates AISession creation
    AI_CLINICAL_RECS_ENABLED = "ai_clinical_recs_enabled" # Gates viewing/acting on recs
    AI_ESCALATION_ENABLED   = "ai_escalation_enabled"    # Gates escalation workflows

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
}

def is_enabled(flag: FeatureFlag | str) -> bool:
    """Check if a feature flag is enabled.
    
    Guards must fail closed (unknown flag = disabled).
    Reads from environment variables: FEATURE_<FLAG_NAME>=true|false.
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

    env_var_name = f"FEATURE_{flag_enum.name}"
    env_val = os.getenv(env_var_name)
    if env_val is not None:
        return env_val.lower() in ("true", "1", "yes", "on", "t")

    return _DEFAULTS.get(flag_enum, False)
