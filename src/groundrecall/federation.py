from __future__ import annotations

import argparse
import hashlib
import hmac
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Literal

from pydantic import BaseModel, Field

from .export_guardrails import _secret_field_path
from .models import GroundRecallSnapshot
from .store import GroundRecallStore


ReleaseLevel = Literal["public", "internal", "confidential", "privileged", "private"]
ProvenanceVisibility = Literal["full", "partial", "redacted", "hidden"]
ImportDecision = Literal["quarantined", "rejected"]

RELEASE_LEVELS: tuple[ReleaseLevel, ...] = (
    "public",
    "internal",
    "confidential",
    "privileged",
    "private",
)
RELEASE_RANK: dict[ReleaseLevel, int] = {level: index for index, level in enumerate(RELEASE_LEVELS)}
RELEASE_METADATA_KEYS = (
    "release_level",
    "release",
    "release_status",
    "classification",
    "confidentiality",
    "sensitivity",
    "visibility",
    "access_level",
)

RELEASE_VALUE_ALIASES: dict[str, ReleaseLevel] = {
    "public": "public",
    "publish": "public",
    "published": "public",
    "released": "public",
    "internal": "internal",
    "team": "internal",
    "project": "internal",
    "organization": "internal",
    "organisation": "internal",
    "confidential": "confidential",
    "restricted": "confidential",
    "sensitive": "confidential",
    "nonpublic": "confidential",
    "non_public": "confidential",
    "privileged": "privileged",
    "legal_privileged": "privileged",
    "attorney_client": "privileged",
    "medical": "privileged",
    "security": "privileged",
    "hr": "privileged",
    "private": "private",
    "local": "private",
    "local_only": "private",
    "do_not_export": "private",
    "no_export": "private",
    "secret": "private",
}


class FederationPolicyError(ValueError):
    """Raised when a federation bundle violates release or signature policy."""


class FederationExportFinding(BaseModel):
    record_kind: str
    record_id: str
    reason: str
    release_level: ReleaseLevel | None = None
    field_path: str = ""


class FederationPolicyReport(BaseModel):
    policy_id: str = "groundrecall_federation_release_policy.v1"
    target_release_level: ReleaseLevel
    included_counts: dict[str, int] = Field(default_factory=dict)
    excluded_total: int = 0
    findings: list[FederationExportFinding] = Field(default_factory=list)


class FederationSignature(BaseModel):
    algorithm: str = "hmac-sha256"
    key_id: str
    value: str


class FederationManifest(BaseModel):
    bundle_kind: str = "groundrecall_federation_bundle"
    schema_version: str = "groundrecall.federation_bundle.v1"
    bundle_id: str
    created_at: str
    producer_instance_id: str
    owner_instance_id: str = ""
    target_release_level: ReleaseLevel
    source_snapshot_id: str
    record_count: int
    content_hash: str
    signature: FederationSignature | None = None


class FederationBundle(BaseModel):
    manifest: FederationManifest
    snapshot: GroundRecallSnapshot
    policy_report: FederationPolicyReport


class FederationImportResult(BaseModel):
    decision: ImportDecision
    bundle_id: str
    quarantine_path: str = ""
    reasons: list[str] = Field(default_factory=list)
    record_count: int = 0
    origin_instance_id: str = ""
    target_release_level: ReleaseLevel


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def release_level_from_metadata(metadata: dict[str, Any]) -> ReleaseLevel | None:
    for key in RELEASE_METADATA_KEYS:
        if key not in metadata:
            continue
        level = normalize_release_level(metadata.get(key))
        if level is not None:
            return level
    return None


def normalize_release_level(value: Any) -> ReleaseLevel | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    return RELEASE_VALUE_ALIASES.get(normalized)


def is_less_restrictive(candidate: ReleaseLevel, source: ReleaseLevel) -> bool:
    return RELEASE_RANK[candidate] < RELEASE_RANK[source]


def is_allowed_for_target(record_level: ReleaseLevel, target_level: ReleaseLevel) -> bool:
    if record_level == "private":
        return False
    return RELEASE_RANK[record_level] <= RELEASE_RANK[target_level]


def export_federation_bundle(
    store_dir: str | Path,
    out_path: str | Path,
    *,
    target_release_level: ReleaseLevel,
    producer_instance_id: str,
    signing_key: str | bytes,
    key_id: str,
    owner_instance_id: str = "",
    snapshot_id: str | None = None,
    created_at: str | None = None,
    allow_unclassified_public: bool = False,
    allow_privileged: bool = False,
) -> FederationBundle:
    if target_release_level == "private":
        raise FederationPolicyError("private is local-only and cannot be used as a federation target")
    if target_release_level == "privileged" and not allow_privileged:
        raise FederationPolicyError("privileged federation requires allow_privileged=True")

    store = GroundRecallStore(store_dir)
    timestamp = created_at or now_utc()
    snapshot = store.build_snapshot(
        snapshot_id=snapshot_id or f"federation-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        created_at=timestamp,
        metadata={
            "export_kind": "federation",
            "producer_instance_id": producer_instance_id,
            "target_release_level": target_release_level,
        },
    )
    filtered, report = filter_snapshot_for_federation(
        snapshot,
        target_release_level=target_release_level,
        allow_unclassified_public=allow_unclassified_public,
    )
    manifest = _manifest_for_snapshot(
        snapshot=filtered,
        producer_instance_id=producer_instance_id,
        owner_instance_id=owner_instance_id,
        target_release_level=target_release_level,
        created_at=timestamp,
    )
    unsigned = FederationBundle(manifest=manifest, snapshot=filtered, policy_report=report)
    signed_manifest = manifest.model_copy(
        update={
            "signature": FederationSignature(
                key_id=key_id,
                value=_signature_for_payload(unsigned.model_dump(mode="json"), signing_key),
            )
        }
    )
    bundle = unsigned.model_copy(update={"manifest": signed_manifest})
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(bundle.model_dump(mode="json"), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return bundle


def filter_snapshot_for_federation(
    snapshot: GroundRecallSnapshot,
    *,
    target_release_level: ReleaseLevel,
    allow_unclassified_public: bool = False,
) -> tuple[GroundRecallSnapshot, FederationPolicyReport]:
    findings: list[FederationExportFinding] = []

    sources = _filter_records(snapshot.sources, "source", "source_id", target_release_level, findings, allow_unclassified_public)
    allowed_source_ids = {item.source_id for item in sources}

    fragments = [
        item
        for item in _filter_records(snapshot.fragments, "fragment", "fragment_id", target_release_level, findings, allow_unclassified_public)
        if _dependency_allowed("fragment", item.fragment_id, item.source_id, allowed_source_ids, "source", findings)
    ]
    allowed_fragment_ids = {item.fragment_id for item in fragments}

    artifacts = _filter_records(snapshot.artifacts, "artifact", "artifact_id", target_release_level, findings, allow_unclassified_public)
    allowed_artifact_ids = {item.artifact_id for item in artifacts}

    observations = [
        item
        for item in _filter_records(snapshot.observations, "observation", "observation_id", target_release_level, findings, allow_unclassified_public)
        if not item.artifact_id
        or _dependency_allowed("observation", item.observation_id, item.artifact_id, allowed_artifact_ids, "artifact", findings)
    ]
    allowed_observation_ids = {item.observation_id for item in observations}

    concepts = _filter_records(snapshot.concepts, "concept", "concept_id", target_release_level, findings, allow_unclassified_public)
    pruned_concepts = []
    for item in concepts:
        source_artifact_ids = [value for value in item.source_artifact_ids if value in allowed_artifact_ids]
        if item.source_artifact_ids and not source_artifact_ids:
            findings.append(_finding("concept", item.concept_id, "no_exportable_artifacts", item))
            continue
        pruned_concepts.append(item.model_copy(update={"source_artifact_ids": source_artifact_ids}))
    concepts = pruned_concepts
    allowed_concept_ids = {item.concept_id for item in concepts}

    claims = []
    for item in _filter_records(snapshot.claims, "claim", "claim_id", target_release_level, findings, allow_unclassified_public):
        source_observation_ids = [value for value in item.source_observation_ids if value in allowed_observation_ids]
        supporting_fragment_ids = [value for value in item.supporting_fragment_ids if value in allowed_fragment_ids]
        concept_ids = [value for value in item.concept_ids if value in allowed_concept_ids]
        hidden_count = len(item.source_observation_ids) - len(source_observation_ids)
        hidden_count += len(item.supporting_fragment_ids) - len(supporting_fragment_ids)
        if hidden_count and not _has_redaction_policy(item):
            findings.append(_finding("claim", item.claim_id, "hidden_basis_without_redaction_policy", item))
            continue
        if item.concept_ids and not concept_ids:
            findings.append(_finding("claim", item.claim_id, "no_exportable_concepts", item))
            continue
        metadata = dict(item.metadata)
        if hidden_count:
            metadata.setdefault("assessment_basis_visibility", "partial")
            metadata.setdefault("hidden_basis_count", hidden_count)
        claims.append(
            item.model_copy(
                update={
                    "source_observation_ids": source_observation_ids,
                    "supporting_fragment_ids": supporting_fragment_ids,
                    "concept_ids": concept_ids,
                    "contradicts_claim_ids": [],
                    "supersedes_claim_ids": [],
                    "metadata": metadata,
                }
            )
        )
    allowed_claim_ids = {item.claim_id for item in claims}
    claims = [
        item.model_copy(
            update={
                "contradicts_claim_ids": [value for value in item.contradicts_claim_ids if value in allowed_claim_ids],
                "supersedes_claim_ids": [value for value in item.supersedes_claim_ids if value in allowed_claim_ids],
            }
        )
        for item in claims
    ]

    relations = []
    for item in _filter_records(snapshot.relations, "relation", "relation_id", target_release_level, findings, allow_unclassified_public):
        if item.source_id not in allowed_concept_ids or item.target_id not in allowed_concept_ids:
            findings.append(_finding("relation", item.relation_id, "non_exportable_relation_endpoint", item))
            continue
        relations.append(item.model_copy(update={"evidence_ids": [value for value in item.evidence_ids if value in allowed_observation_ids]}))

    promotions = [
        item
        for item in snapshot.promotions
        if item.candidate_id in allowed_claim_ids or item.candidate_id in allowed_concept_ids or item.candidate_id in {rel.relation_id for rel in relations}
    ]

    filtered = snapshot.model_copy(
        update={
            "sources": sources,
            "fragments": fragments,
            "artifacts": artifacts,
            "observations": observations,
            "claims": claims,
            "concepts": concepts,
            "relations": relations,
            "promotions": promotions,
        }
    )
    counts = {
        "sources": len(sources),
        "fragments": len(fragments),
        "artifacts": len(artifacts),
        "observations": len(observations),
        "claims": len(claims),
        "concepts": len(concepts),
        "relations": len(relations),
        "promotions": len(promotions),
    }
    return filtered, FederationPolicyReport(
        target_release_level=target_release_level,
        included_counts=counts,
        excluded_total=len(findings),
        findings=findings,
    )


def verify_federation_bundle(bundle: FederationBundle | dict[str, Any], *, signing_key: str | bytes, key_id: str | None = None) -> FederationBundle:
    parsed = bundle if isinstance(bundle, FederationBundle) else FederationBundle.model_validate(bundle)
    signature = parsed.manifest.signature
    if signature is None:
        raise FederationPolicyError("federation bundle is unsigned")
    if key_id is not None and signature.key_id != key_id:
        raise FederationPolicyError(f"unexpected federation key_id: {signature.key_id}")
    unsigned_manifest = parsed.manifest.model_copy(update={"signature": None})
    unsigned_bundle = parsed.model_copy(update={"manifest": unsigned_manifest})
    expected = _signature_for_payload(unsigned_bundle.model_dump(mode="json"), signing_key)
    if not hmac.compare_digest(signature.value, expected):
        raise FederationPolicyError("federation bundle signature verification failed")
    content_hash = _content_hash_for_snapshot(parsed.snapshot)
    if parsed.manifest.content_hash != content_hash:
        raise FederationPolicyError("federation bundle content hash verification failed")
    return parsed


def import_federation_bundle_to_quarantine(
    bundle_path: str | Path,
    quarantine_dir: str | Path,
    *,
    signing_key: str | bytes,
    accepted_release_levels: Iterable[ReleaseLevel],
    key_id: str | None = None,
) -> FederationImportResult:
    payload = json.loads(Path(bundle_path).read_text(encoding="utf-8"))
    bundle = verify_federation_bundle(payload, signing_key=signing_key, key_id=key_id)
    accepted = set(accepted_release_levels)
    reasons: list[str] = []
    if bundle.manifest.target_release_level not in accepted:
        reasons.append(f"target_release_level_not_accepted:{bundle.manifest.target_release_level}")
    for finding in _bundle_policy_violations(bundle):
        reasons.append(finding)
    if reasons:
        return FederationImportResult(
            decision="rejected",
            bundle_id=bundle.manifest.bundle_id,
            reasons=reasons,
            record_count=bundle.manifest.record_count,
            origin_instance_id=bundle.manifest.producer_instance_id,
            target_release_level=bundle.manifest.target_release_level,
        )

    target = Path(quarantine_dir) / f"{bundle.manifest.bundle_id}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(bundle.model_dump(mode="json"), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return FederationImportResult(
        decision="quarantined",
        bundle_id=bundle.manifest.bundle_id,
        quarantine_path=str(target),
        record_count=bundle.manifest.record_count,
        origin_instance_id=bundle.manifest.producer_instance_id,
        target_release_level=bundle.manifest.target_release_level,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export or import GroundRecall federation bundles.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    export_parser = subparsers.add_parser("export", help="Write a signed federation bundle from a local store.")
    export_parser.add_argument("store_dir")
    export_parser.add_argument("out_path")
    export_parser.add_argument("--target-release-level", required=True, choices=["public", "internal", "confidential", "privileged"])
    export_parser.add_argument("--producer-instance-id", required=True)
    export_parser.add_argument("--owner-instance-id", default="")
    export_parser.add_argument("--key-file", required=True, help="Path containing the HMAC signing key.")
    export_parser.add_argument("--key-id", required=True)
    export_parser.add_argument("--snapshot-id", default=None)
    export_parser.add_argument("--allow-unclassified-public", action="store_true")
    export_parser.add_argument("--allow-privileged", action="store_true")

    import_parser = subparsers.add_parser("import", help="Verify a federation bundle and place it in quarantine.")
    import_parser.add_argument("bundle_path")
    import_parser.add_argument("quarantine_dir")
    import_parser.add_argument("--key-file", required=True, help="Path containing the HMAC verification key.")
    import_parser.add_argument("--key-id", default=None)
    import_parser.add_argument(
        "--accept-release-level",
        action="append",
        default=[],
        choices=["public", "internal", "confidential", "privileged"],
        help="Accepted target release level. May be repeated.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    key = Path(args.key_file).read_bytes()
    if args.command == "export":
        bundle = export_federation_bundle(
            store_dir=args.store_dir,
            out_path=args.out_path,
            target_release_level=args.target_release_level,
            producer_instance_id=args.producer_instance_id,
            owner_instance_id=args.owner_instance_id,
            signing_key=key,
            key_id=args.key_id,
            snapshot_id=args.snapshot_id,
            allow_unclassified_public=args.allow_unclassified_public,
            allow_privileged=args.allow_privileged,
        )
        print(json.dumps(bundle.model_dump(mode="json"), indent=2, sort_keys=True))
        return
    if args.command == "import":
        accepted = args.accept_release_level or ["public"]
        result = import_federation_bundle_to_quarantine(
            args.bundle_path,
            args.quarantine_dir,
            signing_key=key,
            accepted_release_levels=accepted,
            key_id=args.key_id,
        )
        print(json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True))
        return


def _filter_records(
    records: list[Any],
    record_kind: str,
    id_field: str,
    target_release_level: ReleaseLevel,
    findings: list[FederationExportFinding],
    allow_unclassified_public: bool,
) -> list[Any]:
    kept = []
    for record in records:
        record_id = str(getattr(record, id_field))
        level = _record_release_level(record, allow_unclassified_public=allow_unclassified_public)
        if level is None:
            findings.append(FederationExportFinding(record_kind=record_kind, record_id=record_id, reason="missing_release_level"))
            continue
        blocked_reason = _record_block_reason(record, level, target_release_level)
        if blocked_reason is not None:
            findings.append(FederationExportFinding(record_kind=record_kind, record_id=record_id, reason=blocked_reason, release_level=level))
            continue
        kept.append(record)
    return kept


def _record_release_level(record: Any, *, allow_unclassified_public: bool) -> ReleaseLevel | None:
    metadata = getattr(record, "metadata", None)
    if isinstance(metadata, dict):
        level = release_level_from_metadata(metadata)
        if level is not None:
            return level
    return "public" if allow_unclassified_public else None


def _record_block_reason(record: Any, level: ReleaseLevel, target_release_level: ReleaseLevel) -> str | None:
    if level == "private":
        return "private_never_federated"
    if not is_allowed_for_target(level, target_release_level):
        return f"release_level_exceeds_target:{level}"
    secret_path = _secret_field_path(record.model_dump())
    if secret_path is not None:
        return f"secret_like_content:{secret_path}"
    metadata = getattr(record, "metadata", {})
    if isinstance(metadata, dict):
        source_levels = _source_release_levels(metadata)
        if source_levels and any(is_less_restrictive(level, source) for source in source_levels) and not _has_redaction_policy(record):
            return "derivative_requires_redaction_policy"
    return None


def _source_release_levels(metadata: dict[str, Any]) -> list[ReleaseLevel]:
    values = metadata.get("source_release_levels") or metadata.get("derived_from_release_levels") or []
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return []
    levels = []
    for value in values:
        level = normalize_release_level(value)
        if level is not None:
            levels.append(level)
    return levels


def _has_redaction_policy(record: Any) -> bool:
    metadata = getattr(record, "metadata", {})
    return isinstance(metadata, dict) and bool(metadata.get("redaction_policy_id") or metadata.get("declassification_policy_id"))


def _finding(record_kind: str, record_id: str, reason: str, record: Any) -> FederationExportFinding:
    return FederationExportFinding(
        record_kind=record_kind,
        record_id=record_id,
        reason=reason,
        release_level=_record_release_level(record, allow_unclassified_public=False),
    )


def _dependency_allowed(
    record_kind: str,
    record_id: str,
    dependency_id: str,
    allowed_dependency_ids: set[str],
    dependency_kind: str,
    findings: list[FederationExportFinding],
) -> bool:
    if dependency_id in allowed_dependency_ids:
        return True
    findings.append(FederationExportFinding(record_kind=record_kind, record_id=record_id, reason=f"non_exportable_{dependency_kind}"))
    return False


def _manifest_for_snapshot(
    *,
    snapshot: GroundRecallSnapshot,
    producer_instance_id: str,
    owner_instance_id: str,
    target_release_level: ReleaseLevel,
    created_at: str,
) -> FederationManifest:
    record_count = sum(
        len(items)
        for items in (
            snapshot.sources,
            snapshot.fragments,
            snapshot.artifacts,
            snapshot.observations,
            snapshot.claims,
            snapshot.concepts,
            snapshot.relations,
            snapshot.promotions,
            snapshot.adjudications,
        )
    )
    digest = _content_hash_for_snapshot(snapshot)
    return FederationManifest(
        bundle_id=f"federation::{producer_instance_id}::{snapshot.snapshot_id}::{digest[:12]}",
        created_at=created_at,
        producer_instance_id=producer_instance_id,
        owner_instance_id=owner_instance_id,
        target_release_level=target_release_level,
        source_snapshot_id=snapshot.snapshot_id,
        record_count=record_count,
        content_hash=digest,
    )


def _content_hash_for_snapshot(snapshot: GroundRecallSnapshot) -> str:
    return hashlib.sha256(_canonical_json(snapshot.model_dump(mode="json")).encode("utf-8")).hexdigest()


def _signature_for_payload(payload: dict[str, Any], signing_key: str | bytes) -> str:
    key = signing_key.encode("utf-8") if isinstance(signing_key, str) else signing_key
    return hmac.new(key, _canonical_json(payload).encode("utf-8"), hashlib.sha256).hexdigest()


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _bundle_policy_violations(bundle: FederationBundle) -> list[str]:
    violations: list[str] = []
    for record_kind, records, id_field in (
        ("source", bundle.snapshot.sources, "source_id"),
        ("fragment", bundle.snapshot.fragments, "fragment_id"),
        ("artifact", bundle.snapshot.artifacts, "artifact_id"),
        ("observation", bundle.snapshot.observations, "observation_id"),
        ("claim", bundle.snapshot.claims, "claim_id"),
        ("concept", bundle.snapshot.concepts, "concept_id"),
        ("relation", bundle.snapshot.relations, "relation_id"),
    ):
        for record in records:
            record_id = str(getattr(record, id_field))
            level = _record_release_level(record, allow_unclassified_public=False)
            if level is None:
                violations.append(f"{record_kind}:{record_id}:missing_release_level")
            elif not is_allowed_for_target(level, bundle.manifest.target_release_level):
                violations.append(f"{record_kind}:{record_id}:release_level_exceeds_target:{level}")
    return violations
