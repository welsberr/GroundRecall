"""R2 deterministic, draft-only extraction from doclift-normalized chunks."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .library_argument_bundle import serialize_library_argument_bundle, validate_library_argument_bundle

SCHEMA_VERSION = "library.argument_bundle.v1"
_CITATION_MARKER = re.compile(
    r"https?://[^\s)\]]+|\bdoi:\s*10\.\d{4,9}/[^\s)\]]+|\b10\.\d{4,9}/[^\s)\]]+|\[\d+(?:[-,]\d+)*\]|\([A-Z][A-Za-z'’-]+(?:\s+et al\.)?,?\s+\d{4}[a-z]?\)"
)
_ROLE_TO_KIND = {
    "claim": "statement", "statement": "statement", "body": "statement",
    "summary": "summary", "premise": "premise", "inference": "inference",
    "conclusion": "conclusion", "evidence": "evidence", "objection": "objection",
    "counterargument": "objection", "rebuttal": "rebuttal", "response": "rebuttal",
    "critique": "critique", "question": "question",
}
_HINT_TO_KIND = (
    ("conclusion_candidate", "conclusion"), ("premise_candidate", "premise"),
    ("evidence_candidate", "evidence"), ("rebuttal_candidate", "rebuttal"),
    ("counterargument_candidate", "objection"), ("objection_candidate", "objection"),
    ("critique_candidate", "critique"), ("question_candidate", "question"),
    ("statement_candidate", "statement"), ("argument_chain_candidate", "statement"),
)


class DocliftArgumentAdapterError(ValueError):
    """Raised for malformed input that cannot produce a safe draft bundle."""


def _digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _id(prefix: str, *parts: Any) -> str:
    material = "\x1f".join(str(part) for part in parts)
    return f"{prefix}.{hashlib.sha256(material.encode()).hexdigest()[:20]}"


def _now(value: str | None) -> str:
    return value or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _kind(chunk: Mapping[str, Any]) -> str:
    role = str(chunk.get("role", "")).strip().lower()
    for hint, candidate_kind in _HINT_TO_KIND:
        if hint in {str(item).strip().lower() for item in chunk.get("analysis_hints", [])}:
            return candidate_kind
    return _ROLE_TO_KIND.get(role, "statement")


def _anchor(chunk: Mapping[str, Any], *, version_id: str, suffix: str = "") -> dict[str, Any]:
    chunk_id = str(chunk.get("chunk_id", "chunk"))
    locator_kind = str(chunk.get("locator_kind", "line"))
    start_key = {"character": "character_start", "page": "page_start", "timestamp": "timestamp_start"}.get(locator_kind, "line_start")
    end_key = {"character": "character_end", "page": "page_end", "timestamp": "timestamp_end"}.get(locator_kind, "line_end")
    span: dict[str, Any] = {
        "span_id": _id("span", version_id, chunk_id, suffix),
        "version_id": version_id,
        "locator_kind": locator_kind,
        "start": chunk.get(start_key, chunk.get("start", 0)),
        "end": chunk.get(end_key, chunk.get("end", chunk.get(start_key, 0))),
        "release_level": "private", "review_state": "draft",
    }
    for key in ("page", "speaker"):
        if key in chunk:
            span[key] = chunk[key]
    if "quoted_text" in chunk:
        span["quoted_text"] = str(chunk["quoted_text"])
    else:
        span["quoted_text"] = str(chunk.get("text", ""))
    return span


def extract_doclift_argument_bundle(
    payload: Mapping[str, Any], *, run_id: str = "", created_at: str | None = None,
    source_id: str = "", document_id: str = "", source_title: str = "",
    canonical_uri: str = "", source_kind: str = "text", document_kind: str = "other",
) -> dict[str, Any]:
    """Extract a private/draft bundle from a chunks object or equivalent JSON.

    This adapter performs no truth, support, alignment, or promotion judgment.
    """
    if not isinstance(payload, Mapping):
        raise DocliftArgumentAdapterError("input must be a JSON object")
    raw_chunks = payload.get("chunks", payload.get("document", {}).get("chunks", []))
    if not isinstance(raw_chunks, list):
        raise DocliftArgumentAdapterError("input must contain a chunks array")
    chunks = [chunk for chunk in raw_chunks if isinstance(chunk, Mapping) and str(chunk.get("text", "")).strip()]
    if not chunks:
        raise DocliftArgumentAdapterError("input contains no non-empty chunks")
    metadata = payload.get("metadata", {}) if isinstance(payload.get("metadata", {}), Mapping) else {}
    source_id = source_id or str(metadata.get("source_id") or payload.get("source_id") or "source.doclift")
    document_id = document_id or str(metadata.get("document_id") or payload.get("document_id") or source_id.replace("source.", "doc.", 1))
    source_title = source_title or str(metadata.get("title") or payload.get("title") or document_id)
    canonical_uri = canonical_uri or str(metadata.get("canonical_uri") or payload.get("canonical_uri") or f"urn:groundrecall:source:{source_id}")
    source_kind = str(metadata.get("source_kind") or payload.get("source_kind") or source_kind)
    document_kind = str(metadata.get("document_kind") or payload.get("document_kind") or document_kind)
    if source_kind not in {"text", "audio", "video", "web_page", "book", "article", "multimedia", "other"}:
        source_kind = "other"
    if document_kind not in {"article", "transcript", "chapter", "post", "recording", "video", "web_page", "other"}:
        document_kind = "other"

    captured_at = _now(created_at)
    input_hash = _digest(payload)
    run_id = run_id or _id("run", input_hash)
    version_id = _id("version", document_id, input_hash)
    source_hash = str(metadata.get("source_hash") or payload.get("source_hash") or input_hash)
    source_provenance = {"origin": "import", "captured_at": captured_at, "agent_or_tool": "groundrecall.r2.doclift-adapter", "run_id": run_id, "input_hash": input_hash}
    extraction_provenance = {"origin": "deterministic", "captured_at": captured_at, "agent_or_tool": "groundrecall.r2.doclift-adapter", "run_id": run_id, "input_hash": input_hash}
    spans: list[dict[str, Any]] = []
    citation_spans: list[dict[str, Any]] = []
    claims: list[dict[str, Any]] = []
    citations: list[dict[str, Any]] = []
    for chunk in chunks:
        chunk_id = str(chunk.get("chunk_id") or _id("chunk", document_id, chunk.get("text", "")))
        span = _anchor(chunk, version_id=version_id)
        spans.append(span)
        claim_id = _id("claim", document_id, chunk_id, chunk.get("text", ""))
        hints = ", ".join(str(item) for item in chunk.get("analysis_hints", []))
        claims.append({"claim_id": claim_id, "text": str(chunk["text"]).strip(), "claim_kind": _kind(chunk), "source_span_ids": [span["span_id"]], "release_level": "private", "review_state": "draft", "provenance": {**extraction_provenance, "notes": f"chunk_role={chunk.get('role', '')}; analysis_hints={hints}"}})
        for index, match in enumerate(_CITATION_MARKER.finditer(str(chunk["text"]))):
            citation_span = _anchor(chunk, version_id=version_id, suffix=f"citation-{index}")
            citation_span["quoted_text"] = match.group(0)
            citation_spans.append(citation_span)
            citations.append({"citation_assertion_id": _id("citation", claim_id, index), "claim_id": claim_id, "target_source_id": source_id, "target_span_ids": [citation_span["span_id"]], "assertion_type": "mentions", "support_status": "unresolved", "release_level": "private", "review_state": "draft", "provenance": {**extraction_provenance, "notes": "citation anchor detected; target and support require review"}})
    spans.extend(citation_spans)
    span_ids = [item["span_id"] for item in spans[:len(chunks)]]
    coverage_id = _id("coverage", document_id, input_hash)
    bundle = {
        "schema_version": SCHEMA_VERSION, "bundle_id": _id("bundle", input_hash), "created_at": captured_at,
        "release_level": "private", "review_state": "draft",
        "knowledge_basis_manifest": {"manifest_id": _id("basis", input_hash), "source_ids": [source_id], "claim_ids": [item["claim_id"] for item in claims], "coverage_audit_ids": [coverage_id], "completeness": "partial", "basis_note": "R2 deterministic draft extraction; no support or truth judgment performed.", "release_level": "private", "review_state": "draft"},
        "sources": [{"source_id": source_id, "source_kind": source_kind, "title": source_title, "canonical_uri": canonical_uri, "source_hash": source_hash, "release_level": "private", "review_state": "draft", "provenance": source_provenance}],
        "documents": [{"document_id": document_id, "source_id": source_id, "document_kind": document_kind, "release_level": "private", "review_state": "draft"}],
        "versions": [{"version_id": version_id, "document_id": document_id, "content_hash": input_hash, "captured_at": captured_at, "normalization": "doclift-normalized-chunks", "tool": "groundrecall.r2.doclift-adapter", "release_level": "private", "review_state": "draft"}],
        "spans": spans, "claim_instances": claims, "canonical_claim_references": [], "argument_relations": [], "citation_assertions": citations, "lineage_candidates": [],
        "coverage_audits": [{"coverage_audit_id": coverage_id, "scope": "non-empty normalized chunks", "expected_span_ids": span_ids, "covered_claim_ids": [item["claim_id"] for item in claims], "status": "complete", "gaps": ["Candidate classification and citation anchors require review."], "release_level": "private", "review_state": "draft"}],
        "review_receipts": [],
    }
    return validate_library_argument_bundle(bundle)


def export_doclift_argument_bundle(input_path: str | Path, output_path: str | Path, **kwargs: Any) -> dict[str, Any]:
    payload = json.loads(Path(input_path).read_text(encoding="utf-8"))
    bundle = extract_doclift_argument_bundle(payload, **kwargs)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(serialize_library_argument_bundle(bundle), encoding="utf-8")
    return bundle


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract draft argument candidates from doclift chunks.")
    parser.add_argument("input_json"); parser.add_argument("output_json")
    parser.add_argument("--source-id", default=""); parser.add_argument("--document-id", default="")
    parser.add_argument("--source-title", default=""); parser.add_argument("--canonical-uri", default="")
    parser.add_argument("--run-id", default=""); parser.add_argument("--created-at", default=None)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    export_doclift_argument_bundle(args.input_json, args.output_json, run_id=args.run_id, created_at=args.created_at, source_id=args.source_id, document_id=args.document_id, source_title=args.source_title, canonical_uri=args.canonical_uri)
