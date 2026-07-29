"""Policy-gated institutional record write helpers."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .institutional_lifecycle import transition_contribution
from .models import (
    ContributionRecord,
    ContributionReviewReceipt,
    CustodyEventRecord,
    DecisionRecord,
    ScopeRecord,
    StewardshipRecord,
    WorkRecord,
)
from .policy import PolicyDecision, PolicyDecisionProvider, PolicyRequest, compose_policy_decisions
from .store import GroundRecallStore


InstitutionalWritableRecord = (
    ScopeRecord
    | WorkRecord
    | DecisionRecord
    | ContributionRecord
    | ContributionReviewReceipt
    | StewardshipRecord
    | CustodyEventRecord
)


class InstitutionalWriteError(PermissionError):
    """Raised when policy blocks an institutional write."""

    def __init__(self, message: str, *, decision: PolicyDecision):
        super().__init__(message)
        self.decision = decision


class InstitutionalWriteResult(BaseModel):
    schema_version: str = "groundrecall.institutional_write_result.v1"
    record_kind: str
    record_id: str
    writes_performed: bool
    policy_decision: PolicyDecision
    written_record_ids: list[str] = Field(default_factory=list)


def save_institutional_record(
    store: GroundRecallStore,
    record: InstitutionalWritableRecord,
    *,
    policy_provider: PolicyDecisionProvider | None = None,
    action: str = "save_institutional_record",
    metadata: dict[str, Any] | None = None,
) -> InstitutionalWriteResult:
    """Policy-gate and save one institutional record.

    The helper treats direct store methods as low-level primitives and gives
    coding agents a single policy-aware entry point for durable institutional
    writes.  Deny and hard-gate decisions raise before any store write.
    """

    record_kind, record_id = _record_identity(record)
    decision = _evaluate_policy(
        policy_provider,
        PolicyRequest(
            decision_point=_decision_point_for_record(record),
            subject_id=record_id,
            action=action,
            record_kind=record_kind,
            record_id=record_id,
            release_level=getattr(record, "release_level", None),
            scope_id=_scope_id_for_record(record),
            durable_memory_change=True,
            metadata={"groundrecall.record_kind": record_kind, **(metadata or {})},
        ),
    )
    _raise_if_blocked(decision, f"policy blocked institutional {record_kind} write: {record_id}")
    _save_record(store, record)
    return InstitutionalWriteResult(
        record_kind=record_kind,
        record_id=record_id,
        writes_performed=True,
        policy_decision=decision,
        written_record_ids=[record_id],
    )


def transition_contribution_with_policy(
    store: GroundRecallStore,
    contribution_id: str,
    *,
    target_state: str,
    reviewer_id: str,
    rationale: str,
    receipt_id: str,
    reviewer_role: str = "",
    policy_id: str = "",
    reviewed_at: str = "",
    policy_provider: PolicyDecisionProvider | None = None,
    metadata: dict[str, Any] | None = None,
) -> InstitutionalWriteResult:
    """Policy-gate, transition, and persist a contribution plus receipt."""

    contribution = store.get_contribution(contribution_id)
    if contribution is None:
        raise KeyError(f"unknown contribution: {contribution_id}")
    decision = _evaluate_policy(
        policy_provider,
        PolicyRequest(
            decision_point="review",
            subject_id=contribution_id,
            action="review_group_contribution",
            record_kind="contribution",
            record_id=contribution_id,
            release_level=contribution.release_level,
            target_release_level=contribution.proposed_release_level,
            scope_id=contribution.destination_scope_id,
            durable_memory_change=True,
            metadata={
                "groundrecall.target_state": target_state,
                "groundrecall.reviewer_role": reviewer_role,
                **(metadata or {}),
            },
        ),
    )
    _raise_if_blocked(decision, f"policy blocked contribution transition: {contribution_id} -> {target_state}")
    updated, receipt = transition_contribution(
        contribution,
        target_state=target_state,
        reviewer_id=reviewer_id,
        reviewer_role=reviewer_role,
        rationale=rationale,
        receipt_id=receipt_id,
        policy_id=policy_id or decision.policy_id,
        reviewed_at=reviewed_at,
    )
    store.save_contribution(updated)
    store.save_contribution_review_receipt(receipt)
    return InstitutionalWriteResult(
        record_kind="contribution",
        record_id=contribution_id,
        writes_performed=True,
        policy_decision=decision,
        written_record_ids=[contribution_id, receipt.receipt_id],
    )


def _evaluate_policy(provider: PolicyDecisionProvider | None, request: PolicyRequest) -> PolicyDecision:
    if provider is None:
        return compose_policy_decisions([], request=request)
    return provider.evaluate(request)


def _raise_if_blocked(decision: PolicyDecision, message: str) -> None:
    if decision.decision in {"deny", "hard_gate"}:
        raise InstitutionalWriteError(message, decision=decision)


def _record_identity(record: InstitutionalWritableRecord) -> tuple[str, str]:
    if isinstance(record, ScopeRecord):
        return "scope", record.scope_id
    if isinstance(record, WorkRecord):
        return "work", record.work_id
    if isinstance(record, DecisionRecord):
        return "decision", record.decision_id
    if isinstance(record, ContributionRecord):
        return "contribution", record.contribution_id
    if isinstance(record, ContributionReviewReceipt):
        return "contribution_review_receipt", record.receipt_id
    if isinstance(record, StewardshipRecord):
        return "stewardship", record.stewardship_id
    if isinstance(record, CustodyEventRecord):
        return "custody_event", record.event_id
    raise TypeError(f"unsupported institutional record type: {type(record).__name__}")


def _scope_id_for_record(record: InstitutionalWritableRecord) -> str:
    if isinstance(record, ScopeRecord):
        return record.scope_id
    if isinstance(record, WorkRecord):
        return record.scope_id
    if isinstance(record, DecisionRecord):
        return record.scope_id
    if isinstance(record, ContributionRecord):
        return record.destination_scope_id
    if isinstance(record, StewardshipRecord):
        return record.scope_id
    if isinstance(record, CustodyEventRecord):
        return record.scope_id
    return ""


def _decision_point_for_record(record: InstitutionalWritableRecord) -> str:
    if isinstance(record, ContributionReviewReceipt):
        return "review"
    if isinstance(record, CustodyEventRecord):
        return "act"
    return "propose"


def _save_record(store: GroundRecallStore, record: InstitutionalWritableRecord) -> None:
    if isinstance(record, ScopeRecord):
        store.save_scope(record)
    elif isinstance(record, WorkRecord):
        store.save_work(record)
    elif isinstance(record, DecisionRecord):
        store.save_decision(record)
    elif isinstance(record, ContributionRecord):
        store.save_contribution(record)
    elif isinstance(record, ContributionReviewReceipt):
        store.save_contribution_review_receipt(record)
    elif isinstance(record, StewardshipRecord):
        store.save_stewardship(record)
    elif isinstance(record, CustodyEventRecord):
        store.save_custody_event(record)
    else:
        raise TypeError(f"unsupported institutional record type: {type(record).__name__}")
