from __future__ import annotations

import json
from pathlib import Path

from groundrecall.institutional_views import (
    change_impact_report,
    governance_health_report,
    scope_orientation_pack,
    stewardship_view,
)
from groundrecall.models import (
    ClaimRecord,
    ConceptRecord,
    ContradictionCaseRecord,
    DecisionRecord,
    ScopeRecord,
    StewardshipRecord,
    WorkRecord,
)
from groundrecall.store import GroundRecallStore


def _seed(store: GroundRecallStore) -> None:
    store.save_scope(ScopeRecord(scope_id="scope-public", scope_kind="project", title="Public scope", release_level="public", current_status="reviewed"))
    store.save_scope(ScopeRecord(scope_id="scope-private", scope_kind="project", title="Private scope", release_level="private", current_status="reviewed"))
    store.save_concept(ConceptRecord(concept_id="concept::alpha", title="Alpha", current_status="reviewed"))
    store.save_work(
        WorkRecord(
            work_id="work-current",
            work_kind="project",
            title="Current work",
            scope_id="scope-public",
            related_claim_ids=["claim-a"],
            release_level="public",
            current_status="reviewed",
        )
    )
    store.save_work(
        WorkRecord(
            work_id="work-negative",
            work_kind="experiment",
            title="Negative result",
            scope_id="scope-public",
            outcome="failed",
            release_level="public",
            current_status="reviewed",
        )
    )
    store.save_work(
        WorkRecord(
            work_id="work-private",
            work_kind="project",
            title="Private work",
            scope_id="scope-private",
            release_level="private",
            current_status="reviewed",
        )
    )
    store.save_decision(
        DecisionRecord(
            decision_id="decision-a",
            scope_id="scope-public",
            question="Use A?",
            outcome="Yes",
            supporting_record_ids=["claim-a"],
            release_level="public",
            current_status="reviewed",
        )
    )
    store.save_claim(
        ClaimRecord(
            claim_id="claim-a",
            claim_text="A public scoped claim.",
            concept_ids=["concept::alpha"],
            contradicts_claim_ids=["claim-b"],
            confidence_hint=0.7,
            review_confidence=0.8,
            metadata={"scope_id": "scope-public", "release_level": "public", "stale": True},
            provenance={"support_kind": "direct_source", "grounding_status": "grounded"},
            current_status="reviewed",
        )
    )
    store.save_claim(
        ClaimRecord(
            claim_id="claim-b",
            claim_text="A private scoped claim.",
            metadata={"scope_id": "scope-private", "release_level": "private"},
            current_status="reviewed",
        )
    )
    store.save_claim(
        ClaimRecord(
            claim_id="claim-no-provenance",
            claim_text="Needs provenance.",
            metadata={"scope_id": "scope-public", "release_level": "public"},
            current_status="reviewed",
        )
    )
    store.save_contradiction_case(
        ContradictionCaseRecord(case_id="case-a", claim_ids=["claim-a", "claim-b"], status="open", current_status="triaged")
    )
    store.save_stewardship(
        StewardshipRecord(
            stewardship_id="steward-a",
            subject_type="scope",
            subject_id="scope-public",
            scope_id="scope-public",
            steward_principal_id="alice",
            steward_role_id="scope-steward",
            status="active",
            release_level="public",
            current_status="reviewed",
        )
    )


def test_orientation_pack_excludes_unauthorized_scope_content(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    _seed(store)

    pack = scope_orientation_pack(store.base_dir, scope_id="scope-public", release_cap="public")

    assert pack.scope["record_id"] == "scope-public"
    assert [item["record_id"] for item in pack.current_work] == ["work-current", "work-negative"]
    assert {item["record_id"] for item in pack.negative_results} == {"work-negative"}
    assert {item["record_id"] for item in pack.stale_items} == {"claim-a"}
    assert "work-private" not in json.dumps(pack.model_dump(mode="json"))
    assert pack.steward_roles[0]["basis"] == "explicit_stewardship_record"


def test_impact_report_preserves_contradiction_and_confidence_state(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    _seed(store)

    report = change_impact_report(store.base_dir, subject_type="claim", subject_id="claim-a", release_cap="public")

    assert any(item["record_id"] == "work-current" for item in report.direct_dependents)
    assert any(item["record_id"] == "decision-a" for item in report.direct_dependents)
    assert report.contradiction_state[0]["record_id"] == "case-a"
    assert report.confidence_state["confidence_hint"] == 0.7
    assert report.confidence_state["review_confidence"] == 0.8


def test_governance_report_flags_currentness_and_incomplete_basis(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    _seed(store)
    subs = tmp_path / "subscriptions"
    subs.mkdir()
    (subs / "sub.json").write_text(json.dumps({"subscription_id": "sub-1", "active": True, "cursor": ""}), encoding="utf-8")

    report = governance_health_report(store.base_dir, release_cap="public", subscriptions_dir=subs)

    assert report.stale_high_impact_count == 1
    assert report.incomplete_provenance_count >= 1
    assert report.unacknowledged_change_count == 1
    assert any(item["code"] == "subscription_without_acknowledged_cursor" for item in report.policy_drift_items)


def test_stewardship_view_does_not_rank_people_by_activity(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    _seed(store)

    view = stewardship_view(store.base_dir, release_cap="public")

    assert view.entries == sorted(view.entries, key=lambda item: (item["steward_principal_id"], item["subject_type"], item["subject_id"]))
    assert view.entries[0]["basis"] == "explicit_stewardship_record"
    assert "raw_activity_rankings_suppressed" in view.unavailable_evidence
    assert "rank" not in view.entries[0]
