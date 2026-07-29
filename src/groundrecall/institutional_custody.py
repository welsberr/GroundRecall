from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .catalog import _RELEASE_RANK
from .federation import FederationPolicyError, FederationTrustRegistry
from .models import CustodyEventRecord, ReleaseLevel, StewardshipRecord
from .policy import PolicyDecision, PolicyDecisionProvider, PolicyRequest
from .store import GroundRecallStore


CUSTODY_PLAN_SCHEMA_VERSION = "groundrecall.institutional_custody_plan.v1"


class OrphanStewardshipItem(BaseModel):
    subject_type: str
    subject_id: str
    scope_id: str = ""
    release_level: ReleaseLevel = "private"
    current_status: str = ""
    reason: str


class OrphanStewardshipReport(BaseModel):
    schema_version: str = CUSTODY_PLAN_SCHEMA_VERSION
    store_dir: str
    orphan_count: int
    items: list[OrphanStewardshipItem] = Field(default_factory=list)


class TenancyDeparturePlan(BaseModel):
    schema_version: str = CUSTODY_PLAN_SCHEMA_VERSION
    plan_id: str
    store_dir: str
    departing_principal_id: str
    dry_run: bool = True
    planned_at: str = ""
    active_stewardship_ids: list[str] = Field(default_factory=list)
    custody_event_ids: list[str] = Field(default_factory=list)
    handoff_required: list[dict[str, Any]] = Field(default_factory=list)
    private_personal_records: list[dict[str, Any]] = Field(default_factory=list)
    group_owned_records_retained: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class InstanceRetirementPlan(BaseModel):
    schema_version: str = CUSTODY_PLAN_SCHEMA_VERSION
    plan_id: str
    store_dir: str
    instance_id: str
    dry_run: bool = True
    planned_at: str = ""
    replacement_instance_id: str = ""
    trust_key_count: int = 0
    active_trust_key_count: int = 0
    subscription_count: int = 0
    catalog_count: int = 0
    pending_contribution_count: int = 0
    active_stewardship_count: int = 0
    canonical_record_counts: dict[str, int] = Field(default_factory=dict)
    quarantine_item_count: int = 0
    backup_item_count: int = 0
    required_actions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class CustodyPolicyError(FederationPolicyError):
    """Raised when policy blocks a custody event write."""

    def __init__(self, message: str, *, decision: PolicyDecision):
        super().__init__(message)
        self.decision = decision


def record_custody_event(
    store_dir: str | Path,
    event: CustodyEventRecord,
    *,
    authority: str = "",
    policy_provider: PolicyDecisionProvider | None = None,
) -> CustodyEventRecord:
    store = GroundRecallStore(store_dir)
    subject = _subject_record(store, event.subject_type, event.subject_id)
    if subject is not None:
        subject_release = _record_release(subject)
        if _RELEASE_RANK.get(event.release_level, 4) < _RELEASE_RANK.get(subject_release, 4):
            raise FederationPolicyError("custody event cannot broaden subject release level")
    if authority and not event.authority_id:
        event = event.model_copy(update={"authority_id": authority})
    if policy_provider is not None:
        decision = policy_provider.evaluate(
            PolicyRequest(
                decision_point="act",
                subject_id=event.subject_id,
                action="transfer_knowledge_custody",
                record_kind="custody_event",
                record_id=event.event_id,
                release_level=event.release_level,
                scope_id=event.scope_id,
                durable_memory_change=True,
                metadata={
                    "groundrecall.custody_event_kind": event.event_kind,
                    "groundrecall.custody_subject_type": event.subject_type,
                    "groundrecall.previous_custodian_id": event.previous_custodian_id,
                    "groundrecall.new_custodian_id": event.new_custodian_id,
                    "groundrecall.authority_id": event.authority_id,
                },
            )
        )
        if decision.decision in {"deny", "hard_gate"}:
            raise CustodyPolicyError("policy blocked custody event write", decision=decision)
    return store.save_custody_event(event)


def orphan_stewardship_report(store_dir: str | Path) -> OrphanStewardshipReport:
    store = GroundRecallStore(store_dir)
    active_subjects = {
        (item.subject_type, item.subject_id)
        for item in store.list_stewardship()
        if item.status in {"assigned", "active"} and item.steward_principal_id
    }
    explicit_orphans = {
        (item.subject_type, item.subject_id)
        for item in store.list_stewardship()
        if item.status == "orphaned"
    }
    items: list[OrphanStewardshipItem] = []
    for subject_type, subject_id, record in _stewardable_records(store):
        key = (subject_type, subject_id)
        if key in active_subjects:
            continue
        reason = "explicitly_orphaned" if key in explicit_orphans else "missing_active_steward"
        items.append(
            OrphanStewardshipItem(
                subject_type=subject_type,
                subject_id=subject_id,
                scope_id=str(getattr(record, "scope_id", "") or getattr(record, "destination_scope_id", "") or ""),
                release_level=_record_release(record),
                current_status=str(getattr(record, "current_status", "") or ""),
                reason=reason,
            )
        )
    items = sorted(items, key=lambda item: (item.subject_type, item.subject_id))
    return OrphanStewardshipReport(schema_version=CUSTODY_PLAN_SCHEMA_VERSION, store_dir=str(Path(store_dir)), orphan_count=len(items), items=items)


def plan_tenancy_departure(
    store_dir: str | Path,
    *,
    departing_principal_id: str,
    planned_at: str = "",
) -> TenancyDeparturePlan:
    store = GroundRecallStore(store_dir)
    active_stewardships = [
        item
        for item in store.list_stewardship()
        if item.steward_principal_id == departing_principal_id and item.status in {"assigned", "active"}
    ]
    custody_events = [
        item
        for item in store.list_custody_events()
        if departing_principal_id in {item.previous_custodian_id, item.new_custodian_id}
    ]
    handoff_required = [
        {
            "stewardship_id": item.stewardship_id,
            "subject_type": item.subject_type,
            "subject_id": item.subject_id,
            "scope_id": item.scope_id,
            "release_level": item.release_level,
            "required_action": "assign_successor_or_mark_orphan",
        }
        for item in sorted(active_stewardships, key=lambda value: value.stewardship_id)
    ]
    private_personal = []
    group_retained = []
    for subject_type, subject_id, record in _stewardable_records(store):
        release = _record_release(record)
        owners = set(getattr(record, "owner_principal_ids", []) or [])
        contributor = str(getattr(record, "contributor_id", "") or "")
        if release == "private" and (departing_principal_id in owners or contributor == departing_principal_id):
            private_personal.append(_record_ref(subject_type, subject_id, record, "review_before_group_retention"))
        elif getattr(record, "current_status", "") in {"reviewed", "promoted"} and release != "private":
            group_retained.append(_record_ref(subject_type, subject_id, record, "retain_group_owned_reviewed_knowledge"))
    warnings = []
    if active_stewardships:
        warnings.append("active_stewardship_requires_handoff")
    if private_personal:
        warnings.append("private_personal_records_require_separate_retention_authority")
    basis = {
        "store_dir": str(Path(store_dir)),
        "departing_principal_id": departing_principal_id,
        "planned_at": planned_at,
        "active_stewardship_ids": sorted(item.stewardship_id for item in active_stewardships),
        "private_personal": sorted((item["record_kind"], item["record_id"]) for item in private_personal),
    }
    return TenancyDeparturePlan(
        plan_id="tenancy_departure_plan::" + _hash_payload(basis)[:16],
        store_dir=str(Path(store_dir)),
        departing_principal_id=departing_principal_id,
        planned_at=planned_at,
        active_stewardship_ids=sorted(item.stewardship_id for item in active_stewardships),
        custody_event_ids=sorted(item.event_id for item in custody_events),
        handoff_required=handoff_required,
        private_personal_records=sorted(private_personal, key=lambda item: (item["record_kind"], item["record_id"])),
        group_owned_records_retained=sorted(group_retained, key=lambda item: (item["record_kind"], item["record_id"])),
        warnings=warnings,
    )


def plan_instance_retirement(
    store_dir: str | Path,
    *,
    instance_id: str,
    planned_at: str = "",
    replacement_instance_id: str = "",
    registry_path: str | Path | None = None,
    subscriptions_dir: str | Path | None = None,
    catalogs_dir: str | Path | None = None,
    quarantine_dir: str | Path | None = None,
    backups_dir: str | Path | None = None,
) -> InstanceRetirementPlan:
    store = GroundRecallStore(store_dir)
    trust_keys = _trust_keys_for_instance(registry_path, instance_id)
    canonical_counts = _canonical_counts(store)
    pending = [item for item in store.list_contributions() if item.origin_instance_id == instance_id and item.state in {"proposed", "triaged", "under_review", "deferred"}]
    active_stewardships = [item for item in store.list_stewardship() if item.steward_principal_id == instance_id and item.status in {"assigned", "active"}]
    subscription_count = _count_json_files(subscriptions_dir)
    catalog_count = _count_json_files(catalogs_dir)
    quarantine_count = _count_json_files(quarantine_dir)
    backup_count = _count_path_items(backups_dir)
    required_actions = [
        "revoke_or_supersede_trust_keys",
        "disable_or_transfer_subscriptions",
        "archive_catalogs_and_feedback",
        "resolve_pending_contributions",
        "handoff_active_stewardship",
        "preserve_quarantine_and_audit_history",
        "verify_backup_before_shutdown",
    ]
    warnings = []
    if not replacement_instance_id:
        warnings.append("replacement_instance_not_recorded")
    if any(key.active and not key.revoked_at for key in trust_keys):
        warnings.append("active_trust_keys_require_revocation")
    if pending:
        warnings.append("pending_contributions_require_resolution")
    if active_stewardships:
        warnings.append("active_stewardship_requires_handoff")
    basis = {
        "store_dir": str(Path(store_dir)),
        "instance_id": instance_id,
        "planned_at": planned_at,
        "replacement_instance_id": replacement_instance_id,
        "canonical_counts": canonical_counts,
        "trust_keys": sorted(key.key_id for key in trust_keys),
    }
    return InstanceRetirementPlan(
        plan_id="instance_retirement_plan::" + _hash_payload(basis)[:16],
        store_dir=str(Path(store_dir)),
        instance_id=instance_id,
        planned_at=planned_at,
        replacement_instance_id=replacement_instance_id,
        trust_key_count=len(trust_keys),
        active_trust_key_count=sum(1 for key in trust_keys if key.active and not key.revoked_at),
        subscription_count=subscription_count,
        catalog_count=catalog_count,
        pending_contribution_count=len(pending),
        active_stewardship_count=len(active_stewardships),
        canonical_record_counts=canonical_counts,
        quarantine_item_count=quarantine_count,
        backup_item_count=backup_count,
        required_actions=required_actions,
        warnings=warnings,
    )


def _subject_record(store: GroundRecallStore, subject_type: str, subject_id: str) -> Any | None:
    getters = {
        "scope": store.get_scope,
        "work": store.get_work,
        "decision": store.get_decision,
        "contribution": store.get_contribution,
        "claim": store.get_claim,
        "contradiction_case": store.get_contradiction_case,
        "relation": store.get_relation,
    }
    getter = getters.get(subject_type)
    return getter(subject_id) if getter else None


def _stewardable_records(store: GroundRecallStore) -> list[tuple[str, str, Any]]:
    return [
        *[("scope", item.scope_id, item) for item in store.list_scopes()],
        *[("work", item.work_id, item) for item in store.list_works()],
        *[("decision", item.decision_id, item) for item in store.list_decisions()],
        *[("contribution", item.contribution_id, item) for item in store.list_contributions()],
    ]


def _record_release(record: Any) -> ReleaseLevel:
    release = str(getattr(record, "release_level", "") or getattr(record, "proposed_release_level", "") or "private")
    return release if release in _RELEASE_RANK else "private"


def _record_ref(record_kind: str, record_id: str, record: Any, disposition: str) -> dict[str, Any]:
    return {
        "record_kind": record_kind,
        "record_id": record_id,
        "scope_id": str(getattr(record, "scope_id", "") or getattr(record, "destination_scope_id", "") or ""),
        "release_level": _record_release(record),
        "current_status": str(getattr(record, "current_status", "") or ""),
        "disposition": disposition,
    }


def _trust_keys_for_instance(registry_path: str | Path | None, instance_id: str) -> list[Any]:
    if not registry_path or not Path(registry_path).exists():
        return []
    registry = FederationTrustRegistry.model_validate_json(Path(registry_path).read_text(encoding="utf-8"))
    return [key for key in registry.keys if key.instance_id == instance_id]


def _canonical_counts(store: GroundRecallStore) -> dict[str, int]:
    return {
        "sources": len(store.list_sources()),
        "fragments": len(store.list_fragments()),
        "artifacts": len(store.list_artifacts()),
        "scopes": len(store.list_scopes()),
        "works": len(store.list_works()),
        "decisions": len(store.list_decisions()),
        "contributions": len(store.list_contributions()),
        "review_receipts": len(store.list_review_receipts()),
        "federation_feedback": len(store.list_federation_feedback()),
        "stewardship": len(store.list_stewardship()),
        "custody_events": len(store.list_custody_events()),
        "observations": len(store.list_observations()),
        "claims": len(store.list_claims()),
        "contradiction_cases": len(store.list_contradiction_cases()),
        "concepts": len(store.list_concepts()),
        "relations": len(store.list_relations()),
        "promotions": len(store.list_promotions()),
        "adjudications": len(store.list_adjudications()),
    }


def _count_json_files(path: str | Path | None) -> int:
    if not path or not Path(path).exists():
        return 0
    root = Path(path)
    if root.is_file():
        return 1 if root.suffix == ".json" else 0
    return sum(1 for item in root.rglob("*.json") if item.is_file())


def _count_path_items(path: str | Path | None) -> int:
    if not path or not Path(path).exists():
        return 0
    root = Path(path)
    if root.is_file():
        return 1
    return sum(1 for item in root.rglob("*") if item.is_file())


def _hash_payload(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plan GroundRecall custody handoff, tenancy departure, and instance retirement.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    orphans = subparsers.add_parser("orphans")
    orphans.add_argument("store_dir")
    departure = subparsers.add_parser("departure-plan")
    departure.add_argument("store_dir")
    departure.add_argument("--departing-principal-id", required=True)
    departure.add_argument("--planned-at", default="")
    retirement = subparsers.add_parser("retirement-plan")
    retirement.add_argument("store_dir")
    retirement.add_argument("--instance-id", required=True)
    retirement.add_argument("--replacement-instance-id", default="")
    retirement.add_argument("--planned-at", default="")
    retirement.add_argument("--registry-path", default="")
    retirement.add_argument("--subscriptions-dir", default="")
    retirement.add_argument("--catalogs-dir", default="")
    retirement.add_argument("--quarantine-dir", default="")
    retirement.add_argument("--backups-dir", default="")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "orphans":
        print(orphan_stewardship_report(args.store_dir).model_dump_json(indent=2))
        return
    if args.command == "departure-plan":
        print(
            plan_tenancy_departure(
                args.store_dir,
                departing_principal_id=args.departing_principal_id,
                planned_at=args.planned_at,
            ).model_dump_json(indent=2)
        )
        return
    print(
        plan_instance_retirement(
            args.store_dir,
            instance_id=args.instance_id,
            replacement_instance_id=args.replacement_instance_id,
            planned_at=args.planned_at,
            registry_path=args.registry_path or None,
            subscriptions_dir=args.subscriptions_dir or None,
            catalogs_dir=args.catalogs_dir or None,
            quarantine_dir=args.quarantine_dir or None,
            backups_dir=args.backups_dir or None,
        ).model_dump_json(indent=2)
    )
