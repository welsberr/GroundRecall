"""R4 candidate-only claim-family alignment and argument lineage generation.

This module deliberately produces review work, not canonical truth.  Wording
similarity and citation topology are recorded as signals and are never treated
as support, entailment, or evidence that a claim is true.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .library_argument_bundle import SCHEMA_VERSION, serialize_library_argument_bundle, validate_library_argument_bundle

_STOPWORDS = {"a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "is", "of", "on", "or", "that", "the", "this", "to", "with"}
_TOOL = "groundrecall.r4.claim-family-lineage"


def _digest(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _id(prefix: str, *values: Any) -> str:
    material = "\x1f".join(map(str, values)).encode()
    return f"{prefix}.{hashlib.sha256(material).hexdigest()[:20]}"


def _tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", text.lower()) if len(token) > 2 and token not in _STOPWORDS}


def _similarity(left: str, right: str) -> float:
    a, b = _tokens(left), _tokens(right)
    return round(len(a & b) / len(a | b), 3) if a and b else 0.0


def _provenance(captured_at: str, run_id: str, input_hash: str, notes: str) -> dict[str, str]:
    return {"origin": "deterministic", "captured_at": captured_at, "agent_or_tool": _TOOL, "run_id": run_id, "input_hash": input_hash, "notes": notes}


def _reference_text(reference: Mapping[str, Any]) -> str:
    return str(reference.get("text") or reference.get("claim_text") or reference.get("label") or reference.get("description") or "")


def _reference(reference: Mapping[str, Any], *, status: str, evidence_span_ids: list[str], match_type: str, confidence: float, rationale: str, provenance: dict[str, str]) -> dict[str, Any]:
    ref_id = str(reference.get("canonical_claim_ref_id") or _id("ref", reference.get("namespace", "groundrecall.claim-family"), reference.get("key", "")))
    result = {
        "canonical_claim_ref_id": ref_id,
        "namespace": str(reference.get("namespace") or "groundrecall.claim-family"),
        "key": str(reference.get("key") or ref_id),
        "match_status": status,
        "release_level": "private",
        "review_state": "draft",
        "evidence_span_ids": sorted(set(evidence_span_ids)),
        "match_type": match_type,
        "confidence": confidence,
        "rationale": rationale,
        "evidence_basis": "similarity_only",
        "truth_status": "not_assessed",
        "provenance": provenance,
    }
    if reference.get("label"):
        result["label"] = str(reference["label"])
    return result


def generate_r4_candidates(
    payload: Mapping[str, Any],
    canonical_references: Sequence[Mapping[str, Any]] | None = None,
    *,
    threshold: float = 0.2,
    created_at: str | None = None,
    run_id: str = "",
) -> dict[str, Any]:
    """Return a deterministic copy containing unresolved refs and lineage candidates."""
    bundle = validate_library_argument_bundle(payload)
    references = [dict(item) for item in (canonical_references or []) if isinstance(item, Mapping)]
    input_hash = _digest({"bundle": bundle, "canonical_references": references, "threshold": threshold})
    captured_at = created_at or str(bundle["created_at"])
    run_id = run_id or _id("run", input_hash)
    provenance = _provenance(captured_at, run_id, input_hash, "Candidate alignment; similarity/citation topology are not truth or support.")
    output = copy.deepcopy(bundle)
    refs_by_id = {str(item["canonical_claim_ref_id"]): item for item in output["canonical_claim_references"]}
    claim_by_id = {str(item["claim_id"]): item for item in output["claim_instances"]}
    generated_refs: dict[str, dict[str, Any]] = {}

    # Match each claim to a supplied canonical reference, or create an
    # unresolved family key. No reference is accepted or promoted here.
    for claim in sorted(output["claim_instances"], key=lambda item: str(item["claim_id"])):
        candidates = []
        for reference in references:
            score = _similarity(str(claim["text"]), _reference_text(reference))
            if score >= threshold:
                candidates.append((score, str(reference.get("canonical_claim_ref_id") or _id("ref", reference.get("namespace", ""), reference.get("key", ""))), reference))
        if candidates:
            score, ref_id, reference = sorted(candidates, key=lambda item: (-item[0], item[1]))[0]
            if ref_id not in refs_by_id:
                refs_by_id[ref_id] = _reference(reference, status="candidate", evidence_span_ids=list(claim["source_span_ids"]), match_type="text_similarity", confidence=score, rationale="Lexical overlap with a supplied canonical reference; human review must decide whether the claim family is the same.", provenance=provenance)
            claim["canonical_claim_ref_ids"] = sorted(set(claim.get("canonical_claim_ref_ids", [])) | {ref_id})
        else:
            tokens = "-".join(sorted(_tokens(str(claim["text"])))) or "unresolved"
            family_id = _id("ref", "groundrecall.claim-family", tokens)
            if family_id not in generated_refs:
                generated_refs[family_id] = _reference({"canonical_claim_ref_id": family_id, "namespace": "groundrecall.claim-family", "key": tokens, "label": str(claim["text"])[:120]}, status="unresolved", evidence_span_ids=list(claim["source_span_ids"]), match_type="unresolved", confidence=0.0, rationale="No supplied canonical reference met the threshold; this is an unresolved claim-family review item.", provenance=provenance)
            else:
                generated_refs[family_id]["evidence_span_ids"] = sorted(set(generated_refs[family_id]["evidence_span_ids"]) | set(claim["source_span_ids"]))
            claim["canonical_claim_ref_ids"] = sorted(set(claim.get("canonical_claim_ref_ids", [])) | {family_id})
    refs_by_id.update(generated_refs)
    output["canonical_claim_references"] = [refs_by_id[key] for key in sorted(refs_by_id)]

    spans_by_id = {str(item["span_id"]): item for item in output["spans"]}
    document_by_version = {str(item["version_id"]): str(item["document_id"]) for item in output["versions"]}
    document_by_id = {str(item["document_id"]): item for item in output["documents"]}
    claim_document: dict[str, str] = {}
    for claim in output["claim_instances"]:
        docs = {document_by_version.get(str(spans_by_id[span_id]["version_id"])) for span_id in claim["source_span_ids"] if span_id in spans_by_id}
        if len(docs) == 1:
            claim_document[str(claim["claim_id"])] = next(iter(docs))
    citation_targets: dict[str, set[str]] = {}
    for citation in output["citation_assertions"]:
        citation_targets.setdefault(str(citation["claim_id"]), set()).add(str(citation["target_source_id"]))
    candidates: list[dict[str, Any]] = []
    claims = sorted(output["claim_instances"], key=lambda item: str(item["claim_id"]))
    for index, left in enumerate(claims):
        for right in claims[index + 1:]:
            left_doc, right_doc = claim_document.get(str(left["claim_id"])), claim_document.get(str(right["claim_id"]))
            if not left_doc or not right_doc or left_doc == right_doc:
                continue
            score = _similarity(str(left["text"]), str(right["text"]))
            left_source = str(document_by_id[left_doc]["source_id"]); right_source = str(document_by_id[right_doc]["source_id"])
            explicit_left = right_source in citation_targets.get(str(left["claim_id"]), set())
            explicit_right = left_source in citation_targets.get(str(right["claim_id"]), set())
            if score < threshold and not (explicit_left or explicit_right):
                continue
            if explicit_left or explicit_right:
                from_doc, to_doc = (left_doc, right_doc) if explicit_left else (right_doc, left_doc)
                lineage_type, basis = "explicit_citation", "citation_topology"
            elif score >= 0.75:
                from_doc, to_doc, lineage_type, basis = sorted([left_doc, right_doc]) + ["shared_phrase", "similarity"]
            elif score >= 0.5:
                from_doc, to_doc, lineage_type, basis = sorted([left_doc, right_doc]) + ["shared_argument", "similarity"]
            else:
                from_doc, to_doc, lineage_type, basis = sorted([left_doc, right_doc]) + ["independent_recurrence", "similarity"]
            evidence = sorted(set(left["source_span_ids"]) | set(right["source_span_ids"]))
            candidates.append({"lineage_candidate_id": _id("lineage", from_doc, to_doc, lineage_type, *evidence), "from_document_id": from_doc, "to_document_id": to_doc, "lineage_type": lineage_type, "evidence_span_ids": evidence, "confidence": round(max(score, 0.55 if basis == "citation_topology" else score), 3), "release_level": "private", "review_state": "draft", "provenance": _provenance(captured_at, run_id, input_hash, f"{basis}; similarity/citation topology only; truth and support not assessed."), "evidence_claim_ids": sorted([str(left["claim_id"]), str(right["claim_id"])]), "evidence_basis": basis, "truth_status": "not_assessed", "rationale": "Candidate shared wording/argument or citation topology. It does not establish support, influence, entailment, or truth; independent recurrence requires review."})
    output["lineage_candidates"] = sorted(candidates, key=lambda item: str(item["lineage_candidate_id"]))
    return validate_library_argument_bundle(output)


def align_claim_families(payload: Mapping[str, Any], canonical_references: Sequence[Mapping[str, Any]] | None = None, **kwargs: Any) -> dict[str, Any]:
    return generate_r4_candidates(payload, canonical_references, **kwargs)


def export_r4_candidates(input_path: str | Path, output_path: str | Path, references_path: str | Path | None = None, **kwargs: Any) -> dict[str, Any]:
    payload = json.loads(Path(input_path).read_text(encoding="utf-8"))
    references = json.loads(Path(references_path).read_text(encoding="utf-8")) if references_path else []
    result = generate_r4_candidates(payload, references if isinstance(references, list) else references.get("canonical_claim_references", []), **kwargs)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(serialize_library_argument_bundle(result), encoding="utf-8")
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate private/draft R4 claim-family and lineage candidates.")
    parser.add_argument("input_json"); parser.add_argument("output_json"); parser.add_argument("--canonical-references", default=None)
    parser.add_argument("--threshold", type=float, default=0.2); parser.add_argument("--run-id", default=""); parser.add_argument("--created-at", default=None)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    print(json.dumps(export_r4_candidates(args.input_json, args.output_json, args.canonical_references, threshold=args.threshold, run_id=args.run_id, created_at=args.created_at), indent=2, sort_keys=True))
