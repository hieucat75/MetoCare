"""Centralized system/service-actor identity registry (Medication Knowledge
Slice 0, docs/medication-management/
MEDICATION_KNOWLEDGE_SLICE0_ORIGIN_PROVENANCE_FLAGS_IMPLEMENTATION_PLAN.md §0.3
item 3).

Every non-human `authored_by`/`created_by`/`actor_user_id` value written by
this codebase's own automated processes (migrations, backfills, future
ingestion/normalization/synthesis jobs) must come from this module — never
an ad hoc inline string. This is a closed set, not a convention: no
migration, service, or job may invent a new `system:*` string outside
`SystemActor` without extending this file first.

Precedent this mirrors: `app/core/feature_flags.py`'s `FeatureFlag` StrEnum
+ closed set (fail-closed on anything not a member) — same shape, different
concern (identity, not capability).

Model/provider identity (which LLM, which prompt version) is NEVER encoded
here — that lives in `KnowledgeAIGeneration.model_provider`/`model_identifier`/
etc (drug_knowledge_ai_generation.py). A `SystemActor` value only ever
answers "which internal process did this," never "which AI model."
"""

from __future__ import annotations

import enum


class SystemActor(enum.StrEnum):
    """Reserved non-human actor identities. `str` values are what actually
    gets persisted in `authored_by`/`status_changed_by`/`created_by`
    columns — never a real human `user_id`, and never attributed to a real
    admin account."""

    MEDICATION_INGESTION = "system:medication-ingestion"
    MEDICATION_NORMALIZATION = "system:medication-normalization"
    MEDICATION_AI_SYNTHESIS = "system:medication-ai-synthesis"
    MEDICATION_MIGRATION = "system:medication-migration"
    MEDICATION_BACKFILL = "system:medication-backfill"


def is_system_actor(value: str) -> bool:
    """True iff `value` is one of this registry's reserved identities.

    Callers that need to assert a value is NOT a system actor (e.g. a
    self-approval check, or a guard that a real human performed an action)
    should use this rather than pattern-matching a `"system:"` prefix —
    keeps the check anchored to the closed registry, not a naming
    convention a future caller could accidentally satisfy with an
    unregistered string."""
    try:
        SystemActor(value)
    except ValueError:
        return False
    return True


# PR #136 Codex Round 1 finding #4 (fix round 1, 2026-07-28): the reserved
# "system:" namespace was previously only checked via `is_system_actor`
# (True iff REGISTERED) — an unregistered value like "system:attacker" made
# `is_system_actor` return False, so any caller using it to gate "is this a
# real human" (e.g. `assert_actor_is_not_system` in knowledge_repository.py)
# incorrectly classified a forged, unregistered system:* string as human.
# The namespace itself must be reserved, not just the finitely many values
# already registered in it.
RESERVED_NAMESPACE_PREFIX = "system:"


def is_reserved_namespace(value: str) -> bool:
    """True iff `value` falls in the reserved `system:` namespace,
    REGARDLESS of whether it is a registered `SystemActor` member. Use this
    (never `is_system_actor` alone) anywhere a forged, unregistered
    `system:*` string must not be silently treated as an ordinary human
    identity."""
    return value.startswith(RESERVED_NAMESPACE_PREFIX)


def assert_no_forged_system_actor(value: str) -> None:
    """Raise ValueError iff `value` is in the reserved `system:` namespace
    but is NOT a registered `SystemActor` member. Never classifies an
    unknown `system:*` value as human — the caller must separately decide
    whether a *registered* system actor is acceptable in the field being
    validated (this function only rejects the forged/unregistered case)."""
    if is_reserved_namespace(value) and not is_system_actor(value):
        raise ValueError(
            f"{value!r} is in the reserved {RESERVED_NAMESPACE_PREFIX!r} namespace but is "
            "not a registered SystemActor. Register it in SystemActor first, or use a real "
            "actor identity outside the reserved namespace."
        )
