from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Literal

from pydantic import BaseModel, Field

from .models import (
    AdjudicationRecord,
    ArtifactRecord,
    ClaimRecord,
    ConceptRecord,
    ContradictionCaseRecord,
    FragmentRecord,
    ObservationRecord,
    PromotionRecord,
    RelationRecord,
    ReviewCandidateRecord,
    SourceRecord,
)
from .search_index import index_path
from .store import GroundRecallStore


ERASURE_SCHEMA_VERSION = "groundrecall.exceptional_erasure.v1"
ErasureReasonClass = Literal["privacy_request", "secret_exposure", "legal_request", "unauthorized_collection", "security_risk", "other"]


class ErasureTarget(BaseModel):
    record_kind: str
    record_id: str


class ErasureTombstone(BaseModel):
    schema_version: str = ERASURE_SCHEMA_VERSION
    tombstone_id: str
    reason_class: ErasureReasonClass
    authority: str
    requested_at: str
    target_ids: list[ErasureTarget] = Field(default_factory=list)
    affected_counts: dict[str, int] = Field(default_factory=dict)
    content_hashes: list[str] = Field(default_factory=list)
    origin_hashes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ErasurePlan(BaseModel):
    schema_version: str = ERASURE_SCHEMA_VERSION
    plan_id: str
    store_dir: str
    dry_run: bool = True
    reason_class: ErasureReasonClass
    authority: str
    requested_at: str
    target_ids: list[ErasureTarget] = Field(default_factory=list)
    affected_records: list[dict[str, Any]] = Field(default_factory=list)
    derived_artifacts: list[dict[str, Any]] = Field(default_factory=list)
    tombstone: ErasureTombstone
    warnings: list[str] = Field(default_factory=list)


def plan_exceptional_erasure(
    store_dir: str | Path,
    *,
    targets: Iterable[str],
    reason_class: ErasureReasonClass,
    authority: str,
    requested_at: str | None = None,
    exports_dir: str | Path | None = None,
    quarantine_dir: str | Path | None = None,
) -> ErasurePlan:
    """Build a dry-run exceptional-erasure plan without deleting content."""

    store = GroundRecallStore(store_dir)
    timestamp = requested_at or _now_utc()
    normalized_targets = _normalize_targets(targets)
    records_by_kind = _records_by_kind(store)
    known_ids = {
        (kind, record_id)
        for kind, records in records_by_kind.items()
        for record_id in records
    }
    seed_keys = _resolve_target_keys(normalized_targets, known_ids)
    affected_keys = _expand_affected_keys(seed_keys, records_by_kind)
    affected_records = [
        _affected_record_payload(kind, record_id, record, store.base_dir)
        for kind, record_id in sorted(affected_keys)
        for record in [records_by_kind.get(kind, {}).get(record_id)]
        if record is not None
    ]
    content_hashes = sorted({item["content_hash"] for item in affected_records if item.get("content_hash")})
    origin_hashes = sorted(
        {
            value
            for item in affected_records
            for value in item.get("origin_hashes", [])
            if value
        }
    )
    derived_artifacts = _derived_artifact_payloads(
        store.base_dir,
        affected_records=affected_records,
        exports_dir=exports_dir,
        quarantine_dir=quarantine_dir,
    )
    warnings = []
    unresolved = [target for target in normalized_targets if not _target_matches_known_id(target, known_ids)]
    for target in unresolved:
        warnings.append(f"unresolved_target:{target}")
    plan_basis = {
        "store_dir": str(Path(store_dir)),
        "targets": sorted([f"{kind}:{record_id}" for kind, record_id in affected_keys]),
        "requested_at": timestamp,
        "authority": authority,
        "reason_class": reason_class,
    }
    plan_id = "erasure_plan::" + _hash_payload(plan_basis)[:16]
    tombstone = ErasureTombstone(
        tombstone_id="erasure_tombstone::" + _hash_payload({**plan_basis, "content_hashes": content_hashes})[:16],
        reason_class=reason_class,
        authority=authority,
        requested_at=timestamp,
        target_ids=[ErasureTarget(record_kind=kind, record_id=record_id) for kind, record_id in sorted(seed_keys)],
        affected_counts=_counts_by_kind(affected_records),
        content_hashes=content_hashes,
        origin_hashes=origin_hashes,
        metadata={
            "purpose": "minimal_non_sensitive_reimport_prevention",
            "ordinary_epistemic_forgetting": False,
            "destructive_execution_required": True,
        },
    )
    return ErasurePlan(
        plan_id=plan_id,
        store_dir=str(Path(store_dir)),
        reason_class=reason_class,
        authority=authority,
        requested_at=timestamp,
        target_ids=[ErasureTarget(record_kind=kind, record_id=record_id) for kind, record_id in sorted(seed_keys)],
        affected_records=affected_records,
        derived_artifacts=derived_artifacts,
        tombstone=tombstone,
        warnings=warnings,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plan exceptional GroundRecall erasure without deleting content.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan_parser = subparsers.add_parser("plan", help="Dry-run exceptional erasure planning")
    plan_parser.add_argument("store_dir")
    plan_parser.add_argument("--target", action="append", required=True, help="Record id or kind:id target. May be repeated.")
    plan_parser.add_argument("--reason-class", choices=["privacy_request", "secret_exposure", "legal_request", "unauthorized_collection", "security_risk", "other"], required=True)
    plan_parser.add_argument("--authority", required=True)
    plan_parser.add_argument("--requested-at", default=None)
    plan_parser.add_argument("--exports-dir", default=None)
    plan_parser.add_argument("--quarantine-dir", default=None)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    payload = plan_exceptional_erasure(
        args.store_dir,
        targets=args.target,
        reason_class=args.reason_class,
        authority=args.authority,
        requested_at=args.requested_at,
        exports_dir=args.exports_dir,
        quarantine_dir=args.quarantine_dir,
    )
    print(json.dumps(payload.model_dump(mode="json"), indent=2, sort_keys=True))


def _records_by_kind(store: GroundRecallStore) -> dict[str, dict[str, Any]]:
    return {
        "source": {item.source_id: item for item in store.list_sources()},
        "fragment": {item.fragment_id: item for item in store.list_fragments()},
        "artifact": {item.artifact_id: item for item in store.list_artifacts()},
        "observation": {item.observation_id: item for item in store.list_observations()},
        "claim": {item.claim_id: item for item in store.list_claims()},
        "concept": {item.concept_id: item for item in store.list_concepts()},
        "relation": {item.relation_id: item for item in store.list_relations()},
        "review_candidate": {item.review_candidate_id: item for item in store.list_review_candidates()},
        "promotion": {item.promotion_id: item for item in store.list_promotions()},
        "adjudication": {item.adjudication_id: item for item in store.list_adjudications()},
        "contradiction_case": {item.case_id: item for item in store.list_contradiction_cases()},
    }


def _normalize_targets(targets: Iterable[str]) -> list[str]:
    return [str(target).strip() for target in targets if str(target).strip()]


def _resolve_target_keys(targets: list[str], known_ids: set[tuple[str, str]]) -> set[tuple[str, str]]:
    resolved: set[tuple[str, str]] = set()
    by_id = {record_id: kind for kind, record_id in known_ids}
    for target in targets:
        if ":" in target:
            kind, record_id = target.split(":", 1)
            key = (kind.strip(), record_id.strip())
            if key in known_ids:
                resolved.add(key)
                continue
        kind = by_id.get(target)
        if kind is not None:
            resolved.add((kind, target))
    return resolved


def _target_matches_known_id(target: str, known_ids: set[tuple[str, str]]) -> bool:
    if ":" in target:
        kind, record_id = target.split(":", 1)
        if (kind.strip(), record_id.strip()) in known_ids:
            return True
    return any(record_id == target for _, record_id in known_ids)


def _expand_affected_keys(
    seeds: set[tuple[str, str]],
    records_by_kind: dict[str, dict[str, Any]],
) -> set[tuple[str, str]]:
    affected = set(seeds)
    changed = True
    while changed:
        changed = False
        affected_ids = {record_id for _, record_id in affected}
        for kind, records in records_by_kind.items():
            for record_id, record in records.items():
                key = (kind, record_id)
                direct_refs = _record_reference_ids(record)
                if key in affected:
                    for ref_kind, ref_records in records_by_kind.items():
                        for ref_id in direct_refs:
                            if ref_id in ref_records and (ref_kind, ref_id) not in affected:
                                affected.add((ref_kind, ref_id))
                                changed = True
                    continue
                if bool(direct_refs & affected_ids):
                    affected.add(key)
                    changed = True
    return affected


def _record_reference_ids(record: Any) -> set[str]:
    if isinstance(record, SourceRecord):
        return set()
    if isinstance(record, FragmentRecord):
        return {record.source_id}
    if isinstance(record, ArtifactRecord):
        return set()
    if isinstance(record, ObservationRecord):
        return {record.artifact_id, record.provenance.origin_artifact_id} - {""}
    if isinstance(record, ClaimRecord):
        return (
            set(record.source_observation_ids)
            | set(record.supporting_fragment_ids)
            | set(record.concept_ids)
            | set(record.contradicts_claim_ids)
            | set(record.supersedes_claim_ids)
        )
    if isinstance(record, ConceptRecord):
        return set(record.source_artifact_ids)
    if isinstance(record, RelationRecord):
        return {record.source_id, record.target_id, *record.evidence_ids} - {""}
    if isinstance(record, ReviewCandidateRecord):
        return {record.candidate_id} - {""}
    if isinstance(record, PromotionRecord):
        return {record.candidate_id, *record.promoted_object_ids} - {""}
    if isinstance(record, AdjudicationRecord):
        return {record.subject_id, *record.selected_assessment_ids, *record.considered_assessment_ids} - {""}
    if isinstance(record, ContradictionCaseRecord):
        return {*record.claim_ids, record.adjudication_id} - {""}
    return set()


def _affected_record_payload(kind: str, record_id: str, record: Any, store_dir: Path) -> dict[str, Any]:
    payload = record.model_dump(mode="json")
    return {
        "record_kind": kind,
        "record_id": record_id,
        "current_status": str(payload.get("current_status", "")),
        "path": str(_record_path(store_dir, kind, record_id)),
        "content_hash": "sha256:" + _hash_payload(payload),
        "origin_hashes": _origin_hashes(payload),
    }


def _record_path(store_dir: Path, kind: str, record_id: str) -> Path:
    directory = {
        "source": "sources",
        "fragment": "fragments",
        "artifact": "artifacts",
        "observation": "observations",
        "claim": "claims",
        "concept": "concepts",
        "relation": "relations",
        "review_candidate": "review_candidates",
        "promotion": "promotions",
        "adjudication": "adjudications",
        "contradiction_case": "contradiction_cases",
    }[kind]
    safe_id = record_id.replace("::", "__") if kind == "concept" else record_id
    return store_dir / directory / f"{safe_id}.json"


def _derived_artifact_payloads(
    store_dir: Path,
    *,
    affected_records: list[dict[str, Any]],
    exports_dir: str | Path | None,
    quarantine_dir: str | Path | None,
) -> list[dict[str, Any]]:
    if not affected_records:
        return []
    payloads: list[dict[str, Any]] = []
    fts_path = index_path(store_dir)
    payloads.append(
        {
            "artifact_kind": "search_index",
            "path": str(fts_path),
            "exists": fts_path.exists(),
            "required_action": "rebuild_or_remove_before_next_query",
            "rebuildable": True,
        }
    )
    snapshot_dir = store_dir / "snapshots"
    payloads.append(
        {
            "artifact_kind": "snapshots",
            "path": str(snapshot_dir),
            "exists": snapshot_dir.exists(),
            "required_action": "inspect_and_remove_or_regenerate_snapshots_containing_erased_ids",
            "rebuildable": True,
        }
    )
    for artifact_kind, raw_path in [("exports", exports_dir), ("federation_quarantine", quarantine_dir)]:
        if raw_path is None:
            continue
        path = Path(raw_path)
        payloads.append(
            {
                "artifact_kind": artifact_kind,
                "path": str(path),
                "exists": path.exists(),
                "required_action": "inspect_and_remove_or_regenerate_containing_erased_ids",
                "rebuildable": artifact_kind == "exports",
            }
        )
    return payloads


def _origin_hashes(payload: dict[str, Any]) -> list[str]:
    values: set[str] = set()
    provenance = payload.get("provenance")
    if isinstance(provenance, dict):
        for key in ("origin_artifact_id", "origin_path", "source_url", "retrieval_date"):
            value = str(provenance.get(key, "")).strip()
            if value:
                values.add(f"{key}:sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}")
    for key in ("path", "url", "source_url"):
        value = str(payload.get(key, "")).strip()
        if value:
            values.add(f"{key}:sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}")
    return sorted(values)


def _counts_by_kind(records: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        kind = str(record.get("record_kind", ""))
        counts[kind] = counts.get(kind, 0) + 1
    return dict(sorted(counts.items()))


def _hash_payload(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    main()
