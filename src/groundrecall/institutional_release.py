from __future__ import annotations

import argparse
import hashlib
import hmac
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from .catalog import _RELEASE_RANK
from .federation import FederationPolicyError
from .models import ReleaseLevel
from .store import GroundRecallStore


RELEASE_PACK_SCHEMA_VERSION = "groundrecall.knowledge_release_pack.v1"
WITHDRAWAL_NOTICE_SCHEMA_VERSION = "groundrecall.knowledge_release_withdrawal.v1"


class ReleasePackManifest(BaseModel):
    schema_version: str = RELEASE_PACK_SCHEMA_VERSION
    pack_id: str
    created_at: str = ""
    target_release_level: ReleaseLevel = "public"
    record_count: int = 0
    content_hash: str
    license_ids: list[str] = Field(default_factory=list)
    attribution_count: int = 0
    redaction_policy_ids: list[str] = Field(default_factory=list)
    supersedes_pack_ids: list[str] = Field(default_factory=list)
    review_receipt_ids: list[str] = Field(default_factory=list)
    policy_id: str = ""
    signature_algorithm: Literal["hmac-sha256"] = "hmac-sha256"
    key_id: str = ""
    signature: str = ""


class ReleasePack(BaseModel):
    manifest: ReleasePackManifest
    records: list[dict[str, Any]] = Field(default_factory=list)
    findings: list[dict[str, str]] = Field(default_factory=list)


class WithdrawalNotice(BaseModel):
    schema_version: str = WITHDRAWAL_NOTICE_SCHEMA_VERSION
    notice_id: str
    pack_id: str
    withdrawn_at: str = ""
    reason: str = ""
    superseded_by_pack_id: str = ""
    authority: str = ""
    distinct_from_erasure: bool = True
    preserve_historical_audit: bool = True
    signature_algorithm: Literal["hmac-sha256"] = "hmac-sha256"
    key_id: str = ""
    content_hash: str
    signature: str = ""


def build_release_pack(
    store_dir: str | Path,
    *,
    target_release_level: ReleaseLevel,
    allowed_license_ids: list[str],
    signing_key: str | bytes,
    key_id: str,
    created_at: str = "",
    pack_id: str = "",
    supersedes_pack_ids: list[str] | None = None,
    review_receipt_ids: list[str] | None = None,
    policy_id: str = "",
    out_dir: str | Path | None = None,
    withdrawal_notice_paths: list[str | Path] | None = None,
) -> ReleasePack:
    withdrawn_ids = _withdrawn_pack_ids(withdrawal_notice_paths or [])
    if pack_id and pack_id in withdrawn_ids:
        raise FederationPolicyError("withdrawn release pack cannot silently re-enter current context")
    records, findings = _release_records(GroundRecallStore(store_dir), target_release_level=target_release_level, allowed_license_ids=allowed_license_ids)
    if findings:
        raise FederationPolicyError("; ".join(sorted({item["reason"] for item in findings})))
    content_hash = _hash_payload(records)
    manifest = ReleasePackManifest(
        pack_id=pack_id or f"release_pack::{target_release_level}::{content_hash[:16]}",
        created_at=created_at,
        target_release_level=target_release_level,
        record_count=len(records),
        content_hash=content_hash,
        license_ids=sorted({str(record.get("license_id", "")) for record in records if record.get("license_id")}),
        attribution_count=sum(1 for record in records if record.get("attribution")),
        redaction_policy_ids=sorted({str(record.get("redaction_policy_id", "")) for record in records if record.get("redaction_policy_id")}),
        supersedes_pack_ids=sorted(supersedes_pack_ids or []),
        review_receipt_ids=sorted(review_receipt_ids or []),
        policy_id=policy_id,
        key_id=key_id,
    )
    signed = manifest.model_copy(update={"signature": _sign(manifest.model_dump(mode="json", exclude={"signature"}), signing_key)})
    pack = ReleasePack(manifest=signed, records=records, findings=[])
    if out_dir is not None:
        target = Path(out_dir)
        target.mkdir(parents=True, exist_ok=True)
        (target / "release_manifest.json").write_text(pack.manifest.model_dump_json(indent=2), encoding="utf-8")
        (target / "records.json").write_text(json.dumps(records, indent=2, sort_keys=True), encoding="utf-8")
    return pack


def verify_release_pack(pack: ReleasePack | dict[str, Any], *, verification_key: str | bytes, key_id: str | None = None) -> ReleasePack:
    parsed = pack if isinstance(pack, ReleasePack) else ReleasePack.model_validate(pack)
    if key_id is not None and parsed.manifest.key_id != key_id:
        raise FederationPolicyError("release pack key ID does not match")
    if parsed.manifest.content_hash != _hash_payload(parsed.records):
        raise FederationPolicyError("release pack content hash does not match")
    expected = _sign(parsed.manifest.model_dump(mode="json", exclude={"signature"}), verification_key)
    if not hmac.compare_digest(parsed.manifest.signature, expected):
        raise FederationPolicyError("release pack signature does not match")
    return parsed


def build_withdrawal_notice(
    *,
    pack_id: str,
    signing_key: str | bytes,
    key_id: str,
    withdrawn_at: str = "",
    reason: str = "",
    superseded_by_pack_id: str = "",
    authority: str = "",
    out_path: str | Path | None = None,
) -> WithdrawalNotice:
    basis = {
        "pack_id": pack_id,
        "withdrawn_at": withdrawn_at,
        "reason": reason,
        "superseded_by_pack_id": superseded_by_pack_id,
        "authority": authority,
        "distinct_from_erasure": True,
        "preserve_historical_audit": True,
    }
    content_hash = _hash_payload(basis)
    notice = WithdrawalNotice(
        notice_id=f"withdrawal::{pack_id}::{content_hash[:16]}",
        pack_id=pack_id,
        withdrawn_at=withdrawn_at,
        reason=reason,
        superseded_by_pack_id=superseded_by_pack_id,
        authority=authority,
        key_id=key_id,
        content_hash=content_hash,
    )
    notice = notice.model_copy(update={"signature": _sign(notice.model_dump(mode="json", exclude={"signature"}), signing_key)})
    if out_path is not None:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_text(notice.model_dump_json(indent=2), encoding="utf-8")
    return notice


def verify_withdrawal_notice(notice: WithdrawalNotice | dict[str, Any], *, verification_key: str | bytes, key_id: str | None = None) -> WithdrawalNotice:
    parsed = notice if isinstance(notice, WithdrawalNotice) else WithdrawalNotice.model_validate(notice)
    if key_id is not None and parsed.key_id != key_id:
        raise FederationPolicyError("withdrawal notice key ID does not match")
    basis = {
        "pack_id": parsed.pack_id,
        "withdrawn_at": parsed.withdrawn_at,
        "reason": parsed.reason,
        "superseded_by_pack_id": parsed.superseded_by_pack_id,
        "authority": parsed.authority,
        "distinct_from_erasure": parsed.distinct_from_erasure,
        "preserve_historical_audit": parsed.preserve_historical_audit,
    }
    if parsed.content_hash != _hash_payload(basis):
        raise FederationPolicyError("withdrawal notice content hash does not match")
    expected = _sign(parsed.model_dump(mode="json", exclude={"signature"}), verification_key)
    if not hmac.compare_digest(parsed.signature, expected):
        raise FederationPolicyError("withdrawal notice signature does not match")
    return parsed


def _release_records(store: GroundRecallStore, *, target_release_level: ReleaseLevel, allowed_license_ids: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    records: list[dict[str, Any]] = []
    findings: list[dict[str, str]] = []
    for kind, items, id_field in (
        ("source", store.list_sources(), "source_id"),
        ("artifact", store.list_artifacts(), "artifact_id"),
        ("claim", store.list_claims(), "claim_id"),
    ):
        for item in items:
            if _RELEASE_RANK.get(_release_level_for_pack(item), 4) > _RELEASE_RANK[target_release_level]:
                continue
            if getattr(item, "current_status", "") not in {"reviewed", "promoted"}:
                findings.append({"record_kind": kind, "record_id": str(getattr(item, id_field)), "reason": "record_not_reviewed_for_release"})
                continue
            license_id = str(getattr(item, "license_id", "") or getattr(item, "metadata", {}).get("license_id", ""))
            attribution = str(getattr(item, "attribution", "") or getattr(item, "metadata", {}).get("attribution", ""))
            record_id = str(getattr(item, id_field))
            if not license_id:
                findings.append({"record_kind": kind, "record_id": record_id, "reason": "missing_required_license"})
                continue
            if allowed_license_ids and license_id not in allowed_license_ids:
                findings.append({"record_kind": kind, "record_id": record_id, "reason": "incompatible_license"})
                continue
            if not attribution:
                findings.append({"record_kind": kind, "record_id": record_id, "reason": "missing_attribution"})
                continue
            records.append(_release_record(kind, record_id, item, license_id=license_id, attribution=attribution))
    return sorted(records, key=lambda item: (item["record_kind"], item["record_id"])), findings


def _release_record(record_kind: str, record_id: str, item: Any, *, license_id: str, attribution: str) -> dict[str, Any]:
    metadata = getattr(item, "metadata", {}) or {}
    provenance_visibility = str(metadata.get("provenance_visibility", "full"))
    redaction_policy_id = str(getattr(item, "redaction_policy_id", "") or metadata.get("redaction_policy_id", ""))
    payload = {
        "record_kind": record_kind,
        "record_id": record_id,
        "title": str(getattr(item, "title", "") or getattr(item, "claim_text", ""))[:240],
        "release_level": _release_level_for_pack(item),
        "license_id": license_id,
        "attribution": attribution,
        "source_release_level": str(getattr(item, "source_release_level", "") or metadata.get("source_release_level", "")),
        "redaction_policy_id": redaction_policy_id,
        "derivative_source_ids": list(getattr(item, "derivative_source_ids", []) or metadata.get("derivative_source_ids", []) or []),
        "provenance_visibility": provenance_visibility,
    }
    if provenance_visibility in {"full", "partial"}:
        provenance = getattr(item, "provenance", None)
        payload["provenance"] = {
            "source_url": getattr(provenance, "source_url", "") if provenance else str(getattr(item, "url", "")),
            "origin_path": getattr(provenance, "origin_path", "") if provenance else str(getattr(item, "path", "")),
            "basis_visibility": provenance_visibility,
        }
    elif redaction_policy_id:
        payload["provenance"] = {"basis_visibility": provenance_visibility, "redaction_policy_id": redaction_policy_id}
    return payload


def _release_level_for_pack(item: Any) -> str:
    metadata = getattr(item, "metadata", {}) or {}
    explicit = getattr(item, "release_level", "")
    if explicit in _RELEASE_RANK:
        return explicit
    if isinstance(metadata, dict) and metadata.get("release_level") in _RELEASE_RANK:
        return str(metadata["release_level"])
    source_release = getattr(item, "source_release_level", "")
    if source_release in _RELEASE_RANK:
        return str(source_release)
    if isinstance(metadata, dict) and metadata.get("source_release_level") in _RELEASE_RANK:
        return str(metadata["source_release_level"])
    return "private"


def _withdrawn_pack_ids(paths: list[str | Path]) -> set[str]:
    withdrawn: set[str] = set()
    for path in paths:
        candidate = Path(path)
        if candidate.is_dir():
            files = sorted(candidate.glob("*.json"))
        else:
            files = [candidate]
        for file_path in files:
            if not file_path.exists():
                continue
            try:
                withdrawn.add(WithdrawalNotice.model_validate_json(file_path.read_text(encoding="utf-8")).pack_id)
            except Exception:
                continue
    return withdrawn


def _hash_payload(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()


def _sign(payload: Any, key: str | bytes) -> str:
    key_bytes = key.encode("utf-8") if isinstance(key, str) else key
    return hmac.new(key_bytes, json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8"), hashlib.sha256).hexdigest()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build license-aware release packs and withdrawal notices.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    pack = subparsers.add_parser("pack")
    pack.add_argument("store_dir")
    pack.add_argument("out_dir")
    pack.add_argument("--target-release-level", choices=tuple(_RELEASE_RANK), default="public")
    pack.add_argument("--allowed-license-id", action="append", default=[])
    pack.add_argument("--signing-key-file", required=True)
    pack.add_argument("--key-id", required=True)
    pack.add_argument("--created-at", default="")
    pack.add_argument("--pack-id", default="")
    pack.add_argument("--supersedes-pack-id", action="append", default=[])
    pack.add_argument("--review-receipt-id", action="append", default=[])
    pack.add_argument("--policy-id", default="")
    pack.add_argument("--withdrawal-notice-path", action="append", default=[])
    withdraw = subparsers.add_parser("withdraw")
    withdraw.add_argument("out_path")
    withdraw.add_argument("--pack-id", required=True)
    withdraw.add_argument("--signing-key-file", required=True)
    withdraw.add_argument("--key-id", required=True)
    withdraw.add_argument("--withdrawn-at", default="")
    withdraw.add_argument("--reason", default="")
    withdraw.add_argument("--superseded-by-pack-id", default="")
    withdraw.add_argument("--authority", default="")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    signing_key = Path(args.signing_key_file).read_text(encoding="utf-8").strip()
    if args.command == "pack":
        payload = build_release_pack(
            args.store_dir,
            target_release_level=args.target_release_level,
            allowed_license_ids=args.allowed_license_id,
            signing_key=signing_key,
            key_id=args.key_id,
            created_at=args.created_at,
            pack_id=args.pack_id,
            supersedes_pack_ids=args.supersedes_pack_id,
            review_receipt_ids=args.review_receipt_id,
            policy_id=args.policy_id,
            out_dir=args.out_dir,
            withdrawal_notice_paths=args.withdrawal_notice_path,
        )
    else:
        payload = build_withdrawal_notice(
            pack_id=args.pack_id,
            signing_key=signing_key,
            key_id=args.key_id,
            withdrawn_at=args.withdrawn_at,
            reason=args.reason,
            superseded_by_pack_id=args.superseded_by_pack_id,
            authority=args.authority,
            out_path=args.out_path,
        )
    print(payload.model_dump_json(indent=2))
