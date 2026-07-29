from __future__ import annotations

from pathlib import Path

import pytest

from groundrecall.federation import FederationPolicyError, FederationTrustKey, FederationTrustRegistry
from groundrecall.institutional_custody import (
    CUSTODY_PLAN_SCHEMA_VERSION,
    orphan_stewardship_report,
    plan_instance_retirement,
    plan_tenancy_departure,
    record_custody_event,
)
from groundrecall.models import ContributionRecord, CustodyEventRecord, ScopeRecord, StewardshipRecord, WorkRecord
from groundrecall.store import GroundRecallStore


def _seed_store(store: GroundRecallStore) -> None:
    store.save_scope(
        ScopeRecord(
            scope_id="scope-group",
            scope_kind="project",
            title="Group project",
            owner_principal_ids=["group-a"],
            release_level="internal",
            current_status="reviewed",
        )
    )
    store.save_scope(
        ScopeRecord(
            scope_id="scope-private",
            scope_kind="project",
            title="Private notes",
            owner_principal_ids=["alice"],
            release_level="private",
            current_status="reviewed",
        )
    )
    store.save_work(
        WorkRecord(
            work_id="work-group",
            work_kind="project",
            title="Reviewed group work",
            scope_id="scope-group",
            release_level="internal",
            current_status="reviewed",
        )
    )
    store.save_work(
        WorkRecord(
            work_id="work-orphan",
            work_kind="lesson",
            title="Needs steward",
            scope_id="scope-group",
            release_level="internal",
            current_status="reviewed",
        )
    )
    store.save_contribution(
        ContributionRecord(
            contribution_id="contrib-private",
            origin_instance_id="host-a",
            contributor_id="alice",
            destination_scope_id="scope-private",
            contribution_intent="personal note",
            proposed_release_level="private",
            release_level="private",
            state="proposed",
            current_status="draft",
        )
    )
    store.save_stewardship(
        StewardshipRecord(
            stewardship_id="steward-group",
            subject_type="work",
            subject_id="work-group",
            scope_id="scope-group",
            steward_principal_id="alice",
            status="active",
            release_level="internal",
            current_status="reviewed",
        )
    )
    store.save_custody_event(
        CustodyEventRecord(
            event_id="custody-existing",
            event_kind="assign",
            subject_type="work",
            subject_id="work-group",
            new_custodian_id="alice",
            release_level="internal",
        )
    )


def test_orphan_report_is_deterministic_and_uses_explicit_stewardship(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    _seed_store(store)

    report = orphan_stewardship_report(store.base_dir)

    assert report.schema_version == CUSTODY_PLAN_SCHEMA_VERSION
    assert ("work", "work-orphan") in {(item.subject_type, item.subject_id) for item in report.items}
    assert ("work", "work-group") not in {(item.subject_type, item.subject_id) for item in report.items}
    assert report.items == sorted(report.items, key=lambda item: (item.subject_type, item.subject_id))


def test_departure_plan_does_not_delete_or_convert_private_records(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    _seed_store(store)

    plan = plan_tenancy_departure(store.base_dir, departing_principal_id="alice", planned_at="2026-07-29T00:00:00Z")

    assert plan.dry_run is True
    assert plan.active_stewardship_ids == ["steward-group"]
    assert plan.handoff_required[0]["required_action"] == "assign_successor_or_mark_orphan"
    assert {item["record_id"] for item in plan.private_personal_records} == {"scope-private", "contrib-private"}
    assert "private_personal_records_require_separate_retention_authority" in plan.warnings
    assert any(item["record_id"] == "work-group" for item in plan.group_owned_records_retained)
    assert store.get_scope("scope-private") is not None


def test_record_custody_event_blocks_release_broadening(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    _seed_store(store)

    with pytest.raises(FederationPolicyError, match="broaden"):
        record_custody_event(
            store.base_dir,
            CustodyEventRecord(
                event_id="custody-public",
                event_kind="transfer",
                subject_type="work",
                subject_id="work-group",
                previous_custodian_id="alice",
                new_custodian_id="bob",
                release_level="public",
            ),
        )
    saved = record_custody_event(
        store.base_dir,
        CustodyEventRecord(
            event_id="custody-internal",
            event_kind="transfer",
            subject_type="work",
            subject_id="work-group",
            previous_custodian_id="alice",
            new_custodian_id="bob",
            release_level="internal",
        ),
        authority="scope-steward",
    )
    assert saved.authority_id == "scope-steward"


def test_instance_retirement_plan_reports_required_surfaces(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    _seed_store(store)
    registry = FederationTrustRegistry(
        keys=[
            FederationTrustKey(instance_id="host-a", key_id="active", key_material="secret", release_levels=["internal"]),
            FederationTrustKey(instance_id="host-b", key_id="other", key_material="secret"),
        ]
    )
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(registry.model_dump_json(indent=2), encoding="utf-8")
    subscriptions = tmp_path / "subscriptions"
    catalogs = tmp_path / "catalogs"
    quarantine = tmp_path / "quarantine"
    backups = tmp_path / "backups"
    for directory in (subscriptions, catalogs, quarantine, backups):
        directory.mkdir()
        (directory / "item.json").write_text("{}", encoding="utf-8")

    plan = plan_instance_retirement(
        store.base_dir,
        instance_id="host-a",
        planned_at="2026-07-29T00:00:00Z",
        replacement_instance_id="host-new",
        registry_path=registry_path,
        subscriptions_dir=subscriptions,
        catalogs_dir=catalogs,
        quarantine_dir=quarantine,
        backups_dir=backups,
    )

    assert plan.dry_run is True
    assert plan.trust_key_count == 1
    assert plan.active_trust_key_count == 1
    assert plan.subscription_count == 1
    assert plan.catalog_count == 1
    assert plan.quarantine_item_count == 1
    assert plan.backup_item_count == 1
    assert plan.pending_contribution_count == 1
    assert "revoke_or_supersede_trust_keys" in plan.required_actions
    assert "active_trust_keys_require_revocation" in plan.warnings
