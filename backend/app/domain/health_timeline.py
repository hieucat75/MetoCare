"""Engine 20 — Health Timeline Engine (E20).

Aggregates health events from multiple sources into a unified chronological timeline.
Sources: LabResult, HealthMetric (weight, BP, etc.), Medication, MedicationAdherence, SymptomLog.

BP support via HealthMetric(metric_type="bp_systolic" / "bp_diastolic"):
- Pairs systolic + diastolic by same measured_at date (same day, nearest match).
- Classifies: normal / elevated / high / urgent_red_flag — safe wording only.

Timeline Intelligence: summarizes what improved, worsened, stable, and biggest change.

No new DB migration. No LLM. No diagnosis language.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

# ── TimelineEvent ──────────────────────────────────────────────────────────────

@dataclass
class TimelineEvent:
    event_id: str           # deterministic: "{source}_{record_id}" or "{source}_{date}_{canonical}"
    event_type: str         # see EVENT_TYPES below
    date: dt.date           # primary sort key
    title_vi: str
    summary_vi: str
    source: str             # "lab_result"|"health_metric"|"medication"|"symptom"|"weight"|"blood_pressure"
    importance: str         # "info"|"watch"|"warning"|"urgent"
    related_markers: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)   # raw values, units, etc.
    evidence_level: str = ""    # "established"|"moderate"|"emerging"|""

# EVENT_TYPES:
# "lab_result"         — normal lab batch
# "abnormal_lab"       — batch with ≥1 abnormal result
# "medication_started" — new Medication record created
# "medication_adherence" — adherence log entry
# "symptom"            — SymptomLog
# "weight_change"      — HealthMetric metric_type="weight_kg" with significant change
# "blood_pressure"     — paired systolic+diastolic reading
# "note"               — free-form note (future)


# ── BP Classification ─────────────────────────────────────────────────────────

def classify_bp(systolic: float, diastolic: float) -> tuple[str, str, str]:
    """Return (level, label_vi, summary_vi). Conservative, safe wording."""
    if systolic >= 180 or diastolic >= 120:
        return "urgent_red_flag", "Huyết áp rất cao", f"Huyết áp {systolic:.0f}/{diastolic:.0f} mmHg — nên liên hệ y tế ngay."
    if systolic >= 140 or diastolic >= 90:
        return "high", "Huyết áp cao", f"Huyết áp {systolic:.0f}/{diastolic:.0f} mmHg — nên trao đổi với bác sĩ."
    if systolic >= 130 or diastolic >= 80:
        return "elevated", "Huyết áp tăng nhẹ", f"Huyết áp {systolic:.0f}/{diastolic:.0f} mmHg — cần theo dõi định kỳ."
    return "normal", "Huyết áp bình thường", f"Huyết áp {systolic:.0f}/{diastolic:.0f} mmHg — trong giới hạn bình thường."

_BP_IMPORTANCE = {
    "urgent_red_flag": "urgent",
    "high": "warning",
    "elevated": "watch",
    "normal": "info",
}


# ── TimelineSummary ────────────────────────────────────────────────────────────

@dataclass
class TimelineSummary:
    improved_areas: list[str] = field(default_factory=list)     # e.g. ["LDL", "Cân nặng"]
    worsened_areas: list[str] = field(default_factory=list)
    stable_areas: list[str] = field(default_factory=list)
    biggest_change_vi: str = ""     # 1 sentence describing the most notable change
    missing_longitudinal_vi: list[str] = field(default_factory=list)  # e.g. ["Không có dữ liệu huyết áp"]
    data_span_days: int = 0         # days from oldest to newest event
    total_events: int = 0


# ── HealthTimelineEngine ──────────────────────────────────────────────────────

class HealthTimelineEngine:
    """Aggregate health data into a unified timeline.

    Usage:
        engine = HealthTimelineEngine()
        events = engine.build(
            lab_batches=lab_batches,
            lab_results=lab_results,
            health_metrics=health_metrics,
            medications=medications,
            symptom_logs=symptom_logs,
            from_date=...,
            to_date=...,
        )
        summary = engine.summarize(events, lab_results)
    """

    # Significant weight change threshold (kg)
    _WEIGHT_CHANGE_KG = 2.0

    def build(
        self,
        *,
        lab_batches: list[Any],           # LabUploadBatch rows
        lab_results: list[Any],           # LabResult rows
        health_metrics: list[Any],        # HealthMetric rows
        medications: list[Any],           # Medication rows
        symptom_logs: list[Any],          # SymptomLog rows
        dose_occurrences: list[Any] | None = None,   # DoseOccurrence rows (J3)
        documents: list[Any] | None = None,          # MedicalDocument rows (J2)
        confirmed_candidates: list[Any] | None = None,  # ExtractionCandidate confirmed/merged (J2)
        from_date: dt.date | None = None,
        to_date: dt.date | None = None,
        event_type_filter: str | None = None,
        limit: int = 100,
    ) -> list[TimelineEvent]:
        events: list[TimelineEvent] = []

        events.extend(self._lab_events(lab_batches, lab_results))
        events.extend(self._bp_events(health_metrics))
        events.extend(self._weight_events(health_metrics))
        events.extend(self._medication_events(medications))
        events.extend(self._symptom_events(symptom_logs))
        events.extend(self._dose_events(dose_occurrences or []))
        events.extend(self._document_events(documents or [], confirmed_candidates or []))

        # Filter by date range
        if from_date:
            events = [e for e in events if e.date >= from_date]
        if to_date:
            events = [e for e in events if e.date <= to_date]
        if event_type_filter:
            events = [e for e in events if e.event_type == event_type_filter]

        # Sort newest first
        events.sort(key=lambda e: e.date, reverse=True)
        return events[:limit]

    # ── Lab Events ────────────────────────────────────────────────────────────

    def _lab_events(self, batches: list[Any], results: list[Any]) -> list[TimelineEvent]:
        events = []
        # Group results by batch_id
        batch_results: dict[str, list[Any]] = {}
        for r in results:
            bid = getattr(r, "batch_id", None) or "no_batch"
            batch_results.setdefault(str(bid), []).append(r)

        for batch in batches:
            bid = str(batch.id)
            b_results = batch_results.get(bid, [])
            date = getattr(batch, "test_date", None) or (batch.created_at.date() if hasattr(batch, "created_at") and batch.created_at else dt.date.today())
            abnormals = [r for r in b_results if getattr(r, "status", "") in ("high", "low", "critical")]
            lab_name = getattr(batch, "lab_name", "") or "Xét nghiệm"

            if abnormals:
                abnormal_names = [r.test_name for r in abnormals[:3]]
                extra = f" và {len(abnormals) - 3} chỉ số khác" if len(abnormals) > 3 else ""
                summary = f"{', '.join(abnormal_names)}{extra} nằm ngoài giới hạn bình thường."
                events.append(TimelineEvent(
                    event_id=f"lab_abnormal_{bid}",
                    event_type="abnormal_lab",
                    date=date,
                    title_vi=f"Xét nghiệm — {len(abnormals)} chỉ số cần chú ý",
                    summary_vi=summary,
                    source="lab_result",
                    importance="warning" if any(r.status == "critical" for r in abnormals) else "watch",
                    related_markers=[r.canonical_name or r.test_name for r in abnormals if r.canonical_name],
                    metadata={"batch_id": bid, "lab_name": lab_name, "total_results": len(b_results), "abnormal_count": len(abnormals)},
                    evidence_level="established",
                ))
            elif b_results:
                events.append(TimelineEvent(
                    event_id=f"lab_{bid}",
                    event_type="lab_result",
                    date=date,
                    title_vi=f"Xét nghiệm — {len(b_results)} chỉ số",
                    summary_vi=f"Tất cả {len(b_results)} chỉ số trong giới hạn bình thường.",
                    source="lab_result",
                    importance="info",
                    metadata={"batch_id": bid, "lab_name": lab_name, "total_results": len(b_results)},
                    evidence_level="established",
                ))
        return events

    # ── BP Events ─────────────────────────────────────────────────────────────

    def _bp_events(self, metrics: list[Any]) -> list[TimelineEvent]:
        """Pair bp_systolic + bp_diastolic by same measured_at date."""
        systolics: dict[str, tuple[dt.date, float]] = {}  # date_str -> (date, value)
        diastolics: dict[str, tuple[dt.date, float]] = {}

        for m in metrics:
            mt = getattr(m, "metric_type", "")
            val = getattr(m, "value", None)
            measured = getattr(m, "measured_at", None)
            if val is None or measured is None:
                continue
            d = measured.date() if hasattr(measured, "date") else measured
            key = str(d)
            if mt == "bp_systolic":
                systolics[key] = (d, float(val))
            elif mt == "bp_diastolic":
                diastolics[key] = (d, float(val))

        events = []
        for key, (date, sys_val) in systolics.items():
            if key not in diastolics:
                # Unpaired systolic — still record it
                events.append(TimelineEvent(
                    event_id=f"bp_{key}",
                    event_type="blood_pressure",
                    date=date,
                    title_vi=f"Huyết áp tâm thu: {sys_val:.0f} mmHg",
                    summary_vi=f"Chỉ có dữ liệu huyết áp tâm thu ({sys_val:.0f} mmHg). Cần đo thêm huyết áp tâm trương.",
                    source="health_metric",
                    importance="info",
                    metadata={"systolic": sys_val, "diastolic": None},
                ))
                continue
            _, dia_val = diastolics[key]
            level, label_vi, summary_vi = classify_bp(sys_val, dia_val)
            events.append(TimelineEvent(
                event_id=f"bp_{key}",
                event_type="blood_pressure",
                date=date,
                title_vi=f"Huyết áp: {sys_val:.0f}/{dia_val:.0f} mmHg — {label_vi}",
                summary_vi=summary_vi,
                source="health_metric",
                importance=_BP_IMPORTANCE[level],
                metadata={"systolic": sys_val, "diastolic": dia_val, "level": level},
                evidence_level="established",
            ))
        return events

    # ── Weight Events ─────────────────────────────────────────────────────────

    def _weight_events(self, metrics: list[Any]) -> list[TimelineEvent]:
        weights = sorted(
            [(m.measured_at.date() if hasattr(m.measured_at, "date") else m.measured_at, float(m.value))
             for m in metrics if getattr(m, "metric_type", "") == "weight_kg" and m.value is not None],
            key=lambda x: x[0],
        )
        if not weights:
            return []
        events = []
        prev_val: float | None = None
        for date, val in weights:
            if prev_val is not None:
                delta = val - prev_val
                if abs(delta) >= self._WEIGHT_CHANGE_KG:
                    direction = "giảm" if delta < 0 else "tăng"
                    importance = "info" if delta < 0 else "watch"
                    events.append(TimelineEvent(
                        event_id=f"weight_{date}",
                        event_type="weight_change",
                        date=date,
                        title_vi=f"Cân nặng {direction} {abs(delta):.1f} kg",
                        summary_vi=f"Cân nặng {direction} từ {prev_val:.1f} kg xuống {val:.1f} kg." if delta < 0 else f"Cân nặng {direction} từ {prev_val:.1f} kg lên {val:.1f} kg.",
                        source="health_metric",
                        importance=importance,
                        metadata={"weight_kg": val, "previous_kg": prev_val, "delta_kg": round(delta, 1)},
                    ))
            prev_val = val
        return events

    # ── Medication Events ─────────────────────────────────────────────────────

    def _medication_events(self, medications: list[Any]) -> list[TimelineEvent]:
        events = []
        for med in medications:
            created = getattr(med, "created_at", None)
            if not created:
                continue
            date = created.date() if hasattr(created, "date") else created
            dose_str = f" {med.dose}" if getattr(med, "dose", None) else ""
            freq_str = f", {med.frequency}" if getattr(med, "frequency", None) else ""
            events.append(TimelineEvent(
                event_id=f"med_{med.id}",
                event_type="medication_started",
                date=date,
                title_vi=f"Ghi nhận thuốc: {med.name}",
                summary_vi=f"Thuốc {med.name}{dose_str}{freq_str} được ghi nhận vào hồ sơ.",
                source="medication",
                importance="info",
                metadata={"medication_id": str(med.id), "name": med.name, "dose": getattr(med, "dose", None), "frequency": getattr(med, "frequency", None)},
            ))
        return events

    # ── Medication dose events (Journey 3) ────────────────────────────────────

    def _dose_events(self, doses: list[Any]) -> list[TimelineEvent]:
        events = []
        label = {
            "taken": ("Đã uống thuốc", "info"),
            "skipped": ("Bỏ liều", "watch"),
            "missed": ("Quên liều", "warning"),
        }
        for d in doses:
            st = getattr(d, "state", None)
            if st not in label:
                continue  # pending/notified are not timeline history
            when = getattr(d, "acted_at", None) or getattr(d, "scheduled_utc", None)
            if not when:
                continue
            date = when.date() if hasattr(when, "date") else when
            title, importance = label[st]
            render = getattr(d, "local_render", None) or ""
            events.append(
                TimelineEvent(
                    event_id=f"dose_{d.id}",
                    event_type=f"medication_dose_{st}",
                    date=date,
                    title_vi=title,
                    summary_vi=f"{title} ({render}).".strip() if render else f"{title}.",
                    source="medication_dose",
                    importance=importance,
                    metadata={
                        "dose_id": str(d.id),
                        "schedule_id": str(getattr(d, "schedule_id", "")),
                        "state": st,
                    },
                )
            )
        return events

    # ── Medical document events (Journey 2) ───────────────────────────────────

    def _document_events(
        self, documents: list[Any], confirmed_candidates: list[Any]
    ) -> list[TimelineEvent]:
        events = []
        _doc_label = {
            "prescription": "đơn thuốc",
            "lab_report": "phiếu xét nghiệm",
            "general": "tài liệu y tế",
        }
        for doc in documents:
            created = getattr(doc, "created_at", None)
            if not created:
                continue
            date = created.date() if hasattr(created, "date") else created
            lbl = _doc_label.get(getattr(doc, "doc_type", None), "tài liệu")
            events.append(
                TimelineEvent(
                    event_id=f"doc_{doc.id}",
                    event_type="document_uploaded",
                    date=date,
                    title_vi=f"Đã tải lên {lbl}",
                    summary_vi=f"{lbl.capitalize()} được thêm vào hồ sơ.",
                    source="medical_document",
                    importance="info",
                    metadata={
                        "document_id": str(doc.id),
                        "doc_type": getattr(doc, "doc_type", None),
                        "status": getattr(doc, "status", None),
                    },
                )
            )
        for c in confirmed_candidates:
            when = getattr(c, "reviewed_at", None) or getattr(c, "created_at", None)
            if not when:
                continue
            date = when.date() if hasattr(when, "date") else when
            fields = getattr(c, "fields_json", None) or {}
            text = fields.get("text") or fields.get("name") or fields.get("test_name") or "Mục"
            ctype = getattr(c, "candidate_type", "")
            events.append(
                TimelineEvent(
                    event_id=f"cand_{c.id}",
                    event_type=f"confirmed_{ctype}",
                    date=date,
                    title_vi=f"Đã xác nhận: {text}"[:120],
                    summary_vi=f"{ctype}: {text}"[:200],
                    source="medical_document",
                    importance="info",
                    # backlink to the source document for provenance (§B/§H)
                    metadata={
                        "candidate_id": str(c.id),
                        "document_id": str(getattr(c, "document_id", "")),
                        "candidate_type": ctype,
                    },
                )
            )
        return events

    # ── Symptom Events ────────────────────────────────────────────────────────

    def _symptom_events(self, symptom_logs: list[Any]) -> list[TimelineEvent]:
        events = []
        for log in symptom_logs:
            reported = getattr(log, "reported_at", None) or getattr(log, "created_at", None)
            if not reported:
                continue
            date = reported.date() if hasattr(reported, "date") else reported
            severity = getattr(log, "severity", None)
            desc = getattr(log, "description", "") or ""
            sev_str = f" (mức độ {severity}/10)" if severity is not None else ""
            importance = "warning" if severity is not None and severity >= 7 else ("watch" if severity is not None and severity >= 4 else "info")
            events.append(TimelineEvent(
                event_id=f"symptom_{log.id}",
                event_type="symptom",
                date=date,
                title_vi=f"Triệu chứng{sev_str}",
                summary_vi=desc[:200] if desc else "Triệu chứng được ghi nhận.",
                source="symptom",
                importance=importance,
                metadata={"severity": severity, "description": desc[:200]},
            ))
        return events

    # ── Timeline Summary ──────────────────────────────────────────────────────

    def summarize(
        self,
        events: list[TimelineEvent],
        lab_results: list[Any],
    ) -> TimelineSummary:
        if not events:
            return TimelineSummary(missing_longitudinal_vi=["Chưa có dữ liệu sức khỏe nào được ghi nhận."])

        summary = TimelineSummary()
        summary.total_events = len(events)

        dates = [e.date for e in events]
        if dates:
            summary.data_span_days = (max(dates) - min(dates)).days

        # Detect improved/worsened areas from lab results grouped by canonical
        canonical_results: dict[str, list[Any]] = {}
        for r in lab_results:
            c = getattr(r, "canonical_name", None)
            if c and getattr(r, "test_date", None):
                canonical_results.setdefault(c, []).append(r)

        for canonical, results in canonical_results.items():
            if len(results) < 2:
                continue
            sorted_r = sorted(results, key=lambda x: x.test_date)
            first_status = getattr(sorted_r[0], "status", None) or "unknown"
            last_status = getattr(sorted_r[-1], "status", "normal") or "normal"
            _bad = {"high", "low", "critical"}
            if first_status in _bad and last_status == "normal":
                summary.improved_areas.append(canonical)
            elif first_status == "normal" and last_status in _bad:
                summary.worsened_areas.append(canonical)
            elif first_status == last_status:
                summary.stable_areas.append(canonical)

        # Biggest change
        if summary.worsened_areas:
            summary.biggest_change_vi = f"{summary.worsened_areas[0].replace('_', ' ').title()} có xu hướng xấu đi — nên theo dõi kỹ hơn."
        elif summary.improved_areas:
            summary.biggest_change_vi = f"{summary.improved_areas[0].replace('_', ' ').title()} đang cải thiện — tiếp tục duy trì."
        else:
            summary.biggest_change_vi = "Chưa có đủ dữ liệu theo thời gian để nhận định xu hướng."

        # Missing longitudinal data
        source_types = {e.source for e in events}
        if "health_metric" not in source_types and "blood_pressure" not in source_types:
            summary.missing_longitudinal_vi.append("Chưa có dữ liệu huyết áp — thêm vào để theo dõi tim mạch.")
        if "medication" not in source_types:
            summary.missing_longitudinal_vi.append("Chưa có danh sách thuốc — thêm vào để AI đánh giá đầy đủ hơn.")

        return summary
