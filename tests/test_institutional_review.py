from __future__ import annotations

from pathlib import Path

import pytest

from groundrecall.federation import FederationPolicyError
from groundrecall.institutional_review import (
    QuorumRule,
    build_feedback_bundle,
    content_hash,
    evaluate_review_quorum,
    record_federation_feedback,
    record_review_receipt,
    unresolved_federation_disagreements,
    verify_feedback_bundle,
)
from groundrecall.models import FederationFeedbackRecord, ReviewReceiptRecord
from groundrecall.store import GroundRecallStore


KEY = "feedback signing secret"


def _receipt(receipt_id: str, reviewer: str, role: str, decision: str = "approve", reviewed_hash: str = "hash-current") -> ReviewReceiptRecord:
    return ReviewReceiptRecord(
        receipt_id=receipt_id,
        subject_type="claim",
        subject_id="claim-1",
        reviewer_principal_id=reviewer,
        reviewer_role_id=role,
        decision=decision,
        rationale=f"{decision} by {reviewer}",
        reviewed_content_hash=reviewed_hash,
        policy_id="policy.v1",
        reviewed_at="2026-07-29T00:00:00Z",
        release_level="internal",
    )


def test_quorum_requires_independent_distinct_reviewers_and_preserves_dissent() -> None:
    receipts = [
        _receipt("r1", "author", "group-reviewer"),
        _receipt("r2", "reviewer-b", "scope-steward"),
        _receipt("r3", "reviewer-b", "scope-steward"),
        _receipt("r4", "reviewer-c", "adversarial-reviewer", decision="dissent"),
        _receipt("old", "reviewer-d", "group-reviewer", reviewed_hash="old-hash"),
    ]
    result = evaluate_review_quorum(
        receipts,
        subject_type="claim",
        subject_id="claim-1",
        rule=QuorumRule(
            subject_type="claim",
            minimum_approvals=2,
            required_role_ids=["group-reviewer", "scope-steward"],
            independent_from_principal_ids=["author"],
        ),
        current_content_hash="hash-current",
    )

    assert result.satisfied is False
    assert result.approval_count == 2
    assert result.duplicate_principal_ids == ["reviewer-b"]
    assert result.non_independent_principal_ids == ["author"]
    assert result.dissent_receipt_ids == ["r4"]
    assert result.invalidated_receipt_ids == ["old"]


def test_review_receipt_content_hash_mismatch_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(FederationPolicyError, match="content hash"):
        record_review_receipt(tmp_path / "store", _receipt("r1", "reviewer-a", "group-reviewer"), expected_content_hash="other")


def test_feedback_bundle_signs_verifies_and_disagreement_remains_visible(tmp_path: Path) -> None:
    store_dir = tmp_path / "store"
    record_review_receipt(store_dir, _receipt("approve", "reviewer-a", "group-reviewer", decision="approve"))
    record_review_receipt(store_dir, _receipt("dissent", "reviewer-b", "adversarial-reviewer", decision="dissent"))
    feedback = record_federation_feedback(
        store_dir,
        FederationFeedbackRecord(
            feedback_id="fb-1",
            origin_instance_id="receiver-a",
            target_instance_id="producer-a",
            subject_type="claim",
            subject_id="claim-1",
            decision="dissent",
            rationale="Receiver adjudication preserves disagreement.",
            related_receipt_ids=["dissent"],
            created_at="2026-07-29T01:00:00Z",
            release_level="internal",
        ),
    )

    assert feedback.content_hash == content_hash(feedback.model_dump(mode="json", exclude={"content_hash"}))
    assert unresolved_federation_disagreements(store_dir)[0]["decisions"] == ["approve", "dissent"]
    bundle = build_feedback_bundle(
        store_dir,
        origin_instance_id="receiver-a",
        target_instance_id="producer-a",
        signing_key=KEY,
        key_id="k1",
        out_path=tmp_path / "feedback.json",
    )
    verified = verify_feedback_bundle(bundle, verification_key=KEY, key_id="k1")
    assert verified.content_hash == bundle.content_hash
    assert verified.feedback[0].feedback_id == "fb-1"


def test_snapshot_includes_review_feedback_records(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    store.save_review_receipt(_receipt("r1", "reviewer-a", "group-reviewer"))
    store.save_federation_feedback(
        FederationFeedbackRecord(
            feedback_id="fb-1",
            origin_instance_id="receiver-a",
            subject_type="claim",
            subject_id="claim-1",
            decision="needs_review",
        )
    )

    snapshot = store.build_snapshot("snap-1", "2026-07-29T00:00:00Z")
    assert [item.receipt_id for item in snapshot.review_receipts] == ["r1"]
    assert [item.feedback_id for item in snapshot.federation_feedback] == ["fb-1"]
