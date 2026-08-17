"""backup_retention.py — safe pruning of workflow-owned pre-migration backups (#163).

Background: the guarded production/staging deploy workflow
(scripts/pre_migration_backup.sh) creates a Customer On-Demand Postgres
backup before every migration, named ``pre-migration-{env}-{timestamp}-
{sha8}``. Azure caps a Flexible Server at 7 Customer On-Demand backups total
— nothing ever pruned them, so production deploy run 31989510477 failed at
7/7 with ``CustomerOnDemandBackupCannotBePerformedLimitOfBackupsReached``
before the migration or any deploy step ran.

This module prunes ONLY backups this workflow itself created, keeping the
newest ``RETENTION_TARGET`` and deleting older ones, before a new backup is
requested. Everything else — Azure's separate Automatic/PITR backups, any
Customer On-Demand backup that doesn't match this exact naming convention,
or any entry whose shape can't be trusted — is never touched. Any ambiguity
fails closed (raises / exits non-zero) rather than guessing: a wrong keep-or-
prune decision here either loses a real restore point or reproduces the
exact quota failure this exists to prevent.

The Azure-CLI-calling functions (`_az_backup_list`, `_az_backup_delete`) are
the only I/O boundary — everything else is pure and unit-tested without
touching Azure.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime

#: Keep this many newest workflow-owned backups; prune the rest. Leaves
#: headroom below Azure's hard cap of 7 Customer On-Demand backups so a
#: fresh pre-migration backup can always be created afterward.
RETENTION_TARGET = 5

#: Azure's hard limit on Customer On-Demand backups per Flexible Server.
AZURE_ON_DEMAND_QUOTA = 7

#: The workflow's own backup naming convention (scripts/pre_migration_backup.sh).
_WORKFLOW_PREFIX_TEMPLATE = "pre-migration-{env}-"


class BackupRetentionError(Exception):
    """Raised whenever inventory or a delete result can't be trusted.

    Every call site must treat this as fail-closed: no deletion, no backup
    creation, no migration, no deploy continuation.
    """


@dataclass(frozen=True)
class Backup:
    name: str
    backup_type: str
    source: str
    completed_time: str | None


@dataclass(frozen=True)
class RetentionPlan:
    eligible: tuple[Backup, ...]
    ineligible: tuple[Backup, ...]
    prune: tuple[Backup, ...]
    #: True when pruning everything eligible still wouldn't leave room for a
    #: new backup under the Azure quota, because unrelated Customer On-Demand
    #: backups (never ours to touch) are themselves consuming it. This is a
    #: stop-and-report condition, not something this module can resolve.
    blocked_by_unrelated_backups: bool


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def eligible_prefix(env: str) -> str:
    return _WORKFLOW_PREFIX_TEMPLATE.format(env=env)


def parse_inventory(raw_json: str) -> list[Backup]:
    """Parse `az postgres flexible-server backup list -o json` output.

    Fails closed on anything that isn't the exact expected shape — a
    truncated response or a schema change must never be silently treated as
    "no backups" (which would then look eligible for pruning) or "prune
    nothing" in a way that masks the real inventory.
    """
    try:
        data = json.loads(raw_json)
    except (json.JSONDecodeError, TypeError) as exc:
        raise BackupRetentionError(f"could not parse backup inventory JSON: {exc}") from exc
    if not isinstance(data, list):
        raise BackupRetentionError("backup inventory JSON is not a list")

    backups: list[Backup] = []
    for entry in data:
        if not isinstance(entry, dict):
            raise BackupRetentionError(f"malformed backup inventory entry (not an object): {entry!r}")
        try:
            backups.append(
                Backup(
                    name=entry["name"],
                    backup_type=entry["backupType"],
                    source=entry.get("source", ""),
                    completed_time=entry.get("completedTime"),
                )
            )
        except KeyError as exc:
            raise BackupRetentionError(f"backup inventory entry missing {exc}: {entry!r}") from exc
    return backups


#: backup_type values this module understands. Anything else means the
#: inventory has a shape this module was never taught — abort rather than
#: guess how to classify entries around it.
_KNOWN_BACKUP_TYPES = frozenset({"Full", "Customer On-Demand"})


def classify(backups: list[Backup], env: str) -> tuple[list[Backup], list[Backup]]:
    """Split into (eligible, ineligible).

    Eligible = ALL of:
      - backup_type == "Customer On-Demand" (never an Automatic/Full backup)
      - name starts with this exact workflow's prefix for this env
      - completed_time parses as a real timestamp

    An Automatic/Full backup, or a Customer On-Demand backup with an
    unrelated name, is unambiguously not ours — safely ineligible, no error.
    This is the everyday case: Azure's own daily Automatic backups never
    match our prefix, so the pipeline must not treat their mere presence as
    an error.

    Two conditions instead ABORT the whole classification (raise), because
    they mean something can't be trusted rather than something is simply not
    ours: an unrecognized backup_type anywhere in the inventory (Azure may
    have introduced a shape this module doesn't know how to reason about),
    or a Customer On-Demand backup whose name matches this workflow's own
    naming convention but has no parseable completed_time (it looks like
    ours, so silently excluding it risks silently discarding history a
    human should look at instead).
    """
    prefix = eligible_prefix(env)
    eligible: list[Backup] = []
    ineligible: list[Backup] = []
    for b in backups:
        if b.backup_type not in _KNOWN_BACKUP_TYPES:
            raise BackupRetentionError(
                f"unrecognized backup_type {b.backup_type!r} for backup {b.name!r} — "
                "refusing to classify any backup while the inventory contains an "
                "unknown shape"
            )
        if b.backup_type == "Full":
            ineligible.append(b)  # Automatic/PITR — never ours, never touched
            continue
        # Customer On-Demand from here.
        if not b.name.startswith(prefix):
            ineligible.append(b)  # unrelated on-demand backup — never ours to touch
            continue
        if _parse_timestamp(b.completed_time) is None:
            raise BackupRetentionError(
                f"backup {b.name!r} matches this workflow's naming convention but has "
                f"an unparseable completed_time ({b.completed_time!r}) — refusing to "
                "guess whether it is safe to keep or prune"
            )
        eligible.append(b)
    return eligible, ineligible


def _sort_key(b: Backup) -> tuple[datetime, str]:
    # classify() already guarantees a parseable timestamp for anything
    # eligible; the assert documents that invariant rather than re-deriving it.
    ts = _parse_timestamp(b.completed_time)
    assert ts is not None  # noqa: S101 — invariant guaranteed by classify()
    return (ts, b.name)  # name is the deterministic tiebreak for equal timestamps


def compute_prune_set(eligible: list[Backup], *, retain: int = RETENTION_TARGET) -> list[Backup]:
    """Oldest-first prune list leaving at most `retain` newest eligible backups.

    Deterministic regardless of the API's own list order: sorted by
    completed_time ascending, backup name as the tiebreak.
    """
    ordered = sorted(eligible, key=_sort_key)
    if len(ordered) <= retain:
        return []
    return ordered[: len(ordered) - retain]


def plan_retention(
    raw_json: str,
    *,
    env: str,
    retain: int = RETENTION_TARGET,
    quota: int = AZURE_ON_DEMAND_QUOTA,
) -> RetentionPlan:
    backups = parse_inventory(raw_json)
    eligible, ineligible = classify(backups, env)
    prune = compute_prune_set(eligible, retain=retain)

    unrelated_on_demand = [b for b in ineligible if b.backup_type == "Customer On-Demand"]
    remaining_eligible = len(eligible) - len(prune)
    # +1 for the new pre-migration backup this whole pipeline exists to make room for.
    projected_total = remaining_eligible + len(unrelated_on_demand) + 1
    blocked = projected_total > quota

    return RetentionPlan(
        eligible=tuple(eligible),
        ineligible=tuple(ineligible),
        prune=tuple(prune),
        blocked_by_unrelated_backups=blocked,
    )


# --------------------------------------------------------------------------- #
# Azure CLI I/O boundary — the only functions that touch a subprocess.
# --------------------------------------------------------------------------- #


def _az_backup_list(*, server_name: str, resource_group: str) -> str:
    result = subprocess.run(
        [
            "az",
            "postgres",
            "flexible-server",
            "backup",
            "list",
            "--server-name",
            server_name,
            "--resource-group",
            resource_group,
            "--output",
            "json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise BackupRetentionError(
            f"az backup list failed (exit {result.returncode}): {result.stderr.strip()}"
        )
    return result.stdout


def _az_backup_delete(*, server_name: str, resource_group: str, name: str) -> None:
    result = subprocess.run(
        [
            "az",
            "postgres",
            "flexible-server",
            "backup",
            "delete",
            "--server-name",
            server_name,
            "--resource-group",
            resource_group,
            "--name",
            name,
            "--yes",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise BackupRetentionError(
            f"az backup delete failed for {name!r} (exit {result.returncode}): {result.stderr.strip()}"
        )


def _verify_post_delete(
    *,
    before: list[Backup],
    pruned: tuple[Backup, ...],
    after_raw_json: str,
) -> None:
    """Fail closed unless the post-delete inventory changed by EXACTLY the
    pruned set — nothing more, nothing less, nothing substituted."""
    after = parse_inventory(after_raw_json)
    before_names = {b.name for b in before}
    after_names = {b.name for b in after}
    pruned_names = {b.name for b in pruned}

    expected_names = before_names - pruned_names
    if after_names != expected_names:
        missing_extra = expected_names - after_names
        unexpected_extra = after_names - expected_names
        raise BackupRetentionError(
            "post-delete inventory does not match exactly the intended prune set — "
            f"missing (besides pruned): {sorted(missing_extra)}; "
            f"unexpected: {sorted(unexpected_extra)}"
        )


def execute_retention(
    *,
    env: str,
    server_name: str,
    resource_group: str,
    retain: int = RETENTION_TARGET,
    quota: int = AZURE_ON_DEMAND_QUOTA,
    dry_run: bool = True,
) -> RetentionPlan:
    """List → plan → (optionally) prune → verify. Fails closed at every step.

    Never raises for a plan alone (dry_run=True always succeeds if the
    inventory itself was readable) — only execution failures raise.
    """
    raw_json = _az_backup_list(server_name=server_name, resource_group=resource_group)
    plan = plan_retention(raw_json, env=env, retain=retain, quota=quota)

    if dry_run:
        return plan

    # Checked BEFORE the "nothing to prune" early return: a fresh backup
    # being unsafe to create is exactly as blocking when there's nothing
    # eligible to prune (quota is full of backups we may never touch) as
    # when there is — either way the caller must not proceed.
    if plan.blocked_by_unrelated_backups:
        raise BackupRetentionError(
            "pruning every eligible backup still would not leave room under the "
            f"Azure quota ({quota}) because unrelated Customer On-Demand backups "
            "are consuming it — refusing to touch backups outside this workflow's "
            "ownership. Manual review required."
        )

    if not plan.prune:
        return plan

    before = parse_inventory(raw_json)
    for backup in plan.prune:
        _az_backup_delete(server_name=server_name, resource_group=resource_group, name=backup.name)

    after_raw_json = _az_backup_list(server_name=server_name, resource_group=resource_group)
    _verify_post_delete(before=before, pruned=plan.prune, after_raw_json=after_raw_json)

    return plan


def _format_plan(plan: RetentionPlan) -> str:
    lines = [
        f"eligible_workflow_backups={len(plan.eligible)}",
        f"prune_count={len(plan.prune)}",
        f"blocked_by_unrelated_backups={plan.blocked_by_unrelated_backups}",
    ]
    for b in plan.prune:
        lines.append(f"  prune: {b.name} ({b.completed_time})")
    for b in plan.eligible:
        if b not in plan.prune:
            lines.append(f"  keep:  {b.name} ({b.completed_time})")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", required=True)
    parser.add_argument("--server-name", required=True)
    parser.add_argument("--resource-group", required=True)
    parser.add_argument("--retain", type=int, default=RETENTION_TARGET)
    parser.add_argument("--execute", action="store_true", help="Actually prune (default: dry-run/print only)")
    args = parser.parse_args(argv)

    try:
        plan = execute_retention(
            env=args.env,
            server_name=args.server_name,
            resource_group=args.resource_group,
            retain=args.retain,
            dry_run=not args.execute,
        )
    except BackupRetentionError as exc:
        print(f"BACKUP RETENTION FAILED CLOSED: {exc}", file=sys.stderr)
        return 1

    print(_format_plan(plan))
    if plan.blocked_by_unrelated_backups and not args.execute:
        print(
            "WARNING: dry-run shows this would fail closed on --execute "
            "(unrelated backups are consuming quota).",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
