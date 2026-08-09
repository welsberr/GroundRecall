"""Safe local application of explicitly trusted principal-realm changes.

This is deliberately narrower than team federation: it is an auto-accept path
only for a subscription whose realm is a principal and whose subscription
explicitly opts in. Project and team bundles stop at quarantine.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .change_feed import (
    FederationChangeBundle,
    FederationSubscription,
    acknowledge_change_bundle,
    import_incremental_change_bundle_to_quarantine,
    verify_incremental_change_bundle,
)
from .federation import _canonical_json
from .models import (
    AdjudicationRecord,
    ArtifactRecord,
    ClaimRecord,
    ConceptRecord,
    ContributionRecord,
    ContributionReviewReceipt,
    ContradictionCaseRecord,
    CustodyEventRecord,
    DecisionRecord,
    FederationFeedbackRecord,
    FragmentRecord,
    ObservationRecord,
    PromotionRecord,
    RelationRecord,
    ReviewCandidateRecord,
    ReviewReceiptRecord,
    ScopeRecord,
    SourceRecord,
    StewardshipRecord,
    WorkRecord,
)
from .store import GroundRecallStore


class PersonalSyncResult(BaseModel):
    decision: str
    bundle_id: str
    quarantine_path: str = ""
    applied_event_ids: list[str] = Field(default_factory=list)
    unchanged_event_ids: list[str] = Field(default_factory=list)
    conflict_event_ids: list[str] = Field(default_factory=list)
    rejected_event_ids: list[str] = Field(default_factory=list)
    cursor_advanced: bool = False
    reasons: list[str] = Field(default_factory=list)


_BINDINGS: dict[str, tuple[str, Any, str, str]] = {
    "source": ("source_id", SourceRecord, "get_source", "save_source"),
    "fragment": ("fragment_id", FragmentRecord, "get_fragment", "save_fragment"),
    "artifact": ("artifact_id", ArtifactRecord, "get_artifact", "save_artifact"),
    "scope": ("scope_id", ScopeRecord, "get_scope", "save_scope"),
    "work": ("work_id", WorkRecord, "get_work", "save_work"),
    "decision": ("decision_id", DecisionRecord, "get_decision", "save_decision"),
    "contribution": ("contribution_id", ContributionRecord, "get_contribution", "save_contribution"),
    "contribution_review_receipt": ("receipt_id", ContributionReviewReceipt, "get_contribution_review_receipt", "save_contribution_review_receipt"),
    "review_receipt": ("receipt_id", ReviewReceiptRecord, "get_review_receipt", "save_review_receipt"),
    "federation_feedback": ("feedback_id", FederationFeedbackRecord, "get_federation_feedback", "save_federation_feedback"),
    "stewardship": ("stewardship_id", StewardshipRecord, "get_stewardship", "save_stewardship"),
    "custody_event": ("event_id", CustodyEventRecord, "get_custody_event", "save_custody_event"),
    "observation": ("observation_id", ObservationRecord, "get_observation", "save_observation"),
    "claim": ("claim_id", ClaimRecord, "get_claim", "save_claim"),
    "contradiction_case": ("case_id", ContradictionCaseRecord, "get_contradiction_case", "save_contradiction_case"),
    "concept": ("concept_id", ConceptRecord, "get_concept", "save_concept"),
    "relation": ("relation_id", RelationRecord, "get_relation", "save_relation"),
    "review_candidate": ("candidate_id", ReviewCandidateRecord, "get_review_candidate", "save_review_candidate"),
    "promotion": ("promotion_id", PromotionRecord, "get_promotion", "save_promotion"),
    "adjudication": ("adjudication_id", AdjudicationRecord, "get_adjudication", "save_adjudication"),
}


def _state_path(store_dir: str | Path) -> Path:
    return Path(store_dir) / ".federation" / "personal-sync-state.json"


def _load_applied(store_dir: str | Path) -> set[str]:
    path = _state_path(store_dir)
    if not path.exists():
        return set()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return {str(item) for item in payload.get("applied_event_ids", [])}
    except (OSError, json.JSONDecodeError, AttributeError):
        return set()


def _save_applied(store_dir: str | Path, event_ids: set[str]) -> None:
    path = _state_path(store_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema_version": "groundrecall.personal-sync-state.v1", "applied_event_ids": sorted(event_ids)}, indent=2) + "\n", encoding="utf-8")


def apply_personal_change_bundle(
    bundle_path: str | Path,
    store_dir: str | Path,
    *,
    verification_key: str | bytes,
    subscription: FederationSubscription,
    key_id: str | None = None,
    conflict_dir: str | Path | None = None,
) -> PersonalSyncResult:
    """Apply a verified principal-realm bundle without overwriting conflicts."""
    bundle = FederationChangeBundle.model_validate_json(Path(bundle_path).read_text(encoding="utf-8"))
    verify_incremental_change_bundle(bundle, verification_key=verification_key, key_id=key_id)
    if subscription.audience != "principal" or not subscription.realm_id or not subscription.auto_accept:
        return PersonalSyncResult(
            decision="quarantined",
            bundle_id=bundle.manifest.bundle_id,
            reasons=["personal_auto_accept_requires_principal_realm_opt_in"],
        )
    store = GroundRecallStore(store_dir)
    applied = _load_applied(store_dir)
    applied_ids: list[str] = []
    unchanged_ids: list[str] = []
    conflict_ids: list[str] = []
    rejected_ids: list[str] = []
    reasons: list[str] = []
    conflict_target = Path(conflict_dir) if conflict_dir else Path(store_dir) / ".federation" / "conflicts"
    for event in bundle.events:
        if event.event_id in applied:
            unchanged_ids.append(event.event_id)
            continue
        binding = _BINDINGS.get(event.record_kind)
        if binding is None:
            rejected_ids.append(event.event_id)
            reasons.append(f"unsupported_record_kind:{event.record_kind}")
            continue
        id_field, model_type, getter_name, saver_name = binding
        if hashlib_payload(event.payload) != event.content_hash:
            rejected_ids.append(event.event_id)
            reasons.append(f"payload_hash_mismatch:{event.event_id}")
            continue
        incoming = model_type.model_validate(event.payload)
        record_id = str(getattr(incoming, id_field))
        existing = getattr(store, getter_name)(record_id)
        if existing is None:
            getattr(store, saver_name)(incoming)
            applied.add(event.event_id)
            applied_ids.append(event.event_id)
        elif hashlib_payload(existing.model_dump(mode="json")) == event.content_hash:
            applied.add(event.event_id)
            unchanged_ids.append(event.event_id)
        else:
            conflict_target.mkdir(parents=True, exist_ok=True)
            (conflict_target / f"{event.event_id}.json").write_text(json.dumps({"event": event.model_dump(mode="json"), "existing": existing.model_dump(mode="json")}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            conflict_ids.append(event.event_id)
            reasons.append(f"existing_record_conflict:{event.record_kind}:{record_id}")
    if not conflict_ids and not rejected_ids:
        _save_applied(store_dir, applied)
        return PersonalSyncResult(decision="applied", bundle_id=bundle.manifest.bundle_id, applied_event_ids=applied_ids, unchanged_event_ids=unchanged_ids, cursor_advanced=True)
    if applied_ids or unchanged_ids:
        _save_applied(store_dir, applied)
    return PersonalSyncResult(decision="partial", bundle_id=bundle.manifest.bundle_id, applied_event_ids=applied_ids, unchanged_event_ids=unchanged_ids, conflict_event_ids=conflict_ids, rejected_event_ids=rejected_ids, reasons=reasons)


def hashlib_payload(payload: dict[str, Any]) -> str:
    import hashlib
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def sync_personal_change_bundle(
    bundle_path: str | Path,
    store_dir: str | Path,
    quarantine_dir: str | Path,
    *,
    verification_key: str | bytes,
    subscription: FederationSubscription,
    key_id: str | None = None,
    subscription_path: str | Path | None = None,
) -> PersonalSyncResult:
    """Verify, quarantine, and apply an opted-in personal bundle."""
    import_result = import_incremental_change_bundle_to_quarantine(
        bundle_path,
        quarantine_dir,
        verification_key=verification_key,
        subscription=subscription,
        key_id=key_id,
    )
    if import_result.decision != "quarantined":
        return PersonalSyncResult(decision="rejected", bundle_id=import_result.bundle_id, reasons=import_result.reasons)
    result = apply_personal_change_bundle(
        bundle_path,
        store_dir,
        verification_key=verification_key,
        subscription=subscription,
        key_id=key_id,
    )
    if result.cursor_advanced and subscription_path is not None:
        acknowledge_change_bundle(subscription_path, bundle_path, verification_key=verification_key, key_id=key_id)
        result = result.model_copy(update={"cursor_advanced": True})
    return result.model_copy(update={"quarantine_path": import_result.quarantine_path})
