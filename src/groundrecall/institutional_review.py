from __future__ import annotations

import argparse
import hashlib
import hmac
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from .federation import FederationPolicyError
from .models import FederationFeedbackRecord, ReviewReceiptRecord
from .store import GroundRecallStore


FEDERATION_FEEDBACK_BUNDLE_SCHEMA_VERSION = "groundrecall.federation_feedback_bundle.v1"


class QuorumRule(BaseModel):
    subject_type: str = ""
    minimum_approvals: int = 1
    required_role_ids: list[str] = Field(default_factory=list)
    independent_from_principal_ids: list[str] = Field(default_factory=list)
    allow_duplicate_principals: bool = False


class QuorumEvaluation(BaseModel):
    subject_type: str
    subject_id: str
    satisfied: bool
    approval_count: int
    reviewer_principal_ids: list[str] = Field(default_factory=list)
    required_role_ids: list[str] = Field(default_factory=list)
    missing_role_ids: list[str] = Field(default_factory=list)
    duplicate_principal_ids: list[str] = Field(default_factory=list)
    non_independent_principal_ids: list[str] = Field(default_factory=list)
    dissent_receipt_ids: list[str] = Field(default_factory=list)
    invalidated_receipt_ids: list[str] = Field(default_factory=list)


class FederationFeedbackBundle(BaseModel):
    schema_version: str = FEDERATION_FEEDBACK_BUNDLE_SCHEMA_VERSION
    bundle_id: str
    origin_instance_id: str
    target_instance_id: str = ""
    created_at: str = ""
    key_id: str = ""
    signature_algorithm: Literal["hmac-sha256"] = "hmac-sha256"
    content_hash: str
    signature: str = ""
    feedback: list[FederationFeedbackRecord] = Field(default_factory=list)


def content_hash(payload: Any) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def record_review_receipt(
    store_dir: str | Path,
    receipt: ReviewReceiptRecord,
    *,
    expected_content_hash: str = "",
) -> ReviewReceiptRecord:
    if expected_content_hash and receipt.reviewed_content_hash != expected_content_hash:
        raise FederationPolicyError("review receipt content hash does not match reviewed content")
    return GroundRecallStore(store_dir).save_review_receipt(receipt)


def evaluate_review_quorum(
    receipts: list[ReviewReceiptRecord],
    *,
    subject_type: str,
    subject_id: str,
    rule: QuorumRule | None = None,
    current_content_hash: str = "",
) -> QuorumEvaluation:
    active_rule = rule or QuorumRule(subject_type=subject_type)
    relevant = [
        item
        for item in receipts
        if item.subject_type == subject_type and item.subject_id == subject_id and item.current_status == "reviewed"
    ]
    invalidated = [
        item.receipt_id
        for item in relevant
        if current_content_hash and item.reviewed_content_hash and item.reviewed_content_hash != current_content_hash
    ]
    relevant = [item for item in relevant if item.receipt_id not in set(invalidated)]
    approvals = [item for item in relevant if item.decision == "approve"]
    dissent_receipt_ids = [item.receipt_id for item in relevant if item.decision in {"dissent", "appeal", "reject", "needs_changes"}]
    reviewer_principal_ids = [item.reviewer_principal_id for item in approvals]
    duplicate_principal_ids = _duplicates(reviewer_principal_ids)
    role_ids = {item.reviewer_role_id for item in approvals if item.reviewer_role_id}
    missing_role_ids = sorted(set(active_rule.required_role_ids) - role_ids)
    non_independent = sorted(set(reviewer_principal_ids) & set(active_rule.independent_from_principal_ids))
    distinct_approval_count = len(set(reviewer_principal_ids)) if not active_rule.allow_duplicate_principals else len(approvals)
    satisfied = (
        distinct_approval_count >= active_rule.minimum_approvals
        and not missing_role_ids
        and (active_rule.allow_duplicate_principals or not duplicate_principal_ids)
        and not non_independent
    )
    return QuorumEvaluation(
        subject_type=subject_type,
        subject_id=subject_id,
        satisfied=satisfied,
        approval_count=distinct_approval_count,
        reviewer_principal_ids=sorted(set(reviewer_principal_ids)),
        required_role_ids=list(active_rule.required_role_ids),
        missing_role_ids=missing_role_ids,
        duplicate_principal_ids=duplicate_principal_ids,
        non_independent_principal_ids=non_independent,
        dissent_receipt_ids=sorted(dissent_receipt_ids),
        invalidated_receipt_ids=sorted(invalidated),
    )


def unresolved_federation_disagreements(store_dir: str | Path) -> list[dict[str, Any]]:
    store = GroundRecallStore(store_dir)
    receipts_by_subject: dict[tuple[str, str], list[ReviewReceiptRecord]] = {}
    for receipt in store.list_review_receipts():
        receipts_by_subject.setdefault((receipt.subject_type, receipt.subject_id), []).append(receipt)
    rows: list[dict[str, Any]] = []
    for subject, receipts in sorted(receipts_by_subject.items()):
        decisions = sorted({receipt.decision for receipt in receipts})
        if len(decisions) <= 1:
            continue
        rows.append(
            {
                "subject_type": subject[0],
                "subject_id": subject[1],
                "decisions": decisions,
                "receipt_ids": sorted(receipt.receipt_id for receipt in receipts),
                "status": "unresolved",
            }
        )
    return rows


def record_federation_feedback(store_dir: str | Path, feedback: FederationFeedbackRecord) -> FederationFeedbackRecord:
    if not feedback.content_hash:
        feedback = feedback.model_copy(update={"content_hash": content_hash(feedback.model_dump(mode="json", exclude={"content_hash"}))})
    return GroundRecallStore(store_dir).save_federation_feedback(feedback)


def build_feedback_bundle(
    store_dir: str | Path,
    *,
    origin_instance_id: str,
    signing_key: str | bytes,
    key_id: str,
    bundle_id: str = "",
    target_instance_id: str = "",
    created_at: str = "",
    out_path: str | Path | None = None,
) -> FederationFeedbackBundle:
    feedback = [
        item
        for item in GroundRecallStore(store_dir).list_federation_feedback()
        if item.origin_instance_id == origin_instance_id and (not target_instance_id or item.target_instance_id == target_instance_id)
    ]
    body_hash = content_hash([item.model_dump(mode="json") for item in feedback])
    bundle = FederationFeedbackBundle(
        bundle_id=bundle_id or f"feedback::{origin_instance_id}::{body_hash[:16]}",
        origin_instance_id=origin_instance_id,
        target_instance_id=target_instance_id,
        created_at=created_at,
        key_id=key_id,
        content_hash=body_hash,
        feedback=feedback,
    )
    signature = _sign(bundle.model_dump(mode="json", exclude={"signature"}), signing_key)
    bundle = bundle.model_copy(update={"signature": signature})
    if out_path is not None:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_text(bundle.model_dump_json(indent=2), encoding="utf-8")
    return bundle


def verify_feedback_bundle(bundle: FederationFeedbackBundle | dict[str, Any], *, verification_key: str | bytes, key_id: str | None = None) -> FederationFeedbackBundle:
    parsed = bundle if isinstance(bundle, FederationFeedbackBundle) else FederationFeedbackBundle.model_validate(bundle)
    if key_id is not None and parsed.key_id != key_id:
        raise FederationPolicyError("feedback bundle key ID does not match")
    expected_hash = content_hash([item.model_dump(mode="json") for item in parsed.feedback])
    if parsed.content_hash != expected_hash:
        raise FederationPolicyError("feedback bundle content hash does not match")
    expected_signature = _sign(parsed.model_dump(mode="json", exclude={"signature"}), verification_key)
    if not hmac.compare_digest(parsed.signature, expected_signature):
        raise FederationPolicyError("feedback bundle signature does not match")
    return parsed


def _duplicates(values: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return sorted(duplicates)


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sign(payload: Any, key: str | bytes) -> str:
    key_bytes = key.encode("utf-8") if isinstance(key, str) else key
    return hmac.new(key_bytes, _canonical_json(payload).encode("utf-8"), hashlib.sha256).hexdigest()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage institutional review receipts and federation feedback.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    quorum = subparsers.add_parser("quorum")
    quorum.add_argument("store_dir")
    quorum.add_argument("--subject-type", required=True)
    quorum.add_argument("--subject-id", required=True)
    quorum.add_argument("--minimum-approvals", type=int, default=1)
    quorum.add_argument("--required-role-id", action="append", default=[])
    quorum.add_argument("--independent-from", action="append", default=[])
    quorum.add_argument("--content-hash", default="")
    disagreements = subparsers.add_parser("disagreements")
    disagreements.add_argument("store_dir")
    bundle = subparsers.add_parser("feedback-bundle")
    bundle.add_argument("store_dir")
    bundle.add_argument("out_path")
    bundle.add_argument("--origin-instance-id", required=True)
    bundle.add_argument("--target-instance-id", default="")
    bundle.add_argument("--key-id", required=True)
    bundle.add_argument("--signing-key-file", required=True)
    bundle.add_argument("--created-at", default="")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "quorum":
        rule = QuorumRule(
            subject_type=args.subject_type,
            minimum_approvals=args.minimum_approvals,
            required_role_ids=args.required_role_id,
            independent_from_principal_ids=args.independent_from,
        )
        result = evaluate_review_quorum(
            GroundRecallStore(args.store_dir).list_review_receipts(),
            subject_type=args.subject_type,
            subject_id=args.subject_id,
            rule=rule,
            current_content_hash=args.content_hash,
        )
        print(result.model_dump_json(indent=2))
        return
    if args.command == "disagreements":
        print(json.dumps(unresolved_federation_disagreements(args.store_dir), indent=2))
        return
    signing_key = Path(args.signing_key_file).read_text(encoding="utf-8").strip()
    built = build_feedback_bundle(
        args.store_dir,
        origin_instance_id=args.origin_instance_id,
        target_instance_id=args.target_instance_id,
        signing_key=signing_key,
        key_id=args.key_id,
        created_at=args.created_at,
        out_path=args.out_path,
    )
    print(built.model_dump_json(indent=2))
