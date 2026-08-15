"""Bounded ClaimWright decision-challenge receipts.

GroundRecall stores only a concise, release-scoped review receipt. Evidence
remains in the producer's scoped artifact store and is never copied into the
policy decision by this adapter.
"""

from __future__ import annotations

import hashlib
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError


DecisionChallengeOutcome = Literal["proceed", "revise", "defer", "escalate"]
DecisionChallengeLevel = Literal["none", "quick", "standard", "escalated"]
DecisionChallengeStopReason = Literal[
    "not_triggered",
    "no_plausible_decision_changing_failure_mode",
    "highest_value_check_completed",
    "one_pass_complete",
    "budget_exhausted",
    "evidence_unavailable",
    "human_authority_required",
    "decision_revised",
    "decision_deferred",
]


class DecisionChallengeReceipt(BaseModel):
    """Public-safe summary attached to a GroundRecall policy decision."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["groundrecall.decision_challenge_receipt.v1"] = (
        "groundrecall.decision_challenge_receipt.v1"
    )
    receipt_id: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)
    challenge_id: str = Field(min_length=1)
    decision_id: str = Field(min_length=1)
    decision_version: int = Field(ge=1)
    policy_version: str = Field(min_length=1)
    review_level: DecisionChallengeLevel
    outcome: DecisionChallengeOutcome
    stop_reason: DecisionChallengeStopReason
    review_state: Literal["draft", "reviewed", "escalated", "closed"]
    failure_mode_count: int = Field(ge=0, le=3)
    failure_mode_ids: list[str] = Field(default_factory=list, max_length=3)
    release_level: str = Field(default="private", min_length=1)
    authority: str = Field(min_length=1, max_length=1000)


def build_decision_challenge_receipt(
    payload: dict[str, Any],
    *,
    policy_version: str,
    release_level: str = "private",
) -> DecisionChallengeReceipt:
    """Validate and reduce a ClaimWright challenge to an idempotent receipt."""

    if payload.get("schema_version") != "claimwright.decision_challenge.v1":
        raise ValueError("unsupported decision challenge schema_version")
    failure_modes = payload.get("failure_modes", [])
    if not isinstance(failure_modes, list) or len(failure_modes) > 3:
        raise ValueError("decision challenge failure_modes must contain at most three entries")
    failure_mode_ids: list[str] = []
    for item in failure_modes:
        if not isinstance(item, dict) or not item.get("failure_mode_id"):
            raise ValueError("decision challenge failure modes require stable IDs")
        failure_mode_ids.append(str(item["failure_mode_id"]))
    if len(set(failure_mode_ids)) != len(failure_mode_ids):
        raise ValueError("decision challenge failure mode IDs must be unique")

    decision_id = str(payload.get("decision_id", ""))
    decision_version = payload.get("decision_version")
    if not decision_id or not isinstance(decision_version, int) or decision_version < 1:
        raise ValueError("decision challenge requires a decision ID and positive version")
    if payload.get("parent_challenge_id") not in (None, ""):
        raise ValueError("nested decision challenges are not supported")
    if not policy_version:
        raise ValueError("policy_version is required for a durable decision challenge receipt")

    idempotency_key = f"{decision_id}:{decision_version}:{policy_version}"
    receipt_id = "decision-challenge-" + hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()[:20]
    try:
        return DecisionChallengeReceipt(
            receipt_id=receipt_id,
            idempotency_key=idempotency_key,
            challenge_id=str(payload["challenge_id"]),
            decision_id=decision_id,
            decision_version=decision_version,
            policy_version=policy_version,
            review_level=payload["review_level"],
            outcome=payload["outcome"],
            stop_reason=payload["stop_reason"],
            review_state=payload["review_state"],
            failure_mode_count=len(failure_modes),
            failure_mode_ids=failure_mode_ids,
            release_level=release_level,
            authority=str(payload["authority"]),
        )
    except (KeyError, TypeError, ValidationError) as exc:
        raise ValueError(f"invalid decision challenge receipt: {exc}") from exc
