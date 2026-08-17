"""Tests for scripts/backup_retention.py (#163).

Locks the exact scenario that failed production deploy run 31989510477
(CustomerOnDemandBackupCannotBePerformedLimitOfBackupsReached at 7/7) and the
safety invariants around it: only this workflow's own pre-migration backups
are ever eligible for pruning; Azure's Automatic backups and any unrelated
Customer On-Demand backup are never touched; anything ambiguous fails closed.
"""

from __future__ import annotations

import json

import pytest
from scripts import backup_retention as br

ENV = "production"


def _backup(name: str, *, backup_type: str = "Customer On-Demand", completed_time="2026-08-10T08:00:00+00:00", source="Customer Initiated"):
    return {
        "backupType": backup_type,
        "completedTime": completed_time,
        "id": f"/subscriptions/x/resourceGroups/rg/.../backups/{name}",
        "name": name,
        "resourceGroup": "rg-metocare-prod",
        "source": source,
        "systemData": None,
        "type": "Microsoft.DBforPostgreSQL/flexibleServers/backups",
    }


def _workflow_backup(day: int, *, hour: int = 8, sha="4c48302a"):
    ts = f"2026-08-{day:02d}T{hour:02d}:00:00+00:00"
    return _backup(f"pre-migration-{ENV}-202608{day:02d}T{hour:02d}0000-{sha}", completed_time=ts)


def _automatic_backup(day: int):
    return _backup(
        f"backup_{day}",
        backup_type="Full",
        source="Automatic",
        completed_time=f"2026-08-{day:02d}T02:00:00+00:00",
    )


def _unrelated_on_demand(name: str, day: int = 10):
    return _backup(name, completed_time=f"2026-08-{day:02d}T09:00:00+00:00")


def _inventory_json(entries: list[dict]) -> str:
    return json.dumps(entries)


# --------------------------------------------------------------------------- #
# Case 1-5: retention count thresholds
# --------------------------------------------------------------------------- #


def test_case1_zero_eligible_backups_prunes_none():
    plan = br.plan_retention(_inventory_json([]), env=ENV)
    assert plan.eligible == ()
    assert plan.prune == ()


def test_case2_four_eligible_prunes_none():
    entries = [_workflow_backup(d) for d in (10, 11, 12, 13)]
    plan = br.plan_retention(_inventory_json(entries), env=ENV)
    assert len(plan.eligible) == 4
    assert plan.prune == ()


def test_case3_five_eligible_prunes_none():
    entries = [_workflow_backup(d) for d in (10, 11, 12, 13, 14)]
    plan = br.plan_retention(_inventory_json(entries), env=ENV)
    assert len(plan.eligible) == 5
    assert plan.prune == ()


def test_case4_six_eligible_prunes_oldest_one():
    entries = [_workflow_backup(d) for d in (10, 11, 12, 13, 14, 15)]
    plan = br.plan_retention(_inventory_json(entries), env=ENV)
    assert len(plan.eligible) == 6
    assert len(plan.prune) == 1
    assert plan.prune[0].name == _workflow_backup(10)["name"]


def test_case5_seven_eligible_prunes_oldest_two_to_reach_target_five():
    entries = [_workflow_backup(d) for d in (10, 11, 12, 13, 14, 15, 16)]
    plan = br.plan_retention(_inventory_json(entries), env=ENV)
    assert len(plan.eligible) == 7
    assert len(plan.prune) == 2
    pruned_names = {b.name for b in plan.prune}
    assert pruned_names == {_workflow_backup(10)["name"], _workflow_backup(11)["name"]}


# --------------------------------------------------------------------------- #
# Case 6-7: never touch backups outside this workflow's exact ownership
# --------------------------------------------------------------------------- #


def test_case6_automatic_backups_never_eligible_or_pruned():
    entries = [_workflow_backup(d) for d in (10, 11, 12, 13, 14, 15)] + [
        _automatic_backup(d) for d in (11, 12, 13, 14, 15, 16, 17)
    ]
    plan = br.plan_retention(_inventory_json(entries), env=ENV)
    automatic_names = {e["name"] for e in entries if e["backupType"] == "Full"}
    assert all(b.name not in automatic_names for b in plan.eligible)
    assert all(b.name not in automatic_names for b in plan.prune)
    assert len(plan.ineligible) == 7  # all 7 automatic backups land here, untouched


def test_case7_unrelated_customer_on_demand_never_pruned():
    entries = [_workflow_backup(d) for d in (10, 11, 12, 13, 14, 15)] + [
        _unrelated_on_demand("someone-elses-manual-backup"),
    ]
    plan = br.plan_retention(_inventory_json(entries), env=ENV)
    assert all(b.name != "someone-elses-manual-backup" for b in plan.prune)
    assert any(b.name == "someone-elses-manual-backup" for b in plan.ineligible)


# --------------------------------------------------------------------------- #
# Case 8: quota exhausted by backups we're not allowed to touch
# --------------------------------------------------------------------------- #


def test_case8_blocked_when_unrelated_backups_alone_fill_the_quota():
    # 5 eligible (at target, nothing to prune) + 2 unrelated on-demand = 7 total.
    # Creating one more backup would hit the 7-backup quota, and none of the
    # 2 unrelated ones may be pruned to make room.
    entries = [_workflow_backup(d) for d in (10, 11, 12, 13, 14)] + [
        _unrelated_on_demand("other-team-backup-1", day=10),
        _unrelated_on_demand("other-team-backup-2", day=11),
    ]
    plan = br.plan_retention(_inventory_json(entries), env=ENV)
    assert plan.prune == ()  # already at/under target, nothing eligible to prune
    assert plan.blocked_by_unrelated_backups is True


def test_case8_execute_retention_raises_when_blocked(monkeypatch):
    entries = [_workflow_backup(d) for d in (10, 11, 12, 13, 14)] + [
        _unrelated_on_demand("other-team-backup-1", day=10),
        _unrelated_on_demand("other-team-backup-2", day=11),
    ]
    raw = _inventory_json(entries)
    monkeypatch.setattr(br, "_az_backup_list", lambda **_: raw)
    deletes: list[str] = []
    monkeypatch.setattr(br, "_az_backup_delete", lambda **kw: deletes.append(kw["name"]))

    with pytest.raises(br.BackupRetentionError, match="unrelated Customer On-Demand"):
        br.execute_retention(
            env=ENV, server_name="s", resource_group="rg", dry_run=False
        )
    assert deletes == []  # never attempted a delete once blocked


# --------------------------------------------------------------------------- #
# Case 9-10: ambiguous/unrecognized entries abort the whole plan
# --------------------------------------------------------------------------- #


def test_case9_malformed_timestamp_on_matching_backup_fails_closed():
    entries = [_workflow_backup(10), _workflow_backup(11)]
    entries[1]["completedTime"] = "not-a-timestamp"
    with pytest.raises(br.BackupRetentionError, match="unparseable completed_time"):
        br.plan_retention(_inventory_json(entries), env=ENV)


def test_case9_missing_timestamp_on_matching_backup_fails_closed():
    entries = [_workflow_backup(10)]
    entries[0]["completedTime"] = None
    with pytest.raises(br.BackupRetentionError, match="unparseable completed_time"):
        br.plan_retention(_inventory_json(entries), env=ENV)


def test_case10_unknown_backup_type_fails_closed():
    entries = [_workflow_backup(10), _backup("weird-backup", backup_type="Differential")]
    with pytest.raises(br.BackupRetentionError, match="unrecognized backup_type"):
        br.plan_retention(_inventory_json(entries), env=ENV)


# --------------------------------------------------------------------------- #
# Case 11: deterministic ordering, independent of API list order
# --------------------------------------------------------------------------- #


def test_case11_identical_timestamps_break_ties_deterministically_by_name():
    same_ts = "2026-08-10T08:00:00+00:00"
    entries = [
        _backup(f"pre-migration-{ENV}-20260810T080000-cccccccc", completed_time=same_ts),
        _backup(f"pre-migration-{ENV}-20260810T080000-aaaaaaaa", completed_time=same_ts),
        _backup(f"pre-migration-{ENV}-20260810T080000-bbbbbbbb", completed_time=same_ts),
    ] + [_workflow_backup(d) for d in (11, 12, 13, 14)]  # pad to 7 total, prune 2

    plan1 = br.plan_retention(_inventory_json(entries), env=ENV)
    # Re-run with the SAME entries in a different (reversed) list order — the
    # API gives no ordering guarantee, so the result must not depend on it.
    plan2 = br.plan_retention(_inventory_json(list(reversed(entries))), env=ENV)

    assert [b.name for b in plan1.prune] == [b.name for b in plan2.prune]
    pruned_names = {b.name for b in plan1.prune}
    # Among the three identical timestamps, the alphabetically-first name is
    # treated as "older" — deterministic, not incidental.
    assert f"pre-migration-{ENV}-20260810T080000-aaaaaaaa" in pruned_names


# --------------------------------------------------------------------------- #
# Case 12-14: execution safety — list failure, delete failure, post-verify
# --------------------------------------------------------------------------- #


def test_case12_inventory_list_failure_causes_no_deletion(monkeypatch):
    def _boom(**_):
        raise br.BackupRetentionError("az backup list failed (exit 1): simulated")

    monkeypatch.setattr(br, "_az_backup_list", _boom)
    deletes: list[str] = []
    monkeypatch.setattr(br, "_az_backup_delete", lambda **kw: deletes.append(kw["name"]))

    with pytest.raises(br.BackupRetentionError):
        br.execute_retention(env=ENV, server_name="s", resource_group="rg", dry_run=False)
    assert deletes == []


def test_case13_delete_failure_stops_before_any_backup_creation_signal(monkeypatch):
    entries = [_workflow_backup(d) for d in (10, 11, 12, 13, 14, 15, 16)]
    raw = _inventory_json(entries)
    monkeypatch.setattr(br, "_az_backup_list", lambda **_: raw)

    attempted: list[str] = []

    def _fail_delete(**kw):
        attempted.append(kw["name"])
        raise br.BackupRetentionError(f"az backup delete failed for {kw['name']!r} (exit 1): simulated")

    monkeypatch.setattr(br, "_az_backup_delete", _fail_delete)

    with pytest.raises(br.BackupRetentionError, match="delete failed"):
        br.execute_retention(env=ENV, server_name="s", resource_group="rg", dry_run=False)
    assert len(attempted) == 1  # stopped at the first failing delete, no partial continuation


def test_case14_unexpected_post_delete_inventory_fails_closed(monkeypatch):
    entries = [_workflow_backup(d) for d in (10, 11, 12, 13, 14, 15, 16)]
    raw_before = _inventory_json(entries)
    calls = {"n": 0}

    def _list(**_):
        calls["n"] += 1
        if calls["n"] == 1:
            return raw_before
        # Second call (post-delete verification): report an inventory that
        # doesn't match "before minus the intended prune set" — e.g. Azure's
        # own state ended up different from what this run caused.
        return _inventory_json([_workflow_backup(d) for d in (12, 13, 14, 15, 16)] + [_workflow_backup(20)])

    monkeypatch.setattr(br, "_az_backup_list", _list)
    monkeypatch.setattr(br, "_az_backup_delete", lambda **_: None)

    with pytest.raises(br.BackupRetentionError, match="does not match exactly the intended prune set"):
        br.execute_retention(env=ENV, server_name="s", resource_group="rg", dry_run=False)


# --------------------------------------------------------------------------- #
# Dry-run mode never deletes
# --------------------------------------------------------------------------- #


def test_dry_run_never_calls_delete(monkeypatch):
    entries = [_workflow_backup(d) for d in (10, 11, 12, 13, 14, 15, 16)]
    monkeypatch.setattr(br, "_az_backup_list", lambda **_: _inventory_json(entries))
    deletes: list[str] = []
    monkeypatch.setattr(br, "_az_backup_delete", lambda **kw: deletes.append(kw["name"]))

    plan = br.execute_retention(env=ENV, server_name="s", resource_group="rg", dry_run=True)

    assert deletes == []
    assert len(plan.prune) == 2  # plan is still computed, just not acted on


# --------------------------------------------------------------------------- #
# Regression fixture: the exact inventory shape observed on psql-metocare-prod
# immediately after the manual #163 incident recovery (7 Automatic + 6
# Customer On-Demand, all workflow-owned). No Azure calls in this test — the
# JSON was captured via a prior read-only `az ... backup list` and is asserted
# here as a frozen fixture so this stays a pure, network-free unit test.
# --------------------------------------------------------------------------- #


def test_actual_post_recovery_production_inventory_shape_is_handled():
    automatic = [_automatic_backup(d) for d in (11, 12, 13, 14, 15, 16, 17)]
    workflow = [
        _backup(name, completed_time=ts)
        for name, ts in [
            ("pre-migration-production-20260810T104051-a9b416fe", "2026-08-10T10:46:53.790474+00:00"),
            ("pre-migration-production-20260810T120841-e12d5841", "2026-08-10T12:14:47.213708+00:00"),
            ("pre-migration-production-20260811T063632-0419626d", "2026-08-11T06:38:15.139063+00:00"),
            ("pre-migration-production-20260812T013030-f7557a60", "2026-08-12T01:31:59.146860+00:00"),
            ("pre-migration-production-20260814T011950-c6389a84", "2026-08-14T01:21:15.742092+00:00"),
            ("pre-migration-production-20260814T044558-870145b9", "2026-08-14T04:52:17.140025+00:00"),
        ]
    ]
    plan = br.plan_retention(_inventory_json(automatic + workflow), env=ENV)
    assert len(plan.eligible) == 6
    assert len(plan.prune) == 1  # 6 > retain(5) — one more prune due before the next deploy
    assert plan.blocked_by_unrelated_backups is False
