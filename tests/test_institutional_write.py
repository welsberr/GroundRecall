from __future__ import annotations

import pytest

from groundrecall.institutional_write import (
    InstitutionalWriteError,
    save_institutional_record,
    transition_contribution_with_policy,
)
from groundrecall.models import ContributionRecord, ScopeRecord, WorkRecord
from groundrecall.policy import StaticPolicyProvider
from groundrecall.policy_coverage import build_policy_coverage_report
from groundrecall.store import GroundRecallStore


def test_policy_gated_institutional_save_writes_when_allowed(tmp_path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    record = ScopeRecord(
        scope_id="scope-alpha",
        scope_kind="project",
        title="Alpha",
        release_level="internal",
        current_status="reviewed",
    )

    result = save_institutional_record(store, record)

    assert result.writes_performed is True
    assert result.record_kind == "scope"
    assert result.policy_decision.decision == "allow"
    assert store.get_scope("scope-alpha") == record


def test_policy_gated_institutional_save_blocks_before_write(tmp_path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    provider = StaticPolicyProvider(default_decision="hard_gate", policy_id="test.hard_gate")
    record = WorkRecord(
        work_id="work-alpha",
        work_kind="experiment",
        title="Alpha experiment",
        scope_id="scope-alpha",
        release_level="internal",
    )

    with pytest.raises(InstitutionalWriteError) as exc_info:
        save_institutional_record(store, record, policy_provider=provider)

    assert exc_info.value.decision.decision == "hard_gate"
    assert exc_info.value.decision.subject_id == "work-alpha"
    assert store.get_work("work-alpha") is None


def test_policy_gated_contribution_transition_persists_receipt_when_allowed(tmp_path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    contribution = ContributionRecord(
        contribution_id="contrib-alpha",
        contributor_id="alice",
        destination_scope_id="scope-alpha",
        contribution_intent="share result",
        contributed_record_ids=["work-alpha"],
        contributed_content_hashes=["sha256:abc"],
        release_level="internal",
        proposed_release_level="internal",
    )
    store.save_contribution(contribution)

    result = transition_contribution_with_policy(
        store,
        "contrib-alpha",
        target_state="triaged",
        reviewer_id="bob",
        reviewer_role="group-reviewer",
        rationale="ready for review",
        receipt_id="receipt-alpha",
    )

    assert result.writes_performed is True
    assert result.written_record_ids == ["contrib-alpha", "receipt-alpha"]
    assert store.get_contribution("contrib-alpha").state == "triaged"  # type: ignore[union-attr]
    assert store.get_contribution_review_receipt("receipt-alpha").reviewed_content_hashes == ["sha256:abc"]  # type: ignore[union-attr]


def test_policy_gated_contribution_transition_blocks_before_write(tmp_path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    provider = StaticPolicyProvider(default_decision="deny", policy_id="test.deny")
    contribution = ContributionRecord(
        contribution_id="contrib-alpha",
        contributor_id="alice",
        destination_scope_id="scope-alpha",
        contribution_intent="share result",
        contributed_record_ids=["work-alpha"],
        contributed_content_hashes=["sha256:abc"],
    )
    store.save_contribution(contribution)

    with pytest.raises(InstitutionalWriteError) as exc_info:
        transition_contribution_with_policy(
            store,
            "contrib-alpha",
            target_state="triaged",
            reviewer_id="bob",
            rationale="blocked",
            receipt_id="receipt-alpha",
            policy_provider=provider,
        )

    assert exc_info.value.decision.decision == "deny"
    assert store.get_contribution("contrib-alpha").state == "proposed"  # type: ignore[union-attr]
    assert store.get_contribution_review_receipt("receipt-alpha") is None


def test_institutional_write_policy_coverage_is_no_longer_future() -> None:
    report = build_policy_coverage_report()
    routes = {item["route_id"]: item for item in report["routes"]}

    assert routes["python_api.institutional.save_records"]["status"] == "covered"
    assert routes["python_api.institutional.transition_contribution"]["status"] == "covered"
    assert report["summary"]["future_route_count"] == 1
