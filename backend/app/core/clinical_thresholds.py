import dataclasses
import os
from dataclasses import dataclass


@dataclass
class VitalThreshold:
    metric_type: str
    critical_high: float | None
    critical_low: float | None
    unit: str
    source: str           # e.g. "ADA 2024", "AHA 2023"
    board_approved: bool  # False until Medical Board signs off
    proposed: bool        # True = PROPOSED_THRESHOLD

_DEFAULT_VITAL_THRESHOLDS = {
    "blood_pressure_systolic": VitalThreshold(
        metric_type="blood_pressure_systolic",
        critical_high=180.0,
        critical_low=80.0,
        unit="mmHg",
        source="AHA 2023",
        board_approved=False,
        proposed=True
    ),
    "blood_pressure_diastolic": VitalThreshold(
        metric_type="blood_pressure_diastolic",
        critical_high=120.0,
        critical_low=50.0,
        unit="mmHg",
        source="AHA 2023",
        board_approved=False,
        proposed=True
    ),
    "fasting_glucose": VitalThreshold(
        metric_type="fasting_glucose",
        critical_high=500.0,
        critical_low=54.0,
        unit="mg/dL",
        source="ADA 2024",
        board_approved=False,
        proposed=True
    ),
    "postprandial_glucose": VitalThreshold(
        metric_type="postprandial_glucose",
        critical_high=500.0,
        critical_low=54.0,
        unit="mg/dL",
        source="ADA 2024",
        board_approved=False,
        proposed=True
    ),
    "temperature": VitalThreshold(
        metric_type="temperature",
        critical_high=39.0,
        critical_low=35.0,
        unit="°C",
        source="WHO 2023",
        board_approved=False,
        proposed=True
    ),
    "bmi": VitalThreshold(
        metric_type="bmi",
        critical_high=40.0,
        critical_low=15.0,
        unit="kg/m²",
        source="WHO 2023",
        board_approved=False,
        proposed=True
    ),
    "sleep_hours": VitalThreshold(
        metric_type="sleep_hours",
        critical_high=None,
        critical_low=None,
        unit="h",
        source="NSF 2023",
        board_approved=False,
        proposed=True
    ),
    "steps": VitalThreshold(
        metric_type="steps",
        critical_high=None,
        critical_low=None,
        unit="steps",
        source="WHO 2023",
        board_approved=False,
        proposed=True
    ),
    "activity_minutes": VitalThreshold(
        metric_type="activity_minutes",
        critical_high=None,
        critical_low=None,
        unit="min",
        source="WHO 2023",
        board_approved=False,
        proposed=True
    ),
}

_DEFAULT_SYMPTOMS = {
    "chest_pain": ("đau ngực", "tức ngực", "đau thắt ngực", "nặng ngực"),
    "dyspnea": ("khó thở", "hụt hơi", "thở gấp", "không thở được"),
    "cold_sweat": ("vã mồ hôi", "toát mồ hôi lạnh", "đổ mồ hôi lạnh"),
    "stroke_signs": (
        "yếu liệt", "liệt nửa người", "méo miệng", "nói khó", "nói đớ",
        "tê nửa người", "đột quỵ", "lú lẫn",
    ),
    "syncope": ("ngất", "bất tỉnh", "mất ý thức", "xỉu"),
    "severe_hypertension_combo": ("đau đầu dữ dội", "mờ mắt", "hoa mắt dữ dội"),
    "hyperglycemia_combo": ("nôn", "mệt lả", "lơ mơ", "khát nước dữ dội"),
    "severe_hypoglycemia": ("run tay", "vã mồ hôi lú lẫn", "hạ đường huyết nặng", "co giật"),
    "severe_abdominal_pain": ("đau bụng dữ dội", "đau bụng quặn dữ dội"),
    "cyanosis": ("tím tái", "môi tím", "tím môi"),
    "suicidal_ideation": ("tự tử", "tự hại", "muốn chết", "kết liễu"),
    "anaphylaxis": ("sốc phản vệ", "phù nề đường thở", "co thắt phế quản", "phát ban toàn thân"),
}

def parse_yaml_lines(lines: list[str]) -> dict:
    """A simple parser for the specific schema in clinical_thresholds.yml."""
    result = {}
    current_key_path = []
    
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
            
        indent = len(line) - len(line.lstrip())
        level = indent // 2
        current_key_path = current_key_path[:level]
        
        if stripped.startswith("- "):
            val = stripped[2:].strip().strip('"').strip("'")
            container = result
            for k in current_key_path:
                container = container[k]
            if isinstance(container, list):
                container.append(val)
        elif ":" in stripped:
            key, val = stripped.split(":", 1)
            key = key.strip().strip('"').strip("'")
            val = val.strip()
            
            container = result
            for k in current_key_path:
                if k not in container:
                    container[k] = {}
                container = container[k]
                
            if val == "":
                if len(current_key_path) > 0 and current_key_path[0] == "symptoms":
                    container[key] = []
                else:
                    container[key] = {}
                current_key_path.append(key)
            else:
                val = val.split("#")[0].strip()
                if val.lower() == "true":
                    parsed_val = True
                elif val.lower() == "false":
                    parsed_val = False
                elif val.lower() == "null" or val.lower() == "none":
                    parsed_val = None
                else:
                    try:
                        parsed_val = float(val)
                        if parsed_val.is_integer():
                            parsed_val = int(parsed_val)
                    except ValueError:
                        parsed_val = val.strip('"').strip("'")
                container[key] = parsed_val
    return result

def parse_yaml_file(file_path: str) -> dict:
    if not os.path.exists(file_path):
        return {}
    try:
        with open(file_path, encoding="utf-8") as f:
            lines = f.readlines()
        return parse_yaml_lines(lines)
    except Exception:
        return {}

def load_from_env(
    vitals: dict[str, VitalThreshold],
    symptoms: dict[str, tuple[str, ...]]
) -> tuple[dict[str, VitalThreshold], dict[str, tuple[str, ...]]]:
    updated_vitals = {k: dataclasses.replace(v) for k, v in vitals.items()}
    updated_symptoms = {k: v for k, v in symptoms.items()}

    for metric in updated_vitals.keys():
        metric_upper = metric.upper()
        
        high_val = os.getenv(f"CLINICAL_{metric_upper}_CRITICAL_HIGH")
        if high_val is not None:
            updated_vitals[metric].critical_high = (
                float(high_val) if high_val.lower() != "none" else None
            )
            
        low_val = os.getenv(f"CLINICAL_{metric_upper}_CRITICAL_LOW")
        if low_val is not None:
            updated_vitals[metric].critical_low = (
                float(low_val) if low_val.lower() != "none" else None
            )
            
        approved_val = os.getenv(f"CLINICAL_{metric_upper}_BOARD_APPROVED")
        if approved_val is not None:
            updated_vitals[metric].board_approved = approved_val.lower() in ("true", "1", "yes")
            
        proposed_val = os.getenv(f"CLINICAL_{metric_upper}_PROPOSED")
        if proposed_val is not None:
            updated_vitals[metric].proposed = proposed_val.lower() in ("true", "1", "yes")

    for symptom in updated_symptoms.keys():
        symptom_upper = symptom.upper()
        symptom_val = os.getenv(f"CLINICAL_SYMPTOMS_{symptom_upper}")
        if symptom_val is not None:
            updated_symptoms[symptom] = tuple(
                kw.strip() for kw in symptom_val.split(",") if kw.strip()
            )

    return updated_vitals, updated_symptoms

def load_thresholds() -> tuple[dict[str, VitalThreshold], dict[str, tuple[str, ...]]]:
    vitals = {k: dataclasses.replace(v) for k, v in _DEFAULT_VITAL_THRESHOLDS.items()}
    symptoms = {k: v for k, v in _DEFAULT_SYMPTOMS.items()}
    
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "config",
        "clinical_thresholds.yml"
    )
    
    config_data = parse_yaml_file(config_path)
    
    if "vitals" in config_data:
        for metric, data in config_data["vitals"].items():
            if metric in vitals:
                if "critical_high" in data:
                    vitals[metric].critical_high = data["critical_high"]
                if "critical_low" in data:
                    vitals[metric].critical_low = data["critical_low"]
                if "unit" in data:
                    vitals[metric].unit = data["unit"]
                if "source" in data:
                    vitals[metric].source = data["source"]
                if "board_approved" in data:
                    vitals[metric].board_approved = data["board_approved"]
                if "proposed" in data:
                    vitals[metric].proposed = data["proposed"]
                    
    if "symptoms" in config_data:
        for symptom, keywords in config_data["symptoms"].items():
            if isinstance(keywords, list):
                symptoms[symptom] = tuple(keywords)
                
    vitals, symptoms = load_from_env(vitals, symptoms)
    
    return vitals, symptoms

# Loaded active values
VITAL_THRESHOLDS, RED_FLAG_SYMPTOMS = load_thresholds()

def get_symptom_keywords() -> dict[str, tuple[str, ...]]:
    """Return the loaded red-flag symptom keyword map."""
    return dict(RED_FLAG_SYMPTOMS)


def get_vital_thresholds_dict() -> dict[str, dict[str, float]]:
    result = {}
    for metric, vt in VITAL_THRESHOLDS.items():
        result[metric] = {}
        if vt.critical_high is not None:
            result[metric]["critical_high"] = vt.critical_high
        if vt.critical_low is not None:
            result[metric]["critical_low"] = vt.critical_low
    return result
