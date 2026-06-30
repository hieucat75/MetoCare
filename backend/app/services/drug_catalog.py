"""Drug catalog service: seed, suggest, and normalize medication names.

Design constraints
------------------
- NO prescribing logic.  This service identifies and groups drug names only.
- All search is done in Python (not DB-side) so the same code runs on SQLite
  (dev/test) and Postgres (prod) without dialect-specific SQL.
- The safety_notice field is always present on every outbound schema — enforced
  at the schema layer, not here.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.drug_catalog import DrugEntry
from app.schemas.drug_catalog import SAFETY_NOTICE, DrugSuggestItem, MedicationMatch

# ---------------------------------------------------------------------------
# Text normalisation helpers
# ---------------------------------------------------------------------------

_DOSAGE_RE = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*"
    r"(?:mg|mcg|µg|ug|g|ml|l|iu|kcal|units?|tabs?|viên|gói|lọ|ống)\b",
    re.IGNORECASE,
)


def _normalize(text: str) -> str:
    """Accent-strip, lowercase, collapse whitespace."""
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_only = nfkd.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", ascii_only.lower()).strip()


def _strip_dosage(text: str) -> str:
    """Remove dosage tokens like '500mg', '10 mcg', '125mcg'."""
    return re.sub(r"\s+", " ", _DOSAGE_RE.sub("", text)).strip(" ,.")


def _parse_dosage(text: str) -> str | None:
    """Extract dosage string if present."""
    m = _DOSAGE_RE.search(text)
    return m.group(0).strip() if m else None


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _score_against(candidate: str, q_norm: str) -> float:
    c = _normalize(candidate)
    if not c:
        return 0.0
    if c == q_norm:
        return 100.0
    if c.startswith(q_norm):
        return 90.0
    if q_norm in c:
        return 80.0
    if len(q_norm) >= 3 and c.startswith(q_norm[:3]):
        return 45.0
    return 0.0


def _best_score_and_match(entry: DrugEntry, q_norm: str) -> tuple[float, str]:
    candidates: list[tuple[str, str]] = (
        [(entry.generic_name, entry.generic_name)]
        + [(b, b) for b in (entry.brand_names or [])]
        + [(a, a) for a in (entry.aliases or [])]
        + [(v, v) for v in (entry.vietnamese_common_names or [])]
        + [(i, i) for i in (entry.active_ingredients or [])]
    )
    best_score = 0.0
    best_name = entry.generic_name
    for raw, label in candidates:
        s = _score_against(raw, q_norm)
        if s > best_score:
            best_score = s
            best_name = label
    return best_score, best_name


def _to_suggest_item(entry: DrugEntry, score: float, matched_name: str) -> DrugSuggestItem:
    display = (entry.brand_names or [entry.generic_name])[0]
    return DrugSuggestItem(
        id=entry.id,
        display_name=display,
        generic_name=entry.generic_name,
        matched_name=matched_name,
        brand_names=list(entry.brand_names or []),
        drug_class=entry.drug_class,
        metric_groups=list(entry.metric_groups or []),
        prescription_required=entry.prescription_required,
        caution_flags=list(entry.caution_flags or []),
        confidence_score=round(score, 1),
        safety_notice=SAFETY_NOTICE,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def suggest_drugs(
    db: Session,
    *,
    q: str,
    metric_group: str | None = None,
    limit: int = 10,
    strict: bool = False,
) -> list[DrugSuggestItem]:
    """Return ranked drug suggestions for a free-text query.

    Parameters
    ----------
    q:            Raw user input (may include dosage text, mixed case, accents).
    metric_group: Optional group key to boost/filter (e.g. "lipid", "diabetes").
    limit:        Maximum results (1-25).
    strict:       If True, restrict results to drugs in metric_group only.
    """
    limit = max(1, min(limit, 25))
    q_norm = _normalize(_strip_dosage(q))
    if not q_norm:
        return []

    entries = db.query(DrugEntry).filter(DrugEntry.is_active.is_(True)).all()

    scored: list[tuple[float, DrugEntry, str]] = []
    for entry in entries:
        score, matched = _best_score_and_match(entry, q_norm)
        if score <= 0:
            continue
        in_group = metric_group is not None and metric_group in (entry.metric_groups or [])
        if strict and metric_group and not in_group:
            continue
        if in_group:
            score = min(score + 10.0, 100.0)
        scored.append((score, entry, matched))

    scored.sort(key=lambda t: -t[0])
    return [_to_suggest_item(e, s, m) for s, e, m in scored[:limit]]


@dataclass
class _NormResult:
    drug_id: str | None
    parsed_name: str
    dosage_text: str | None
    confidence: float
    candidates: list[DrugSuggestItem]


def normalize_medication_name(db: Session, *, input_text: str) -> MedicationMatch:
    """Map a free-text medication name to a canonical catalog entry.

    Handles brand-to-generic, accents, dosage stripping, and casing.
    Returns confidence 0-100 and up to 5 ambiguous candidates.
    """
    dosage = _parse_dosage(input_text)
    cleaned = _strip_dosage(input_text)
    suggestions = suggest_drugs(db, q=cleaned, limit=5)

    top = suggestions[0] if suggestions else None
    return MedicationMatch(
        drug_id=top.id if top and top.confidence_score >= 80 else None,
        parsed_name=cleaned.strip(),
        dosage_text=dosage,
        confidence=top.confidence_score if top else 0.0,
        ambiguous_matches=suggestions,
        safety_notice=SAFETY_NOTICE,
    )


# ---------------------------------------------------------------------------
# Seed catalog
# ---------------------------------------------------------------------------

_SEED: list[dict] = [
    # ── Diabetes / blood glucose ──────────────────────────────────────────
    {
        "generic_name": "metformin",
        "brand_names": ["Glucophage", "Glumetza", "Metformin"],
        "vietnamese_common_names": ["Metformin", "Glucophage"],
        "aliases": ["metformin hydrochloride", "metformin hcl"],
        "active_ingredients": ["metformin hydrochloride"],
        "drug_class": "biguanide",
        "metric_groups": ["diabetes"],
        "common_indications": ["Đái tháo đường type 2"],
        "prescription_required": True,
        "caution_flags": ["lactic_acidosis_risk"],
        "contraindication_keywords": ["severe_renal_impairment", "eGFR<30"],
        "renal_caution": True,
        "hepatic_caution": True,
        "pregnancy_caution": False,
        "notes_for_matching_only": "Most common first-line T2DM drug in VN",
    },
    {
        "generic_name": "gliclazide",
        "brand_names": ["Diamicron", "Gliclazide MR", "Glyclada"],
        "vietnamese_common_names": ["Diamicron", "Gliclazide"],
        "aliases": ["gliclazide mr", "gliclazide modified release"],
        "active_ingredients": ["gliclazide"],
        "drug_class": "sulfonylurea",
        "metric_groups": ["diabetes"],
        "common_indications": ["Đái tháo đường type 2"],
        "prescription_required": True,
        "caution_flags": ["hypoglycemia_risk"],
        "contraindication_keywords": ["severe_renal_impairment", "type1_diabetes"],
        "renal_caution": True,
        "hepatic_caution": False,
        "pregnancy_caution": True,
    },
    {
        "generic_name": "glimepiride",
        "brand_names": ["Amaryl", "Glimepiride", "Glimpid"],
        "vietnamese_common_names": ["Amaryl", "Glimepiride"],
        "aliases": ["glimepirid"],
        "active_ingredients": ["glimepiride"],
        "drug_class": "sulfonylurea",
        "metric_groups": ["diabetes"],
        "common_indications": ["Đái tháo đường type 2"],
        "prescription_required": True,
        "caution_flags": ["hypoglycemia_risk"],
        "contraindication_keywords": ["severe_renal_impairment"],
        "renal_caution": True,
        "hepatic_caution": False,
        "pregnancy_caution": True,
    },
    {
        "generic_name": "sitagliptin",
        "brand_names": ["Januvia", "Sitagliptin"],
        "vietnamese_common_names": ["Januvia", "Sitagliptin"],
        "aliases": ["sitagliptin phosphate"],
        "active_ingredients": ["sitagliptin phosphate monohydrate"],
        "drug_class": "dpp4_inhibitor",
        "metric_groups": ["diabetes"],
        "common_indications": ["Đái tháo đường type 2"],
        "prescription_required": True,
        "caution_flags": [],
        "contraindication_keywords": [],
        "renal_caution": True,
        "hepatic_caution": False,
        "pregnancy_caution": False,
    },
    {
        "generic_name": "vildagliptin",
        "brand_names": ["Galvus", "Vildagliptin"],
        "vietnamese_common_names": ["Galvus", "Vildagliptin"],
        "aliases": [],
        "active_ingredients": ["vildagliptin"],
        "drug_class": "dpp4_inhibitor",
        "metric_groups": ["diabetes"],
        "common_indications": ["Đái tháo đường type 2"],
        "prescription_required": True,
        "caution_flags": ["liver_enzyme_elevation"],
        "contraindication_keywords": ["severe_hepatic_impairment"],
        "renal_caution": False,
        "hepatic_caution": True,
        "pregnancy_caution": False,
    },
    {
        "generic_name": "empagliflozin",
        "brand_names": ["Jardiance", "Empagliflozin"],
        "vietnamese_common_names": ["Jardiance", "Empagliflozin"],
        "aliases": [],
        "active_ingredients": ["empagliflozin"],
        "drug_class": "sglt2_inhibitor",
        "metric_groups": ["diabetes", "kidney"],
        "common_indications": ["Đái tháo đường type 2", "Bảo vệ tim mạch và thận"],
        "prescription_required": True,
        "caution_flags": ["dka_risk", "uti_risk"],
        "contraindication_keywords": ["eGFR<30"],
        "renal_caution": True,
        "hepatic_caution": False,
        "pregnancy_caution": True,
    },
    {
        "generic_name": "dapagliflozin",
        "brand_names": ["Forxiga", "Farxiga", "Dapagliflozin"],
        "vietnamese_common_names": ["Forxiga", "Dapagliflozin"],
        "aliases": [],
        "active_ingredients": ["dapagliflozin propanediol"],
        "drug_class": "sglt2_inhibitor",
        "metric_groups": ["diabetes", "kidney"],
        "common_indications": ["Đái tháo đường type 2", "Suy tim", "Bệnh thận mạn"],
        "prescription_required": True,
        "caution_flags": ["dka_risk", "uti_risk"],
        "contraindication_keywords": ["eGFR<25"],
        "renal_caution": True,
        "hepatic_caution": False,
        "pregnancy_caution": True,
    },
    {
        "generic_name": "insulin glargine",
        "brand_names": ["Lantus", "Toujeo", "Basaglar"],
        "vietnamese_common_names": ["Lantus", "Insulin Glargine", "Toujeo"],
        "aliases": ["glargine insulin", "basal insulin", "long acting insulin"],
        "active_ingredients": ["insulin glargine"],
        "drug_class": "long_acting_insulin",
        "metric_groups": ["diabetes"],
        "common_indications": ["Đái tháo đường type 1", "Đái tháo đường type 2"],
        "prescription_required": True,
        "caution_flags": ["hypoglycemia_risk", "injection_site_reaction"],
        "contraindication_keywords": [],
        "renal_caution": True,
        "hepatic_caution": False,
        "pregnancy_caution": False,
        "notes_for_matching_only": "Match 'lantus', 'basal insulin', 'glargine'",
    },
    {
        "generic_name": "insulin aspart",
        "brand_names": ["NovoRapid", "Fiasp", "NovoLog"],
        "vietnamese_common_names": ["NovoRapid", "Insulin Aspart"],
        "aliases": ["rapid acting insulin", "mealtime insulin", "bolus insulin"],
        "active_ingredients": ["insulin aspart"],
        "drug_class": "rapid_acting_insulin",
        "metric_groups": ["diabetes"],
        "common_indications": ["Đái tháo đường type 1", "Đái tháo đường type 2"],
        "prescription_required": True,
        "caution_flags": ["hypoglycemia_risk"],
        "contraindication_keywords": [],
        "renal_caution": True,
        "hepatic_caution": False,
        "pregnancy_caution": False,
    },
    {
        "generic_name": "pioglitazone",
        "brand_names": ["Actos", "Pioglitazone"],
        "vietnamese_common_names": ["Actos", "Pioglitazone"],
        "aliases": ["thiazolidinedione"],
        "active_ingredients": ["pioglitazone hydrochloride"],
        "drug_class": "thiazolidinedione",
        "metric_groups": ["diabetes"],
        "common_indications": ["Đái tháo đường type 2"],
        "prescription_required": True,
        "caution_flags": ["fluid_retention", "heart_failure_risk", "bladder_cancer_risk"],
        "contraindication_keywords": ["heart_failure", "bladder_cancer"],
        "renal_caution": False,
        "hepatic_caution": True,
        "pregnancy_caution": True,
    },
    # ── Lipid / cholesterol ───────────────────────────────────────────────
    {
        "generic_name": "rosuvastatin",
        "brand_names": ["Crestor", "Rosuca", "Rovast", "Rosuvast"],
        "vietnamese_common_names": ["Crestor", "Rosuvastatin"],
        "aliases": ["rosuvastatin calcium"],
        "active_ingredients": ["rosuvastatin calcium"],
        "drug_class": "statin",
        "metric_groups": ["lipid"],
        "common_indications": ["Tăng cholesterol máu", "Rối loạn lipid máu"],
        "prescription_required": True,
        "caution_flags": ["myopathy", "rhabdomyolysis_risk", "liver_toxicity"],
        "contraindication_keywords": ["pregnancy", "severe_hepatic_impairment"],
        "renal_caution": True,
        "hepatic_caution": True,
        "pregnancy_caution": True,
        "notes_for_matching_only": "Also match 'crestor' brand -> rosuvastatin generic",
    },
    {
        "generic_name": "atorvastatin",
        "brand_names": ["Lipitor", "Atorlip", "Atorvast", "Sortis"],
        "vietnamese_common_names": ["Lipitor", "Atorvastatin"],
        "aliases": ["atorvastatin calcium"],
        "active_ingredients": ["atorvastatin calcium trihydrate"],
        "drug_class": "statin",
        "metric_groups": ["lipid"],
        "common_indications": ["Tăng cholesterol máu", "Rối loạn lipid máu"],
        "prescription_required": True,
        "caution_flags": ["myopathy", "liver_toxicity"],
        "contraindication_keywords": ["pregnancy", "severe_hepatic_impairment"],
        "renal_caution": False,
        "hepatic_caution": True,
        "pregnancy_caution": True,
    },
    {
        "generic_name": "simvastatin",
        "brand_names": ["Zocor", "Simvast", "Simcard"],
        "vietnamese_common_names": ["Zocor", "Simvastatin"],
        "aliases": ["simvastatin"],
        "active_ingredients": ["simvastatin"],
        "drug_class": "statin",
        "metric_groups": ["lipid"],
        "common_indications": ["Tăng cholesterol máu"],
        "prescription_required": True,
        "caution_flags": ["myopathy", "CYP3A4_interactions"],
        "contraindication_keywords": ["pregnancy", "severe_hepatic_impairment"],
        "renal_caution": False,
        "hepatic_caution": True,
        "pregnancy_caution": True,
    },
    {
        "generic_name": "fenofibrate",
        "brand_names": ["Tricor", "Lipanthyl", "Fenolib"],
        "vietnamese_common_names": ["Lipanthyl", "Fenofibrate"],
        "aliases": ["fenofibric acid"],
        "active_ingredients": ["fenofibrate"],
        "drug_class": "fibrate",
        "metric_groups": ["lipid"],
        "common_indications": ["Tăng triglyceride máu", "Rối loạn lipid máu hỗn hợp"],
        "prescription_required": True,
        "caution_flags": ["myopathy_when_combined_with_statin", "gallstone_risk"],
        "contraindication_keywords": ["severe_renal_impairment", "gallbladder_disease"],
        "renal_caution": True,
        "hepatic_caution": True,
        "pregnancy_caution": True,
    },
    {
        "generic_name": "ezetimibe",
        "brand_names": ["Ezetrol", "Zetia", "Ezetimibe"],
        "vietnamese_common_names": ["Ezetrol", "Ezetimibe"],
        "aliases": [],
        "active_ingredients": ["ezetimibe"],
        "drug_class": "cholesterol_absorption_inhibitor",
        "metric_groups": ["lipid"],
        "common_indications": ["Tăng cholesterol máu"],
        "prescription_required": True,
        "caution_flags": [],
        "contraindication_keywords": ["severe_hepatic_impairment"],
        "renal_caution": False,
        "hepatic_caution": True,
        "pregnancy_caution": True,
    },
    # ── Blood pressure / cardiovascular ──────────────────────────────────
    {
        "generic_name": "amlodipine",
        "brand_names": ["Norvasc", "Amlor", "Amlodipin", "Stamlo"],
        "vietnamese_common_names": ["Norvasc", "Amlodipine", "Amlor"],
        "aliases": ["amlodipine besylate", "amlodipine besilate"],
        "active_ingredients": ["amlodipine besilate"],
        "drug_class": "calcium_channel_blocker",
        "metric_groups": ["hypertension"],
        "common_indications": ["Tăng huyết áp", "Đau thắt ngực"],
        "prescription_required": True,
        "caution_flags": ["ankle_edema", "hypotension"],
        "contraindication_keywords": ["severe_aortic_stenosis"],
        "renal_caution": False,
        "hepatic_caution": True,
        "pregnancy_caution": True,
    },
    {
        "generic_name": "perindopril",
        "brand_names": ["Coversyl", "Acertil", "Coversum"],
        "vietnamese_common_names": ["Coversyl", "Perindopril"],
        "aliases": ["perindopril arginine", "perindopril erbumine"],
        "active_ingredients": ["perindopril arginine"],
        "drug_class": "ace_inhibitor",
        "metric_groups": ["hypertension"],
        "common_indications": ["Tăng huyết áp", "Suy tim", "Bảo vệ tim mạch"],
        "prescription_required": True,
        "caution_flags": ["dry_cough", "hyperkalemia", "angioedema_risk"],
        "contraindication_keywords": [
            "pregnancy", "bilateral_renal_artery_stenosis", "angioedema_history",
        ],
        "renal_caution": True,
        "hepatic_caution": False,
        "pregnancy_caution": True,
        "notes_for_matching_only": "Match both 'perindopril' and 'coversyl'",
    },
    {
        "generic_name": "losartan",
        "brand_names": ["Cozaar", "Losartas", "Lozap"],
        "vietnamese_common_names": ["Cozaar", "Losartan"],
        "aliases": ["losartan potassium"],
        "active_ingredients": ["losartan potassium"],
        "drug_class": "arb",
        "metric_groups": ["hypertension", "kidney"],
        "common_indications": ["Tăng huyết áp", "Bảo vệ thận trong đái tháo đường"],
        "prescription_required": True,
        "caution_flags": ["hyperkalemia"],
        "contraindication_keywords": ["pregnancy", "bilateral_renal_artery_stenosis"],
        "renal_caution": True,
        "hepatic_caution": True,
        "pregnancy_caution": True,
    },
    {
        "generic_name": "valsartan",
        "brand_names": ["Diovan", "Tareg", "Valsartan"],
        "vietnamese_common_names": ["Diovan", "Valsartan"],
        "aliases": [],
        "active_ingredients": ["valsartan"],
        "drug_class": "arb",
        "metric_groups": ["hypertension"],
        "common_indications": ["Tăng huyết áp", "Suy tim"],
        "prescription_required": True,
        "caution_flags": ["hyperkalemia"],
        "contraindication_keywords": ["pregnancy", "severe_hepatic_impairment"],
        "renal_caution": True,
        "hepatic_caution": True,
        "pregnancy_caution": True,
    },
    {
        "generic_name": "telmisartan",
        "brand_names": ["Micardis", "Telmista", "Pritor"],
        "vietnamese_common_names": ["Micardis", "Telmisartan"],
        "aliases": [],
        "active_ingredients": ["telmisartan"],
        "drug_class": "arb",
        "metric_groups": ["hypertension"],
        "common_indications": ["Tăng huyết áp", "Giảm nguy cơ tim mạch"],
        "prescription_required": True,
        "caution_flags": ["hyperkalemia"],
        "contraindication_keywords": ["pregnancy", "biliary_obstruction"],
        "renal_caution": False,
        "hepatic_caution": True,
        "pregnancy_caution": True,
    },
    {
        "generic_name": "candesartan",
        "brand_names": ["Atacand", "Candesartan"],
        "vietnamese_common_names": ["Atacand", "Candesartan"],
        "aliases": ["candesartan cilexetil"],
        "active_ingredients": ["candesartan cilexetil"],
        "drug_class": "arb",
        "metric_groups": ["hypertension"],
        "common_indications": ["Tăng huyết áp", "Suy tim"],
        "prescription_required": True,
        "caution_flags": ["hyperkalemia"],
        "contraindication_keywords": ["pregnancy"],
        "renal_caution": True,
        "hepatic_caution": True,
        "pregnancy_caution": True,
    },
    {
        "generic_name": "bisoprolol",
        "brand_names": ["Concor", "Bisoprolol", "Cardicor"],
        "vietnamese_common_names": ["Concor", "Bisoprolol"],
        "aliases": ["bisoprolol fumarate"],
        "active_ingredients": ["bisoprolol fumarate"],
        "drug_class": "beta_blocker",
        "metric_groups": ["hypertension"],
        "common_indications": ["Tăng huyết áp", "Suy tim", "Loạn nhịp tim"],
        "prescription_required": True,
        "caution_flags": ["bradycardia", "bronchospasm"],
        "contraindication_keywords": ["asthma", "severe_bradycardia", "av_block"],
        "renal_caution": True,
        "hepatic_caution": True,
        "pregnancy_caution": False,
    },
    {
        "generic_name": "nebivolol",
        "brand_names": ["Nebilet", "Nebilong", "Lobivon"],
        "vietnamese_common_names": ["Nebilet", "Nebivolol"],
        "aliases": [],
        "active_ingredients": ["nebivolol hydrochloride"],
        "drug_class": "beta_blocker",
        "metric_groups": ["hypertension"],
        "common_indications": ["Tăng huyết áp", "Suy tim mạn ổn định"],
        "prescription_required": True,
        "caution_flags": ["bradycardia"],
        "contraindication_keywords": [
            "severe_bradycardia", "av_block", "severe_hepatic_impairment",
        ],
        "renal_caution": True,
        "hepatic_caution": True,
        "pregnancy_caution": False,
    },
    {
        "generic_name": "metoprolol",
        "brand_names": ["Betaloc", "Toprol", "Metoprolol"],
        "vietnamese_common_names": ["Betaloc", "Metoprolol"],
        "aliases": ["metoprolol succinate", "metoprolol tartrate"],
        "active_ingredients": ["metoprolol succinate"],
        "drug_class": "beta_blocker",
        "metric_groups": ["hypertension"],
        "common_indications": ["Tăng huyết áp", "Nhồi máu cơ tim", "Suy tim"],
        "prescription_required": True,
        "caution_flags": ["bradycardia", "bronchospasm"],
        "contraindication_keywords": ["asthma", "severe_bradycardia"],
        "renal_caution": False,
        "hepatic_caution": True,
        "pregnancy_caution": False,
    },
    {
        "generic_name": "hydrochlorothiazide",
        "brand_names": ["HCT", "Hydrochlorot", "Esidrex"],
        "vietnamese_common_names": ["HCT", "Hydrochlorothiazide"],
        "aliases": ["HCTZ", "hct"],
        "active_ingredients": ["hydrochlorothiazide"],
        "drug_class": "thiazide_diuretic",
        "metric_groups": ["hypertension"],
        "common_indications": ["Tăng huyết áp", "Phù nề"],
        "prescription_required": True,
        "caution_flags": ["hypokalemia", "hyperuricemia", "hyponatremia"],
        "contraindication_keywords": ["severe_renal_impairment", "anuria"],
        "renal_caution": True,
        "hepatic_caution": True,
        "pregnancy_caution": True,
    },
    {
        "generic_name": "indapamide",
        "brand_names": ["Natrilix", "Indacar", "Tertensif"],
        "vietnamese_common_names": ["Natrilix", "Indapamide"],
        "aliases": ["indapamide sr"],
        "active_ingredients": ["indapamide"],
        "drug_class": "thiazide_like_diuretic",
        "metric_groups": ["hypertension"],
        "common_indications": ["Tăng huyết áp"],
        "prescription_required": True,
        "caution_flags": ["hypokalemia", "hyponatremia"],
        "contraindication_keywords": ["severe_renal_impairment", "hypokalemia"],
        "renal_caution": True,
        "hepatic_caution": True,
        "pregnancy_caution": True,
    },
    {
        "generic_name": "spironolactone",
        "brand_names": ["Aldactone", "Spirolact", "Spiractin"],
        "vietnamese_common_names": ["Aldactone", "Spironolactone"],
        "aliases": [],
        "active_ingredients": ["spironolactone"],
        "drug_class": "aldosterone_antagonist",
        "metric_groups": ["hypertension"],
        "common_indications": ["Tăng huyết áp kháng trị", "Suy tim", "Hội chứng Conn"],
        "prescription_required": True,
        "caution_flags": ["hyperkalemia", "gynecomastia"],
        "contraindication_keywords": ["severe_renal_impairment", "hyperkalemia", "anuria"],
        "renal_caution": True,
        "hepatic_caution": False,
        "pregnancy_caution": True,
    },
    # ── Thyroid ───────────────────────────────────────────────────────────
    {
        "generic_name": "levothyroxine",
        "brand_names": ["Euthyrox", "Berlthyrox", "Thyrax", "Synthroid", "Eltroxin"],
        "vietnamese_common_names": ["Euthyrox", "Berlthyrox", "Levothyroxine"],
        "aliases": ["l-thyroxine", "t4", "thyroxine sodium", "levothyroxine sodium"],
        "active_ingredients": ["levothyroxine sodium"],
        "drug_class": "thyroid_hormone",
        "metric_groups": ["thyroid"],
        "common_indications": ["Suy giáp", "Bướu giáp", "Ung thư tuyến giáp"],
        "prescription_required": True,
        "caution_flags": ["cardiac_arrhythmia_risk_if_overdose", "narrow_therapeutic_index"],
        "contraindication_keywords": ["thyrotoxicosis", "untreated_adrenal_insufficiency"],
        "renal_caution": False,
        "hepatic_caution": False,
        "pregnancy_caution": False,
        "notes_for_matching_only": "Match 'euthyrox', 'berlthyrox', 'l-thyroxin'",
    },
    # ── Gout / uric acid ─────────────────────────────────────────────────
    {
        "generic_name": "allopurinol",
        "brand_names": ["Zyloprim", "Lopuric", "Zyloric"],
        "vietnamese_common_names": ["Zyloric", "Allopurinol"],
        "aliases": [],
        "active_ingredients": ["allopurinol"],
        "drug_class": "xanthine_oxidase_inhibitor",
        "metric_groups": ["gout"],
        "common_indications": ["Gút mạn tính", "Tăng acid uric máu"],
        "prescription_required": True,
        "caution_flags": ["severe_cutaneous_reactions", "HLA_B_5801_screening"],
        "contraindication_keywords": ["acute_gout_attack"],
        "renal_caution": True,
        "hepatic_caution": False,
        "pregnancy_caution": True,
    },
    {
        "generic_name": "febuxostat",
        "brand_names": ["Uloric", "Febustat", "Adenuric"],
        "vietnamese_common_names": ["Febustat", "Febuxostat"],
        "aliases": [],
        "active_ingredients": ["febuxostat"],
        "drug_class": "xanthine_oxidase_inhibitor",
        "metric_groups": ["gout"],
        "common_indications": ["Gút mạn tính", "Tăng acid uric máu"],
        "prescription_required": True,
        "caution_flags": ["cardiovascular_events"],
        "contraindication_keywords": ["acute_gout_attack"],
        "renal_caution": False,
        "hepatic_caution": True,
        "pregnancy_caution": True,
    },
    {
        "generic_name": "colchicine",
        "brand_names": ["Colcrys", "Colchicin", "Mitigare"],
        "vietnamese_common_names": ["Colchicine", "Colchicin"],
        "aliases": [],
        "active_ingredients": ["colchicine"],
        "drug_class": "anti_inflammatory_gout",
        "metric_groups": ["gout"],
        "common_indications": ["Cơn gút cấp", "Phòng ngừa cơn gút"],
        "prescription_required": True,
        "caution_flags": ["narrow_therapeutic_index", "CYP3A4_interactions"],
        "contraindication_keywords": ["severe_renal_impairment", "severe_hepatic_impairment"],
        "renal_caution": True,
        "hepatic_caution": True,
        "pregnancy_caution": True,
    },
    # ── Antiplatelet / anticoagulant ──────────────────────────────────────
    {
        "generic_name": "aspirin",
        "brand_names": ["Aspirin", "Aspégic", "Cardioaspirin", "Aspirin Protect"],
        "vietnamese_common_names": ["Aspirin", "Aspegic"],
        "aliases": ["acetylsalicylic acid", "asa", "low-dose aspirin"],
        "active_ingredients": ["acetylsalicylic acid"],
        "drug_class": "antiplatelet",
        "metric_groups": ["antiplatelet", "hypertension"],
        "common_indications": ["Phòng ngừa huyết khối", "Bệnh tim mạch"],
        "prescription_required": False,
        "caution_flags": ["gi_bleeding_risk", "reye_syndrome_in_children"],
        "contraindication_keywords": ["active_peptic_ulcer", "bleeding_disorder"],
        "renal_caution": True,
        "hepatic_caution": False,
        "pregnancy_caution": True,
    },
    {
        "generic_name": "clopidogrel",
        "brand_names": ["Plavix", "Clopivas", "Zyllt"],
        "vietnamese_common_names": ["Plavix", "Clopidogrel"],
        "aliases": ["clopidogrel bisulphate"],
        "active_ingredients": ["clopidogrel bisulphate"],
        "drug_class": "antiplatelet",
        "metric_groups": ["antiplatelet"],
        "common_indications": ["Phòng ngừa huyết khối", "Nhồi máu cơ tim", "Đột quỵ"],
        "prescription_required": True,
        "caution_flags": ["bleeding_risk", "CYP2C19_polymorphism"],
        "contraindication_keywords": ["active_bleeding", "severe_hepatic_impairment"],
        "renal_caution": False,
        "hepatic_caution": True,
        "pregnancy_caution": True,
    },
    {
        "generic_name": "rivaroxaban",
        "brand_names": ["Xarelto"],
        "vietnamese_common_names": ["Xarelto", "Rivaroxaban"],
        "aliases": ["factor xa inhibitor"],
        "active_ingredients": ["rivaroxaban"],
        "drug_class": "noac",
        "metric_groups": ["antiplatelet"],
        "common_indications": ["Rung nhĩ", "Phòng ngừa đột quỵ", "Huyết khối tĩnh mạch sâu"],
        "prescription_required": True,
        "caution_flags": ["bleeding_risk"],
        "contraindication_keywords": ["active_bleeding", "severe_renal_impairment", "pregnancy"],
        "renal_caution": True,
        "hepatic_caution": True,
        "pregnancy_caution": True,
    },
    {
        "generic_name": "apixaban",
        "brand_names": ["Eliquis"],
        "vietnamese_common_names": ["Eliquis", "Apixaban"],
        "aliases": [],
        "active_ingredients": ["apixaban"],
        "drug_class": "noac",
        "metric_groups": ["antiplatelet"],
        "common_indications": ["Rung nhĩ", "Phòng ngừa đột quỵ", "Huyết khối tĩnh mạch sâu"],
        "prescription_required": True,
        "caution_flags": ["bleeding_risk"],
        "contraindication_keywords": ["active_bleeding", "pregnancy"],
        "renal_caution": True,
        "hepatic_caution": True,
        "pregnancy_caution": True,
    },
    {
        "generic_name": "warfarin",
        "brand_names": ["Coumadin", "Wafarin", "Marevan"],
        "vietnamese_common_names": ["Coumadin", "Warfarin"],
        "aliases": ["warfarin sodium"],
        "active_ingredients": ["warfarin sodium"],
        "drug_class": "vitamin_k_antagonist",
        "metric_groups": ["antiplatelet"],
        "common_indications": ["Rung nhĩ", "Huyết khối tĩnh mạch sâu", "Van tim cơ học"],
        "prescription_required": True,
        "caution_flags": ["bleeding_risk", "narrow_therapeutic_index", "many_drug_interactions"],
        "contraindication_keywords": ["pregnancy", "active_bleeding", "hemorrhagic_stroke"],
        "renal_caution": True,
        "hepatic_caution": True,
        "pregnancy_caution": True,
    },
    # ── Gastroprotection ──────────────────────────────────────────────────
    {
        "generic_name": "omeprazole",
        "brand_names": ["Losec", "Prilosec", "Omez", "Omeprazole"],
        "vietnamese_common_names": ["Losec", "Omeprazole", "Omez"],
        "aliases": ["omeprazol"],
        "active_ingredients": ["omeprazole"],
        "drug_class": "proton_pump_inhibitor",
        "metric_groups": ["gastroprotection"],
        "common_indications": ["Loét dạ dày tá tràng", "Trào ngược dạ dày thực quản"],
        "prescription_required": False,
        "caution_flags": ["magnesium_deficiency_long_term", "c_diff_risk"],
        "contraindication_keywords": [],
        "renal_caution": False,
        "hepatic_caution": True,
        "pregnancy_caution": False,
    },
    {
        "generic_name": "esomeprazole",
        "brand_names": ["Nexium", "Esomez", "Esomeprazole"],
        "vietnamese_common_names": ["Nexium", "Esomeprazole"],
        "aliases": ["esomeprazol"],
        "active_ingredients": ["esomeprazole magnesium"],
        "drug_class": "proton_pump_inhibitor",
        "metric_groups": ["gastroprotection"],
        "common_indications": ["Loét dạ dày tá tràng", "Trào ngược dạ dày thực quản"],
        "prescription_required": False,
        "caution_flags": ["magnesium_deficiency_long_term"],
        "contraindication_keywords": [],
        "renal_caution": False,
        "hepatic_caution": True,
        "pregnancy_caution": False,
    },
    {
        "generic_name": "pantoprazole",
        "brand_names": ["Protonix", "Pantop", "Controloc"],
        "vietnamese_common_names": ["Pantoprazole", "Pantop"],
        "aliases": ["pantoprazol"],
        "active_ingredients": ["pantoprazole sodium sesquihydrate"],
        "drug_class": "proton_pump_inhibitor",
        "metric_groups": ["gastroprotection"],
        "common_indications": ["Loét dạ dày tá tràng", "Trào ngược dạ dày thực quản"],
        "prescription_required": True,
        "caution_flags": ["magnesium_deficiency_long_term"],
        "contraindication_keywords": [],
        "renal_caution": False,
        "hepatic_caution": True,
        "pregnancy_caution": False,
    },
    # ── Liver support / supplements ───────────────────────────────────────
    {
        "generic_name": "silymarin",
        "brand_names": ["Livosil", "Legalon", "Silymarin", "Siliphos"],
        "vietnamese_common_names": ["Livosil", "Silymarin", "Legalon"],
        "aliases": ["milk thistle extract", "silybin"],
        "active_ingredients": ["silymarin"],
        "drug_class": "hepatoprotective_supplement",
        "metric_groups": ["liver", "supplement"],
        "common_indications": ["Hỗ trợ bảo vệ gan", "Xơ gan nhẹ"],
        "prescription_required": False,
        "caution_flags": [],
        "contraindication_keywords": [],
        "renal_caution": False,
        "hepatic_caution": False,
        "pregnancy_caution": False,
        "notes_for_matching_only": "Supplement — NOT a prescription hepatic treatment",
    },
    {
        "generic_name": "essential phospholipids",
        "brand_names": ["Essentiale", "Essentiale Forte", "Phospholipid"],
        "vietnamese_common_names": ["Essentiale", "Phospholipid"],
        "aliases": ["phosphatidylcholine", "polyenylphosphatidylcholine"],
        "active_ingredients": ["polyenylphosphatidylcholine"],
        "drug_class": "hepatoprotective_supplement",
        "metric_groups": ["liver", "supplement"],
        "common_indications": ["Hỗ trợ chức năng gan", "Gan nhiễm mỡ"],
        "prescription_required": False,
        "caution_flags": [],
        "contraindication_keywords": [],
        "renal_caution": False,
        "hepatic_caution": False,
        "pregnancy_caution": False,
        "notes_for_matching_only": "Supplement — NOT a prescription hepatic treatment",
    },
]


def seed_catalog(db: Session) -> int:
    """Idempotently seed the drug catalog.

    Inserts entries not yet present (keyed on lowercase generic_name).
    Returns the count of newly inserted rows.
    """
    existing = {
        row.generic_name.lower()
        for row in db.query(DrugEntry.generic_name).all()
    }
    inserted = 0
    for spec in _SEED:
        key = spec["generic_name"].lower()
        if key in existing:
            continue
        entry = DrugEntry(
            generic_name=spec["generic_name"],
            brand_names=spec.get("brand_names", []),
            vietnamese_common_names=spec.get("vietnamese_common_names", []),
            aliases=spec.get("aliases", []),
            active_ingredients=spec.get("active_ingredients", []),
            drug_class=spec["drug_class"],
            metric_groups=spec.get("metric_groups", []),
            common_indications=spec.get("common_indications", []),
            prescription_required=spec.get("prescription_required", True),
            country_context="VN",
            caution_flags=spec.get("caution_flags", []),
            contraindication_keywords=spec.get("contraindication_keywords", []),
            renal_caution=spec.get("renal_caution", False),
            hepatic_caution=spec.get("hepatic_caution", False),
            pregnancy_caution=spec.get("pregnancy_caution", False),
            notes_for_matching_only=spec.get("notes_for_matching_only"),
            is_active=True,
            source_version="1.0.0",
        )
        db.add(entry)
        inserted += 1
    db.commit()
    return inserted
