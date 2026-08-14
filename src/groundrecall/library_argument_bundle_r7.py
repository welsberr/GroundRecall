"""R7 deterministic end-to-end readiness evaluation for Library bundles.

R7 composes the existing handoff, audit, lineage, evidence, and preflight
contracts into one inspection report.  It is deliberately report-only:
inputs are copied by the underlying APIs and this module never opens a store,
promotes a record, or publishes an artifact.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .library_argument_bundle import validate_library_argument_bundle
from .library_argument_bundle_audit import audit_library_argument_bundle
from .library_argument_bundle_r4 import generate_r4_candidates
from .library_argument_bundle_r5 import generate_r5_candidates
from .library_argument_bundle_r6 import compile_knowledge_basis_manifest, preflight_library_argument_bundle

SCHEMA_VERSION = "groundrecall.library-argument-bundle-r7.e2e-readiness.v1"
_COLLECTION_IDS = {
    "sources": "source_id", "documents": "document_id", "versions": "version_id",
    "spans": "span_id", "claim_instances": "claim_id",
    "canonical_claim_references": "canonical_claim_ref_id", "argument_relations": "relation_id",
    "citation_assertions": "citation_assertion_id", "lineage_candidates": "lineage_candidate_id",
    "coverage_audits": "coverage_audit_id", "review_receipts": "receipt_id",
}


def _hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _id(prefix: str, *values: Any) -> str:
    material = "\x1f".join(map(str, values)).encode()
    return f"{prefix}.{hashlib.sha256(material).hexdigest()[:24]}"


def _rows(value: Any) -> list[Mapping[str, Any]]:
    return [row for row in value if isinstance(row, Mapping)] if isinstance(value, list) else []


def _artifacts(value: Mapping[str, Any], collections: Mapping[str, str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for collection, id_key in collections.items():
        rows = _rows(value.get(collection))
        result[collection] = {"count": len(rows), "ids": sorted(str(row[id_key]) for row in rows if row.get(id_key))}
    return result


def _phase(name: str, status: str, *, artifacts: Mapping[str, Any] | None = None, detail: str = "", error: str = "") -> dict[str, Any]:
    result: dict[str, Any] = {"phase": name, "status": status, "automated": True, "detail": detail}
    if artifacts is not None:
        result["artifacts"] = dict(artifacts)
    if error:
        result["error"] = error
    return result


def evaluate_library_argument_bundle(
    bundle: Mapping[str, Any],
    *,
    r5: Mapping[str, Any] | None = None,
    target: str = "public",
    as_of: str | None = None,
    max_age_days: int | None = None,
) -> dict[str, Any]:
    """Evaluate the R0-R6 chain and return a stable, read-only readiness report."""
    if target not in {"public", "downstream"}:
        raise ValueError("target must be 'public' or 'downstream'")
    original = copy.deepcopy(dict(bundle))
    input_hash = _hash({"bundle": original, "r5": r5, "target": target, "as_of": as_of, "max_age_days": max_age_days})
    phases: list[dict[str, Any]] = []
    unresolved: list[str] = []
    blockers: list[dict[str, str]] = []
    validated: dict[str, Any] | None = None
    audit: dict[str, Any] | None = None
    r4: dict[str, Any] | None = None
    packet: Mapping[str, Any] | None = r5
    manifest: dict[str, Any] | None = None
    preflight: dict[str, Any] | None = None

    # R0/R1: the contract validator is the authoritative boundary.
    try:
        schema_version = str(bundle.get("schema_version", "")) if isinstance(bundle, Mapping) else ""
        validated = validate_library_argument_bundle(bundle)
        phases.append(_phase("R0-contract", "passed", detail=f"validated {schema_version}"))
        phases.append(_phase("R1-handoff", "passed", artifacts=_artifacts(validated, _COLLECTION_IDS), detail="identity and references are closed"))
    except Exception as exc:
        reason = str(exc)
        phases.extend([_phase("R0-contract", "blocked", detail="bundle contract validation failed", error=reason), _phase("R1-handoff", "not_run", detail="requires a valid R0 contract")])
        blockers.append({"phase": "R0-contract", "reason": reason})

    # R2 is an inspection of the supplied anchored bundle, not a claim that a
    # producer corpus has been exhaustively ingested.
    if validated is not None:
        anchored = all(_rows(validated.get(key)) for key in ("sources", "documents", "versions", "spans", "claim_instances"))
        status = "passed" if anchored else "blocked"
        phases.append(_phase("R2-adapter-coverage", status, artifacts=_artifacts(validated, _COLLECTION_IDS), detail="anchored bundle records are available" if anchored else "one or more required anchored collections are empty"))
        if not anchored:
            blockers.append({"phase": "R2-adapter-coverage", "reason": "required anchored collections are empty"})
    else:
        phases.append(_phase("R2-adapter-coverage", "not_run", detail="requires a valid R0 contract"))

    if validated is not None:
        audit = audit_library_argument_bundle(validated)
        audit_artifacts = {"audit_id": audit["audit_id"], "finding_count": audit["finding_count"], "candidate_count": audit["candidate_count"]}
        phases.append(_phase("R3-audit", "passed" if audit["finding_count"] == 0 else "blocked", artifacts=audit_artifacts, detail="deterministic completeness and review audit"))
        unresolved.extend(str(item["reason"]) for item in audit["findings"])
        if audit["public_release_blocker_count"]:
            blockers.append({"phase": "R3-audit", "reason": f"{audit['public_release_blocker_count']} public-release audit blockers"})

        try:
            r4 = generate_r4_candidates(validated, validated.get("canonical_claim_references", []))
            phases.append(_phase("R4-lineage", "passed", artifacts=_artifacts(r4, {"canonical_claim_references": "canonical_claim_ref_id", "lineage_candidates": "lineage_candidate_id"}), detail="candidate claim-family and lineage chain exercised"))
        except Exception as exc:
            phases.append(_phase("R4-lineage", "blocked", detail="lineage candidate generation failed", error=str(exc)))
            blockers.append({"phase": "R4-lineage", "reason": str(exc)})

        if packet is None:
            packet = generate_r5_candidates(validated)
            packet_origin = "generated deterministically from supplied bundle"
        else:
            packet = copy.deepcopy(dict(packet))
            packet_origin = "supplied R5 packet inspected read-only"
        phases.append(_phase("R5-evidence", "passed", artifacts=_artifacts(packet, {"evidence_cards": "evidence_card_id", "foundation_dossiers": "dossier_id", "adjudications": "adjudication_id"}), detail=packet_origin))

        manifest = compile_knowledge_basis_manifest(validated, r5=packet, as_of=as_of)
        preflight = preflight_library_argument_bundle(validated, r5=packet, target=target, as_of=as_of, max_age_days=max_age_days)
        phases.append(_phase("R6-preflight", "passed" if preflight["passed"] else "blocked", artifacts={"manifest_id": manifest["manifest_id"], "preflight_id": preflight["preflight_id"]}, detail="knowledge-basis manifest and release gates evaluated"))
        unresolved.extend(str(gap) for gap in manifest["unresolved_gaps"])
        unresolved.extend(str(item["reason"]) for item in preflight["findings"])
        blockers.extend({"phase": "R6-preflight", "reason": str(item["reason"])} for item in preflight["findings"])
    else:
        phases.extend([_phase("R3-audit", "not_run", detail="requires a valid R0 contract"), _phase("R4-lineage", "not_run", detail="requires a valid R0 contract"), _phase("R5-evidence", "not_run", detail="requires a valid R0 contract"), _phase("R6-preflight", "not_run", detail="requires a valid R0 contract")])

    automated_coverage = [
        "R0-R1 schema, identity, and reference-integrity validation",
        "R3 deterministic completeness/review audit",
        "R4 deterministic candidate claim-family and lineage generation",
        "R5 deterministic evidence-card and dossier scaffolding",
        "R6 mechanical review, provenance, citation, completeness, rights, privacy, and freshness gates",
        "read-only/no-promotion/no-database-write report boundary",
    ]
    corpus_work = [
        "confirm corpus coverage and ingest any documents, versions, spans, or claims absent from the supplied bundle",
        "human review of candidate claim families and lineage; lexical/citation signals are not truth or influence",
        "direct source reading, expert adjudication, counterevidence, and limitations for each evidence card",
        "resolve audit gaps, provenance/rights metadata, supported citations, and release-state decisions",
    ]
    if not unresolved:
        corpus_work = ["perform corpus-specific expert review and release approval even though no mechanical gaps were reported"]
    blockers = sorted({(item["phase"], item["reason"]): item for item in blockers}.values(), key=lambda item: (item["phase"], item["reason"]))
    unresolved = sorted(set(unresolved))
    ready = not blockers and all(item["status"] == "passed" for item in phases)
    return {
        "schema_version": SCHEMA_VERSION,
        "evaluation_id": _id("r7-evaluation", input_hash),
        "input_hash": input_hash,
        "bundle_id": str((validated or bundle).get("bundle_id", "")),
        "target": target,
        "ready": ready,
        "release_allowed": ready,
        "phase_status": phases,
        "artifact_summary": {"bundle": _artifacts(validated or bundle, _COLLECTION_IDS), "audit": {"audit_id": audit["audit_id"], "finding_count": audit["finding_count"]} if audit else {}, "r4": _artifacts(r4 or {}, {"lineage_candidates": "lineage_candidate_id"}), "r5": _artifacts(packet or {}, {"evidence_cards": "evidence_card_id", "foundation_dossiers": "dossier_id", "adjudications": "adjudication_id"}), "r6": {"manifest_id": manifest["manifest_id"], "preflight_id": preflight["preflight_id"]} if manifest and preflight else {}},
        "unresolved_gaps": unresolved,
        "release_blockers": blockers,
        "coverage": {"automated": automated_coverage, "corpus_specific_work_required": corpus_work},
        "boundary": "Report only; no GroundRecall database write, promotion, or publication occurred.",
        "provenance": {"origin": "deterministic", "agent_or_tool": "groundrecall.r7.e2e-readiness", "input_hash": input_hash, "notes": "R0-R6 chain evaluation; private/draft report"},
    }


def evaluate_library_argument_bundle_file(input_path: str | Path, output_path: str | Path, **kwargs: Any) -> dict[str, Any]:
    bundle = json.loads(Path(input_path).read_text(encoding="utf-8"))
    r5_path = kwargs.pop("r5_path", None)
    r5 = json.loads(Path(r5_path).read_text(encoding="utf-8")) if r5_path else None
    report = evaluate_library_argument_bundle(bundle, r5=r5, **kwargs)
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a deterministic, read-only R0-R6 end-to-end readiness evaluation.")
    parser.add_argument("input_json"); parser.add_argument("output_json"); parser.add_argument("--r5", default=None)
    parser.add_argument("--target", choices=("public", "downstream"), default="public"); parser.add_argument("--as-of", default=None); parser.add_argument("--max-age-days", type=int, default=None)
    parser.add_argument("--fail-on-blockers", action="store_true", help="exit 2 when the report is not ready")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = evaluate_library_argument_bundle_file(args.input_json, args.output_json, r5_path=args.r5, target=args.target, as_of=args.as_of, max_age_days=args.max_age_days)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    if args.fail_on_blockers and not report["ready"]:
        raise SystemExit(2)
