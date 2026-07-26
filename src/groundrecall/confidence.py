from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Literal

from epistemap import (
    AssessmentMethodRef,
    ConfidenceAssessment,
    GraphBundle,
    bayesian_update_from_evidence_ledger,
    graph_to_evidence_ledger,
)

from .models import AdjudicationRecord, ClaimRecord, ObservationRecord
from .store import GroundRecallStore


MIGRATION_VERSION = "groundrecall.confidence_migration.v1"
PRODUCER_POLICY_VERSION = "1.0"
PRODUCER_POLICY_ID_PREFIX = "groundrecall_adapter_confidence"
RECORDED_AT = "2026-07-25T00:00:00Z"
REVIEWER_POLICY_ID = "groundrecall_reviewer_endorsement.v1"


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


def reviewer_endorsement_assessment(
    *,
    subject_id: str,
    reviewer_id: str,
    value: float,
    scope: str,
    rationale: str,
    evidence_inspected: list[str],
    recorded_at: str,
    assessment_id: str | None = None,
    method_version: str = "1.0",
) -> ConfidenceAssessment:
    """Build an explicit reviewer endorsement assessment.

    A reviewer endorsement is append-only assessment evidence. It is not a
    promotion decision; promotion remains controlled by review/promotion gates.
    """

    basis_ids = sorted(dict.fromkeys([subject_id, *[str(item) for item in evidence_inspected if str(item)]]))
    return ConfidenceAssessment(
        assessment_id=assessment_id or f"{subject_id}::reviewer_endorsement::{reviewer_id}::{basis_hash([recorded_at, *basis_ids])[:12]}",
        subject_id=subject_id,
        dimension="reviewer_endorsement",
        value=_require_bounded(value),
        band=confidence_band(float(value)),
        assessor_id=reviewer_id,
        method=AssessmentMethodRef(
            name="groundrecall.reviewer_endorsement",
            version=method_version,
            policy_id=REVIEWER_POLICY_ID,
        ),
        basis_record_ids=basis_ids,
        basis_hash=basis_hash(basis_ids),
        rationale=rationale,
        recorded_at=recorded_at,
        metadata={
            "scope": scope,
            "evidence_inspected": list(evidence_inspected),
            "not_promotion_authority": True,
        },
    )


def append_reviewer_endorsement(
    store_dir: str | Path,
    claim_id: str,
    *,
    reviewer_id: str,
    value: float,
    scope: str = "claim",
    rationale: str = "",
    evidence_inspected: list[str] | None = None,
    recorded_at: str | None = None,
) -> ConfidenceAssessment:
    store = GroundRecallStore(store_dir)
    claim = store.get_claim(claim_id)
    if claim is None:
        raise KeyError(f"Unknown GroundRecall claim: {claim_id}")
    assessment = reviewer_endorsement_assessment(
        subject_id=claim_id,
        reviewer_id=reviewer_id,
        value=value,
        scope=scope,
        rationale=rationale,
        evidence_inspected=evidence_inspected or [*claim.supporting_fragment_ids, *claim.source_observation_ids],
        recorded_at=recorded_at or _now(),
    )
    store.save_claim(claim.model_copy(update={"assessments": [*claim.assessments, assessment]}))
    return assessment


def save_adjudication(
    store_dir: str | Path,
    *,
    adjudication_id: str,
    subject_id: str,
    considered_assessment_ids: list[str],
    selected_assessment_ids: list[str],
    adjudicator: str,
    rationale: str,
    decided_at: str | None = None,
    subject_type: Literal["claim", "observation", "relation"] = "claim",
) -> AdjudicationRecord:
    record = AdjudicationRecord(
        adjudication_id=adjudication_id,
        subject_id=subject_id,
        subject_type=subject_type,
        considered_assessment_ids=list(considered_assessment_ids),
        selected_assessment_ids=list(selected_assessment_ids),
        adjudicator=adjudicator,
        rationale=rationale,
        decided_at=decided_at or _now(),
        metadata={
            "selection_policy": "explicit_adjudication_no_silent_averaging",
            "disagreement_preserved": True,
        },
    )
    GroundRecallStore(store_dir).save_adjudication(record)
    return record


def confidence_profile_for_query_payload(
    payload: dict[str, Any],
    *,
    graph_bundle: GraphBundle | None = None,
    adjudications: list[AdjudicationRecord | dict[str, Any]] | None = None,
    as_of: str | None = None,
) -> dict[str, Any]:
    claims = [dict(item) for item in payload.get("claims", [])]
    observations = [dict(item) for item in payload.get("supporting_observations", [])]
    readiness = _readiness_blocks(claims, observations)
    claim_profiles = [
        _claim_profile(
            claim,
            graph_bundle=graph_bundle,
            adjudications=[_adjudication_dict(item) for item in adjudications or [] if _adjudication_dict(item).get("subject_id") == claim.get("claim_id")],
            as_of=as_of,
        )
        for claim in claims
    ]
    return {
        "profile_kind": "groundrecall_confidence_profile",
        "schema_version": "groundrecall.confidence_profile.v1",
        "generated_at": _now(),
        "summary": {
            "claim_count": len(claim_profiles),
            "observation_count": len(observations),
            "assessment_count": sum(len(item["assessments"]["all"]) for item in claim_profiles),
            "adjudicated_claim_count": sum(1 for item in claim_profiles if item["adjudication"]["records"]),
            "ready": readiness["ready"],
        },
        "blocks": {
            "extraction": _dimension_block(claim_profiles, "extraction_fidelity"),
            "grounding": _grounding_block(claims, observations),
            "reviewer": _dimension_block(claim_profiles, "reviewer_endorsement"),
            "posterior_support": _posterior_block(claim_profiles),
            "temporal_applicability": _temporal_block(claim_profiles),
            "readiness": readiness,
        },
        "claims": claim_profiles,
        "selection_policy": {
            "mode": "preserve_multiple_assessments",
            "rule": "Do not silently average reviewer disagreement; use explicit adjudication records to identify selected assessments.",
        },
    }


def _claim_profile(
    claim: dict[str, Any],
    *,
    graph_bundle: GraphBundle | None,
    adjudications: list[dict[str, Any]],
    as_of: str | None,
) -> dict[str, Any]:
    claim_id = str(claim.get("claim_id", ""))
    assessments = existing_assessments(claim)
    by_dimension: dict[str, list[dict[str, Any]]] = {}
    for assessment in assessments:
        by_dimension.setdefault(assessment.dimension, []).append(assessment.model_dump())
    posterior = _posterior_for_claim(graph_bundle, claim_id) if graph_bundle is not None and claim_id else {}
    return {
        "claim_id": claim_id,
        "status": claim.get("current_status", ""),
        "assessments": {
            "all": [assessment.model_dump() for assessment in assessments],
            "by_dimension": by_dimension,
        },
        "adjudication": {
            "records": adjudications,
            "selection_explanation": _selection_explanation(assessments, adjudications),
        },
        "posterior_support": posterior,
        "temporal_applicability": _temporal_applicability(claim, as_of=as_of),
        "promotion_authority": {
            "confidence_can_promote": False,
            "rationale": "Confidence assessments inform review; promotion requires explicit review/promotion gates.",
        },
    }


def _posterior_for_claim(graph_bundle: GraphBundle, claim_id: str) -> dict[str, Any]:
    try:
        ledger = graph_to_evidence_ledger(graph_bundle, claim_id)
        posterior = bayesian_update_from_evidence_ledger(ledger)
    except Exception as exc:  # pragma: no cover - defensive against older graph contracts
        return {"available": False, "error": str(exc)}
    return {
        "available": True,
        "ledger": ledger.model_dump(),
        "posterior": posterior,
        "reconstructable": True,
    }


def _selection_explanation(assessments: list[ConfidenceAssessment], adjudications: list[dict[str, Any]]) -> dict[str, Any]:
    if not assessments:
        return {"mode": "none", "rationale": "No assessments are available."}
    if not adjudications:
        return {
            "mode": "unadjudicated_disagreement_preserved",
            "considered_assessment_ids": [item.assessment_id for item in assessments],
            "selected_assessment_ids": [],
            "rationale": "Multiple active assessments are exposed without averaging until an adjudication record selects among them.",
        }
    selected = sorted({value for item in adjudications for value in item.get("selected_assessment_ids", [])})
    considered = sorted({value for item in adjudications for value in item.get("considered_assessment_ids", [])})
    return {
        "mode": "explicit_adjudication",
        "considered_assessment_ids": considered,
        "selected_assessment_ids": selected,
        "rationale": "Selection follows append-only adjudication records; unselected assessments remain visible.",
    }


def _temporal_applicability(claim: dict[str, Any], *, as_of: str | None) -> dict[str, Any]:
    metadata = claim.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
    status = str(claim.get("current_status", ""))
    as_of_dt = _parse_time(as_of) if as_of else datetime.now(timezone.utc)
    expires_at = metadata.get("expires_at") or metadata.get("valid_until")
    expired = bool(as_of_dt and expires_at and (_parse_time(str(expires_at)) or as_of_dt) < as_of_dt)
    if metadata.get("retracted_at") or status == "rejected":
        applicability = "retracted"
    elif metadata.get("superseded_at") or status == "superseded":
        applicability = "superseded"
    elif expired:
        applicability = "expired"
    else:
        applicability = "current"
    return {
        "applicability": applicability,
        "claim_status": status,
        "valid_at": metadata.get("valid_at", ""),
        "valid_until": expires_at or "",
        "last_confirmed_at": claim.get("last_confirmed_at", ""),
        "superseded_at": metadata.get("superseded_at", ""),
        "retracted_at": metadata.get("retracted_at", ""),
        "historical_support_preserved": True,
    }


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _dimension_block(claim_profiles: list[dict[str, Any]], dimension: str) -> dict[str, Any]:
    assessments = [
        assessment
        for profile in claim_profiles
        for assessment in profile["assessments"]["by_dimension"].get(dimension, [])
    ]
    return {
        "dimension": dimension,
        "assessment_count": len(assessments),
        "subject_ids": sorted({str(item.get("subject_id", "")) for item in assessments if item.get("subject_id")}),
        "assessments": assessments,
    }


def _grounding_block(claims: list[dict[str, Any]], observations: list[dict[str, Any]]) -> dict[str, Any]:
    grounded_claims = [
        claim
        for claim in claims
        if (claim.get("provenance", {}) if isinstance(claim.get("provenance"), dict) else {}).get("grounding_status")
        == "grounded"
    ]
    grounded_observations = [
        obs
        for obs in observations
        if (obs.get("provenance", {}) if isinstance(obs.get("provenance"), dict) else {}).get("grounding_status")
        == "grounded"
    ]
    return {
        "claim_count": len(claims),
        "grounded_claim_count": len(grounded_claims),
        "observation_count": len(observations),
        "grounded_observation_count": len(grounded_observations),
    }


def _posterior_block(claim_profiles: list[dict[str, Any]]) -> dict[str, Any]:
    available = [item for item in claim_profiles if item["posterior_support"].get("available")]
    return {
        "claim_count": len(claim_profiles),
        "available_count": len(available),
        "reconstructable": all(item["posterior_support"].get("reconstructable") for item in available),
    }


def _temporal_block(claim_profiles: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for profile in claim_profiles:
        applicability = profile["temporal_applicability"]["applicability"]
        counts[applicability] = counts.get(applicability, 0) + 1
    return {"claim_count": len(claim_profiles), "applicability_counts": dict(sorted(counts.items()))}


def _readiness_blocks(claims: list[dict[str, Any]], observations: list[dict[str, Any]]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    for row_kind, rows in (("claim", claims), ("observation", observations)):
        for row in rows:
            if row.get("confidence_hint") not in ("", None) and not existing_assessments(row):
                findings.append(
                    {
                        "severity": "warning",
                        "code": "legacy_scalar_without_typed_assessment",
                        "record_kind": row_kind,
                        "record_id": _subject_id(row, row_kind),
                    }
                )
    return {"ready": not findings, "finding_count": len(findings), "findings": findings}


def _adjudication_dict(item: AdjudicationRecord | dict[str, Any]) -> dict[str, Any]:
    if isinstance(item, AdjudicationRecord):
        return item.model_dump()
    return dict(item)


def _require_bounded(value: float) -> float:
    numeric = _bounded_float(value)
    if numeric is None:
        raise ValueError("confidence value is required")
    return numeric


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
