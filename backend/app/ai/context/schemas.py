"""Meto AI — Context Engine schemas.

Defines the data structures for assembled context blocks passed to the prompt
assembler. Follows 02_CONTEXT_ENGINE.md specification.
"""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, Field


class ScreenContext(BaseModel):
    """Frontend-injected context about the current screen and entity."""

    screen_id: str = "dashboard"
    """Current screen: dashboard | labs | medications | metrics | care_plan | nutrition | profile"""

    entity_id: str | None = None
    """E.g. lab_batch_id, medication_id, metric_type — the focused entity."""

    entity_type: str | None = None
    """Type hint for entity_id: lab_batch | medication | metric_type | appointment | etc."""

    view_context: dict[str, Any] = Field(default_factory=dict)
    """Additional frontend-provided context (e.g. selected date range, filters)."""


class AssembledContext(BaseModel):
    """All assembled context blocks for a single Meto chat request.

    None = not available (missing data or no consent).
    Never contains hallucinated values — only real DB data or None.
    """

    user_profile: dict | None = None
    """Block 1: Basic user info (no consent required)."""

    health_summary: dict | None = None
    """Block 2: Conditions, allergies, blood type (requires health_data consent)."""

    care_plan: dict | None = None
    """Block 3: Active care plan + upcoming tasks (requires care_plan consent)."""

    medications: list | None = None
    """Block 4: Active medications (requires medications consent)."""

    recent_labs: list | None = None
    """Block 5: Lab results last 90 days (requires labs consent)."""

    recent_metrics: list | None = None
    """Block 6: Health metrics last 30 days (requires metrics consent)."""

    screen_context: dict = Field(default_factory=dict)
    """Block 7: Current screen info (no consent required, injected by frontend)."""

    today_context: dict = Field(default_factory=dict)
    """Block 8: Date, upcoming appointments, pending tasks."""

    safety_flags: list[str] = Field(default_factory=list)
    """Block 9: Critical lab/metric values requiring immediate attention."""

    # Metadata (not part of prompt context, used for auditing)
    total_estimated_tokens: int = 0
    missing_consents: list[str] = Field(default_factory=list)
    included_blocks: list[str] = Field(default_factory=list)

    degraded_blocks: list[str] = Field(default_factory=list)
    """Blocks whose query RAISED and were dropped — not blocks that were empty.

    Absence of data and failure to retrieve data are clinically different and were
    indistinguishable: every block builder caught Exception, logged, and returned
    None, which is the same value the block has when the patient genuinely has no
    rows. `safety_flags` is derived from `recent_labs`/`recent_metrics`, so a
    transient failure of the labs query produced an empty flag list and Meto
    answered as though nothing was abnormal — a false reassurance to a patient who
    may have had a CRITICAL value on file.

    Reachability is not hypothetical: SEC-F11 sets `on_decrypt_failure="raise"`,
    so a single unreadable ciphertext now RAISES inside these builders instead of
    yielding None. Hardening the crypto made this path easier to reach, which is
    correct — the wrong response to unreadable PHI is to silently proceed.

    The assembler turns a non-empty list into an explicit instruction telling the
    model that data is missing due to an error and that it must not assert the
    absence of abnormal findings.
    """

    SAFETY_CRITICAL_BLOCKS: ClassVar[frozenset[str]] = frozenset(
        {"recent_labs", "recent_metrics", "medications", "health_summary"}
    )
    """Blocks whose silent loss can turn into a false reassurance."""

    def has_safety_critical_degradation(self) -> bool:
        return bool(set(self.degraded_blocks) & self.SAFETY_CRITICAL_BLOCKS)

    # -----------------------------------------------------------------------
    # Helper methods
    # -----------------------------------------------------------------------

    def has_safety_flags(self) -> bool:
        """Return True if any safety flags are present."""
        return bool(self.safety_flags)

    def to_prompt_dict(self) -> dict:
        """Return the context blocks as a dict for prompt serialization.

        Includes all blocks (None values preserved as-is).
        Does NOT include metadata fields.
        """
        return {
            "user_profile": self.user_profile,
            "health_summary": self.health_summary,
            "care_plan": self.care_plan,
            "medications": self.medications,
            "recent_labs": self.recent_labs,
            "recent_metrics": self.recent_metrics,
            "screen_context": self.screen_context,
            "today_context": self.today_context,
            "safety_flags": self.safety_flags,
        }
