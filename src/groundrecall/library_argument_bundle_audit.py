"""R3 read-only completeness and review audit for argument bundles.

The audit deliberately accepts malformed draft payloads so that missing
references become review work instead of disappearing behind R1 validation.
It never opens a GroundRecall store and never changes the supplied payload.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

SCHEMA_VERSION = "groundrecall.library-argument-bundle-audit.v1"
_REVIEWED = {"reviewed", "promoted", "public", "verified"}
_COLLECTIONS = {
    "sources": "source_id", "documents": "document_id", "versions": "version_id",
    "spans": "span_id", "claim_instances": "claim_id",
    "canonical_claim_references": "canonical_claim_ref_id",
    "argument_relations": "relation_id", "citation_assertions": "citation_assertion_id",
    "lineage_candidates": "lineage_candidate_id", "coverage_audits": "coverage_audit_id",
    "review_receipts": "receipt_id",
}


def _hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _id(prefix: str, *parts: Any) -> str:
    material = "\x1f".join(map(str, parts))
    return f"{prefix}.{hashlib.sha256(material.encode()).hexdigest()[:24]}"


def _rows(bundle: Mapping[str, Any], collection: str) -> list[dict[str, Any]]:
    value = bundle.get(collection, [])
    return [dict(row) for row in value if isinstance(row, Mapping)] if isinstance(value, list) else []


def _audit_time(bundle: Mapping[str, Any]) -> str:
    value = bundle.get("created_at")
    return str(value) if isinstance(value, str) and value else "1970-01-01T00:00:00Z"


def audit_library_argument_bundle(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Build stable findings and private/draft review candidates without writes."""
    if not isinstance(payload, Mapping):
        raise TypeError("bundle must be a JSON object")
    bundle = copy.deepcopy(dict(payload))
    digest = _hash(bundle)
    bundle_id = str(bundle.get("bundle_id") or _id("bundle", digest))
    captured_at = _audit_time(bundle)
    provenance = {
        "origin": "deterministic", "captured_at": captured_at,
        "agent_or_tool": "groundrecall.r3.argument-bundle-audit",
        "input_hash": "sha256:" + digest,
        "notes": "read-only audit; no promotion or database write",
    }
    findings: list[dict[str, Any]] = []

    def add(code: str, subject_type: str, subject_id: str, reason: str, *, priority: int = 50,
            blocks_public: bool = True) -> None:
        finding_id = _id("finding", bundle_id, code, subject_type, subject_id, reason)
        findings.append({
            "finding_id": finding_id, "code": code, "severity": "blocker" if blocks_public else "warning",
            "priority": priority, "reason": reason, "subject_type": subject_type,
            "subject_id": subject_id, "blocks_public_release": blocks_public,
            "release_level": "private", "review_state": "draft", "provenance": provenance,
        })

    ids = {name: {str(row.get(key)) for row in _rows(bundle, name) if row.get(key)} for name, key in _COLLECTIONS.items()}
    claims = _rows(bundle, "claim_instances")
    spans = {str(row.get("span_id")): row for row in _rows(bundle, "spans") if row.get("span_id")}
    versions = ids["versions"]
    relations = _rows(bundle, "argument_relations")
    citations = _rows(bundle, "citation_assertions")
    receipts = {(str(row.get("subject_type")), str(row.get("subject_id"))) for row in _rows(bundle, "review_receipts")}

    for claim in claims:
        claim_id = str(claim.get("claim_id", ""))
        if str(claim.get("review_state", "draft")) not in _REVIEWED and ("claim", claim.get("claim_id")) not in receipts:
            add("claim_unreviewed", "claim", claim_id, "claim has no reviewed receipt or reviewed state", priority=30)
        source_span_ids = claim.get("source_span_ids")
        if not isinstance(source_span_ids, list) or not source_span_ids:
            add("source_span_missing", "claim", claim_id, "claim has no source span", priority=10)
        else:
            for span_id in source_span_ids:
                span = spans.get(str(span_id))
                if span is None:
                    add("source_span_missing", "claim", claim_id, f"claim references unknown span {span_id}", priority=10)
                elif str(span.get("version_id", "")) not in versions:
                    add("source_span_invalid", "claim", claim_id, f"span {span_id} references unknown version", priority=10)
                else:
                    try:
                        if float(span.get("start")) > float(span.get("end")):
                            add("source_span_invalid", "claim", claim_id, f"span {span_id} starts after it ends", priority=10)
                    except (TypeError, ValueError):
                        add("source_span_invalid", "claim", claim_id, f"span {span_id} has non-numeric coordinates", priority=10)

    linked = {str(value) for relation in relations for value in (relation.get("from_claim_id"), relation.get("to_claim_id"))}
    if len(claims) > 1:
        for claim in claims:
            claim_id = str(claim.get("claim_id", ""))
            if claim_id not in linked:
                add("argument_link_missing", "claim", claim_id, "claim has no argument relation to another claim", priority=40)

    for span_id, span in spans.items():
        if str(span.get("version_id", "")) not in versions:
            add("source_span_invalid", "span", span_id, "span references an unknown version", priority=10)
        else:
            try:
                if float(span.get("start")) > float(span.get("end")):
                    add("source_span_invalid", "span", span_id, "span starts after it ends", priority=10)
            except (TypeError, ValueError):
                add("source_span_invalid", "span", span_id, "span has non-numeric coordinates", priority=10)

    for citation in citations:
        status = str(citation.get("support_status", "unresolved"))
        citation_id = str(citation.get("citation_assertion_id", ""))
        if status in {"unresolved", "claimed", "partial"} or str(citation.get("review_state", "draft")) not in _REVIEWED:
            add("citation_unresolved", "citation_assertion", citation_id, f"citation support status is {status!r}", priority=20)
        if str(citation.get("claim_id", "")) not in ids["claim_instances"]:
            add("citation_invalid_reference", "citation_assertion", citation_id, "citation references an unknown claim", priority=10)
        if str(citation.get("target_source_id", "")) not in ids["sources"]:
            add("citation_invalid_reference", "citation_assertion", citation_id, "citation references an unknown source", priority=10)
        for span_id in citation.get("target_span_ids", []) if isinstance(citation.get("target_span_ids"), list) else []:
            if str(span_id) not in spans:
                add("citation_invalid_reference", "citation_assertion", citation_id, f"citation references an unknown span {span_id}", priority=10)

    audits = _rows(bundle, "coverage_audits")
    covered_by_claim = {str(span_id) for claim in claims for span_id in (claim.get("source_span_ids") or [])}
    manifest = bundle.get("knowledge_basis_manifest") if isinstance(bundle.get("knowledge_basis_manifest"), Mapping) else {}
    if manifest.get("completeness") != "complete":
        add("coverage_incomplete", "knowledge_basis_manifest", str(manifest.get("manifest_id", bundle_id)), "knowledge basis completeness is not complete", priority=35)
    for audit in audits:
        audit_id = str(audit.get("coverage_audit_id", ""))
        gaps = audit.get("gaps") if isinstance(audit.get("gaps"), list) else []
        expected = {str(value) for value in (audit.get("expected_span_ids") or [])}
        if str(audit.get("status")) != "complete" or gaps or expected - covered_by_claim:
            reason = "coverage audit is incomplete"
            if expected - covered_by_claim:
                reason += "; expected spans lack claim coverage"
            add("coverage_incomplete", "coverage_audit", audit_id, reason, priority=35)

    non_private = str(bundle.get("release_level", "private")) != "private"
    if non_private:
        add("public_release_blocker", "bundle", bundle_id, "audit output must remain private and draft", priority=1)
    for collection in _COLLECTIONS:
        for row in _rows(bundle, collection):
            subject_id = str(row.get(_COLLECTIONS[collection], ""))
            if row.get("release_level", "private") != "public" or str(row.get("review_state", "draft")) not in _REVIEWED:
                add("public_release_blocker", collection[:-1], subject_id, f"{collection} record is not reviewed and public-safe", priority=5)

    findings.sort(key=lambda row: (row["priority"], row["code"], row["subject_type"], row["subject_id"], row["finding_id"]))
    candidates = []
    for finding in findings:
        candidates.append({
            "review_candidate_id": _id("review_candidate", bundle_id, finding["finding_id"]),
            "candidate_type": finding["subject_type"], "candidate_id": finding["subject_id"],
            "subject_ids": [finding["subject_id"]], "finding_codes": [finding["code"]],
            "reason": finding["reason"], "priority": finding["priority"], "current_status": "needs_review",
            "triage_lane": "source_cleanup" if "span" in finding["code"] or "citation" in finding["code"] else "knowledge_capture",
            "release_level": "private", "review_state": "draft", "provenance": provenance,
        })
    return {
        "schema_version": SCHEMA_VERSION, "audit_id": _id("audit", bundle_id, digest),
        "bundle_id": bundle_id, "input_hash": "sha256:" + digest,
        "release_level": "private", "review_state": "draft", "promoted": False,
        "finding_count": len(findings), "candidate_count": len(candidates),
        "public_release_blocker_count": sum(row["blocks_public_release"] for row in findings),
        "findings": findings, "review_candidates": candidates, "provenance": provenance,
    }


def audit_library_argument_bundle_file(input_path: str | Path, output_path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(input_path).read_text(encoding="utf-8"))
    result = audit_library_argument_bundle(payload)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit a library.argument_bundle.v1 without promotion or database writes.")
    parser.add_argument("input_json"); parser.add_argument("output_json")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    print(json.dumps(audit_library_argument_bundle_file(args.input_json, args.output_json), indent=2, sort_keys=True))
