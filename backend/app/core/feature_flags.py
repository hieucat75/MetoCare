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
    # Meto Clinical Copilot: doctor-facing AI decision-support (calls a real LLM
    # over PHI) — default OFF (fail-closed), same precedent as AI_SESSION_ENABLED.
    CLINICAL_COPILOT = "clinical_copilot"
    # Clinic SaaS Phase C0: multi-tenant clinic/branch/membership/subscription
    # module — default OFF (fail-closed) until the tenant-isolation surface is
    # verified end-to-end, same precedent as CLINICAL_COPILOT/AI_SESSION_ENABLED.
    CLINIC_SAAS = "clinic_saas"
    # Medication Knowledge K2 Slice 1: read-only patient/doctor knowledge
    # retrieval over the 5 ADR-13 knowledge tables (mandatory reversible
    # control per ADR-15 §K.1) — default OFF, same fail-closed precedent as
    # CLINICAL_COPILOT/CLINIC_SAAS. Disabling stops new requests from
    # reaching either route; never deletes stored knowledge or provenance.
    MEDICATION_KNOWLEDGE_RETRIEVAL = "medication_knowledge_retrieval"
    # Medication Knowledge Slice 0 (docs/medication-management/
    # MEDICATION_KNOWLEDGE_SLICE0_ORIGIN_PROVENANCE_FLAGS_IMPLEMENTATION_PLAN.md):
    # independently-toggleable capability flags for the ingestion/AI
    # pipeline stages that do not exist yet (Slice 2+) — reserved now so
    # each future slice ships already gated, per ADR-15 §K.1's mandatory
    # reversible-controls requirement. All default OFF; enforcement lives
    # in service/domain logic, not just the router layer, once each
    # capability's service code exists.
    MEDICATION_EXTERNAL_SOURCE_INGESTION = "medication_external_source_ingestion"
    MEDICATION_AI_NORMALIZATION = "medication_ai_normalization"
    MEDICATION_AI_SYNTHESIS = "medication_ai_synthesis"
    MEDICATION_AI_DOCTOR_CONTENT = "medication_ai_doctor_content"
    MEDICATION_AI_PATIENT_CONTENT = "medication_ai_patient_content"
    # Gates evidence_level/theme exposure in K2 responses (ADR-15 §A: both
    # are "external but versioned/experimental"). OFF omits both fields
    # entirely (never null) via response_model_exclude_unset — never
    # deletes or mutates the stored value.
    MEDICATION_EXPERIMENTAL_VOCABULARY = "medication_experimental_vocabulary"


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
    FeatureFlag.CLINICAL_COPILOT: False,  # fail-closed — calls a real LLM over PHI
    FeatureFlag.CLINIC_SAAS: False,  # fail-closed — new multi-tenant module
    FeatureFlag.MEDICATION_KNOWLEDGE_RETRIEVAL: False,  # fail-closed — new read surface
    # Medication Knowledge Slice 0 — all fail-closed, no capability exists yet.
    FeatureFlag.MEDICATION_EXTERNAL_SOURCE_INGESTION: False,
    FeatureFlag.MEDICATION_AI_NORMALIZATION: False,
    FeatureFlag.MEDICATION_AI_SYNTHESIS: False,
    FeatureFlag.MEDICATION_AI_DOCTOR_CONTENT: False,
    FeatureFlag.MEDICATION_AI_PATIENT_CONTENT: False,
    FeatureFlag.MEDICATION_EXPERIMENTAL_VOCABULARY: False,
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
