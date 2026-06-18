"""PDF Report Service — generates clinical summary PDFs for MetoCare (T24).

Public API:
    generate_patient_summary_pdf(patient_id, summary_data) -> bytes

Uses ``reportlab`` to produce a formatted PDF document with standard
clinical sections.  No HTTP concerns; the caller (route) is responsible
for RBAC / consent checks before invoking this function.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime
from typing import Any


def generate_patient_summary_pdf(
    patient_id: str,
    summary_data: dict[str, Any],
) -> bytes:
    """Generate a clinical summary PDF for *patient_id*.

    Args:
        patient_id:   The patient's identifier (printed in the header).
        summary_data: The dict representation of ``PatientSummaryOut`` as
                      returned by ``patient_summary.build_summary()``.

    Returns:
        Raw PDF bytes suitable for streaming directly to the HTTP response.
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        HRFlowable,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        title=f"MetoCare Clinical Summary — {patient_id}",
        author="MetoCare",
        subject="Clinical Summary",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ClinicalTitle",
        parent=styles["Title"],
        fontSize=18,
        textColor=colors.HexColor("#1a4f8a"),
        spaceAfter=4,
    )
    heading_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        fontSize=12,
        textColor=colors.HexColor("#1a4f8a"),
        spaceBefore=10,
        spaceAfter=4,
        borderPad=2,
    )
    body_style = styles["BodyText"]
    small_style = ParagraphStyle(
        "SmallGray",
        parent=styles["Normal"],
        fontSize=8,
        textColor=colors.gray,
    )

    generated_at: str = summary_data.get("generated_at") or datetime.now(UTC).isoformat()
    if hasattr(generated_at, "isoformat"):
        generated_at = generated_at.isoformat()

    story: list[Any] = []

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------
    story.append(Paragraph("MetoCare Clinical Summary", title_style))
    story.append(Paragraph(f"Patient ID: <b>{patient_id}</b>", body_style))
    story.append(Paragraph(f"Generated: {generated_at}", small_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1a4f8a")))
    story.append(Spacer(1, 6 * mm))

    # ------------------------------------------------------------------
    # 1. Vitals
    # ------------------------------------------------------------------
    story.append(Paragraph("Vitals", heading_style))
    vitals: dict = summary_data.get("vitals") or {}
    latest_vitals: list[dict] = vitals.get("latest") or []
    trend: str = vitals.get("trend", "insufficient_data")

    if latest_vitals:
        table_data = [["Metric", "Value", "Unit", "Status", "Measured At"]]
        for v in latest_vitals:
            table_data.append([
                str(v.get("metric_type", "")),
                str(v.get("value", "")),
                str(v.get("unit", "")),
                str(v.get("status", "")),
                str(v.get("measured_at", "")),
            ])
        tbl = Table(table_data, hAlign="LEFT", repeatRows=1)
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a4f8a")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f4f8")]),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(tbl)
    else:
        story.append(Paragraph("No vitals recorded.", body_style))

    story.append(Paragraph(f"Trend: <i>{trend}</i>", small_style))
    story.append(Spacer(1, 4 * mm))

    # ------------------------------------------------------------------
    # 2. Metabolic Score
    # ------------------------------------------------------------------
    story.append(Paragraph("Metabolic Score", heading_style))
    metabolic: dict = summary_data.get("metabolic_score") or {}
    latest_score = metabolic.get("latest_score")
    m_trend = metabolic.get("trend", "insufficient_data")
    m_recorded_at = metabolic.get("recorded_at", "")

    if latest_score is not None:
        score_text = (
            f"Latest Score: <b>{latest_score:.1f}</b> &nbsp;"
            f" Trend: <i>{m_trend}</i> &nbsp; Recorded: {m_recorded_at}"
        )
        story.append(Paragraph(score_text, body_style))
    else:
        story.append(Paragraph("No metabolic score recorded.", body_style))
    story.append(Spacer(1, 4 * mm))

    # ------------------------------------------------------------------
    # 3. Medications
    # ------------------------------------------------------------------
    story.append(Paragraph("Medications (Active)", heading_style))
    medications: list[dict] = summary_data.get("medications") or []

    if medications:
        table_data = [["Name", "Dose", "Note", "Added"]]
        for m in medications:
            table_data.append([
                str(m.get("name", "")),
                str(m.get("dose", "")),
                str(m.get("note", "") or ""),
                str(m.get("created_at", "")),
            ])
        tbl = Table(table_data, hAlign="LEFT", repeatRows=1)
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a4f8a")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f4f8")]),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(tbl)
    else:
        story.append(Paragraph("No active medications.", body_style))
    story.append(Spacer(1, 4 * mm))

    # ------------------------------------------------------------------
    # 4. Symptoms
    # ------------------------------------------------------------------
    story.append(Paragraph("Symptoms (Recent)", heading_style))
    symptoms: list[dict] = summary_data.get("symptoms") or []

    if symptoms:
        table_data = [["Description", "Severity", "Reported At"]]
        for s in symptoms:
            table_data.append([
                str(s.get("description", "")),
                str(s.get("severity", "")),
                str(s.get("reported_at", "")),
            ])
        tbl = Table(table_data, hAlign="LEFT", repeatRows=1)
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a4f8a")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f4f8")]),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(tbl)
    else:
        story.append(Paragraph("No symptoms logged.", body_style))
    story.append(Spacer(1, 4 * mm))

    # ------------------------------------------------------------------
    # 5. Nutrition
    # ------------------------------------------------------------------
    story.append(Paragraph("Nutrition (Recent)", heading_style))
    nutrition: list[dict] = summary_data.get("nutrition") or []

    if nutrition:
        table_data = [["Description", "Meal Type", "Calories (kcal)", "Logged At"]]
        for n in nutrition:
            table_data.append([
                str(n.get("description", "")),
                str(n.get("meal_type", "")),
                str(n.get("calories_kcal", "") or ""),
                str(n.get("logged_at", "")),
            ])
        tbl = Table(table_data, hAlign="LEFT", repeatRows=1)
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a4f8a")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f4f8")]),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(tbl)
    else:
        story.append(Paragraph("No nutrition logs.", body_style))
    story.append(Spacer(1, 4 * mm))

    # ------------------------------------------------------------------
    # 6. Active Care Plans
    # ------------------------------------------------------------------
    story.append(Paragraph("Active Care Plans", heading_style))
    care_plans: list[dict] = summary_data.get("active_care_plans") or []

    if care_plans:
        table_data = [["Title", "Version", "ID"]]
        for cp in care_plans:
            table_data.append([
                str(cp.get("title", "")),
                str(cp.get("version", "")),
                str(cp.get("id", "")),
            ])
        tbl = Table(table_data, hAlign="LEFT", repeatRows=1)
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a4f8a")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f4f8")]),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(tbl)
    else:
        story.append(Paragraph("No active care plans.", body_style))
    story.append(Spacer(1, 8 * mm))

    # ------------------------------------------------------------------
    # Footer rule
    # ------------------------------------------------------------------
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.gray))
    story.append(Paragraph(
        "Generated by MetoCare — Confidential",
        ParagraphStyle(
            "Footer",
            parent=styles["Normal"],
            fontSize=8,
            textColor=colors.gray,
            alignment=1,  # center
        ),
    ))

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
