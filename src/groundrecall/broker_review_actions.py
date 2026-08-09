"""Mockable federated review actions (RB6d); no canonical writes."""
from __future__ import annotations

import hashlib
import uuid
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from .federation_review_source import RemoteReviewItem
from .policy import PolicyRequest, RELEASE_RANK, load_policy_plugins


class BrokerActionResult(BaseModel):
    schema_version: str = "groundrecall.broker-review-action-result.v1"
    ok: bool
    action: str
    item_id: str
    broker_id: str
    correlation_id: str
    idempotency_key: str
    origin: str = "broker"
    decision: str = ""
    reason_codes: list[str] = Field(default_factory=list)
    replayed: bool = False
    quarantine_proposal: bool = False
    canonical_write: bool = False


class BrokerReviewActions(Protocol):
    def acknowledge(self, item: RemoteReviewItem, *, actor: str, idempotency_key: str, **kwargs: Any) -> BrokerActionResult: ...
    def assign(self, item: RemoteReviewItem, *, actor: str, assignee: str, idempotency_key: str, **kwargs: Any) -> BrokerActionResult: ...
    def request_import(self, item: RemoteReviewItem, *, actor: str, idempotency_key: str, **kwargs: Any) -> BrokerActionResult: ...


class FixtureBrokerReviewActions:
    """Deterministic fixture broker; action state is process-local only."""

    def __init__(self) -> None:
        self.results: dict[str, BrokerActionResult] = {}

    def _run(self, action: str, item: RemoteReviewItem, *, actor: str, idempotency_key: str,
             policy_config: str | None = None, maximum_release_level: str = "private", assignee: str = "") -> BrokerActionResult:
        correlation = "corr_" + uuid.uuid4().hex[:16]
        if idempotency_key in self.results:
            return self.results[idempotency_key].model_copy(update={"replayed": True})
        if item.signature_status != "valid": return self._result(action, item, idempotency_key, correlation, False, ["invalid_signature"])
        if item.trust_status != "trusted": return self._result(action, item, idempotency_key, correlation, False, ["untrusted_broker"])
        if item.revocation_status == "revoked": return self._result(action, item, idempotency_key, correlation, False, ["revoked_item"])
        if item.quarantine_status != "none": return self._result(action, item, idempotency_key, correlation, False, ["quarantined_item"])
        if item.supersession_status != "current" or item.freshness_status == "stale": return self._result(action, item, idempotency_key, correlation, False, ["stale_or_superseded"])
        if RELEASE_RANK.get(item.release_level, 4) > RELEASE_RANK.get(maximum_release_level, 4): return self._result(action, item, idempotency_key, correlation, False, ["release_cap"])
        if policy_config:
            decision = load_policy_plugins(policy_config).evaluate(PolicyRequest(decision_point="review", subject_id=actor, action=f"broker_review.{action}", record_kind="remote_review", record_id=item.item_id, release_level=item.release_level, target_release_level=maximum_release_level, scope_id=item.scope_id))
            if decision.decision in {"deny", "hard_gate"}: return self._result(action, item, idempotency_key, correlation, False, [f"policy_{decision.decision}", *decision.reasons])
        return self._result(action, item, idempotency_key, correlation, True, ["broker_action_accepted"], quarantine_proposal=action == "request_import")

    def _result(self, action: str, item: RemoteReviewItem, key: str, correlation: str, ok: bool, reasons: list[str], *, quarantine_proposal: bool = False) -> BrokerActionResult:
        result = BrokerActionResult(ok=ok, action=action, item_id=item.item_id, broker_id=item.broker_id, correlation_id=correlation, idempotency_key=key, reason_codes=reasons, quarantine_proposal=quarantine_proposal)
        self.results[key] = result
        return result

    def acknowledge(self, item: RemoteReviewItem, *, actor: str, idempotency_key: str, **kwargs: Any) -> BrokerActionResult:
        return self._run("acknowledge", item, actor=actor, idempotency_key=idempotency_key, **kwargs)

    def assign(self, item: RemoteReviewItem, *, actor: str, assignee: str, idempotency_key: str, **kwargs: Any) -> BrokerActionResult:
        return self._run("assign", item, actor=actor, assignee=assignee, idempotency_key=idempotency_key, **kwargs)

    def request_import(self, item: RemoteReviewItem, *, actor: str, idempotency_key: str, **kwargs: Any) -> BrokerActionResult:
        return self._run("request_import", item, actor=actor, idempotency_key=idempotency_key, **kwargs)
