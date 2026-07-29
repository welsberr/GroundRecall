from __future__ import annotations

from datetime import datetime, timezone

from .models import ContributionRecord, ContributionReviewReceipt


CONTRIBUTION_STATES = (
    "proposed",
    "triaged",
    "under_review",
    "accepted",
    "partially_accepted",
    "rejected",
    "deferred",
    "withdrawn",
    "superseded",
)

VALID_CONTRIBUTION_TRANSITIONS: dict[str, set[str]] = {
    "proposed": {"triaged", "under_review", "withdrawn"},
    "triaged": {"under_review", "deferred", "withdrawn"},
    "under_review": {"accepted", "partially_accepted", "rejected", "deferred", "withdrawn"},
    "accepted": {"superseded", "withdrawn"},
    "partially_accepted": {"under_review", "accepted", "superseded", "withdrawn"},
    "rejected": {"under_review", "withdrawn"},
    "deferred": {"under_review", "withdrawn", "superseded"},
    "withdrawn": set(),
    "superseded": set(),
}


class ContributionTransitionError(ValueError):
    """Raised when a contribution lifecycle transition is invalid."""


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def transition_contribution(
    contribution: ContributionRecord,
    *,
    target_state: str,
    reviewer_id: str,
    rationale: str,
    receipt_id: str,
    reviewer_role: str = "",
    policy_id: str = "",
    reviewed_at: str = "",
) -> tuple[ContributionRecord, ContributionReviewReceipt]:
    if target_state not in CONTRIBUTION_STATES:
        raise ContributionTransitionError(f"unknown contribution state: {target_state}")
    if target_state not in VALID_CONTRIBUTION_TRANSITIONS.get(contribution.state, set()):
        raise ContributionTransitionError(f"invalid contribution transition: {contribution.state} -> {target_state}")
    if not reviewer_id.strip():
        raise ContributionTransitionError("reviewer_id is required for a contribution transition")
    if not rationale.strip():
        raise ContributionTransitionError("rationale is required for a contribution transition")
    timestamp = reviewed_at or now_utc()
    receipt = ContributionReviewReceipt(
        receipt_id=receipt_id,
        contribution_id=contribution.contribution_id,
        reviewer_id=reviewer_id,
        reviewer_role=reviewer_role,
        decision=target_state,
        rationale=rationale,
        reviewed_content_hashes=list(contribution.contributed_content_hashes),
        policy_id=policy_id,
        reviewed_at=timestamp,
        release_level=contribution.release_level,
    )
    updated = contribution.model_copy(
        update={
            "state": target_state,
            "review_receipt_ids": [*contribution.review_receipt_ids, receipt.receipt_id],
            "rationale": rationale,
            "updated_at": timestamp,
        }
    )
    return updated, receipt
