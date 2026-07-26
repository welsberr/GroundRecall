from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import hmac
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Literal

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from pydantic import BaseModel, Field

from .export_guardrails import _secret_field_path
from .models import GroundRecallSnapshot
from .store import GroundRecallStore


ReleaseLevel = Literal["public", "internal", "confidential", "privileged", "private"]
ProvenanceVisibility = Literal["full", "partial", "redacted", "hidden"]
ImportDecision = Literal["quarantined", "rejected"]
FederationAction = Literal["export", "import", "promote"]
FederationSignatureAlgorithm = Literal["hmac-sha256", "ed25519"]

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
    algorithm: FederationSignatureAlgorithm = "hmac-sha256"
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


class FederationPolicyGrant(BaseModel):
    subject_id: str
    actions: list[FederationAction] = Field(default_factory=list)
    release_levels: list[ReleaseLevel] = Field(default_factory=list)
    instance_ids: list[str] = Field(default_factory=lambda: ["*"])
    scopes: list[str] = Field(default_factory=list)
    allow_privileged: bool = False


class FederationLocalPolicy(BaseModel):
    policy_id: str = "groundrecall.local_federation_policy.v1"
    grants: list[FederationPolicyGrant] = Field(default_factory=list)


class FederationRoleDefinition(BaseModel):
    role_id: str
    actions: list[FederationAction] = Field(default_factory=list)
    release_levels: list[ReleaseLevel] = Field(default_factory=list)
    instance_ids: list[str] = Field(default_factory=lambda: ["*"])
    scopes: list[str] = Field(default_factory=list)
    allow_privileged: bool = False


class FederationRoleMembership(BaseModel):
    subject_id: str
    role_ids: list[str] = Field(default_factory=list)


class FederationRoleDirectory(BaseModel):
    directory_id: str = "groundrecall.federation_role_directory.v1"
    roles: list[FederationRoleDefinition] = Field(default_factory=list)
    memberships: list[FederationRoleMembership] = Field(default_factory=list)


class FederationRoleDirectoryPublicationManifest(BaseModel):
    directory_kind: str = "groundrecall_federation_role_directory_publication"
    schema_version: str = "groundrecall.federation_role_directory_publication.v1"
    publication_id: str
    created_at: str
    producer_instance_id: str
    signer_key_id: str
    role_count: int
    membership_count: int
    content_hash: str
    signature: FederationSignature | None = None


class FederationRoleDirectoryPublication(BaseModel):
    manifest: FederationRoleDirectoryPublicationManifest
    directory: FederationRoleDirectory


class FederationTrustKey(BaseModel):
    instance_id: str
    key_id: str
    key_material: str
    algorithm: FederationSignatureAlgorithm = "hmac-sha256"
    active: bool = True
    created_at: str = ""
    expires_at: str = ""
    revoked_at: str = ""
    revocation_reason: str = ""
    superseded_by_key_id: str = ""
    release_levels: list[ReleaseLevel] = Field(default_factory=lambda: ["public"])
    trusted_actions: list[FederationAction] = Field(default_factory=lambda: ["import", "promote"])


class FederationTrustKeyMetadata(BaseModel):
    instance_id: str
    key_id: str
    algorithm: FederationSignatureAlgorithm = "hmac-sha256"
    active: bool = True
    created_at: str = ""
    expires_at: str = ""
    revoked_at: str = ""
    revocation_reason: str = ""
    superseded_by_key_id: str = ""
    release_levels: list[ReleaseLevel] = Field(default_factory=lambda: ["public"])
    trusted_actions: list[FederationAction] = Field(default_factory=lambda: ["import", "promote"])
    key_material_redacted: bool = True
    key_fingerprint: str = ""


class FederationTrustRegistry(BaseModel):
    registry_id: str = "groundrecall.local_federation_trust_registry.v1"
    keys: list[FederationTrustKey] = Field(default_factory=list)


class FederationTrustRegistryMetadata(BaseModel):
    registry_id: str = "groundrecall.federation_trust_metadata.v1"
    source_registry_id: str = ""
    exported_at: str
    keys: list[FederationTrustKeyMetadata] = Field(default_factory=list)


class FederationPublicKeyEntry(BaseModel):
    instance_id: str
    key_id: str
    public_key_pem: str
    algorithm: Literal["ed25519"] = "ed25519"
    active: bool = True
    created_at: str = ""
    expires_at: str = ""
    revoked_at: str = ""
    revocation_reason: str = ""
    superseded_by_key_id: str = ""
    release_levels: list[ReleaseLevel] = Field(default_factory=lambda: ["public"])
    trusted_actions: list[FederationAction] = Field(default_factory=lambda: ["import", "promote"])


class FederationPublicKeySetManifest(BaseModel):
    keyset_kind: str = "groundrecall_federation_public_keyset"
    schema_version: str = "groundrecall.federation_public_keyset.v1"
    keyset_id: str
    created_at: str
    producer_instance_id: str
    signer_key_id: str
    key_count: int
    content_hash: str
    signature: FederationSignature | None = None


class FederationPublicKeySet(BaseModel):
    manifest: FederationPublicKeySetManifest
    keys: list[FederationPublicKeyEntry] = Field(default_factory=list)


class FederationPolicyDecision(BaseModel):
    allowed: bool
    policy_id: str
    subject_id: str
    action: FederationAction
    release_level: ReleaseLevel
    instance_id: str = ""
    scope_id: str = ""
    reasons: list[str] = Field(default_factory=list)
    grant_index: int | None = None


class FederationAuditEvent(BaseModel):
    event_kind: str = "groundrecall_federation_audit_event"
    schema_version: str = "groundrecall.federation_audit.v1"
    event_id: str
    recorded_at: str
    action: FederationAction
    decision: str
    subject_id: str
    release_level: ReleaseLevel
    bundle_id: str = ""
    instance_id: str = ""
    scope_id: str = ""
    policy_id: str = ""
    reasons: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class FederationQuarantineSummary(BaseModel):
    bundle_id: str
    quarantine_path: str
    producer_instance_id: str
    target_release_level: ReleaseLevel
    record_count: int
    created_at: str
    content_hash: str


class FederationPromotionPlan(BaseModel):
    bundle_id: str
    source_path: str
    target_store_dir: str
    target_release_level: ReleaseLevel
    origin_instance_id: str
    apply: bool = False
    promotable_counts: dict[str, int] = Field(default_factory=dict)
    unchanged_counts: dict[str, int] = Field(default_factory=dict)
    conflict_counts: dict[str, int] = Field(default_factory=dict)
    conflicts: list[dict[str, str]] = Field(default_factory=list)


class FederationPromotionResult(BaseModel):
    decision: Literal["planned", "promoted", "rejected"]
    plan: FederationPromotionPlan
    reasons: list[str] = Field(default_factory=list)


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_federation_time(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = value.strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise FederationPolicyError(f"invalid federation timestamp: {value}") from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def load_federation_policy(path: str | Path) -> FederationLocalPolicy:
    return FederationLocalPolicy.model_validate_json(Path(path).read_text(encoding="utf-8"))


def save_federation_policy(path: str | Path, policy: FederationLocalPolicy) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(policy.model_dump_json(indent=2) + "\n", encoding="utf-8")


def load_federation_role_directory(path: str | Path) -> FederationRoleDirectory:
    return FederationRoleDirectory.model_validate_json(Path(path).read_text(encoding="utf-8"))


def save_federation_role_directory(path: str | Path, directory: FederationRoleDirectory) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(directory.model_dump_json(indent=2) + "\n", encoding="utf-8")


def compile_federation_role_directory_to_policy(
    directory: FederationRoleDirectory,
    *,
    policy_id: str | None = None,
) -> FederationLocalPolicy:
    roles = {role.role_id: role for role in directory.roles}
    grants: list[FederationPolicyGrant] = []
    for membership in directory.memberships:
        if not membership.subject_id:
            raise FederationPolicyError("role directory membership is missing subject_id")
        for role_id in membership.role_ids:
            role = roles.get(role_id)
            if role is None:
                raise FederationPolicyError(f"role directory membership references unknown role: {role_id}")
            grants.append(
                FederationPolicyGrant(
                    subject_id=membership.subject_id,
                    actions=role.actions,
                    release_levels=role.release_levels,
                    instance_ids=role.instance_ids,
                    scopes=role.scopes,
                    allow_privileged=role.allow_privileged,
                )
            )
    return FederationLocalPolicy(
        policy_id=policy_id or f"compiled::{directory.directory_id}",
        grants=grants,
    )


def export_federation_role_directory_publication(
    directory: FederationRoleDirectory,
    out_path: str | Path,
    *,
    producer_instance_id: str,
    signing_key: str | bytes,
    signer_key_id: str,
    created_at: str | None = None,
) -> FederationRoleDirectoryPublication:
    timestamp = created_at or now_utc()
    content_hash = _content_hash_for_role_directory(directory)
    manifest = FederationRoleDirectoryPublicationManifest(
        publication_id=f"federation-role-directory::{producer_instance_id}::{content_hash[:12]}",
        created_at=timestamp,
        producer_instance_id=producer_instance_id,
        signer_key_id=signer_key_id,
        role_count=len(directory.roles),
        membership_count=len(directory.memberships),
        content_hash=content_hash,
    )
    unsigned = FederationRoleDirectoryPublication(manifest=manifest, directory=directory)
    signed_manifest = manifest.model_copy(
        update={
            "signature": FederationSignature(
                algorithm="ed25519",
                key_id=signer_key_id,
                value=_signature_for_payload(unsigned.model_dump(mode="json"), signing_key, algorithm="ed25519"),
            )
        }
    )
    publication = unsigned.model_copy(update={"manifest": signed_manifest})
    target = Path(out_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(publication.model_dump(mode="json"), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return publication


def verify_federation_role_directory_publication(
    publication: FederationRoleDirectoryPublication | dict[str, Any],
    *,
    verification_key: str | bytes,
    signer_key_id: str | None = None,
) -> FederationRoleDirectoryPublication:
    parsed = publication if isinstance(publication, FederationRoleDirectoryPublication) else FederationRoleDirectoryPublication.model_validate(publication)
    signature = parsed.manifest.signature
    if signature is None:
        raise FederationPolicyError("federation role directory publication is unsigned")
    if signature.algorithm != "ed25519":
        raise FederationPolicyError(f"unsupported role directory publication signature algorithm: {signature.algorithm}")
    if signer_key_id is not None and signature.key_id != signer_key_id:
        raise FederationPolicyError(f"unexpected federation role directory signer key_id: {signature.key_id}")
    unsigned_manifest = parsed.manifest.model_copy(update={"signature": None})
    unsigned_publication = parsed.model_copy(update={"manifest": unsigned_manifest})
    if not _verify_signature_for_payload(
        unsigned_publication.model_dump(mode="json"),
        verification_key,
        algorithm="ed25519",
        signature_value=signature.value,
    ):
        raise FederationPolicyError("federation role directory publication signature verification failed")
    if parsed.manifest.role_count != len(parsed.directory.roles):
        raise FederationPolicyError("federation role directory role count verification failed")
    if parsed.manifest.membership_count != len(parsed.directory.memberships):
        raise FederationPolicyError("federation role directory membership count verification failed")
    if parsed.manifest.content_hash != _content_hash_for_role_directory(parsed.directory):
        raise FederationPolicyError("federation role directory content hash verification failed")
    return parsed


def import_federation_role_directory_publication_to_policy(
    publication: FederationRoleDirectoryPublication | dict[str, Any],
    *,
    verification_key: str | bytes,
    signer_key_id: str | None = None,
    policy_id: str | None = None,
    allowed_subject_ids: list[str] | None = None,
    allowed_role_ids: list[str] | None = None,
    allowed_instance_ids: list[str] | None = None,
    allowed_release_levels: list[ReleaseLevel] | None = None,
    allowed_actions: list[FederationAction] | None = None,
    allowed_scopes: list[str] | None = None,
) -> FederationLocalPolicy:
    parsed = verify_federation_role_directory_publication(publication, verification_key=verification_key, signer_key_id=signer_key_id)
    scoped_directory = filter_federation_role_directory(
        parsed.directory,
        allowed_subject_ids=allowed_subject_ids,
        allowed_role_ids=allowed_role_ids,
        allowed_instance_ids=allowed_instance_ids or [parsed.manifest.producer_instance_id],
        allowed_release_levels=allowed_release_levels or ["public"],
        allowed_actions=allowed_actions or ["import", "promote"],
        allowed_scopes=allowed_scopes,
    )
    return compile_federation_role_directory_to_policy(scoped_directory, policy_id=policy_id or f"compiled::{parsed.manifest.publication_id}")


def filter_federation_role_directory(
    directory: FederationRoleDirectory,
    *,
    allowed_subject_ids: list[str] | None = None,
    allowed_role_ids: list[str] | None = None,
    allowed_instance_ids: list[str] | None = None,
    allowed_release_levels: list[ReleaseLevel] | None = None,
    allowed_actions: list[FederationAction] | None = None,
    allowed_scopes: list[str] | None = None,
) -> FederationRoleDirectory:
    subject_allow = set(allowed_subject_ids or [])
    role_allow = set(allowed_role_ids or [])
    instance_allow = set(allowed_instance_ids or [])
    release_allow = set(allowed_release_levels or [])
    action_allow = set(allowed_actions or [])
    scope_allow = set(allowed_scopes or [])
    roles: list[FederationRoleDefinition] = []
    retained_role_ids: set[str] = set()
    for role in directory.roles:
        if role_allow and role.role_id not in role_allow:
            continue
        actions = [action for action in role.actions if not action_allow or action in action_allow]
        release_levels = [level for level in role.release_levels if not release_allow or level in release_allow]
        if instance_allow:
            instance_ids = [instance_id for instance_id in role.instance_ids if instance_id in instance_allow]
            if "*" in role.instance_ids:
                instance_ids = sorted(instance_allow)
        else:
            instance_ids = list(role.instance_ids)
        if scope_allow:
            scopes = [scope for scope in role.scopes if scope in scope_allow]
            if not role.scopes:
                scopes = sorted(scope_allow)
        else:
            scopes = list(role.scopes)
        if not actions or not release_levels or not instance_ids:
            continue
        if scope_allow and not scopes:
            continue
        allow_privileged = role.allow_privileged and "privileged" in release_levels
        roles.append(
            FederationRoleDefinition(
                role_id=role.role_id,
                actions=actions,
                release_levels=release_levels,
                instance_ids=instance_ids,
                scopes=scopes,
                allow_privileged=allow_privileged,
            )
        )
        retained_role_ids.add(role.role_id)
    memberships = [
        FederationRoleMembership(
            subject_id=membership.subject_id,
            role_ids=[role_id for role_id in membership.role_ids if role_id in retained_role_ids],
        )
        for membership in directory.memberships
        if (not subject_allow or membership.subject_id in subject_allow)
    ]
    memberships = [membership for membership in memberships if membership.role_ids]
    return FederationRoleDirectory(
        directory_id=f"filtered::{directory.directory_id}",
        roles=roles,
        memberships=memberships,
    )


def load_federation_trust_registry(path: str | Path) -> FederationTrustRegistry:
    return FederationTrustRegistry.model_validate_json(Path(path).read_text(encoding="utf-8"))


def save_federation_trust_registry(path: str | Path, registry: FederationTrustRegistry) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(registry.model_dump_json(indent=2) + "\n", encoding="utf-8")


def federation_key_fingerprint(key_material: str) -> str:
    return "sha256:" + hashlib.sha256(key_material.encode("utf-8")).hexdigest()


def export_federation_trust_metadata(
    registry: FederationTrustRegistry,
    *,
    exported_at: str | None = None,
    include_key_fingerprints: bool = False,
) -> FederationTrustRegistryMetadata:
    keys = [
        FederationTrustKeyMetadata(
            instance_id=key.instance_id,
            key_id=key.key_id,
            algorithm=key.algorithm,
            active=key.active,
            created_at=key.created_at,
            expires_at=key.expires_at,
            revoked_at=key.revoked_at,
            revocation_reason=key.revocation_reason,
            superseded_by_key_id=key.superseded_by_key_id,
            release_levels=key.release_levels,
            trusted_actions=key.trusted_actions,
            key_fingerprint=federation_key_fingerprint(key.key_material) if include_key_fingerprints else "",
        )
        for key in registry.keys
    ]
    return FederationTrustRegistryMetadata(
        source_registry_id=registry.registry_id,
        exported_at=exported_at or now_utc(),
        keys=keys,
    )


def save_federation_trust_metadata(path: str | Path, metadata: FederationTrustRegistryMetadata) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(metadata.model_dump_json(indent=2) + "\n", encoding="utf-8")


def add_federation_trust_key(
    registry: FederationTrustRegistry,
    *,
    instance_id: str,
    key_id: str,
    key_material: str,
    release_levels: list[ReleaseLevel],
    trusted_actions: list[FederationAction],
    algorithm: FederationSignatureAlgorithm = "hmac-sha256",
    active: bool = True,
    created_at: str | None = None,
    expires_at: str = "",
    revoked_at: str = "",
    revocation_reason: str = "",
    superseded_by_key_id: str = "",
) -> FederationTrustRegistry:
    keys = [key for key in registry.keys if not (key.instance_id == instance_id and key.key_id == key_id)]
    keys.append(
        FederationTrustKey(
            instance_id=instance_id,
            key_id=key_id,
            key_material=key_material,
            algorithm=algorithm,
            active=active,
            created_at=created_at or now_utc(),
            expires_at=expires_at,
            revoked_at=revoked_at,
            revocation_reason=revocation_reason,
            superseded_by_key_id=superseded_by_key_id,
            release_levels=release_levels,
            trusted_actions=trusted_actions,
        )
    )
    return registry.model_copy(update={"keys": keys})


def export_federation_public_keyset(
    registry: FederationTrustRegistry,
    out_path: str | Path,
    *,
    producer_instance_id: str,
    signing_key: str | bytes,
    signer_key_id: str,
    created_at: str | None = None,
    active_only: bool = False,
) -> FederationPublicKeySet:
    keys = [
        FederationPublicKeyEntry(
            instance_id=key.instance_id,
            key_id=key.key_id,
            public_key_pem=key.key_material,
            active=key.active,
            created_at=key.created_at,
            expires_at=key.expires_at,
            revoked_at=key.revoked_at,
            revocation_reason=key.revocation_reason,
            superseded_by_key_id=key.superseded_by_key_id,
            release_levels=key.release_levels,
            trusted_actions=key.trusted_actions,
        )
        for key in registry.keys
        if key.algorithm == "ed25519" and (key.active or not active_only)
    ]
    timestamp = created_at or now_utc()
    content_hash = _content_hash_for_public_key_entries(keys)
    manifest = FederationPublicKeySetManifest(
        keyset_id=f"federation-keyset::{producer_instance_id}::{content_hash[:12]}",
        created_at=timestamp,
        producer_instance_id=producer_instance_id,
        signer_key_id=signer_key_id,
        key_count=len(keys),
        content_hash=content_hash,
    )
    unsigned = FederationPublicKeySet(manifest=manifest, keys=keys)
    signed_manifest = manifest.model_copy(
        update={
            "signature": FederationSignature(
                algorithm="ed25519",
                key_id=signer_key_id,
                value=_signature_for_payload(unsigned.model_dump(mode="json"), signing_key, algorithm="ed25519"),
            )
        }
    )
    keyset = unsigned.model_copy(update={"manifest": signed_manifest})
    target = Path(out_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(keyset.model_dump(mode="json"), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return keyset


def verify_federation_public_keyset(
    keyset: FederationPublicKeySet | dict[str, Any],
    *,
    verification_key: str | bytes,
    signer_key_id: str | None = None,
) -> FederationPublicKeySet:
    parsed = keyset if isinstance(keyset, FederationPublicKeySet) else FederationPublicKeySet.model_validate(keyset)
    signature = parsed.manifest.signature
    if signature is None:
        raise FederationPolicyError("federation public keyset is unsigned")
    if signature.algorithm != "ed25519":
        raise FederationPolicyError(f"unsupported public keyset signature algorithm: {signature.algorithm}")
    if signer_key_id is not None and signature.key_id != signer_key_id:
        raise FederationPolicyError(f"unexpected federation public keyset signer key_id: {signature.key_id}")
    unsigned_manifest = parsed.manifest.model_copy(update={"signature": None})
    unsigned_keyset = parsed.model_copy(update={"manifest": unsigned_manifest})
    if not _verify_signature_for_payload(
        unsigned_keyset.model_dump(mode="json"),
        verification_key,
        algorithm="ed25519",
        signature_value=signature.value,
    ):
        raise FederationPolicyError("federation public keyset signature verification failed")
    if parsed.manifest.key_count != len(parsed.keys):
        raise FederationPolicyError("federation public keyset key count verification failed")
    if parsed.manifest.content_hash != _content_hash_for_public_key_entries(parsed.keys):
        raise FederationPolicyError("federation public keyset content hash verification failed")
    return parsed


def import_federation_public_keyset_to_trust_registry(
    keyset: FederationPublicKeySet | dict[str, Any],
    registry: FederationTrustRegistry,
    *,
    verification_key: str | bytes,
    signer_key_id: str | None = None,
    allowed_instance_ids: list[str] | None = None,
    allowed_release_levels: list[ReleaseLevel] | None = None,
    allowed_trusted_actions: list[FederationAction] | None = None,
) -> FederationTrustRegistry:
    parsed = verify_federation_public_keyset(keyset, verification_key=verification_key, signer_key_id=signer_key_id)
    instance_allow = set(allowed_instance_ids or [parsed.manifest.producer_instance_id])
    release_allow = set(allowed_release_levels or ["public"])
    action_allow = set(allowed_trusted_actions or ["import", "promote"])
    updated = registry
    for key in parsed.keys:
        if key.instance_id not in instance_allow:
            continue
        release_levels = [level for level in key.release_levels if level in release_allow]
        trusted_actions = [action for action in key.trusted_actions if action in action_allow]
        if not release_levels or not trusted_actions:
            continue
        updated = add_federation_trust_key(
            updated,
            instance_id=key.instance_id,
            key_id=key.key_id,
            key_material=key.public_key_pem,
            algorithm="ed25519",
            release_levels=release_levels,
            trusted_actions=trusted_actions,
            active=key.active,
            created_at=key.created_at,
            expires_at=key.expires_at,
            revoked_at=key.revoked_at,
            revocation_reason=key.revocation_reason,
            superseded_by_key_id=key.superseded_by_key_id,
        )
    return updated


def revoke_federation_trust_key(
    registry: FederationTrustRegistry,
    *,
    instance_id: str,
    key_id: str,
    revoked_at: str | None = None,
    reason: str = "",
    superseded_by_key_id: str = "",
) -> FederationTrustRegistry:
    updated: list[FederationTrustKey] = []
    found = False
    for key in registry.keys:
        if key.instance_id == instance_id and key.key_id == key_id:
            found = True
            updated.append(
                key.model_copy(
                    update={
                        "active": False,
                        "revoked_at": revoked_at or now_utc(),
                        "revocation_reason": reason,
                        "superseded_by_key_id": superseded_by_key_id,
                    }
                )
            )
        else:
            updated.append(key)
    if not found:
        raise FederationPolicyError(f"no trusted key for instance {instance_id} key {key_id}")
    return registry.model_copy(update={"keys": updated})


def resolve_trust_key(
    registry: FederationTrustRegistry,
    *,
    instance_id: str,
    key_id: str,
    release_level: ReleaseLevel,
    action: FederationAction,
    algorithm: FederationSignatureAlgorithm | None = None,
    as_of: str | datetime | None = None,
) -> bytes:
    matches = [key for key in registry.keys if key.instance_id == instance_id and key.key_id == key_id]
    if not matches:
        raise FederationPolicyError(f"no trusted key for instance {instance_id} key {key_id}")
    key = matches[-1]
    if key.revoked_at:
        raise FederationPolicyError(f"trusted key is revoked: {instance_id}:{key_id}")
    if not key.active:
        raise FederationPolicyError(f"trusted key is inactive: {instance_id}:{key_id}")
    expires_at = parse_federation_time(key.expires_at)
    if expires_at is not None:
        check_time = parse_federation_time(as_of) or datetime.now(timezone.utc)
        if expires_at <= check_time:
            raise FederationPolicyError(f"trusted key is expired: {instance_id}:{key_id}")
    if algorithm is not None and key.algorithm != algorithm:
        raise FederationPolicyError(f"trusted key algorithm mismatch: expected {algorithm} got {key.algorithm}")
    if key.algorithm not in ("hmac-sha256", "ed25519"):
        raise FederationPolicyError(f"unsupported trusted key algorithm: {key.algorithm}")
    if release_level not in key.release_levels:
        raise FederationPolicyError(f"trusted key does not allow release level: {release_level}")
    if action not in key.trusted_actions:
        raise FederationPolicyError(f"trusted key does not allow action: {action}")
    return key.key_material.encode("utf-8")


def evaluate_federation_policy(
    policy: FederationLocalPolicy,
    *,
    subject_id: str,
    action: FederationAction,
    release_level: ReleaseLevel,
    instance_id: str = "",
    scope_id: str = "",
) -> FederationPolicyDecision:
    if not subject_id:
        return FederationPolicyDecision(
            allowed=False,
            policy_id=policy.policy_id,
            subject_id=subject_id,
            action=action,
            release_level=release_level,
            instance_id=instance_id,
            scope_id=scope_id,
            reasons=["missing_subject_id"],
        )
    for index, grant in enumerate(policy.grants):
        if grant.subject_id != subject_id:
            continue
        if action not in grant.actions:
            continue
        if release_level not in grant.release_levels:
            continue
        if release_level == "privileged" and not grant.allow_privileged:
            continue
        if "*" not in grant.instance_ids and instance_id and instance_id not in grant.instance_ids:
            continue
        if grant.scopes and scope_id not in grant.scopes:
            continue
        return FederationPolicyDecision(
            allowed=True,
            policy_id=policy.policy_id,
            subject_id=subject_id,
            action=action,
            release_level=release_level,
            instance_id=instance_id,
            scope_id=scope_id,
            grant_index=index,
        )
    return FederationPolicyDecision(
        allowed=False,
        policy_id=policy.policy_id,
        subject_id=subject_id,
        action=action,
        release_level=release_level,
        instance_id=instance_id,
        scope_id=scope_id,
        reasons=["no_matching_federation_grant"],
    )


def append_federation_audit_event(path: str | Path, event: FederationAuditEvent) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event.model_dump(mode="json"), sort_keys=True) + "\n")


def build_federation_audit_event(
    *,
    action: FederationAction,
    decision: str,
    subject_id: str,
    release_level: ReleaseLevel,
    bundle_id: str = "",
    instance_id: str = "",
    policy_decision: FederationPolicyDecision | None = None,
    reasons: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> FederationAuditEvent:
    basis = f"{action}:{decision}:{subject_id}:{release_level}:{bundle_id}:{instance_id}:{now_utc()}"
    return FederationAuditEvent(
        event_id=f"federation-audit::{hashlib.sha256(basis.encode('utf-8')).hexdigest()[:16]}",
        recorded_at=now_utc(),
        action=action,
        decision=decision,
        subject_id=subject_id,
        release_level=release_level,
        bundle_id=bundle_id,
        instance_id=instance_id,
        scope_id=policy_decision.scope_id if policy_decision is not None else "",
        policy_id=policy_decision.policy_id if policy_decision is not None else "",
        reasons=list(reasons if reasons is not None else (policy_decision.reasons if policy_decision is not None else [])),
        metadata=metadata or {},
    )


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
    signature_algorithm: FederationSignatureAlgorithm = "hmac-sha256",
    owner_instance_id: str = "",
    snapshot_id: str | None = None,
    created_at: str | None = None,
    allow_unclassified_public: bool = False,
    allow_privileged: bool = False,
    policy: FederationLocalPolicy | None = None,
    requester_id: str = "",
    scope_id: str = "",
    audit_log_path: str | Path | None = None,
) -> FederationBundle:
    if target_release_level == "private":
        raise FederationPolicyError("private is local-only and cannot be used as a federation target")
    if target_release_level == "privileged" and not allow_privileged:
        raise FederationPolicyError("privileged federation requires allow_privileged=True")
    policy_decision = None
    if policy is not None:
        policy_decision = evaluate_federation_policy(
            policy,
            subject_id=requester_id,
            action="export",
            release_level=target_release_level,
            instance_id=producer_instance_id,
            scope_id=scope_id,
        )
        if not policy_decision.allowed:
            if audit_log_path is not None:
                append_federation_audit_event(
                    audit_log_path,
                    build_federation_audit_event(
                        action="export",
                        decision="rejected",
                        subject_id=requester_id,
                        release_level=target_release_level,
                        instance_id=producer_instance_id,
                        policy_decision=policy_decision,
                    ),
                )
            raise FederationPolicyError(";".join(policy_decision.reasons))

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
                algorithm=signature_algorithm,
                key_id=key_id,
                value=_signature_for_payload(unsigned.model_dump(mode="json"), signing_key, algorithm=signature_algorithm),
            )
        }
    )
    bundle = unsigned.model_copy(update={"manifest": signed_manifest})
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(bundle.model_dump(mode="json"), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if audit_log_path is not None:
        append_federation_audit_event(
            audit_log_path,
            build_federation_audit_event(
                action="export",
                decision="exported",
                subject_id=requester_id,
                release_level=target_release_level,
                bundle_id=bundle.manifest.bundle_id,
                instance_id=producer_instance_id,
                policy_decision=policy_decision,
                metadata={"record_count": bundle.manifest.record_count, "excluded_total": bundle.policy_report.excluded_total},
            ),
        )
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
    if not _verify_signature_for_payload(
        unsigned_bundle.model_dump(mode="json"),
        signing_key,
        algorithm=signature.algorithm,
        signature_value=signature.value,
    ):
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
    policy: FederationLocalPolicy | None = None,
    requester_id: str = "",
    scope_id: str = "",
    audit_log_path: str | Path | None = None,
) -> FederationImportResult:
    payload = json.loads(Path(bundle_path).read_text(encoding="utf-8"))
    bundle = verify_federation_bundle(payload, signing_key=signing_key, key_id=key_id)
    accepted = set(accepted_release_levels)
    reasons: list[str] = []
    policy_decision = None
    if policy is not None:
        policy_decision = evaluate_federation_policy(
            policy,
            subject_id=requester_id,
            action="import",
            release_level=bundle.manifest.target_release_level,
            instance_id=bundle.manifest.producer_instance_id,
            scope_id=scope_id,
        )
        if not policy_decision.allowed:
            reasons.extend(policy_decision.reasons)
    if bundle.manifest.target_release_level not in accepted:
        reasons.append(f"target_release_level_not_accepted:{bundle.manifest.target_release_level}")
    for finding in _bundle_policy_violations(bundle):
        reasons.append(finding)
    if reasons:
        result = FederationImportResult(
            decision="rejected",
            bundle_id=bundle.manifest.bundle_id,
            reasons=reasons,
            record_count=bundle.manifest.record_count,
            origin_instance_id=bundle.manifest.producer_instance_id,
            target_release_level=bundle.manifest.target_release_level,
        )
        if audit_log_path is not None:
            append_federation_audit_event(
                audit_log_path,
                build_federation_audit_event(
                    action="import",
                    decision="rejected",
                    subject_id=requester_id,
                    release_level=bundle.manifest.target_release_level,
                    bundle_id=bundle.manifest.bundle_id,
                    instance_id=bundle.manifest.producer_instance_id,
                    policy_decision=policy_decision,
                    reasons=reasons,
                    metadata={"record_count": bundle.manifest.record_count},
                ),
            )
        return result

    target = Path(quarantine_dir) / f"{bundle.manifest.bundle_id}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(bundle.model_dump(mode="json"), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    result = FederationImportResult(
        decision="quarantined",
        bundle_id=bundle.manifest.bundle_id,
        quarantine_path=str(target),
        record_count=bundle.manifest.record_count,
        origin_instance_id=bundle.manifest.producer_instance_id,
        target_release_level=bundle.manifest.target_release_level,
    )
    if audit_log_path is not None:
        append_federation_audit_event(
            audit_log_path,
            build_federation_audit_event(
                action="import",
                decision="quarantined",
                subject_id=requester_id,
                release_level=bundle.manifest.target_release_level,
                bundle_id=bundle.manifest.bundle_id,
                instance_id=bundle.manifest.producer_instance_id,
                policy_decision=policy_decision,
                metadata={"record_count": bundle.manifest.record_count, "quarantine_path": str(target)},
            ),
        )
    return result


def list_quarantine_bundles(quarantine_dir: str | Path) -> list[FederationQuarantineSummary]:
    summaries: list[FederationQuarantineSummary] = []
    for path in sorted(Path(quarantine_dir).glob("*.json")):
        bundle = FederationBundle.model_validate_json(path.read_text(encoding="utf-8"))
        summaries.append(
            FederationQuarantineSummary(
                bundle_id=bundle.manifest.bundle_id,
                quarantine_path=str(path),
                producer_instance_id=bundle.manifest.producer_instance_id,
                target_release_level=bundle.manifest.target_release_level,
                record_count=bundle.manifest.record_count,
                created_at=bundle.manifest.created_at,
                content_hash=bundle.manifest.content_hash,
            )
        )
    return summaries


def plan_quarantine_promotion(
    bundle_path: str | Path,
    store_dir: str | Path,
    *,
    signing_key: str | bytes,
    key_id: str | None = None,
    accepted_release_levels: Iterable[ReleaseLevel] = ("public",),
) -> FederationPromotionPlan:
    bundle = verify_federation_bundle(json.loads(Path(bundle_path).read_text(encoding="utf-8")), signing_key=signing_key, key_id=key_id)
    accepted = set(accepted_release_levels)
    store = GroundRecallStore(store_dir)
    promotable_counts: dict[str, int] = {}
    unchanged_counts: dict[str, int] = {}
    conflict_counts: dict[str, int] = {}
    conflicts: list[dict[str, str]] = []
    if bundle.manifest.target_release_level not in accepted:
        conflicts.append(
            {
                "record_kind": "bundle",
                "record_id": bundle.manifest.bundle_id,
                "reason": f"target_release_level_not_accepted:{bundle.manifest.target_release_level}",
            }
        )
        conflict_counts["bundle"] = 1
    for collection in _promotion_collections(bundle, store):
        _accumulate_promotion_collection(
            collection["record_kind"],
            collection["incoming"],
            collection["id_field"],
            collection["get_existing"],
            promotable_counts,
            unchanged_counts,
            conflict_counts,
            conflicts,
        )
    return FederationPromotionPlan(
        bundle_id=bundle.manifest.bundle_id,
        source_path=str(bundle_path),
        target_store_dir=str(store.base_dir),
        target_release_level=bundle.manifest.target_release_level,
        origin_instance_id=bundle.manifest.producer_instance_id,
        promotable_counts=promotable_counts,
        unchanged_counts=unchanged_counts,
        conflict_counts=conflict_counts,
        conflicts=conflicts,
    )


def promote_quarantined_bundle(
    bundle_path: str | Path,
    store_dir: str | Path,
    *,
    signing_key: str | bytes,
    key_id: str | None = None,
    accepted_release_levels: Iterable[ReleaseLevel] = ("public",),
    policy: FederationLocalPolicy | None = None,
    requester_id: str = "",
    scope_id: str = "",
    audit_log_path: str | Path | None = None,
    apply: bool = False,
) -> FederationPromotionResult:
    bundle = verify_federation_bundle(json.loads(Path(bundle_path).read_text(encoding="utf-8")), signing_key=signing_key, key_id=key_id)
    policy_decision = None
    if policy is not None:
        policy_decision = evaluate_federation_policy(
            policy,
            subject_id=requester_id,
            action="promote",
            release_level=bundle.manifest.target_release_level,
            instance_id=bundle.manifest.producer_instance_id,
            scope_id=scope_id,
        )
        if not policy_decision.allowed:
            plan = plan_quarantine_promotion(
                bundle_path,
                store_dir,
                signing_key=signing_key,
                key_id=key_id,
                accepted_release_levels=accepted_release_levels,
            )
            result = FederationPromotionResult(decision="rejected", plan=plan, reasons=policy_decision.reasons)
            _audit_promotion(audit_log_path, result, requester_id, bundle, policy_decision)
            return result

    plan = plan_quarantine_promotion(
        bundle_path,
        store_dir,
        signing_key=signing_key,
        key_id=key_id,
        accepted_release_levels=accepted_release_levels,
    )
    if plan.conflicts:
        result = FederationPromotionResult(decision="rejected", plan=plan, reasons=["promotion_conflicts"])
        _audit_promotion(audit_log_path, result, requester_id, bundle, policy_decision)
        return result
    if not apply:
        result = FederationPromotionResult(decision="planned", plan=plan)
        _audit_promotion(audit_log_path, result, requester_id, bundle, policy_decision)
        return result

    store = GroundRecallStore(store_dir)
    for collection in _promotion_collections(bundle, store):
        for record in collection["incoming"]:
            existing = collection["get_existing"](getattr(record, collection["id_field"]))
            if existing is None:
                collection["save"](record)
    result = FederationPromotionResult(decision="promoted", plan=plan.model_copy(update={"apply": True}))
    _audit_promotion(audit_log_path, result, requester_id, bundle, policy_decision)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export or import GroundRecall federation bundles.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    export_parser = subparsers.add_parser("export", help="Write a signed federation bundle from a local store.")
    export_parser.add_argument("store_dir")
    export_parser.add_argument("out_path")
    export_parser.add_argument("--target-release-level", required=True, choices=["public", "internal", "confidential", "privileged"])
    export_parser.add_argument("--producer-instance-id", required=True)
    export_parser.add_argument("--owner-instance-id", default="")
    export_parser.add_argument("--key-file", default=None, help="Path containing the HMAC signing key or Ed25519 private signing key.")
    export_parser.add_argument("--trust-registry", default=None, help="Optional local trust registry JSON file.")
    export_parser.add_argument("--key-id", required=True)
    export_parser.add_argument("--signature-algorithm", default="hmac-sha256", choices=["hmac-sha256", "ed25519"])
    export_parser.add_argument("--snapshot-id", default=None)
    export_parser.add_argument("--allow-unclassified-public", action="store_true")
    export_parser.add_argument("--allow-privileged", action="store_true")
    export_parser.add_argument("--policy-file", default=None, help="Optional local federation policy JSON file.")
    export_parser.add_argument("--requester-id", default="", help="Subject/principal requesting the export.")
    export_parser.add_argument("--scope-id", default="", help="Project/entity scope requested for policy evaluation.")
    export_parser.add_argument("--audit-log", default=None, help="Optional JSONL audit log path.")

    import_parser = subparsers.add_parser("import", help="Verify a federation bundle and place it in quarantine.")
    import_parser.add_argument("bundle_path")
    import_parser.add_argument("quarantine_dir")
    import_parser.add_argument("--key-file", default=None, help="Path containing the HMAC verification key.")
    import_parser.add_argument("--trust-registry", default=None, help="Optional local trust registry JSON file.")
    import_parser.add_argument("--key-id", default=None)
    import_parser.add_argument("--policy-file", default=None, help="Optional local federation policy JSON file.")
    import_parser.add_argument("--requester-id", default="", help="Subject/principal requesting the import.")
    import_parser.add_argument("--scope-id", default="", help="Project/entity scope requested for policy evaluation.")
    import_parser.add_argument("--audit-log", default=None, help="Optional JSONL audit log path.")
    import_parser.add_argument(
        "--accept-release-level",
        action="append",
        default=[],
        choices=["public", "internal", "confidential", "privileged"],
        help="Accepted target release level. May be repeated.",
    )
    list_parser = subparsers.add_parser("list-quarantine", help="List quarantined federation bundles.")
    list_parser.add_argument("quarantine_dir")

    promote_parser = subparsers.add_parser("promote", help="Plan or apply promotion of a quarantined bundle into a canonical store.")
    promote_parser.add_argument("bundle_path")
    promote_parser.add_argument("store_dir")
    promote_parser.add_argument("--key-file", default=None, help="Path containing the HMAC verification key.")
    promote_parser.add_argument("--trust-registry", default=None, help="Optional local trust registry JSON file.")
    promote_parser.add_argument("--key-id", default=None)
    promote_parser.add_argument(
        "--accept-release-level",
        action="append",
        default=[],
        choices=["public", "internal", "confidential", "privileged"],
        help="Accepted target release level. May be repeated.",
    )
    promote_parser.add_argument("--policy-file", default=None, help="Optional local federation policy JSON file.")
    promote_parser.add_argument("--requester-id", default="", help="Subject/principal requesting promotion.")
    promote_parser.add_argument("--scope-id", default="", help="Project/entity scope requested for policy evaluation.")
    promote_parser.add_argument("--audit-log", default=None, help="Optional JSONL audit log path.")
    promote_parser.add_argument("--apply", action="store_true", help="Write non-conflicting records into the canonical store.")

    role_compile_parser = subparsers.add_parser(
        "policy-from-roles",
        help="Compile a federation role directory JSON file into a local federation policy JSON file.",
    )
    role_compile_parser.add_argument("role_directory_path")
    role_compile_parser.add_argument("policy_path")
    role_compile_parser.add_argument("--policy-id", default=None)

    role_publish_parser = subparsers.add_parser(
        "role-publish-directory",
        help="Write a signed Ed25519 federation role-directory publication.",
    )
    role_publish_parser.add_argument("role_directory_path")
    role_publish_parser.add_argument("out_path")
    role_publish_parser.add_argument("--producer-instance-id", required=True)
    role_publish_parser.add_argument("--signing-key-file", required=True, help="Path containing the Ed25519 private key that signs the role directory.")
    role_publish_parser.add_argument("--signer-key-id", required=True)

    role_import_parser = subparsers.add_parser(
        "policy-import-roles",
        help="Verify a signed role-directory publication and write a locally capped federation policy.",
    )
    role_import_parser.add_argument("publication_path")
    role_import_parser.add_argument("policy_path")
    role_import_parser.add_argument("--signer-key-file", required=True, help="Path containing the pinned Ed25519 public key for the role-directory signer.")
    role_import_parser.add_argument("--signer-key-id", default=None)
    role_import_parser.add_argument("--policy-id", default=None)
    role_import_parser.add_argument("--allow-subject-id", action="append", default=[], help="Subject ID allowed to receive grants from the publication. May be repeated.")
    role_import_parser.add_argument("--allow-role-id", action="append", default=[], help="Role ID allowed from the publication. May be repeated.")
    role_import_parser.add_argument("--allow-instance-id", action="append", default=[], help="Instance ID allowed in imported grants. Defaults to the publication producer instance.")
    role_import_parser.add_argument(
        "--allow-release-level",
        action="append",
        default=[],
        choices=["public", "internal", "confidential", "privileged"],
        help="Maximum locally allowed release levels to grant. Defaults to public.",
    )
    role_import_parser.add_argument(
        "--allow-action",
        action="append",
        default=[],
        choices=["export", "import", "promote"],
        help="Maximum locally allowed actions to grant. Defaults to import and promote.",
    )
    role_import_parser.add_argument("--allow-scope", action="append", default=[], help="Scope ID allowed in imported grants. May be repeated.")

    trust_add_parser = subparsers.add_parser("trust-add", help="Add or replace a trusted federation key in a local registry.")
    trust_add_parser.add_argument("registry_path")
    trust_add_parser.add_argument("--instance-id", required=True)
    trust_add_parser.add_argument("--key-id", required=True)
    trust_add_parser.add_argument("--key-file", required=True, help="Path containing HMAC key material or an Ed25519 public key to trust.")
    trust_add_parser.add_argument("--algorithm", default="hmac-sha256", choices=["hmac-sha256", "ed25519"])
    trust_add_parser.add_argument(
        "--release-level",
        action="append",
        default=[],
        choices=["public", "internal", "confidential", "privileged"],
        help="Allowed release level. May be repeated.",
    )
    trust_add_parser.add_argument(
        "--trusted-action",
        action="append",
        default=[],
        choices=["export", "import", "promote"],
        help="Allowed action. May be repeated.",
    )
    trust_add_parser.add_argument("--expires-at", default="", help="UTC timestamp after which this trusted key is rejected.")
    trust_add_parser.add_argument("--inactive", action="store_true")

    trust_revoke_parser = subparsers.add_parser("trust-revoke", help="Revoke a trusted federation key in a local registry.")
    trust_revoke_parser.add_argument("registry_path")
    trust_revoke_parser.add_argument("--instance-id", required=True)
    trust_revoke_parser.add_argument("--key-id", required=True)
    trust_revoke_parser.add_argument("--reason", default="")
    trust_revoke_parser.add_argument("--superseded-by-key-id", default="")

    trust_export_metadata_parser = subparsers.add_parser(
        "trust-export-metadata",
        help="Write a non-secret federation trust metadata file with key material redacted.",
    )
    trust_export_metadata_parser.add_argument("registry_path")
    trust_export_metadata_parser.add_argument("out_path")
    trust_export_metadata_parser.add_argument(
        "--include-key-fingerprint",
        action="store_true",
        help="Include sha256 fingerprints of key material for operator comparison. Use only for high-entropy keys.",
    )

    trust_publish_keyset_parser = subparsers.add_parser(
        "trust-publish-keyset",
        help="Write a signed Ed25519 public-key publication from local trust registry entries.",
    )
    trust_publish_keyset_parser.add_argument("registry_path")
    trust_publish_keyset_parser.add_argument("out_path")
    trust_publish_keyset_parser.add_argument("--producer-instance-id", required=True)
    trust_publish_keyset_parser.add_argument("--signing-key-file", required=True, help="Path containing the Ed25519 private key that signs the keyset.")
    trust_publish_keyset_parser.add_argument("--signer-key-id", required=True)
    trust_publish_keyset_parser.add_argument("--active-only", action="store_true", help="Omit inactive/revoked keys from the publication.")

    trust_import_keyset_parser = subparsers.add_parser(
        "trust-import-keyset",
        help="Verify a signed Ed25519 public-key publication and merge it into a local trust registry.",
    )
    trust_import_keyset_parser.add_argument("keyset_path")
    trust_import_keyset_parser.add_argument("registry_path")
    trust_import_keyset_parser.add_argument("--signer-key-file", required=True, help="Path containing the pinned Ed25519 public key for the keyset signer.")
    trust_import_keyset_parser.add_argument("--signer-key-id", default=None)
    trust_import_keyset_parser.add_argument(
        "--allow-instance-id",
        action="append",
        default=[],
        help="Locally allowed instance IDs to import from the keyset. Defaults to the keyset producer instance.",
    )
    trust_import_keyset_parser.add_argument(
        "--allow-release-level",
        action="append",
        default=[],
        choices=["public", "internal", "confidential", "privileged"],
        help="Maximum locally allowed release levels to grant from the keyset. Defaults to public.",
    )
    trust_import_keyset_parser.add_argument(
        "--allow-trusted-action",
        action="append",
        default=[],
        choices=["export", "import", "promote"],
        help="Maximum locally allowed actions to grant from the keyset. Defaults to import and promote.",
    )

    trust_list_parser = subparsers.add_parser("trust-list", help="List trusted federation keys in a local registry.")
    trust_list_parser.add_argument("registry_path")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "policy-from-roles":
        directory = load_federation_role_directory(args.role_directory_path)
        policy = compile_federation_role_directory_to_policy(directory, policy_id=args.policy_id)
        save_federation_policy(args.policy_path, policy)
        print(json.dumps(policy.model_dump(mode="json"), indent=2, sort_keys=True))
        return
    if args.command == "role-publish-directory":
        directory = load_federation_role_directory(args.role_directory_path)
        publication = export_federation_role_directory_publication(
            directory,
            args.out_path,
            producer_instance_id=args.producer_instance_id,
            signing_key=Path(args.signing_key_file).read_bytes(),
            signer_key_id=args.signer_key_id,
        )
        print(json.dumps(publication.model_dump(mode="json"), indent=2, sort_keys=True))
        return
    if args.command == "policy-import-roles":
        publication = FederationRoleDirectoryPublication.model_validate_json(Path(args.publication_path).read_text(encoding="utf-8"))
        policy = import_federation_role_directory_publication_to_policy(
            publication,
            verification_key=Path(args.signer_key_file).read_bytes(),
            signer_key_id=args.signer_key_id,
            policy_id=args.policy_id,
            allowed_subject_ids=args.allow_subject_id or None,
            allowed_role_ids=args.allow_role_id or None,
            allowed_instance_ids=args.allow_instance_id or None,
            allowed_release_levels=args.allow_release_level or ["public"],
            allowed_actions=args.allow_action or ["import", "promote"],
            allowed_scopes=args.allow_scope or None,
        )
        save_federation_policy(args.policy_path, policy)
        print(json.dumps(policy.model_dump(mode="json"), indent=2, sort_keys=True))
        return
    if args.command == "trust-add":
        path = Path(args.registry_path)
        registry = load_federation_trust_registry(path) if path.exists() else FederationTrustRegistry()
        registry = add_federation_trust_key(
            registry,
            instance_id=args.instance_id,
            key_id=args.key_id,
            key_material=Path(args.key_file).read_text(encoding="utf-8").strip(),
            algorithm=args.algorithm,
            release_levels=args.release_level or ["public"],
            trusted_actions=args.trusted_action or ["import", "promote"],
            active=not args.inactive,
            expires_at=args.expires_at,
        )
        save_federation_trust_registry(path, registry)
        print(json.dumps(registry.model_dump(mode="json"), indent=2, sort_keys=True))
        return
    if args.command == "trust-revoke":
        registry = load_federation_trust_registry(args.registry_path)
        registry = revoke_federation_trust_key(
            registry,
            instance_id=args.instance_id,
            key_id=args.key_id,
            reason=args.reason,
            superseded_by_key_id=args.superseded_by_key_id,
        )
        save_federation_trust_registry(args.registry_path, registry)
        print(json.dumps(registry.model_dump(mode="json"), indent=2, sort_keys=True))
        return
    if args.command == "trust-export-metadata":
        registry = load_federation_trust_registry(args.registry_path)
        metadata = export_federation_trust_metadata(
            registry,
            include_key_fingerprints=args.include_key_fingerprint,
        )
        save_federation_trust_metadata(args.out_path, metadata)
        print(json.dumps(metadata.model_dump(mode="json"), indent=2, sort_keys=True))
        return
    if args.command == "trust-publish-keyset":
        registry = load_federation_trust_registry(args.registry_path)
        keyset = export_federation_public_keyset(
            registry,
            args.out_path,
            producer_instance_id=args.producer_instance_id,
            signing_key=Path(args.signing_key_file).read_bytes(),
            signer_key_id=args.signer_key_id,
            active_only=args.active_only,
        )
        print(json.dumps(keyset.model_dump(mode="json"), indent=2, sort_keys=True))
        return
    if args.command == "trust-import-keyset":
        path = Path(args.registry_path)
        registry = load_federation_trust_registry(path) if path.exists() else FederationTrustRegistry()
        keyset = FederationPublicKeySet.model_validate_json(Path(args.keyset_path).read_text(encoding="utf-8"))
        registry = import_federation_public_keyset_to_trust_registry(
            keyset,
            registry,
            verification_key=Path(args.signer_key_file).read_bytes(),
            signer_key_id=args.signer_key_id,
            allowed_instance_ids=args.allow_instance_id or None,
            allowed_release_levels=args.allow_release_level or ["public"],
            allowed_trusted_actions=args.allow_trusted_action or ["import", "promote"],
        )
        save_federation_trust_registry(path, registry)
        print(json.dumps(registry.model_dump(mode="json"), indent=2, sort_keys=True))
        return
    if args.command == "trust-list":
        registry = load_federation_trust_registry(args.registry_path)
        print(json.dumps(registry.model_dump(mode="json"), indent=2, sort_keys=True))
        return
    if args.command == "list-quarantine":
        summaries = list_quarantine_bundles(args.quarantine_dir)
        print(json.dumps([item.model_dump(mode="json") for item in summaries], indent=2, sort_keys=True))
        return
    policy = load_federation_policy(args.policy_file) if getattr(args, "policy_file", None) else None
    if args.command == "export":
        key = _key_for_export_args(args)
        bundle = export_federation_bundle(
            store_dir=args.store_dir,
            out_path=args.out_path,
            target_release_level=args.target_release_level,
            producer_instance_id=args.producer_instance_id,
            owner_instance_id=args.owner_instance_id,
            signing_key=key,
            key_id=args.key_id,
            signature_algorithm=args.signature_algorithm,
            snapshot_id=args.snapshot_id,
            allow_unclassified_public=args.allow_unclassified_public,
            allow_privileged=args.allow_privileged,
            policy=policy,
            requester_id=args.requester_id,
            scope_id=args.scope_id,
            audit_log_path=args.audit_log,
        )
        print(json.dumps(bundle.model_dump(mode="json"), indent=2, sort_keys=True))
        return
    if args.command == "import":
        key, resolved_key_id = _key_for_bundle_args(args, action="import")
        accepted = args.accept_release_level or ["public"]
        result = import_federation_bundle_to_quarantine(
            args.bundle_path,
            args.quarantine_dir,
            signing_key=key,
            accepted_release_levels=accepted,
            key_id=resolved_key_id,
            policy=policy,
            requester_id=args.requester_id,
            scope_id=args.scope_id,
            audit_log_path=args.audit_log,
        )
        print(json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True))
        return
    if args.command == "promote":
        key, resolved_key_id = _key_for_bundle_args(args, action="promote")
        accepted = args.accept_release_level or ["public"]
        result = promote_quarantined_bundle(
            args.bundle_path,
            args.store_dir,
            signing_key=key,
            key_id=resolved_key_id,
            accepted_release_levels=accepted,
            policy=policy,
            requester_id=args.requester_id,
            scope_id=args.scope_id,
            audit_log_path=args.audit_log,
            apply=args.apply,
        )
        print(json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True))
        return


def _key_for_export_args(args: argparse.Namespace) -> bytes:
    if args.key_file:
        return Path(args.key_file).read_bytes()
    if args.trust_registry:
        if args.signature_algorithm != "hmac-sha256":
            raise FederationPolicyError("ed25519 export requires --key-file with an Ed25519 private key")
        registry = load_federation_trust_registry(args.trust_registry)
        return resolve_trust_key(
            registry,
            instance_id=args.producer_instance_id,
            key_id=args.key_id,
            release_level=args.target_release_level,
            action="export",
            algorithm=args.signature_algorithm,
        )
    raise FederationPolicyError("export requires --key-file or --trust-registry")


def _key_for_bundle_args(args: argparse.Namespace, *, action: FederationAction) -> tuple[bytes, str | None]:
    if args.key_file:
        return Path(args.key_file).read_bytes(), args.key_id
    if args.trust_registry:
        bundle = FederationBundle.model_validate_json(Path(args.bundle_path).read_text(encoding="utf-8"))
        signature = bundle.manifest.signature
        if signature is None:
            raise FederationPolicyError("federation bundle is unsigned")
        key_id = args.key_id or signature.key_id
        registry = load_federation_trust_registry(args.trust_registry)
        key = resolve_trust_key(
            registry,
            instance_id=bundle.manifest.producer_instance_id,
            key_id=key_id,
            release_level=bundle.manifest.target_release_level,
            action=action,
            algorithm=signature.algorithm,
        )
        return key, key_id
    raise FederationPolicyError(f"{action} requires --key-file or --trust-registry")


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


def _content_hash_for_public_key_entries(keys: list[FederationPublicKeyEntry]) -> str:
    return hashlib.sha256(_canonical_json([key.model_dump(mode="json") for key in keys]).encode("utf-8")).hexdigest()


def _content_hash_for_role_directory(directory: FederationRoleDirectory) -> str:
    return hashlib.sha256(_canonical_json(directory.model_dump(mode="json")).encode("utf-8")).hexdigest()


def _signature_for_payload(
    payload: dict[str, Any],
    signing_key: str | bytes,
    *,
    algorithm: FederationSignatureAlgorithm,
) -> str:
    key = signing_key.encode("utf-8") if isinstance(signing_key, str) else signing_key
    message = _canonical_json(payload).encode("utf-8")
    if algorithm == "hmac-sha256":
        return hmac.new(key, message, hashlib.sha256).hexdigest()
    if algorithm == "ed25519":
        try:
            private_key = serialization.load_pem_private_key(key, password=None)
        except ValueError as exc:
            raise FederationPolicyError("ed25519 signing requires a valid Ed25519 private key") from exc
        if not isinstance(private_key, Ed25519PrivateKey):
            raise FederationPolicyError("ed25519 signing requires an Ed25519 private key")
        return base64.b64encode(private_key.sign(message)).decode("ascii")
    raise FederationPolicyError(f"unsupported federation signature algorithm: {algorithm}")


def _verify_signature_for_payload(
    payload: dict[str, Any],
    verification_key: str | bytes,
    *,
    algorithm: FederationSignatureAlgorithm,
    signature_value: str,
) -> bool:
    key = verification_key.encode("utf-8") if isinstance(verification_key, str) else verification_key
    message = _canonical_json(payload).encode("utf-8")
    if algorithm == "hmac-sha256":
        expected = hmac.new(key, message, hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature_value, expected)
    if algorithm == "ed25519":
        try:
            public_key = serialization.load_pem_public_key(key)
            if not isinstance(public_key, Ed25519PublicKey):
                raise FederationPolicyError("ed25519 verification requires an Ed25519 public key")
            public_key.verify(base64.b64decode(signature_value.encode("ascii")), message)
        except (InvalidSignature, ValueError, binascii.Error):
            return False
        return True
    raise FederationPolicyError(f"unsupported federation signature algorithm: {algorithm}")


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


def _promotion_collections(bundle: FederationBundle, store: GroundRecallStore) -> list[dict[str, Any]]:
    return [
        {
            "record_kind": "source",
            "incoming": bundle.snapshot.sources,
            "id_field": "source_id",
            "get_existing": store.get_source,
            "save": store.save_source,
        },
        {
            "record_kind": "fragment",
            "incoming": bundle.snapshot.fragments,
            "id_field": "fragment_id",
            "get_existing": store.get_fragment,
            "save": store.save_fragment,
        },
        {
            "record_kind": "artifact",
            "incoming": bundle.snapshot.artifacts,
            "id_field": "artifact_id",
            "get_existing": store.get_artifact,
            "save": store.save_artifact,
        },
        {
            "record_kind": "observation",
            "incoming": bundle.snapshot.observations,
            "id_field": "observation_id",
            "get_existing": store.get_observation,
            "save": store.save_observation,
        },
        {
            "record_kind": "concept",
            "incoming": bundle.snapshot.concepts,
            "id_field": "concept_id",
            "get_existing": store.get_concept,
            "save": store.save_concept,
        },
        {
            "record_kind": "claim",
            "incoming": bundle.snapshot.claims,
            "id_field": "claim_id",
            "get_existing": store.get_claim,
            "save": store.save_claim,
        },
        {
            "record_kind": "relation",
            "incoming": bundle.snapshot.relations,
            "id_field": "relation_id",
            "get_existing": store.get_relation,
            "save": store.save_relation,
        },
        {
            "record_kind": "promotion",
            "incoming": bundle.snapshot.promotions,
            "id_field": "promotion_id",
            "get_existing": store.get_promotion,
            "save": store.save_promotion,
        },
        {
            "record_kind": "adjudication",
            "incoming": bundle.snapshot.adjudications,
            "id_field": "adjudication_id",
            "get_existing": store.get_adjudication,
            "save": store.save_adjudication,
        },
    ]


def _accumulate_promotion_collection(
    record_kind: str,
    incoming: list[Any],
    id_field: str,
    get_existing,
    promotable_counts: dict[str, int],
    unchanged_counts: dict[str, int],
    conflict_counts: dict[str, int],
    conflicts: list[dict[str, str]],
) -> None:
    for record in incoming:
        record_id = str(getattr(record, id_field))
        existing = get_existing(record_id)
        if existing is None:
            promotable_counts[record_kind] = promotable_counts.get(record_kind, 0) + 1
            continue
        if _record_hash(existing) == _record_hash(record):
            unchanged_counts[record_kind] = unchanged_counts.get(record_kind, 0) + 1
            continue
        conflict_counts[record_kind] = conflict_counts.get(record_kind, 0) + 1
        conflicts.append({"record_kind": record_kind, "record_id": record_id, "reason": "existing_record_differs"})


def _record_hash(record: Any) -> str:
    return hashlib.sha256(_canonical_json(record.model_dump(mode="json")).encode("utf-8")).hexdigest()


def _audit_promotion(
    audit_log_path: str | Path | None,
    result: FederationPromotionResult,
    requester_id: str,
    bundle: FederationBundle,
    policy_decision: FederationPolicyDecision | None,
) -> None:
    if audit_log_path is None:
        return
    append_federation_audit_event(
        audit_log_path,
        build_federation_audit_event(
            action="promote",
            decision=result.decision,
            subject_id=requester_id,
            release_level=bundle.manifest.target_release_level,
            bundle_id=bundle.manifest.bundle_id,
            instance_id=bundle.manifest.producer_instance_id,
            policy_decision=policy_decision,
            reasons=result.reasons,
            metadata={
                "promotable_counts": result.plan.promotable_counts,
                "unchanged_counts": result.plan.unchanged_counts,
                "conflict_counts": result.plan.conflict_counts,
                "apply": result.plan.apply,
            },
        ),
    )
