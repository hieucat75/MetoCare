import os

from app.core.feature_flags import FeatureFlag, is_enabled


def test_feature_flag_defaults():
    # Defaults: AI features OFF, consent + doctor review ON
    assert is_enabled(FeatureFlag.AI_TRIAGE) is False
    assert is_enabled(FeatureFlag.AI_LAB_INTERPRET) is False
    assert is_enabled(FeatureFlag.AI_CARE_PLAN_DRAFT) is False
    assert is_enabled(FeatureFlag.AI_SAFETY_LAYER) is False
    assert is_enabled(FeatureFlag.DOCTOR_REVIEW_GATE) is True
    assert is_enabled(FeatureFlag.CONSENT_GATE) is True

def test_feature_flag_fail_closed():
    # Unknown flag should be disabled (fail closed)
    assert is_enabled("unknown_flag") is False
    assert is_enabled("random_name") is False

def test_feature_flag_env_overrides():
    # Test enabling a disabled flag
    os.environ["FEATURE_AI_TRIAGE"] = "true"
    assert is_enabled(FeatureFlag.AI_TRIAGE) is True
    
    # Test disabling an enabled flag
    os.environ["FEATURE_DOCTOR_REVIEW_GATE"] = "false"
    assert is_enabled(FeatureFlag.DOCTOR_REVIEW_GATE) is False

    # Test case insensitivity / alternative true values
    os.environ["FEATURE_AI_LAB_INTERPRET"] = "1"
    assert is_enabled(FeatureFlag.AI_LAB_INTERPRET) is True

    os.environ["FEATURE_AI_SAFETY_LAYER"] = "yes"
    assert is_enabled(FeatureFlag.AI_SAFETY_LAYER) is True  # "yes" is a truthy value

    os.environ["FEATURE_AI_SAFETY_LAYER"] = "off"
    assert is_enabled(FeatureFlag.AI_SAFETY_LAYER) is False  # "off" is not a truthy value

    os.environ["FEATURE_AI_SAFETY_LAYER"] = "on"
    assert is_enabled(FeatureFlag.AI_SAFETY_LAYER) is True

    # Clean up
    env_keys = [
        "FEATURE_AI_TRIAGE", "FEATURE_DOCTOR_REVIEW_GATE",
        "FEATURE_AI_LAB_INTERPRET", "FEATURE_AI_SAFETY_LAYER",
    ]
    for key in env_keys:
        if key in os.environ:
            del os.environ[key]
