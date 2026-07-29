from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from .federation import (
    FederationPolicyError,
    FederationSignature,
    FederationSignatureAlgorithm,
    _canonical_json,
    _signature_for_payload,
    _verify_signature_for_payload,
    filter_snapshot_for_federation,
    now_utc,
    record_restriction_markers,
)
from .models import GroundRecallSnapshot
from .policy import PolicyDecision, PolicyRequest, load_policy_plugins
from .store import GroundRecallStore


FEDERATION_CATALOG_SCHEMA_VERSION = "groundrecall.federation_catalog.v1"
CatalogDetailLevel = Literal["opaque", "aggregate", "descriptive"]
_RELEASE_RANK = {"public": 0, "internal": 1, "confidential": 2, "privileged": 3, "private": 4}


class FederationCatalogEntry(BaseModel):
    entry_id: str
    scope_id: str
    scope_kind: str = ""
    title: str = ""
    topic_summaries: list[str] = Field(default_factory=list)
    record_kind_counts: dict[str, int] = Field(default_factory=dict)
    time_coverage: dict[str, str] = Field(default_factory=dict)
    release_levels: list[str] = Field(default_factory=list)
    provenance_visibility: dict[str, int] = Field(default_factory=dict)
    record_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class FederationCatalogManifest(BaseModel):
    catalog_kind: str = "groundrecall_federation_catalog"
    schema_version: str = FEDERATION_CATALOG_SCHEMA_VERSION
    catalog_id: str
    created_at: str
    producer_instance_id: str
    target_release_level: str
    detail_level: CatalogDetailLevel
    content_hash: str
    signature: FederationSignature | None = None


class FederationCatalog(BaseModel):
    manifest: FederationCatalogManifest
    entries: list[FederationCatalogEntry] = Field(default_factory=list)
    policy_decision: dict[str, Any] = Field(default_factory=dict)


class FederationCatalogImportResult(BaseModel):
    decision: Literal["quarantined", "rejected"]
    catalog_id: str
    quarantine_path: str = ""
    producer_instance_id: str = ""
    accepted_entry_count: int = 0
    excluded_entry_count: int = 0
    reasons: list[str] = Field(default_factory=list)
    receiver_allowed_release_level: str = "private"
    receiver_allowed_instance_ids: list[str] = Field(default_factory=list)
    policy_decision: dict[str, Any] = Field(default_factory=dict)


def _catalog_content_hash(entries: list[FederationCatalogEntry]) -> str:
    return hashlib.sha256(_canonical_json([item.model_dump(mode="json") for item in entries]).encode("utf-8")).hexdigest()


def _scope_entry_id(scope_id: str, detail_level: CatalogDetailLevel) -> str:
    if detail_level == "descriptive":
        return scope_id
    return "scope-hash:" + hashlib.sha256(scope_id.encode("utf-8")).hexdigest()[:16]


def _policy_decision(
    policy_plugins_path: str | Path | None,
    *,
    decision_point: Literal["federate_export", "federate_import"],
    action: str,
    requester_id: str,
    release_level: str,
    target_release_level: str,
    producer_instance_id: str = "",
    scope_id: str = "",
) -> PolicyDecision | None:
    if policy_plugins_path is None:
        return None
    provider = load_policy_plugins(policy_plugins_path)
    return provider.evaluate(
        PolicyRequest(
            decision_point=decision_point,
            subject_id=requester_id,
            action=action,
            release_level=release_level,  # type: ignore[arg-type]
            target_release_level=target_release_level,  # type: ignore[arg-type]
            scope_id=scope_id,
            public_facing=target_release_level == "public",
            metadata={"producer_instance_id": producer_instance_id, "catalog_detail_level": "aggregate"},
        )
    )


def _block_reasons(decision: PolicyDecision | None) -> list[str]:
    if decision is None or decision.decision not in {"deny", "hard_gate"}:
        return []
    return [f"policy_plugin_{decision.decision}:{reason}" for reason in (decision.reasons or [decision.policy_id])]


def _record_release(record: Any) -> str:
    explicit = getattr(record, "release_level", None)
    if explicit in _RELEASE_RANK:
        return explicit
    metadata = getattr(record, "metadata", {})
    if isinstance(metadata, dict) and metadata.get("release_level") in _RELEASE_RANK:
        return str(metadata["release_level"])
    return "private"


def _record_scope(record: Any) -> str:
    return str(getattr(record, "scope_id", "") or getattr(record, "destination_scope_id", ""))


def _time_values(snapshot: GroundRecallSnapshot, scope_id: str) -> list[str]:
    values: list[str] = []
    for record in [*snapshot.works, *snapshot.decisions]:
        if _record_scope(record) != scope_id:
            continue
        for field in ("started_at", "completed_at", "effective_at", "review_due_at"):
            value = str(getattr(record, field, ""))
            if value:
                values.append(value)
    return sorted(values)


def build_federation_catalog(
    store_dir: str | Path,
    *,
    producer_instance_id: str,
    target_release_level: str,
    detail_level: CatalogDetailLevel = "aggregate",
    signing_key: str | bytes,
    key_id: str,
    signature_algorithm: FederationSignatureAlgorithm = "ed25519",
    catalog_id: str | None = None,
    created_at: str | None = None,
    policy_plugins_path: str | Path | None = None,
    requester_id: str = "",
    out_path: str | Path | None = None,
) -> FederationCatalog:
    decision = _policy_decision(
        policy_plugins_path,
        decision_point="federate_export",
        action="publish_federation_catalog",
        requester_id=requester_id,
        release_level=target_release_level,
        target_release_level=target_release_level,
        producer_instance_id=producer_instance_id,
    )
    reasons = _block_reasons(decision)
    if reasons:
        raise FederationPolicyError(";".join(reasons))
    store = GroundRecallStore(store_dir)
    snapshot = store.build_snapshot(
        snapshot_id=f"catalog-source-{producer_instance_id}",
        created_at=created_at or now_utc(),
        metadata={"export_kind": "federation_catalog", "target_release_level": target_release_level},
    )
    filtered, report = filter_snapshot_for_federation(snapshot, target_release_level=target_release_level)
    scopes = {scope.scope_id: scope for scope in filtered.scopes}
    grouped: dict[str, list[tuple[str, Any]]] = {scope_id: [] for scope_id in scopes}
    for kind, records in (
        ("work", filtered.works),
        ("decision", filtered.decisions),
        ("contribution", filtered.contributions),
        ("stewardship", filtered.stewardship),
        ("custody_event", filtered.custody_events),
    ):
        for record in records:
            scope_id = _record_scope(record)
            if scope_id in grouped:
                grouped[scope_id].append((kind, record))
    entries: list[FederationCatalogEntry] = []
    for scope_id, scope in sorted(scopes.items()):
        if record_restriction_markers(scope):
            continue
        records = grouped.get(scope_id, [])
        if any(record_restriction_markers(record) for _, record in records):
            continue
        counts: dict[str, int] = {}
        levels: set[str] = set()
        visibility: dict[str, int] = {}
        for kind, record in records:
            counts[kind] = counts.get(kind, 0) + 1
            level = _record_release(record)
            levels.add(level)
            value = str(getattr(record, "provenance_visibility", "full"))
            visibility[value] = visibility.get(value, 0) + 1
        times = _time_values(filtered, scope_id)
        topics = []
        if detail_level == "descriptive":
            topics = sorted(
                concept.title
                for concept in filtered.concepts
                if concept.current_status in {"reviewed", "promoted"} and not record_restriction_markers(concept)
            )[:25]
        entries.append(
            FederationCatalogEntry(
                entry_id=_scope_entry_id(scope_id, detail_level),
                scope_id=scope_id if detail_level == "descriptive" else _scope_entry_id(scope_id, detail_level),
                scope_kind=scope.scope_kind if detail_level != "opaque" else "",
                title=scope.title if detail_level == "descriptive" else "",
                topic_summaries=topics,
                record_kind_counts={} if detail_level == "opaque" else dict(sorted(counts.items())),
                time_coverage=(
                    {"start": times[0], "end": times[-1]} if times and detail_level != "opaque" else {}
                ),
                # Release classification remains visible even at opaque detail
                # so receiver-side caps can fail closed without inspecting the
                # protected scope contents.
                release_levels=sorted(levels, key=lambda value: _RELEASE_RANK.get(value, 4)),
                provenance_visibility=visibility if detail_level == "descriptive" else {},
                record_count=sum(counts.values()),
            )
        )
    content_hash = _catalog_content_hash(entries)
    timestamp = created_at or now_utc()
    manifest = FederationCatalogManifest(
        catalog_id=catalog_id or f"catalog::{producer_instance_id}::{content_hash[:12]}",
        created_at=timestamp,
        producer_instance_id=producer_instance_id,
        target_release_level=target_release_level,
        detail_level=detail_level,
        content_hash=content_hash,
    )
    unsigned = FederationCatalog(manifest=manifest, entries=entries, policy_decision=decision.model_dump(mode="json") if decision else {})
    signed_manifest = manifest.model_copy(
        update={
            "signature": FederationSignature(
                algorithm=signature_algorithm,
                key_id=key_id,
                value=_signature_for_payload(unsigned.model_dump(mode="json"), signing_key, algorithm=signature_algorithm),
            )
        }
    )
    catalog = unsigned.model_copy(update={"manifest": signed_manifest})
    if out_path is not None:
        target = Path(out_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(catalog.model_dump(mode="json"), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return catalog


def verify_federation_catalog(catalog: FederationCatalog | dict[str, Any], *, verification_key: str | bytes, key_id: str | None = None) -> FederationCatalog:
    parsed = catalog if isinstance(catalog, FederationCatalog) else FederationCatalog.model_validate(catalog)
    signature = parsed.manifest.signature
    if signature is None:
        raise FederationPolicyError("federation catalog is unsigned")
    if key_id is not None and signature.key_id != key_id:
        raise FederationPolicyError(f"unexpected catalog key_id: {signature.key_id}")
    if parsed.manifest.content_hash != _catalog_content_hash(parsed.entries):
        raise FederationPolicyError("federation catalog content hash verification failed")
    unsigned_manifest = parsed.manifest.model_copy(update={"signature": None})
    unsigned = parsed.model_copy(update={"manifest": unsigned_manifest})
    if not _verify_signature_for_payload(
        unsigned.model_dump(mode="json"),
        verification_key,
        algorithm=signature.algorithm,
        signature_value=signature.value,
    ):
        raise FederationPolicyError("federation catalog signature verification failed")
    return parsed


def filter_federation_catalog(
    catalog: FederationCatalog,
    *,
    allowed_release_level: str,
    allowed_instance_ids: list[str] | None = None,
) -> tuple[FederationCatalog, int, list[str]]:
    if allowed_release_level not in _RELEASE_RANK:
        raise FederationPolicyError(f"unknown receiver release cap: {allowed_release_level}")
    allowed_instances = allowed_instance_ids or [catalog.manifest.producer_instance_id]
    if catalog.manifest.producer_instance_id not in allowed_instances:
        return catalog.model_copy(update={"entries": []}), 0, ["producer_instance_not_allowed"]
    kept: list[FederationCatalogEntry] = []
    reasons: list[str] = []
    for entry in catalog.entries:
        if any(_RELEASE_RANK.get(level, 4) > _RELEASE_RANK[allowed_release_level] for level in entry.release_levels):
            reasons.append(f"entry_exceeds_receiver_release_cap:{entry.entry_id}")
            continue
        kept.append(entry)
    return catalog.model_copy(update={"entries": kept}), len(catalog.entries) - len(kept), reasons


def import_federation_catalog_to_quarantine(
    catalog_path: str | Path,
    quarantine_dir: str | Path,
    *,
    verification_key: str | bytes,
    key_id: str | None = None,
    allowed_release_level: str = "private",
    allowed_instance_ids: list[str] | None = None,
    policy_plugins_path: str | Path | None = None,
    requester_id: str = "",
) -> FederationCatalogImportResult:
    catalog = FederationCatalog.model_validate_json(Path(catalog_path).read_text(encoding="utf-8"))
    verify_federation_catalog(catalog, verification_key=verification_key, key_id=key_id)
    decision = _policy_decision(
        policy_plugins_path,
        decision_point="federate_import",
        action="import_federation_catalog",
        requester_id=requester_id,
        release_level=catalog.manifest.target_release_level,
        target_release_level=allowed_release_level,
        producer_instance_id=catalog.manifest.producer_instance_id,
    )
    reasons = _block_reasons(decision)
    if reasons:
        return FederationCatalogImportResult(
            decision="rejected",
            catalog_id=catalog.manifest.catalog_id,
            producer_instance_id=catalog.manifest.producer_instance_id,
            reasons=reasons,
            receiver_allowed_release_level=allowed_release_level,
            receiver_allowed_instance_ids=allowed_instance_ids or [],
            policy_decision=decision.model_dump(mode="json") if decision else {},
        )
    filtered, excluded, cap_reasons = filter_federation_catalog(
        catalog,
        allowed_release_level=allowed_release_level,
        allowed_instance_ids=allowed_instance_ids,
    )
    target = Path(quarantine_dir) / f"{catalog.manifest.catalog_id.replace('/', '_')}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            {
                "schema_version": "groundrecall.federation_catalog_quarantine.v1",
                "catalog": filtered.model_dump(mode="json"),
                "source_catalog_hash": catalog.manifest.content_hash,
                "receiver_allowed_release_level": allowed_release_level,
                "receiver_allowed_instance_ids": allowed_instance_ids or [catalog.manifest.producer_instance_id],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return FederationCatalogImportResult(
        decision="quarantined",
        catalog_id=catalog.manifest.catalog_id,
        quarantine_path=str(target),
        producer_instance_id=catalog.manifest.producer_instance_id,
        accepted_entry_count=len(filtered.entries),
        excluded_entry_count=excluded,
        reasons=cap_reasons,
        receiver_allowed_release_level=allowed_release_level,
        receiver_allowed_instance_ids=allowed_instance_ids or [catalog.manifest.producer_instance_id],
        policy_decision=decision.model_dump(mode="json") if decision else {},
    )


def query_federation_catalog(catalog_path: str | Path, query: str, *, limit: int = 20) -> list[FederationCatalogEntry]:
    payload = json.loads(Path(catalog_path).read_text(encoding="utf-8"))
    if "catalog" in payload:
        payload = payload["catalog"]
    catalog = FederationCatalog.model_validate(payload)
    tokens = set(re.findall(r"[a-z0-9][a-z0-9_-]{1,}", query.lower()))
    scored: list[tuple[float, FederationCatalogEntry]] = []
    for entry in catalog.entries:
        text = " ".join([entry.title, entry.scope_kind, *entry.topic_summaries, entry.scope_id]).lower()
        overlap = len(tokens & set(re.findall(r"[a-z0-9][a-z0-9_-]{1,}", text)))
        if overlap or not tokens:
            scored.append((overlap / max(len(tokens), 1), entry))
    scored.sort(key=lambda item: (-item[0], item[1].entry_id))
    return [entry for _, entry in scored[: max(0, limit)]]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build, verify, import, and query signed federation catalogs.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    export = subparsers.add_parser("export")
    export.add_argument("store_dir")
    export.add_argument("out_path")
    export.add_argument("--producer-instance-id", required=True)
    export.add_argument("--target-release-level", choices=tuple(_RELEASE_RANK), required=True)
    export.add_argument("--detail-level", choices=("opaque", "aggregate", "descriptive"), default="aggregate")
    export.add_argument("--key-file", required=True)
    export.add_argument("--key-id", required=True)
    export.add_argument("--signature-algorithm", choices=("hmac-sha256", "ed25519"), default="ed25519")
    export.add_argument("--policy-plugins", default=None)
    export.add_argument("--requester-id", default="")
    verify = subparsers.add_parser("verify")
    verify.add_argument("catalog_path")
    verify.add_argument("--key-file", required=True)
    verify.add_argument("--key-id", default=None)
    importer = subparsers.add_parser("import")
    importer.add_argument("catalog_path")
    importer.add_argument("quarantine_dir")
    importer.add_argument("--key-file", required=True)
    importer.add_argument("--key-id", default=None)
    importer.add_argument("--allowed-release-level", choices=tuple(_RELEASE_RANK), default="private")
    importer.add_argument("--allowed-instance-id", action="append", default=[])
    importer.add_argument("--policy-plugins", default=None)
    importer.add_argument("--requester-id", default="")
    query = subparsers.add_parser("query")
    query.add_argument("catalog_path")
    query.add_argument("query")
    query.add_argument("--limit", type=int, default=20)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "export":
        key = Path(args.key_file).read_bytes()
        print(
            build_federation_catalog(
                args.store_dir,
                producer_instance_id=args.producer_instance_id,
                target_release_level=args.target_release_level,
                detail_level=args.detail_level,
                signing_key=key,
                key_id=args.key_id,
                signature_algorithm=args.signature_algorithm,
                policy_plugins_path=args.policy_plugins,
                requester_id=args.requester_id,
                out_path=args.out_path,
            ).model_dump_json(indent=2)
        )
    elif args.command == "verify":
        catalog = FederationCatalog.model_validate_json(Path(args.catalog_path).read_text(encoding="utf-8"))
        print(verify_federation_catalog(catalog, verification_key=Path(args.key_file).read_bytes(), key_id=args.key_id).model_dump_json(indent=2))
    elif args.command == "import":
        result = import_federation_catalog_to_quarantine(
            args.catalog_path,
            args.quarantine_dir,
            verification_key=Path(args.key_file).read_bytes(),
            key_id=args.key_id,
            allowed_release_level=args.allowed_release_level,
            allowed_instance_ids=args.allowed_instance_id or None,
            policy_plugins_path=args.policy_plugins,
            requester_id=args.requester_id,
        )
        print(result.model_dump_json(indent=2))
    else:
        print(json.dumps([entry.model_dump(mode="json") for entry in query_federation_catalog(args.catalog_path, args.query, limit=args.limit)], indent=2))
