"""Narrative Memory — stores previous narrative context per patient.

File-based at NARRATIVE_MEMORY_DIR.
Used for continuity wording: "So với lần trước..."
NEVER fabricates previous history.
Only writes when explicitly called after a successful narrative generation.
"""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime

NARRATIVE_MEMORY_DIR: str = os.getenv(
    "NARRATIVE_MEMORY_DIR", "/tmp/metocare_narrative_memory"
)


def _memory_path(patient_id: str) -> str:
    os.makedirs(NARRATIVE_MEMORY_DIR, exist_ok=True)
    return os.path.join(NARRATIVE_MEMORY_DIR, f"{patient_id}.json")


def load_narrative_memory(patient_id: str) -> dict | None:
    """Load previous narrative memory for patient. Returns None if no prior history."""
    path = _memory_path(patient_id)
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None
    return None


def save_narrative_memory(
    patient_id: str, narrative: dict, report_summary: dict
) -> None:
    """Save narrative memory after successful generation.

    Stores:
    - last_narrative_summary: section_1_summary from narrative
    - previous_priorities: list of priority titles
    - previous_section6: most important action today (for continuity)
    - saved_at: ISO timestamp
    - report_overall_status: for comparison context
    """
    memory = {
        "patient_id": patient_id,
        "saved_at": datetime.now(UTC).isoformat(),
        "last_narrative_summary": narrative.get("section_1_summary", ""),
        "previous_section6": narrative.get("section_6_most_important_today", ""),
        "previous_priorities": report_summary.get("top_priorities", []),
        "report_overall_status": report_summary.get("overall_status", ""),
        "previous_doctor_questions": narrative.get("section_9_doctor_questions", []),
    }
    path = _memory_path(patient_id)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(memory, f, ensure_ascii=False, indent=2)
    except OSError:
        pass  # non-fatal


def format_memory_context(memory: dict | None) -> str:
    """Format memory dict into a concise text snippet for Claude prompt.

    Returns empty string if no memory. Claude must use this ONLY for continuity
    phrasing, never to change clinical conclusions.
    """
    if not memory:
        return ""

    lines = []
    if memory.get("last_narrative_summary"):
        lines.append(
            f"Tóm tắt lần trước: {memory['last_narrative_summary'][:200]}"
        )
    if memory.get("previous_section6"):
        lines.append(
            f"Việc quan trọng nhất lần trước: {memory['previous_section6'][:150]}"
        )
    if memory.get("report_overall_status"):
        lines.append(
            f"Trạng thái sức khỏe lần trước: {memory['report_overall_status']}"
        )

    if not lines:
        return ""

    return (
        "\n\nNGỮ CẢNH LỊCH SỬ (chỉ dùng cho câu chuyển tiếp như 'So với lần trước...' "
        "— KHÔNG được thay đổi kết luận lâm sàng dựa trên thông tin này):\n"
        + "\n".join(lines)
    )
