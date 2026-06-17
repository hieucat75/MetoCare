import os

from app.core.clinical_thresholds import load_thresholds, parse_yaml_lines


def test_clinical_threshold_defaults():
    # Load defaults
    vitals, symptoms = load_thresholds()
    
    # Check that all default vitals have proposed=True and board_approved=False
    for metric, vt in vitals.items():
        assert vt.proposed is True, f"{metric} must be proposed=True by default"
        assert vt.board_approved is False, f"{metric} must be board_approved=False by default"
        
    # Check default values are present
    assert vitals["blood_pressure_systolic"].critical_high == 180.0
    assert vitals["blood_pressure_systolic"].critical_low == 80.0
    assert vitals["fasting_glucose"].critical_high == 300.0
    assert vitals["fasting_glucose"].critical_low == 54.0

    # Check that suicidal_ideation and anaphylaxis are in symptoms list
    assert "suicidal_ideation" in symptoms
    assert "anaphylaxis" in symptoms
    assert "tự tử" in symptoms["suicidal_ideation"]
    assert "sốc phản vệ" in symptoms["anaphylaxis"]

def test_clinical_threshold_env_overrides():
    # Set env overrides
    os.environ["CLINICAL_BLOOD_PRESSURE_SYSTOLIC_CRITICAL_HIGH"] = "195.0"
    os.environ["CLINICAL_BLOOD_PRESSURE_SYSTOLIC_BOARD_APPROVED"] = "true"
    os.environ["CLINICAL_BLOOD_PRESSURE_SYSTOLIC_PROPOSED"] = "false"
    os.environ["CLINICAL_SYMPTOMS_SUICIDAL_IDEATION"] = "tu sat, muon chet"
    
    try:
        vitals, symptoms = load_thresholds()
        
        bp_sys = vitals["blood_pressure_systolic"]
        assert bp_sys.critical_high == 195.0
        assert bp_sys.board_approved is True
        assert bp_sys.proposed is False
        
        # Test symptom override
        assert symptoms["suicidal_ideation"] == ("tu sat", "muon chet")
        
    finally:
        # Clean up
        for key in [
            "CLINICAL_BLOOD_PRESSURE_SYSTOLIC_CRITICAL_HIGH",
            "CLINICAL_BLOOD_PRESSURE_SYSTOLIC_BOARD_APPROVED",
            "CLINICAL_BLOOD_PRESSURE_SYSTOLIC_PROPOSED",
            "CLINICAL_SYMPTOMS_SUICIDAL_IDEATION"
        ]:
            if key in os.environ:
                del os.environ[key]

def test_yaml_parser_helper():
    lines = [
        "vitals:",
        "  blood_pressure_systolic:",
        "    critical_high: 175.0",
        "    proposed: false",
        "symptoms:",
        "  chest_pain:",
        "    - dau nguc",
        "    - tuc nguc"
    ]
    data = parse_yaml_lines(lines)
    assert data["vitals"]["blood_pressure_systolic"]["critical_high"] == 175.0
    assert data["vitals"]["blood_pressure_systolic"]["proposed"] is False
    assert data["symptoms"]["chest_pain"] == ["dau nguc", "tuc nguc"]
