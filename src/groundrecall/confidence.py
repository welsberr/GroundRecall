from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Literal

from epistemap import AssessmentMethodRef, ConfidenceAssessment

from .models import ClaimRecord, ObservationRecord
from .store import GroundRecallStore


MIGRATION_VERSION = "groundrecall.confidence_migration.v1"
PRODUCER_POLICY_VERSION = "1.0"
PRODUCER_POLICY_ID_PREFIX = "groundrecall_adapter_confidence"
RECORDED_AT = "2026-07-25T00:00:00Z"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def basis_hash(basis_record_ids: Iterable[str]) -> str:
    encoded = json.dumps(sorted(str(value) for value in basis_record_ids if str(value)), separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def confidence_band(value: float) -> str:
    if value < 0.2:
        return "very_low"
    if value < 0.4:
        return "low"
    if value < 0.7:
        return "moderate"
    if value < 0.9:
        return "high"
    return "very_high"


def _bounded_float(value: Any) -> float | None:
    if value in ("", None):
        return None
    numeric = float(value)
    if numeric < 0.0 or numeric > 1.0:
        raise ValueError(f"confidence value must be between 0 and 1: {numeric}")
    return numeric


def _ensure_metadata(row: dict[str, Any]) -> dict[str, Any]:
    metadata = row.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
        row["metadata"] = metadata
    return metadata


def adapter_policy_id(adapter_name: str) -> str:
    normalized = "".join(ch.lower() if ch.isalnum() else "_" for ch in adapter_name).strip("_") or "unknown"
    return f"{PRODUCER_POLICY_ID_PREFIX}.{normalized}.v1"


def apply_adapter_confidence_policy(
    rows: Iterable[dict[str, Any]],
    *,
    adapter_name: str,
    row_kind: Literal["claim", "observation", "relation"],
    recorded_at: str,
) -> None:
    """Stamp adapter-specific confidence producer metadata onto new import rows.

    The legacy scalar remains in place for compatibility. The metadata is the
    contract that allows later conversion into typed confidence assessments.
    """

    for row in rows:
        if _bounded_float(row.get("confidence_hint")) is None:
            continue
        metadata = _ensure_metadata(row)
        metadata.setdefault(
            "confidence_method",
            {
                "name": f"groundrecall.{adapter_name}.{row_kind}.confidence_hint",
                "version": PRODUCER_POLICY_VERSION,
                "policy_id": adapter_policy_id(adapter_name),
            },
        )
        subject_id = _subject_id(row, row_kind)
        metadata.setdefault("confidence_extracted_field", "confidence_hint")
        metadata.setdefault("confidence_basis_record_ids", _default_basis_ids(row, row_kind, subject_id))
        metadata.setdefault("confidence_basis_hash", basis_hash(metadata["confidence_basis_record_ids"]))
        metadata.setdefault(
            "confidence_rationale",
            f"Adapter-specific {adapter_name} import policy emitted confidence_hint as extraction fidelity only.",
        )
        metadata.setdefault("confidence_recorded_at", recorded_at)


def assessment_from_legacy_hint(
    row: dict[str, Any],
    *,
    row_kind: Literal["claim", "observation"],
    subject_id: str,
) -> ConfidenceAssessment | None:
    value = _bounded_float(row.get("confidence_hint"))
    if value is None:
        return None
    if value == 0.0 and not _legacy_zero_is_explicit(row):
        return None
    metadata = row.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
    method = _method_from_metadata(metadata)
    if method is None:
        return None
    basis_ids = [str(item) for item in metadata.get("confidence_basis_record_ids", []) if str(item)]
    if not basis_ids:
        basis_ids = _default_basis_ids(row, row_kind, subject_id)
    return ConfidenceAssessment(
        assessment_id=f"{subject_id}::extraction_fidelity::{method.policy_id or method.name}",
        subject_id=subject_id,
        dimension="extraction_fidelity",
        value=value,
        band=confidence_band(value),
        method=method,
        basis_record_ids=basis_ids,
        basis_hash=str(metadata.get("confidence_basis_hash") or basis_hash(basis_ids)),
        rationale=str(
            metadata.get("confidence_rationale")
            or "Mapped from GroundRecall confidence_hint as extraction fidelity using explicit producer metadata."
        ),
        recorded_at=str(metadata.get("confidence_recorded_at") or RECORDED_AT),
        metadata={
            "migration_version": MIGRATION_VERSION,
            "extracted_field": str(metadata.get("confidence_extracted_field") or "confidence_hint"),
            "legacy_field": "confidence_hint",
            "producer_record_kind": row_kind,
            "not_review_endorsement": True,
            "not_promotion_authority": True,
        },
    )


def _method_from_metadata(metadata: dict[str, Any]) -> AssessmentMethodRef | None:
    method_payload = metadata.get("confidence_method")
    if isinstance(method_payload, dict):
        name = str(method_payload.get("name", "")).strip()
        version = str(method_payload.get("version", "")).strip()
        if name and version:
            return AssessmentMethodRef(
                name=name,
                version=version,
                policy_id=str(method_payload.get("policy_id", "")).strip(),
            )
    name = str(metadata.get("confidence_method_name", "")).strip()
    version = str(metadata.get("confidence_method_version", "")).strip()
    if name and version:
        return AssessmentMethodRef(name=name, version=version, policy_id=str(metadata.get("confidence_policy_id", "")).strip())
    return None


def _subject_id(row: dict[str, Any], row_kind: str) -> str:
    if row_kind == "claim":
        return str(row.get("claim_id", ""))
    if row_kind == "observation":
        return str(row.get("observation_id", ""))
    if row_kind == "relation":
        return str(row.get("relation_id", ""))
    return ""


def _default_basis_ids(row: dict[str, Any], row_kind: str, subject_id: str) -> list[str]:
    basis = [subject_id] if subject_id else []
    if row_kind == "claim":
        basis.extend(str(value) for value in row.get("supporting_fragment_ids", []) if str(value))
        basis.extend(str(value) for value in row.get("source_observation_ids", []) if str(value))
    elif row_kind == "observation":
        artifact_id = str(row.get("artifact_id", ""))
        if artifact_id:
            basis.append(artifact_id)
    return sorted(dict.fromkeys(basis))


def existing_assessments(row: dict[str, Any]) -> list[ConfidenceAssessment]:
    assessments: list[ConfidenceAssessment] = []
    for item in row.get("assessments", []) or []:
        if isinstance(item, ConfidenceAssessment):
            assessments.append(item)
        elif isinstance(item, dict):
            assessments.append(ConfidenceAssessment.model_validate(item))
    return assessments


def confidence_readiness_report(store_dir: str | Path) -> dict[str, Any]:
    store = GroundRecallStore(store_dir)
    findings: list[dict[str, Any]] = []
    assessed_count = 0
    legacy_scalar_count = 0
    for row_kind, records in (
        ("observation", [item.model_dump() for item in store.list_observations()]),
        ("claim", [item.model_dump() for item in store.list_claims()]),
        ("relation", [item.model_dump() for item in store.list_relations()]),
    ):
        for row in records:
            subject_id = _subject_id(row, row_kind)
            if row.get("assessments"):
                assessed_count += len(row.get("assessments") or [])
            value = _bounded_float(row.get("confidence_hint"))
            if value is None:
                continue
            legacy_scalar_count += 1
            metadata = row.get("metadata", {})
            if not isinstance(metadata, dict) or _method_from_metadata(metadata) is None:
                findings.append(
                    {
                        "severity": "error",
                        "code": "confidence_hint_missing_method",
                        "record_kind": row_kind,
                        "record_id": subject_id,
                        "field": "confidence_hint",
                        "rationale": "Scalar confidence_hint lacks producer method/version/policy metadata.",
                    }
                )
            elif not metadata.get("confidence_basis_record_ids") or not metadata.get("confidence_basis_hash"):
                findings.append(
                    {
                        "severity": "error",
                        "code": "confidence_hint_missing_basis",
                        "record_kind": row_kind,
                        "record_id": subject_id,
                        "field": "confidence_hint",
                        "rationale": "Scalar confidence_hint has a method but lacks deterministic basis identifiers/hash.",
                    }
                )
            if value == 0.0 and not _legacy_zero_is_explicit(row):
                findings.append(
                    {
                        "severity": "warning",
                        "code": "legacy_zero_ambiguous",
                        "record_kind": row_kind,
                        "record_id": subject_id,
                        "field": "confidence_hint",
                        "rationale": "Legacy zero is ambiguous unless explicit provenance marks it as intentional.",
                    }
                )
    error_count = sum(1 for item in findings if item["severity"] == "error")
    return {
        "report_kind": "groundrecall_confidence_readiness",
        "schema_version": MIGRATION_VERSION,
        "store_dir": str(Path(store_dir)),
        "generated_at": _now(),
        "ready": error_count == 0,
        "legacy_scalar_count": legacy_scalar_count,
        "assessment_count": assessed_count,
        "finding_count": len(findings),
        "error_count": error_count,
        "findings": findings,
    }


def _legacy_zero_is_explicit(row: dict[str, Any]) -> bool:
    metadata = row.get("metadata", {})
    if isinstance(metadata, dict):
        return bool(metadata.get("confidence_zero_explicit") or metadata.get("confidence_hint_explicit"))
    return False


def confidence_migration_report(
    store_dir: str | Path,
    *,
    apply: bool = False,
    backup_dir: str | Path | None = None,
) -> dict[str, Any]:
    store = GroundRecallStore(store_dir)
    operations: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    changed_claims: list[ClaimRecord] = []
    changed_observations: list[ObservationRecord] = []

    for observation in store.list_observations():
        row = observation.model_dump()
        subject_id = observation.observation_id
        existing_ids = {item.assessment_id for item in observation.assessments}
        assessment = assessment_from_legacy_hint(row, row_kind="observation", subject_id=subject_id)
        if assessment is None:
            _append_skip_if_legacy_scalar(skipped, row, "observation", subject_id)
            continue
        if assessment.assessment_id in existing_ids:
            continue
        updated = observation.model_copy(update={"assessments": [*observation.assessments, assessment]})
        changed_observations.append(updated)
        operations.append(_operation("observation", subject_id, assessment))

    for claim in store.list_claims():
        row = claim.model_dump()
        subject_id = claim.claim_id
        existing_ids = {item.assessment_id for item in claim.assessments}
        assessment = assessment_from_legacy_hint(row, row_kind="claim", subject_id=subject_id)
        if assessment is None:
            _append_skip_if_legacy_scalar(skipped, row, "claim", subject_id)
            continue
        if assessment.assessment_id in existing_ids:
            continue
        updated = claim.model_copy(update={"assessments": [*claim.assessments, assessment]})
        changed_claims.append(updated)
        operations.append(_operation("claim", subject_id, assessment))

    backup_path = ""
    if apply and operations:
        backup_path = str(Path(backup_dir) if backup_dir else Path(f"{store.base_dir}.confidence-migrate.bak"))
        _backup_store(store.base_dir, Path(backup_path))
        for observation in changed_observations:
            store.save_observation(observation)
        for claim in changed_claims:
            store.save_claim(claim)

    return {
        "report_kind": "groundrecall_confidence_migration",
        "schema_version": MIGRATION_VERSION,
        "store_dir": str(store.base_dir),
        "generated_at": _now(),
        "apply": apply,
        "backup_dir": backup_path,
        "candidate_count": len(operations),
        "applied_count": len(operations) if apply else 0,
        "skipped_count": len(skipped),
        "operations": operations,
        "skipped": skipped,
        "notes": [
            "Migration appends typed extraction_fidelity assessments; it does not delete or overwrite legacy scalar fields.",
            "confidence_hint is never converted into reviewer endorsement or promotion authority.",
            "Legacy zero values are skipped unless producer metadata marks the zero as explicit.",
        ],
    }


def _operation(record_kind: str, record_id: str, assessment: ConfidenceAssessment) -> dict[str, Any]:
    return {
        "operation": "append_assessment",
        "record_kind": record_kind,
        "record_id": record_id,
        "assessment_id": assessment.assessment_id,
        "dimension": assessment.dimension,
        "value": assessment.value,
        "method": assessment.method.model_dump(),
        "basis_record_ids": list(assessment.basis_record_ids),
        "basis_hash": assessment.basis_hash,
    }


def _append_skip_if_legacy_scalar(skipped: list[dict[str, Any]], row: dict[str, Any], row_kind: str, subject_id: str) -> None:
    value = _bounded_float(row.get("confidence_hint"))
    if value is None:
        return
    code = "legacy_confidence_hint_missing_method"
    if value == 0.0 and not _legacy_zero_is_explicit(row):
        code = "legacy_zero_ambiguous"
    skipped.append(
        {
            "record_kind": row_kind,
            "record_id": subject_id,
            "field": "confidence_hint",
            "value": value,
            "code": code,
            "rationale": "Skipped because the legacy scalar lacks sufficient producer provenance for typed assessment migration.",
        }
    )


def _backup_store(source: Path, backup: Path) -> None:
    if backup.exists():
        raise FileExistsError(f"backup already exists: {backup}")
    shutil.copytree(source, backup)


def restore_confidence_backup(store_dir: str | Path, backup_dir: str | Path) -> dict[str, Any]:
    target = Path(store_dir)
    backup = Path(backup_dir)
    if not backup.is_dir():
        raise FileNotFoundError(f"backup directory does not exist: {backup}")
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(backup, target)
    return {
        "report_kind": "groundrecall_confidence_restore",
        "schema_version": MIGRATION_VERSION,
        "store_dir": str(target),
        "backup_dir": str(backup),
        "restored_at": _now(),
    }


def _write_report(path: str | Path | None, payload: dict[str, Any]) -> None:
    if path is None:
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def build_migrate_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Migrate GroundRecall legacy confidence hints into append-only assessments.")
    parser.add_argument("store")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup", default=None, help="Backup directory used before --apply; defaults to STORE.confidence-migrate.bak.")
    parser.add_argument("--report", default=None, help="Write JSON migration report.")
    return parser


def confidence_migrate_main() -> None:
    args = build_migrate_parser().parse_args()
    payload = confidence_migration_report(args.store, apply=args.apply, backup_dir=args.backup)
    _write_report(args.report, payload)
    print(json.dumps(payload, indent=2))


def build_readiness_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check GroundRecall confidence assessment readiness.")
    parser.add_argument("store")
    parser.add_argument("--report", default=None, help="Write JSON readiness report.")
    return parser


def confidence_readiness_main() -> None:
    args = build_readiness_parser().parse_args()
    payload = confidence_readiness_report(args.store)
    _write_report(args.report, payload)
    print(json.dumps(payload, indent=2))


def build_restore_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Restore a GroundRecall store from a confidence migration backup.")
    parser.add_argument("store")
    parser.add_argument("backup")
    parser.add_argument("--report", default=None, help="Write JSON restore report.")
    return parser


def confidence_restore_main() -> None:
    args = build_restore_parser().parse_args()
    payload = restore_confidence_backup(args.store, args.backup)
    _write_report(args.report, payload)
    print(json.dumps(payload, indent=2))
