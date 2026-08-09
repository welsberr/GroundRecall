from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from .catalog import _RELEASE_RANK, _record_release, _record_scope
from .federation import (
    FederationPolicyError,
    FederationSignature,
    FederationSignatureAlgorithm,
    _canonical_json,
    _signature_for_payload,
    _verify_signature_for_payload,
    now_utc,
    record_compartments,
    record_restriction_markers,
)
from .policy import PolicyDecision, PolicyRequest, load_policy_plugins
from .federation_realm import FederationRealm, event_matches_realm
from .store import GroundRecallStore


CHANGE_FEED_SCHEMA_VERSION = "groundrecall.federation_change_feed.v1"


class FederationSubscription(BaseModel):
    schema_version: str = "groundrecall.federation_subscription.v1"
    subscription_id: str
    producer_instance_id: str
    scope_ids: list[str] = Field(default_factory=list)
    record_kinds: list[str] = Field(default_factory=list)
    change_kinds: list[str] = Field(default_factory=lambda: ["upsert", "state"])
    maximum_release_level: str = "private"
    allowed_restriction_markers: list[str] = Field(default_factory=list)
    allowed_compartments: list[str] = Field(default_factory=list)
    cursor: str = ""
    active: bool = True
    purpose: str = ""
    realm_id: str = ""
    audience: str = ""
    principal_id: str = ""
    trusted_instance_ids: list[str] = Field(default_factory=list)
    auto_accept: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class FederationChangeEvent(BaseModel):
    event_id: str
    event_kind: str
    record_kind: str
    record_id: str
    content_hash: str
    scope_id: str = ""
    release_level: str = "private"
    restriction_markers: list[str] = Field(default_factory=list)
    compartments: list[str] = Field(default_factory=list)
    realm_id: str = ""
    audience: str = ""
    origin_instance_id: str = ""
    origin_principal_id: str = ""
    occurred_at: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


class FederationChangeBundleManifest(BaseModel):
    bundle_kind: str = "groundrecall_federation_change_bundle"
    schema_version: str = CHANGE_FEED_SCHEMA_VERSION
    bundle_id: str
    created_at: str
    producer_instance_id: str
    subscription_id: str
    cursor_start: str = ""
    cursor_end: str = ""
    event_count: int = 0
    content_hash: str
    signature: FederationSignature | None = None


class FederationChangeBundle(BaseModel):
    manifest: FederationChangeBundleManifest
    events: list[FederationChangeEvent] = Field(default_factory=list)
    policy_decision: dict[str, Any] = Field(default_factory=dict)


class FederationChangeImportResult(BaseModel):
    decision: Literal["quarantined", "rejected"]
    bundle_id: str
    quarantine_path: str = ""
    producer_instance_id: str = ""
    event_count: int = 0
    replayed: bool = False
    reasons: list[str] = Field(default_factory=list)
    policy_decision: dict[str, Any] = Field(default_factory=dict)


def _records(store: GroundRecallStore) -> list[tuple[str, Any]]:
    groups = (
        ("source", store.list_sources()),
        ("artifact", store.list_artifacts()),
        ("observation", store.list_observations()),
        ("claim", store.list_claims()),
        ("concept", store.list_concepts()),
        ("relation", store.list_relations()),
        ("work", store.list_works()),
        ("decision", store.list_decisions()),
        ("contribution", store.list_contributions()),
        ("contribution_review_receipt", store.list_contribution_review_receipts()),
        ("review_receipt", store.list_review_receipts()),
        ("federation_feedback", store.list_federation_feedback()),
        ("stewardship", store.list_stewardship()),
        ("custody_event", store.list_custody_events()),
    )
    return [(kind, record) for kind, records in groups for record in records]


def _record_id(record_kind: str, record: Any) -> str:
    for field in (f"{record_kind}_id", "receipt_id", "feedback_id", "event_id", "case_id", "relation_id"):
        value = getattr(record, field, None)
        if value:
            return str(value)
    raise FederationPolicyError(f"record has no stable ID: {record_kind}")


def _record_time(record: Any) -> str:
    for field in ("updated_at", "created_at", "occurred_at", "completed_at", "effective_at", "reviewed_at"):
        value = str(getattr(record, field, "") or "")
        if value:
            return value
    return ""


def _event_for_record(record_kind: str, record: Any) -> FederationChangeEvent:
    record_id = _record_id(record_kind, record)
    payload = record.model_dump(mode="json")
    content_hash = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    basis = f"{record_kind}:{record_id}:{content_hash}"
    event_id = "change:" + hashlib.sha256(basis.encode("utf-8")).hexdigest()
    state = str(getattr(record, "state", "") or getattr(record, "current_status", ""))
    event_kind = "state" if state in {"accepted", "partially_accepted", "rejected", "deferred", "withdrawn", "superseded", "orphaned", "retired"} else "upsert"
    metadata = getattr(record, "metadata", {})
    metadata = metadata if isinstance(metadata, dict) else {}
    return FederationChangeEvent(
        event_id=event_id,
        event_kind=event_kind,
        record_kind=record_kind,
        record_id=record_id,
        content_hash=content_hash,
        scope_id=_record_scope(record),
        release_level=_record_release(record),
        restriction_markers=record_restriction_markers(record),
        compartments=record_compartments(record),
        realm_id=str(metadata.get("realm_id", "")),
        audience=str(metadata.get("replication_audience", "")),
        origin_instance_id=str(metadata.get("origin_instance_id", "")),
        origin_principal_id=str(metadata.get("origin_principal_id", "")),
        occurred_at=_record_time(record),
        payload=payload,
    )


def list_change_events(store_dir: str | Path) -> list[FederationChangeEvent]:
    store = GroundRecallStore(store_dir)
    events = [_event_for_record(kind, record) for kind, record in _records(store)]
    events.sort(key=lambda event: (event.occurred_at, event.event_id))
    return events


def save_subscription(path: str | Path, subscription: FederationSubscription) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(subscription.model_dump_json(indent=2) + "\n", encoding="utf-8")


def load_subscription(path: str | Path) -> FederationSubscription:
    return FederationSubscription.model_validate_json(Path(path).read_text(encoding="utf-8"))


def _bundle_hash(events: list[FederationChangeEvent]) -> str:
    return hashlib.sha256(_canonical_json([event.model_dump(mode="json") for event in events]).encode("utf-8")).hexdigest()


def _policy(
    path: str | Path | None,
    *,
    decision_point: Literal["federate_export", "federate_import"],
    action: str,
    requester_id: str,
    subscription: FederationSubscription,
) -> PolicyDecision | None:
    if path is None:
        return None
    provider = load_policy_plugins(path)
    return provider.evaluate(
        PolicyRequest(
            decision_point=decision_point,
            subject_id=requester_id,
            action=action,
            scope_id=subscription.scope_ids[0] if len(subscription.scope_ids) == 1 else "",
            target_release_level=subscription.maximum_release_level,  # type: ignore[arg-type]
            metadata={
                "subscription_id": subscription.subscription_id,
                "change_kinds": subscription.change_kinds,
                "restriction_markers": subscription.allowed_restriction_markers,
                "compartment_ids": subscription.allowed_compartments,
                "purpose": subscription.purpose,
            },
        )
    )


def _policy_block_reasons(decision: PolicyDecision | None) -> list[str]:
    if decision is None or decision.decision not in {"deny", "hard_gate"}:
        return []
    return [f"policy_plugin_{decision.decision}:{reason}" for reason in (decision.reasons or [decision.policy_id])]


def build_incremental_change_bundle(
    store_dir: str | Path,
    subscription: FederationSubscription,
    *,
    signing_key: str | bytes,
    key_id: str,
    signature_algorithm: FederationSignatureAlgorithm = "ed25519",
    policy_plugins_path: str | Path | None = None,
    requester_id: str = "",
    out_path: str | Path | None = None,
    created_at: str | None = None,
) -> FederationChangeBundle:
    decision = _policy(
        policy_plugins_path,
        decision_point="federate_export",
        action="export_incremental_changes",
        requester_id=requester_id,
        subscription=subscription,
    )
    reasons = _policy_block_reasons(decision)
    if reasons:
        raise FederationPolicyError(";".join(reasons))
    events = list_change_events(store_dir)
    event_ids = {event.event_id for event in events}
    if subscription.cursor and subscription.cursor not in event_ids:
        raise FederationPolicyError("subscription cursor is not present in producer event history")
    start_index = next((index + 1 for index, event in enumerate(events) if event.event_id == subscription.cursor), 0)
    selected: list[FederationChangeEvent] = []
    allowed_restrictions = set(subscription.allowed_restriction_markers)
    allowed_compartments = set(subscription.allowed_compartments)
    for event in events[start_index:]:
        if subscription.realm_id:
            realm = FederationRealm(
                realm_id=subscription.realm_id,
                audience=subscription.audience or "device_local",
                principal_id=subscription.principal_id,
                scope_ids=subscription.scope_ids,
                trusted_instance_ids=subscription.trusted_instance_ids,
                maximum_release_level=subscription.maximum_release_level,
                allowed_restriction_markers=subscription.allowed_restriction_markers,
                auto_accept=subscription.auto_accept,
            )
            if not event_matches_realm(
                realm=realm,
                audience=event.audience,
                event_realm_id=event.realm_id,
                event_scope_id=event.scope_id,
                event_origin_instance_id=event.origin_instance_id,
            ):
                continue
        if subscription.scope_ids and event.scope_id not in subscription.scope_ids:
            continue
        if subscription.record_kinds and event.record_kind not in subscription.record_kinds:
            continue
        if subscription.change_kinds and event.event_kind not in subscription.change_kinds:
            continue
        if _RELEASE_RANK.get(event.release_level, 4) > _RELEASE_RANK.get(subscription.maximum_release_level, 4):
            continue
        if event.restriction_markers and not set(event.restriction_markers) <= allowed_restrictions:
            continue
        if event.compartments and not set(event.compartments) <= allowed_compartments:
            continue
        selected.append(event)
    cursor_end = selected[-1].event_id if selected else subscription.cursor
    content_hash = _bundle_hash(selected)
    timestamp = created_at or now_utc()
    manifest = FederationChangeBundleManifest(
        bundle_id=f"changes::{subscription.producer_instance_id}::{subscription.subscription_id}::{content_hash[:12]}",
        created_at=timestamp,
        producer_instance_id=subscription.producer_instance_id,
        subscription_id=subscription.subscription_id,
        cursor_start=subscription.cursor,
        cursor_end=cursor_end,
        event_count=len(selected),
        content_hash=content_hash,
    )
    unsigned = FederationChangeBundle(
        manifest=manifest,
        events=selected,
        policy_decision=decision.model_dump(mode="json") if decision else {},
    )
    signed = unsigned.model_copy(
        update={
            "manifest": manifest.model_copy(
                update={
                    "signature": FederationSignature(
                        algorithm=signature_algorithm,
                        key_id=key_id,
                        value=_signature_for_payload(unsigned.model_dump(mode="json"), signing_key, algorithm=signature_algorithm),
                    )
                }
            )
        }
    )
    if out_path is not None:
        target = Path(out_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(signed.model_dump(mode="json"), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return signed


def verify_incremental_change_bundle(bundle: FederationChangeBundle | dict[str, Any], *, verification_key: str | bytes, key_id: str | None = None) -> FederationChangeBundle:
    parsed = bundle if isinstance(bundle, FederationChangeBundle) else FederationChangeBundle.model_validate(bundle)
    signature = parsed.manifest.signature
    if signature is None:
        raise FederationPolicyError("incremental change bundle is unsigned")
    if key_id is not None and signature.key_id != key_id:
        raise FederationPolicyError(f"unexpected change bundle key_id: {signature.key_id}")
    if parsed.manifest.content_hash != _bundle_hash(parsed.events):
        raise FederationPolicyError("incremental change bundle content hash verification failed")
    unsigned = parsed.model_copy(update={"manifest": parsed.manifest.model_copy(update={"signature": None})})
    if not _verify_signature_for_payload(unsigned.model_dump(mode="json"), verification_key, algorithm=signature.algorithm, signature_value=signature.value):
        raise FederationPolicyError("incremental change bundle signature verification failed")
    return parsed


def import_incremental_change_bundle_to_quarantine(
    bundle_path: str | Path,
    quarantine_dir: str | Path,
    *,
    verification_key: str | bytes,
    subscription: FederationSubscription,
    key_id: str | None = None,
    policy_plugins_path: str | Path | None = None,
    requester_id: str = "",
) -> FederationChangeImportResult:
    bundle = FederationChangeBundle.model_validate_json(Path(bundle_path).read_text(encoding="utf-8"))
    verify_incremental_change_bundle(bundle, verification_key=verification_key, key_id=key_id)
    if bundle.manifest.subscription_id != subscription.subscription_id:
        return FederationChangeImportResult(decision="rejected", bundle_id=bundle.manifest.bundle_id, producer_instance_id=bundle.manifest.producer_instance_id, reasons=["subscription_id_mismatch"])
    decision = _policy(
        policy_plugins_path,
        decision_point="federate_import",
        action="import_incremental_changes",
        requester_id=requester_id,
        subscription=subscription,
    )
    reasons = _policy_block_reasons(decision)
    allowed_restrictions = set(subscription.allowed_restriction_markers)
    allowed_compartments = set(subscription.allowed_compartments)
    for event in bundle.events:
        if subscription.realm_id:
            realm = FederationRealm(
                realm_id=subscription.realm_id,
                audience=subscription.audience or "device_local",
                principal_id=subscription.principal_id,
                scope_ids=subscription.scope_ids,
                trusted_instance_ids=subscription.trusted_instance_ids,
                maximum_release_level=subscription.maximum_release_level,
                allowed_restriction_markers=subscription.allowed_restriction_markers,
                auto_accept=subscription.auto_accept,
            )
            if not event_matches_realm(
                realm=realm,
                audience=event.audience,
                event_realm_id=event.realm_id,
                event_scope_id=event.scope_id,
                event_origin_instance_id=event.origin_instance_id,
            ):
                reasons.append(f"event_not_addressed_to_realm:{event.event_id}")
        if _RELEASE_RANK.get(event.release_level, 4) > _RELEASE_RANK.get(subscription.maximum_release_level, 4):
            reasons.append(f"event_exceeds_receiver_release_cap:{event.event_id}:{event.release_level}")
        if event.restriction_markers and not set(event.restriction_markers) <= allowed_restrictions:
            missing = ",".join(sorted(set(event.restriction_markers) - allowed_restrictions))
            reasons.append(f"event_restriction_markers_not_accepted:{event.event_id}:{missing}")
        if event.compartments and not set(event.compartments) <= allowed_compartments:
            missing = ",".join(sorted(set(event.compartments) - allowed_compartments))
            reasons.append(f"event_compartments_not_accepted:{event.event_id}:{missing}")
    if reasons:
        return FederationChangeImportResult(decision="rejected", bundle_id=bundle.manifest.bundle_id, producer_instance_id=bundle.manifest.producer_instance_id, reasons=reasons, policy_decision=decision.model_dump(mode="json") if decision else {})
    target = Path(quarantine_dir) / f"{bundle.manifest.bundle_id.replace('/', '_')}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(bundle.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    replayed = target.exists() and target.read_text(encoding="utf-8") == serialized
    if not replayed:
        target.write_text(serialized, encoding="utf-8")
    return FederationChangeImportResult(
        decision="quarantined",
        bundle_id=bundle.manifest.bundle_id,
        quarantine_path=str(target),
        producer_instance_id=bundle.manifest.producer_instance_id,
        event_count=len(bundle.events),
        replayed=replayed,
        policy_decision=decision.model_dump(mode="json") if decision else {},
    )


def acknowledge_change_bundle(
    subscription_path: str | Path,
    bundle_path: str | Path,
    *,
    verification_key: str | bytes | None = None,
    key_id: str | None = None,
) -> FederationSubscription:
    subscription = load_subscription(subscription_path)
    bundle = FederationChangeBundle.model_validate_json(Path(bundle_path).read_text(encoding="utf-8"))
    if verification_key is not None:
        verify_incremental_change_bundle(bundle, verification_key=verification_key, key_id=key_id)
    if bundle.manifest.subscription_id != subscription.subscription_id:
        raise FederationPolicyError("bundle subscription does not match local subscription")
    if bundle.manifest.producer_instance_id != subscription.producer_instance_id:
        raise FederationPolicyError("bundle producer does not match local subscription")
    if subscription.cursor and bundle.manifest.cursor_start != subscription.cursor:
        raise FederationPolicyError("bundle cursor does not continue the local subscription")
    updated = subscription.model_copy(update={"cursor": bundle.manifest.cursor_end})
    save_subscription(subscription_path, updated)
    return updated


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage resumable signed federation change feeds.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("subscription-create")
    create.add_argument("path")
    create.add_argument("--subscription-id", required=True)
    create.add_argument("--producer-instance-id", required=True)
    create.add_argument("--scope-id", action="append", default=[])
    create.add_argument("--record-kind", action="append", default=[])
    create.add_argument("--change-kind", action="append", default=[])
    create.add_argument("--maximum-release-level", choices=tuple(_RELEASE_RANK), default="private")
    create.add_argument("--purpose", required=True)
    create.add_argument("--realm-id", default="")
    create.add_argument("--audience", choices=("device_local", "principal", "project", "team", "public"), default="")
    create.add_argument("--principal-id", default="")
    create.add_argument("--trusted-instance-id", action="append", default=[])
    create.add_argument("--auto-accept", action="store_true")
    create.add_argument("--allowed-restriction-marker", action="append", default=[], help="Restriction marker accepted by this subscription. May be repeated.")
    create.add_argument("--allowed-compartment", action="append", default=[], help="Compartment accepted by this subscription. May be repeated.")
    export = subparsers.add_parser("export")
    export.add_argument("store_dir")
    export.add_argument("subscription_path")
    export.add_argument("out_path")
    export.add_argument("--key-file", required=True)
    export.add_argument("--key-id", required=True)
    export.add_argument("--signature-algorithm", choices=("hmac-sha256", "ed25519"), default="ed25519")
    export.add_argument("--policy-plugins", default=None)
    export.add_argument("--requester-id", default="")
    importer = subparsers.add_parser("import")
    importer.add_argument("bundle_path")
    importer.add_argument("quarantine_dir")
    importer.add_argument("subscription_path")
    importer.add_argument("--key-file", required=True)
    importer.add_argument("--key-id", default=None)
    importer.add_argument("--policy-plugins", default=None)
    importer.add_argument("--requester-id", default="")
    ack = subparsers.add_parser("ack")
    ack.add_argument("subscription_path")
    ack.add_argument("bundle_path")
    ack.add_argument("--key-file", default=None)
    ack.add_argument("--key-id", default=None)
    personal = subparsers.add_parser("personal-sync", help="Verify, quarantine, and apply an opted-in principal-realm bundle.")
    personal.add_argument("bundle_path")
    personal.add_argument("store_dir")
    personal.add_argument("quarantine_dir")
    personal.add_argument("subscription_path")
    personal.add_argument("--key-file", required=True)
    personal.add_argument("--key-id", default=None)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "subscription-create":
        subscription = FederationSubscription(
            subscription_id=args.subscription_id,
            producer_instance_id=args.producer_instance_id,
            scope_ids=args.scope_id,
            record_kinds=args.record_kind,
            change_kinds=args.change_kind or ["upsert", "state"],
            maximum_release_level=args.maximum_release_level,
            purpose=args.purpose,
            realm_id=args.realm_id,
            audience=args.audience,
            principal_id=args.principal_id,
            trusted_instance_ids=args.trusted_instance_id,
            auto_accept=args.auto_accept,
            allowed_restriction_markers=args.allowed_restriction_marker,
            allowed_compartments=args.allowed_compartment,
        )
        save_subscription(args.path, subscription)
        print(subscription.model_dump_json(indent=2))
    elif args.command == "export":
        bundle = build_incremental_change_bundle(
            args.store_dir,
            load_subscription(args.subscription_path),
            signing_key=Path(args.key_file).read_bytes(),
            key_id=args.key_id,
            signature_algorithm=args.signature_algorithm,
            policy_plugins_path=args.policy_plugins,
            requester_id=args.requester_id,
            out_path=args.out_path,
        )
        print(bundle.model_dump_json(indent=2))
    elif args.command == "import":
        result = import_incremental_change_bundle_to_quarantine(
            args.bundle_path,
            args.quarantine_dir,
            verification_key=Path(args.key_file).read_bytes(),
            subscription=load_subscription(args.subscription_path),
            key_id=args.key_id,
            policy_plugins_path=args.policy_plugins,
            requester_id=args.requester_id,
        )
        print(result.model_dump_json(indent=2))
    else:
        if args.command == "personal-sync":
            from .personal_sync import sync_personal_change_bundle
            result = sync_personal_change_bundle(
                args.bundle_path,
                args.store_dir,
                args.quarantine_dir,
                verification_key=Path(args.key_file).read_bytes(),
                subscription=load_subscription(args.subscription_path),
                key_id=args.key_id,
                subscription_path=args.subscription_path,
            )
            print(result.model_dump_json(indent=2))
            return
        print(acknowledge_change_bundle(
            args.subscription_path,
            args.bundle_path,
            verification_key=Path(args.key_file).read_bytes() if args.key_file else None,
            key_id=args.key_id,
        ).model_dump_json(indent=2))
