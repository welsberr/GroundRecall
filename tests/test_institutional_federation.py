from __future__ import annotations

import json
from pathlib import Path

import pytest

from groundrecall.institutional_federation import (
    INSTITUTIONAL_FEDERATION_SCHEMA_VERSION,
    INSTITUTIONAL_POLICY_ACTIONS,
    INSTITUTIONAL_POLICY_FIXTURE_SCHEMA_VERSION,
    build_institutional_federation_capability_report,
)
from groundrecall.institutional_conformance import (
    INSTITUTIONAL_CONFORMANCE_SCHEMA_VERSION,
    build_institutional_conformance_report,
)
from groundrecall import inspect as inspect_module
from groundrecall.inspect import inspect_store
from groundrecall.policy import PolicyDecisionPoint, PolicyDecisionValue, PolicyRequest
from groundrecall.export_guardrails import filter_snapshot_for_public_export
from groundrecall.federation import filter_snapshot_for_federation
from groundrecall.models import GroundRecallSnapshot, ScopeRecord, WorkRecord
from groundrecall.models import (
    ContributionRecord,
    CustodyEventRecord,
    DecisionRecord,
    StewardshipRecord,
)
from groundrecall.institutional_lifecycle import ContributionTransitionError, transition_contribution
from groundrecall.store import GroundRecallStore


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "institutional_policy_cases.json"


def test_institutional_policy_fixture_covers_every_action() -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert payload["schema_version"] == INSTITUTIONAL_POLICY_FIXTURE_SCHEMA_VERSION
    expected_actions = {(item["decision_point"], item["action"]) for item in INSTITUTIONAL_POLICY_ACTIONS}
    fixture_actions = {(item["decision_point"], item["action"]) for item in payload["cases"]}
    assert fixture_actions == expected_actions
    for case in payload["cases"]:
        request = PolicyRequest(
            decision_point=case["decision_point"],
            subject_id="fixture-subject",
            action=case["action"],
            scope_id="fixture-scope",
        )
        assert request.decision_point in PolicyDecisionPoint.__args__
        assert case["expected_decision"] in PolicyDecisionValue.__args__


def test_institutional_capability_report_is_deterministic_and_versioned() -> None:
    report = build_institutional_federation_capability_report()
    assert report == build_institutional_federation_capability_report()
    assert report["schema_version"] == INSTITUTIONAL_FEDERATION_SCHEMA_VERSION
    assert report["policy_action_count"] == len(INSTITUTIONAL_POLICY_ACTIONS)
    assert report["summary"] == {"implemented": 2, "partial": 9, "future": 2}

    compact = build_institutional_federation_capability_report(compact=True)
    assert compact["schema_version"] == INSTITUTIONAL_FEDERATION_SCHEMA_VERSION
    assert "capabilities" not in compact


def test_inspect_can_include_institutional_capability_report(tmp_path: Path) -> None:
    payload = inspect_store(tmp_path / "store", include_institutional_federation=True)
    assert payload["institutional_federation"]["schema_version"] == INSTITUTIONAL_FEDERATION_SCHEMA_VERSION
    assert payload["institutional_federation"]["summary"]["partial"] == 9


def test_inspect_cli_can_emit_institutional_capability_report(tmp_path: Path, capsys) -> None:
    import sys

    original_argv = sys.argv
    try:
        sys.argv = [
            "groundrecall inspect",
            str(tmp_path / "store"),
            "--institutional-federation-summary",
        ]
        inspect_module.main()
    finally:
        sys.argv = original_argv
    output = capsys.readouterr().out
    assert INSTITUTIONAL_FEDERATION_SCHEMA_VERSION in output
    assert '"future": 2' in output


def test_institutional_conformance_report_maps_scenarios_to_evidence() -> None:
    report = build_institutional_conformance_report()
    assert report == build_institutional_conformance_report()
    assert report["schema_version"] == INSTITUTIONAL_CONFORMANCE_SCHEMA_VERSION
    assert report["roadmap_package"] == "IF-12"
    assert report["summary"] == {
        "scenario_count": 6,
        "partial_scenario_count": 6,
        "covered_policy_action_count": 13,
        "evidence_file_count": 21,
    }
    scenario_ids = {item["scenario_id"] for item in report["scenarios"]}
    assert "duplicate_effort_avoidance" in scenario_ids
    assert "policy_governed_assistant_surface" in scenario_ids
    for scenario in report["scenarios"]:
        assert scenario["evidence"]
        assert scenario["caveat"]
        assert all(status != "unknown" for status in scenario["capability_status"].values())


def test_inspect_can_include_institutional_conformance_report(tmp_path: Path) -> None:
    payload = inspect_store(tmp_path / "store", include_institutional_conformance=True)
    assert payload["institutional_conformance"]["schema_version"] == INSTITUTIONAL_CONFORMANCE_SCHEMA_VERSION
    assert payload["institutional_conformance"]["summary"]["scenario_count"] == 6


def test_inspect_cli_can_emit_institutional_conformance_summary(tmp_path: Path, capsys) -> None:
    import sys

    original_argv = sys.argv
    try:
        sys.argv = [
            "groundrecall inspect",
            str(tmp_path / "store"),
            "--institutional-conformance-summary",
        ]
        inspect_module.main()
    finally:
        sys.argv = original_argv
    output = capsys.readouterr().out
    assert INSTITUTIONAL_CONFORMANCE_SCHEMA_VERSION in output
    assert '"scenario_count": 6' in output


def test_scope_and_work_records_round_trip_and_snapshot_compatibility(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    scope = ScopeRecord(
        scope_id="scope::alpha",
        scope_kind="project",
        title="Alpha project",
        release_level="public",
        current_status="reviewed",
    )
    work = WorkRecord(
        work_id="work::negative-result",
        work_kind="experiment",
        title="Rejected approach",
        summary="The approach was tested and found inconclusive.",
        scope_id=scope.scope_id,
        outcome="inconclusive",
        release_level="public",
        current_status="reviewed",
    )
    store.save_scope(scope)
    store.save_work(work)
    snapshot = store.build_snapshot("snapshot-institutional", "2026-07-29T00:00:00Z")
    assert snapshot.scopes == [scope]
    assert snapshot.works == [work]

    legacy = GroundRecallSnapshot.model_validate(
        {"snapshot_id": "legacy", "created_at": "2026-01-01T00:00:00Z"}
    )
    assert legacy.scopes == []
    assert legacy.works == []


def test_scope_and_work_release_filtering_preserves_public_dependencies(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    public_scope = ScopeRecord(scope_id="scope-public", scope_kind="group", title="Public", release_level="public", current_status="reviewed")
    private_scope = ScopeRecord(scope_id="scope-private", scope_kind="group", title="Private", release_level="private", current_status="reviewed")
    public_work = WorkRecord(work_id="work-public", work_kind="lesson", title="Public lesson", scope_id="scope-public", release_level="public", current_status="reviewed")
    private_work = WorkRecord(work_id="work-private", work_kind="lesson", title="Private lesson", scope_id="scope-private", release_level="private", current_status="reviewed")
    snapshot = GroundRecallSnapshot(
        snapshot_id="snapshot-filter",
        created_at="2026-07-29T00:00:00Z",
        scopes=[public_scope, private_scope],
        works=[public_work, private_work],
    )

    public_snapshot, public_report = filter_snapshot_for_public_export(snapshot)
    assert [item.scope_id for item in public_snapshot.scopes] == ["scope-public"]
    assert [item.work_id for item in public_snapshot.works] == ["work-public"]
    assert public_report["excluded_counts"] == {"scope": 1, "work": 1}

    federated, federation_report = filter_snapshot_for_federation(snapshot, target_release_level="public")
    assert [item.scope_id for item in federated.scopes] == ["scope-public"]
    assert [item.work_id for item in federated.works] == ["work-public"]
    assert federation_report.included_counts["scopes"] == 1
    assert federation_report.included_counts["works"] == 1


def test_institutional_cli_creates_and_lists_negative_work(tmp_path: Path, capsys) -> None:
    import sys
    from groundrecall import cli

    original_argv = sys.argv
    try:
        sys.argv = [
            "groundrecall.cli",
            "institutional",
            "scope",
            "create",
            str(tmp_path / "store"),
            "--scope-id",
            "scope-alpha",
            "--scope-kind",
            "project",
            "--title",
            "Alpha",
            "--release-level",
            "public",
            "--status",
            "reviewed",
        ]
        cli.main()
        capsys.readouterr()
        sys.argv = [
            "groundrecall.cli",
            "institutional",
            "work",
            "create",
            str(tmp_path / "store"),
            "--work-id",
            "work-negative",
            "--work-kind",
            "experiment",
            "--title",
            "Failed trial",
            "--scope-id",
            "scope-alpha",
            "--outcome",
            "inconclusive",
            "--release-level",
            "public",
            "--status",
            "reviewed",
        ]
        cli.main()
        capsys.readouterr()
        sys.argv = ["groundrecall.cli", "institutional", "work", "list", str(tmp_path / "store")]
        cli.main()
    finally:
        sys.argv = original_argv
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["outcome"] == "inconclusive"


def test_contribution_transition_preserves_hashes_and_appends_receipt() -> None:
    contribution = ContributionRecord(
        contribution_id="contrib-1",
        contributor_id="alice",
        destination_scope_id="scope-alpha",
        contribution_intent="share negative result",
        contributed_record_ids=["work-negative"],
        contributed_content_hashes=["sha256:abc"],
        state="proposed",
    )
    with pytest.raises(ContributionTransitionError):
        transition_contribution(
            contribution,
            target_state="accepted",
            reviewer_id="bob",
            rationale="skip state",
            receipt_id="receipt-invalid",
        )
    updated, receipt = transition_contribution(
        contribution,
        target_state="triaged",
        reviewer_id="bob",
        reviewer_role="group-reviewer",
        rationale="scope and provenance are present",
        receipt_id="receipt-1",
        reviewed_at="2026-07-29T00:00:00Z",
    )
    assert updated.state == "triaged"
    assert updated.review_receipt_ids == ["receipt-1"]
    assert receipt.reviewed_content_hashes == ["sha256:abc"]
    assert updated.contributed_content_hashes == contribution.contributed_content_hashes


def test_institutional_lifecycle_records_round_trip_and_release_filter(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    store.save_decision(
        DecisionRecord(
            decision_id="decision-1",
            question="Which approach?",
            outcome="Use reviewed approach",
            rationale="The rejected alternative lacked evidence.",
            rejected_alternatives=["unreviewed alternative"],
            release_level="public",
            current_status="reviewed",
        )
    )
    store.save_contribution(
        ContributionRecord(
            contribution_id="contrib-public",
            contributor_id="alice",
            destination_scope_id="scope-alpha",
            contribution_intent="share result",
            proposed_release_level="public",
            release_level="public",
            state="accepted",
            current_status="reviewed",
        )
    )
    store.save_stewardship(
        StewardshipRecord(
            stewardship_id="steward-1",
            subject_type="scope",
            subject_id="scope-alpha",
            steward_principal_id="bob",
            status="active",
            release_level="public",
            current_status="reviewed",
        )
    )
    store.save_custody_event(
        CustodyEventRecord(
            event_id="custody-1",
            event_kind="assign",
            subject_type="scope",
            subject_id="scope-alpha",
            new_custodian_id="bob",
            rationale="initial assignment",
            release_level="public",
        )
    )
    snapshot = store.build_snapshot("snapshot-lifecycle", "2026-07-29T00:00:00Z")
    assert len(snapshot.decisions) == 1
    assert len(snapshot.contributions) == 1
    assert len(snapshot.stewardship) == 1
    assert len(snapshot.custody_events) == 1
    public_snapshot, report = filter_snapshot_for_public_export(snapshot)
    assert len(public_snapshot.decisions) == 1
    assert len(public_snapshot.contributions) == 1
    assert len(public_snapshot.stewardship) == 1
    assert len(public_snapshot.custody_events) == 1
    assert report["excluded_total"] == 0
