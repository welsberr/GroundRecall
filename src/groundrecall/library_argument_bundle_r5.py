"""R5 private candidate evidence cards and scientific-foundation dossiers.

R5 is deliberately a read-only compiler.  It turns the already anchored R0-R4
bundle into bounded review packets; it does not decide whether a claim is true,
write to GroundRecall, or promote any assertion.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from .library_argument_bundle import validate_library_argument_bundle

_TOOL = "groundrecall.r5.evidence-adjudication"
_DECISIONS = {"pending", "supported", "partially_supported", "not_supported", "insufficient_evidence", "deferred", "dissent"}


def _digest(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _id(prefix: str, *values: Any) -> str:
    raw = "\x1f".join(map(str, values)).encode()
    return f"{prefix}.{hashlib.sha256(raw).hexdigest()[:20]}"


def _tokens(value: str) -> set[str]:
    return {x for x in re.findall(r"[a-z0-9]{3,}", value.lower()) if x not in {"and", "the", "from", "with", "that", "this"}}


def _provenance(captured_at: str, run_id: str, input_hash: str, notes: str) -> dict[str, str]:
    return {"origin": "deterministic", "captured_at": captured_at, "agent_or_tool": _TOOL, "run_id": run_id, "input_hash": input_hash, "notes": notes}


def _source_quality(source: Mapping[str, Any], bibliography: Mapping[str, Any] | None) -> dict[str, Any]:
    """Expose review flags, never a quality score or truth judgment."""
    flags: list[str] = []
    if not source.get("canonical_uri"):
        flags.append("missing_canonical_uri")
    if not source.get("published_at"):
        flags.append("missing_publication_date")
    if not source.get("publisher"):
        flags.append("missing_publisher")
    bib = bibliography or {}
    fields = bib.get("fields", {}) if isinstance(bib.get("fields", {}), Mapping) else {}
    abstract = str(fields.get("abstract") or bib.get("abstract") or "").strip()
    doi = str(fields.get("doi") or bib.get("doi") or "").strip()
    if not abstract:
        flags.append("abstract_unavailable")
    if not doi:
        flags.append("doi_unavailable")
    return {"flags": sorted(flags), "metadata_depth": {"title": bool(source.get("title")), "publisher": bool(source.get("publisher")), "publication_date": bool(source.get("published_at")), "doi": bool(doi), "abstract": bool(abstract)}, "abstract_triage_available": bool(abstract), "quality_assessment": "not_assessed"}


def _domain_candidates(text: str, domains: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    text_tokens = _tokens(text)
    found = []
    for domain in domains:
        domain_id = str(domain.get("domain_id") or domain.get("id") or "")
        label = str(domain.get("label") or domain.get("name") or domain_id)
        keywords = domain.get("keywords", [])
        keyword_tokens = _tokens(" ".join(map(str, keywords)) + " " + label)
        overlap = sorted(text_tokens & keyword_tokens)
        if overlap and domain_id:
            found.append({"domain_id": domain_id, "label": label, "matched_terms": overlap, "match_basis": "lexical_candidate_only", "review_state": "draft"})
    return sorted(found, key=lambda item: (-len(item["matched_terms"]), item["domain_id"]))


def generate_r5_candidates(
    bundle: Mapping[str, Any],
    *,
    bibliography_entries: Mapping[str, Mapping[str, Any]] | Sequence[Mapping[str, Any]] | None = None,
    knowledge_domains: Sequence[Mapping[str, Any]] | None = None,
    created_at: str | None = None,
    run_id: str = "",
) -> dict[str, Any]:
    """Compile deterministic evidence-card and dossier candidates without writes."""
    source_bundle = validate_library_argument_bundle(bundle)
    bibliography: dict[str, Mapping[str, Any]] = {}
    if isinstance(bibliography_entries, Mapping):
        bibliography = {str(k): v for k, v in bibliography_entries.items() if isinstance(v, Mapping)}
    elif bibliography_entries:
        bibliography = {str(item.get("citation_key")): item for item in bibliography_entries if isinstance(item, Mapping) and item.get("citation_key")}
    domains = [dict(item) for item in (knowledge_domains or []) if isinstance(item, Mapping)]
    input_hash = _digest({"bundle": source_bundle, "bibliography": bibliography, "knowledge_domains": domains})
    captured_at = created_at or str(source_bundle["created_at"])
    run_id = run_id or _id("run", input_hash)
    provenance = _provenance(captured_at, run_id, input_hash, "Candidate evidence packet; no scientific truth, support, or source-quality decision was made.")
    sources = {str(item["source_id"]): item for item in source_bundle["sources"]}
    claims = {str(item["claim_id"]): item for item in source_bundle["claim_instances"]}
    spans = {str(item["span_id"]): item for item in source_bundle["spans"]}
    citations_by_claim: dict[str, list[Mapping[str, Any]]] = {}
    for item in source_bundle["citation_assertions"]:
        citations_by_claim.setdefault(str(item["claim_id"]), []).append(item)
    cards: list[dict[str, Any]] = []
    for claim_id in sorted(claims):
        claim = claims[claim_id]
        assertions = sorted(citations_by_claim.get(claim_id, []), key=lambda item: str(item["citation_assertion_id"]))
        if not assertions:
            assertions = [{"citation_assertion_id": "", "target_source_id": "", "target_span_ids": [], "assertion_type": "unresolved", "support_status": "unresolved"}]
        for assertion in assertions:
            source_id = str(assertion.get("target_source_id") or "")
            source = sources.get(source_id, {})
            bib = bibliography.get(source_id) or bibliography.get(str(assertion.get("citation_key") or ""))
            span_ids = sorted(set(map(str, claim.get("source_span_ids", []))) | set(map(str, assertion.get("target_span_ids", []))))
            card_id = _id("evidence-card", claim_id, assertion.get("citation_assertion_id", ""), *span_ids)
            cards.append({
                "evidence_card_id": card_id, "claim_id": claim_id, "claim_text": str(claim["text"]),
                "citation_assertion_id": str(assertion.get("citation_assertion_id") or ""), "source_id": source_id,
                "source_span_ids": span_ids, "evidence_types": ["source_span"] + (["citation_assertion"] if assertion.get("citation_assertion_id") else []),
                "relevance_status": "candidate", "support_status": str(assertion.get("support_status") or "unresolved"),
                "counterevidence": [], "limitations": ["Direct source reading and expert review are still required."],
                "source_quality_flags": _source_quality(source, bib), "reviewer_decision": "pending", "reviewer_rationale": "",
                "knowledge_domain_candidates": _domain_candidates(str(claim["text"]), domains),
                "release_level": "private", "review_state": "draft", "truth_status": "not_assessed", "provenance": provenance,
            })
    dossiers: list[dict[str, Any]] = []
    for domain in sorted(domains, key=lambda item: str(item.get("domain_id") or item.get("id") or "")):
        domain_id = str(domain.get("domain_id") or domain.get("id") or "")
        related = [card["evidence_card_id"] for card in cards if any(item["domain_id"] == domain_id for item in card["knowledge_domain_candidates"])]
        dossiers.append({"dossier_id": _id("dossier", domain_id), "domain_id": domain_id, "label": str(domain.get("label") or domain.get("name") or domain_id), "description": str(domain.get("description") or ""), "evidence_card_ids": sorted(related), "grouping_basis": "lexical_candidate_only", "scientific_status": "not_assessed", "review_state": "draft", "release_level": "private", "provenance": provenance})
    adjudications = [{"adjudication_id": _id("adjudication", card["evidence_card_id"]), "evidence_card_id": card["evidence_card_id"], "decision": "pending", "reviewer_id": "", "rationale": "", "counterevidence_considered": [], "limitations_acknowledged": [], "review_state": "draft", "release_level": "private", "provenance": provenance} for card in cards]
    return {"r5_schema_version": "library.argument_bundle.r5.candidate-evidence.v1", "bundle_id": str(source_bundle["bundle_id"]), "release_level": "private", "review_state": "draft", "evidence_cards": cards, "foundation_dossiers": dossiers, "adjudications": adjudications, "boundary": "Candidate scaffolding only; no scientific truth is asserted and expert review is required.", "provenance": provenance}


def record_r5_adjudication(candidate: Mapping[str, Any], *, reviewer_id: str, decision: str, rationale: str, counterevidence_considered: Sequence[str] = (), limitations_acknowledged: Sequence[str] = (), reviewed_at: str = "") -> dict[str, Any]:
    """Return a draft review record; this function never persists or promotes it."""
    if decision not in _DECISIONS:
        raise ValueError(f"unsupported R5 decision: {decision}")
    result = copy.deepcopy(dict(candidate))
    result.update({"decision": decision, "reviewer_id": reviewer_id, "rationale": rationale, "counterevidence_considered": sorted(map(str, counterevidence_considered)), "limitations_acknowledged": sorted(map(str, limitations_acknowledged)), "reviewed_at": reviewed_at, "review_state": "draft", "release_level": "private", "truth_status": "not_assessed"})
    return result


def export_r5_candidates(input_path: str | Path, output_path: str | Path, *, bibliography_path: str | Path | None = None, domains_path: str | Path | None = None, **kwargs: Any) -> dict[str, Any]:
    bundle = json.loads(Path(input_path).read_text(encoding="utf-8"))
    bibliography = json.loads(Path(bibliography_path).read_text(encoding="utf-8")) if bibliography_path else None
    domains = json.loads(Path(domains_path).read_text(encoding="utf-8")) if domains_path else None
    result = generate_r5_candidates(bundle, bibliography_entries=bibliography, knowledge_domains=domains, **kwargs)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate private/draft R5 evidence-card and foundation-dossier candidates.")
    parser.add_argument("input_json"); parser.add_argument("output_json"); parser.add_argument("--bibliography", default=None); parser.add_argument("--knowledge-domains", default=None); parser.add_argument("--run-id", default=""); parser.add_argument("--created-at", default=None)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    print(json.dumps(export_r5_candidates(args.input_json, args.output_json, bibliography_path=args.bibliography, domains_path=args.knowledge_domains, run_id=args.run_id, created_at=args.created_at), indent=2, sort_keys=True))
