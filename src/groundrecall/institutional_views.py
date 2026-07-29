from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .catalog import _RELEASE_RANK
from .institutional_custody import orphan_stewardship_report
from .institutional_review import unresolved_federation_disagreements
from .models import ReleaseLevel
from .store import GroundRecallStore


INSTITUTIONAL_VIEW_SCHEMA_VERSION = "groundrecall.institutional_view.v1"


class ScopeOrientationPack(BaseModel):
    schema_version: str = INSTITUTIONAL_VIEW_SCHEMA_VERSION
    scope_id: str
    generated_at: str = ""
    release_cap: ReleaseLevel = "private"
    scope: dict[str, Any] = Field(default_factory=dict)
    vocabulary: list[dict[str, Any]] = Field(default_factory=list)
    reviewed_decisions: list[dict[str, Any]] = Field(default_factory=list)
    current_work: list[dict[str, Any]] = Field(default_factory=list)
    negative_results: list[dict[str, Any]] = Field(default_factory=list)
    unresolved_contradictions: list[dict[str, Any]] = Field(default_factory=list)
    stale_items: list[dict[str, Any]] = Field(default_factory=list)
    steward_roles: list[dict[str, Any]] = Field(default_factory=list)
    incomplete_basis: list[str] = Field(default_factory=list)


class ChangeImpactReport(BaseModel):
    schema_version: str = INSTITUTIONAL_VIEW_SCHEMA_VERSION
    subject_type: str
    subject_id: str
    generated_at: str = ""
    release_cap: ReleaseLevel = "private"
    direct_dependents: list[dict[str, Any]] = Field(default_factory=list)
    contradiction_state: list[dict[str, Any]] = Field(default_factory=list)
    confidence_state: dict[str, Any] = Field(default_factory=dict)
    incomplete_basis: list[str] = Field(default_factory=list)


class GovernanceHealthReport(BaseModel):
    schema_version: str = INSTITUTIONAL_VIEW_SCHEMA_VERSION
    generated_at: str = ""
    release_cap: ReleaseLevel = "private"
    unowned_scope_count: int = 0
    stale_high_impact_count: int = 0
    unresolved_conflict_count: int = 0
    incomplete_provenance_count: int = 0
    unacknowledged_change_count: int = 0
    policy_drift_items: list[dict[str, Any]] = Field(default_factory=list)
    findings: list[dict[str, Any]] = Field(default_factory=list)


class StewardshipView(BaseModel):
    schema_version: str = INSTITUTIONAL_VIEW_SCHEMA_VERSION
    generated_at: str = ""
    release_cap: ReleaseLevel = "private"
    entries: list[dict[str, Any]] = Field(default_factory=list)
    unavailable_evidence: list[str] = Field(default_factory=list)
    anti_surveillance_notice: str = "Explicit stewardship and reviewed provenance are shown; contribution volume is not ranked."


def scope_orientation_pack(
    store_dir: str | Path,
    *,
    scope_id: str,
    release_cap: ReleaseLevel = "private",
    generated_at: str = "",
) -> ScopeOrientationPack:
    store = GroundRecallStore(store_dir)
    scope = store.get_scope(scope_id)
    if scope is None or not _visible(scope, release_cap):
        return ScopeOrientationPack(scope_id=scope_id, generated_at=generated_at, release_cap=release_cap, incomplete_basis=["scope_unavailable_or_not_authorized"])
    claims = [item for item in store.list_claims() if _visible(item, release_cap) and scope_id in _claim_scope_ids(item)]
    concept_ids = sorted({concept_id for claim in claims for concept_id in claim.concept_ids})
    concepts = [item for item in store.list_concepts() if item.concept_id in concept_ids and _visible(item, release_cap)]
    decisions = [item for item in store.list_decisions() if _visible(item, release_cap) and item.scope_id == scope_id and item.current_status in {"reviewed", "promoted"}]
    works = [item for item in store.list_works() if _visible(item, release_cap) and item.scope_id == scope_id and item.work_status not in {"completed", "archived"}]
    negative = [item for item in works if item.outcome in {"failed", "inconclusive", "abandoned"}]
    contradictions = [
        item for item in store.list_contradiction_cases()
        if item.status in {"open", "under_review"} and any(claim_id in {claim.claim_id for claim in claims} for claim_id in item.claim_ids)
    ]
    stewards = [item for item in store.list_stewardship() if _visible(item, release_cap) and (item.scope_id == scope_id or item.subject_id == scope_id) and item.status in {"assigned", "active"}]
    stale = [item for item in claims if _is_stale(item)]
    incomplete = []
    if not stewards:
        incomplete.append("no_active_stewardship_record")
    if not claims:
        incomplete.append("no_visible_claims_for_scope")
    return ScopeOrientationPack(
        scope_id=scope_id,
        generated_at=generated_at,
        release_cap=release_cap,
        scope=_record_ref("scope", scope.scope_id, scope),
        vocabulary=[_record_ref("concept", item.concept_id, item, title=item.title) for item in sorted(concepts, key=lambda value: value.concept_id)],
        reviewed_decisions=[_record_ref("decision", item.decision_id, item, title=item.question) for item in sorted(decisions, key=lambda value: value.decision_id)],
        current_work=[_record_ref("work", item.work_id, item, title=item.title, status=item.work_status) for item in sorted(works, key=lambda value: value.work_id)],
        negative_results=[_record_ref("work", item.work_id, item, title=item.title, outcome=item.outcome) for item in sorted(negative, key=lambda value: value.work_id)],
        unresolved_contradictions=[_record_ref("contradiction_case", item.case_id, item, status=item.status) for item in sorted(contradictions, key=lambda value: value.case_id)],
        stale_items=[_record_ref("claim", item.claim_id, item, title=item.claim_text[:120]) for item in sorted(stale, key=lambda value: value.claim_id)],
        steward_roles=[_steward_ref(item) for item in sorted(stewards, key=lambda value: value.stewardship_id)],
        incomplete_basis=incomplete,
    )


def change_impact_report(
    store_dir: str | Path,
    *,
    subject_type: str,
    subject_id: str,
    release_cap: ReleaseLevel = "private",
    generated_at: str = "",
) -> ChangeImpactReport:
    store = GroundRecallStore(store_dir)
    dependents: list[dict[str, Any]] = []
    for work in store.list_works():
        if _visible(work, release_cap) and subject_id in {*work.related_work_ids, *work.related_claim_ids, *work.related_artifact_ids, work.scope_id}:
            dependents.append(_record_ref("work", work.work_id, work, title=work.title))
    for decision in store.list_decisions():
        if _visible(decision, release_cap) and subject_id in {*decision.supporting_record_ids, *decision.opposing_record_ids, decision.scope_id}:
            dependents.append(_record_ref("decision", decision.decision_id, decision, title=decision.question))
    for claim in store.list_claims():
        if _visible(claim, release_cap) and subject_id in {*claim.source_observation_ids, *claim.supporting_fragment_ids, *claim.concept_ids, *claim.contradicts_claim_ids, *claim.supersedes_claim_ids}:
            dependents.append(_record_ref("claim", claim.claim_id, claim, title=claim.claim_text[:120]))
    contradiction_state = [
        _record_ref("contradiction_case", item.case_id, item, status=item.status)
        for item in store.list_contradiction_cases()
        if subject_id in item.claim_ids and item.status in {"open", "under_review"}
    ]
    subject = _get_subject(store, subject_type, subject_id)
    confidence_state = {}
    incomplete = []
    if subject is None or not _visible(subject, release_cap):
        incomplete.append("subject_unavailable_or_not_authorized")
    else:
        confidence_state = {
            "confidence_hint": getattr(subject, "confidence_hint", None),
            "review_confidence": getattr(subject, "review_confidence", None),
            "assessment_count": len(getattr(subject, "assessments", []) or []),
            "current_status": getattr(subject, "current_status", ""),
        }
    return ChangeImpactReport(
        subject_type=subject_type,
        subject_id=subject_id,
        generated_at=generated_at,
        release_cap=release_cap,
        direct_dependents=sorted(dependents, key=lambda item: (item["record_kind"], item["record_id"])),
        contradiction_state=sorted(contradiction_state, key=lambda item: item["record_id"]),
        confidence_state=confidence_state,
        incomplete_basis=incomplete,
    )


def governance_health_report(
    store_dir: str | Path,
    *,
    release_cap: ReleaseLevel = "private",
    generated_at: str = "",
    subscriptions_dir: str | Path | None = None,
) -> GovernanceHealthReport:
    store = GroundRecallStore(store_dir)
    orphans = [item for item in orphan_stewardship_report(store_dir).items if _RELEASE_RANK[item.release_level] <= _RELEASE_RANK[release_cap]]
    stale_high = [item for item in store.list_claims() if _visible(item, release_cap) and _is_stale(item) and item.current_status in {"reviewed", "promoted"}]
    conflicts = unresolved_federation_disagreements(store_dir)
    incomplete_provenance = [
        item for item in store.list_claims()
        if _visible(item, release_cap) and not (item.source_observation_ids or item.supporting_fragment_ids or item.provenance.source_url or item.provenance.origin_path)
    ]
    unacked = _unacknowledged_subscriptions(subscriptions_dir)
    findings = [
        *[{"code": "unowned_scope_or_record", **item.model_dump(mode="json")} for item in orphans],
        *[{"code": "stale_high_impact_knowledge", "record_kind": "claim", "record_id": item.claim_id} for item in stale_high],
        *[{"code": "incomplete_provenance", "record_kind": "claim", "record_id": item.claim_id} for item in incomplete_provenance],
    ]
    return GovernanceHealthReport(
        generated_at=generated_at,
        release_cap=release_cap,
        unowned_scope_count=len(orphans),
        stale_high_impact_count=len(stale_high),
        unresolved_conflict_count=len(conflicts),
        incomplete_provenance_count=len(incomplete_provenance),
        unacknowledged_change_count=len(unacked),
        policy_drift_items=unacked,
        findings=sorted(findings, key=lambda item: (item.get("code", ""), item.get("record_kind", ""), item.get("record_id", item.get("subject_id", "")))),
    )


def stewardship_view(
    store_dir: str | Path,
    *,
    release_cap: ReleaseLevel = "private",
    generated_at: str = "",
) -> StewardshipView:
    store = GroundRecallStore(store_dir)
    entries = [
        _steward_ref(item)
        for item in store.list_stewardship()
        if _visible(item, release_cap) and item.status in {"assigned", "active"}
    ]
    return StewardshipView(
        generated_at=generated_at,
        release_cap=release_cap,
        entries=sorted(entries, key=lambda item: (item["steward_principal_id"], item["subject_type"], item["subject_id"])),
        unavailable_evidence=["raw_activity_rankings_suppressed", "inferred_familiarity_not_computed"],
    )


def _visible(record: Any, release_cap: ReleaseLevel) -> bool:
    metadata = getattr(record, "metadata", {}) or {}
    release = str(getattr(record, "release_level", "") or metadata.get("release_level") or "private")
    return _RELEASE_RANK.get(release, 4) <= _RELEASE_RANK[release_cap]


def _claim_scope_ids(claim: Any) -> list[str]:
    metadata = getattr(claim, "metadata", {}) or {}
    values = metadata.get("scope_ids") or metadata.get("scope_id") or []
    if isinstance(values, str):
        return [values]
    if isinstance(values, list):
        return [str(value) for value in values]
    return []


def _is_stale(record: Any) -> bool:
    metadata = getattr(record, "metadata", {}) or {}
    return bool(metadata.get("stale") or metadata.get("review_state") == "stale" or metadata.get("stale_pending_review"))


def _record_ref(record_kind: str, record_id: str, record: Any, **extra: Any) -> dict[str, Any]:
    metadata = getattr(record, "metadata", {}) or {}
    payload = {
        "record_kind": record_kind,
        "record_id": record_id,
        "release_level": str(getattr(record, "release_level", "") or metadata.get("release_level") or "private"),
        "current_status": str(getattr(record, "current_status", "") or ""),
    }
    payload.update({key: value for key, value in extra.items() if value not in ("", None, [])})
    return payload


def _steward_ref(record: Any) -> dict[str, Any]:
    return {
        "stewardship_id": record.stewardship_id,
        "subject_type": record.subject_type,
        "subject_id": record.subject_id,
        "scope_id": record.scope_id,
        "steward_principal_id": record.steward_principal_id,
        "steward_role_id": record.steward_role_id,
        "responsibility_type": record.responsibility_type,
        "status": record.status,
        "basis": "explicit_stewardship_record",
    }


def _get_subject(store: GroundRecallStore, subject_type: str, subject_id: str) -> Any | None:
    getters = {
        "source": store.get_source,
        "fragment": store.get_fragment,
        "artifact": store.get_artifact,
        "scope": store.get_scope,
        "work": store.get_work,
        "decision": store.get_decision,
        "contribution": store.get_contribution,
        "claim": store.get_claim,
        "contradiction_case": store.get_contradiction_case,
        "concept": store.get_concept,
        "relation": store.get_relation,
    }
    getter = getters.get(subject_type)
    return getter(subject_id) if getter else None


def _unacknowledged_subscriptions(path: str | Path | None) -> list[dict[str, Any]]:
    if not path or not Path(path).exists():
        return []
    rows = []
    for item in sorted(Path(path).glob("*.json")):
        try:
            payload = json.loads(item.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            rows.append({"path": str(item), "code": "malformed_subscription"})
            continue
        if payload.get("active", True) and not payload.get("cursor"):
            rows.append({"path": str(item), "subscription_id": payload.get("subscription_id", ""), "code": "subscription_without_acknowledged_cursor"})
    return rows


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate institutional orientation, impact, governance, and stewardship views.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    orientation = subparsers.add_parser("orientation")
    orientation.add_argument("store_dir")
    orientation.add_argument("--scope-id", required=True)
    orientation.add_argument("--release-cap", choices=tuple(_RELEASE_RANK), default="private")
    orientation.add_argument("--generated-at", default="")
    impact = subparsers.add_parser("impact")
    impact.add_argument("store_dir")
    impact.add_argument("--subject-type", required=True)
    impact.add_argument("--subject-id", required=True)
    impact.add_argument("--release-cap", choices=tuple(_RELEASE_RANK), default="private")
    impact.add_argument("--generated-at", default="")
    governance = subparsers.add_parser("governance")
    governance.add_argument("store_dir")
    governance.add_argument("--release-cap", choices=tuple(_RELEASE_RANK), default="private")
    governance.add_argument("--generated-at", default="")
    governance.add_argument("--subscriptions-dir", default="")
    stewardship = subparsers.add_parser("stewardship")
    stewardship.add_argument("store_dir")
    stewardship.add_argument("--release-cap", choices=tuple(_RELEASE_RANK), default="private")
    stewardship.add_argument("--generated-at", default="")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "orientation":
        payload = scope_orientation_pack(args.store_dir, scope_id=args.scope_id, release_cap=args.release_cap, generated_at=args.generated_at)
    elif args.command == "impact":
        payload = change_impact_report(args.store_dir, subject_type=args.subject_type, subject_id=args.subject_id, release_cap=args.release_cap, generated_at=args.generated_at)
    elif args.command == "governance":
        payload = governance_health_report(args.store_dir, release_cap=args.release_cap, generated_at=args.generated_at, subscriptions_dir=args.subscriptions_dir or None)
    else:
        payload = stewardship_view(args.store_dir, release_cap=args.release_cap, generated_at=args.generated_at)
    print(payload.model_dump_json(indent=2))
