"""R6 knowledge-basis manifests and release preflight.

This module is intentionally a boundary tool: it reads an R0-R5 handoff,
compiles deterministic inspection metadata, and reports release blockers.  It
never promotes records, opens a store, or publishes an artifact.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from .library_argument_bundle import validate_library_argument_bundle

_REVIEWED = {"reviewed", "promoted", "public", "verified"}
_SUPPORT = {"supported", "partially_supported", "verified"}
_PRIVATE = {"private", "confidential", "restricted", "privileged", "nonpublic", "no_export", "do_not_export"}


def _hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _id(prefix: str, *values: Any) -> str:
    material = "\x1f".join(map(str, values)).encode()
    return f"{prefix}.{hashlib.sha256(material).hexdigest()[:24]}"


def _rows(value: Any) -> list[Mapping[str, Any]]:
    return [row for row in value if isinstance(row, Mapping)] if isinstance(value, list) else []


def _status(rows: list[Mapping[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key, "missing"))
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def compile_knowledge_basis_manifest(
    bundle: Mapping[str, Any],
    *,
    r5: Mapping[str, Any] | None = None,
    as_of: str | None = None,
    run_id: str = "",
) -> dict[str, Any]:
    """Compile a stable private/draft manifest from validated R0-R5 data."""
    source_bundle = validate_library_argument_bundle(bundle)
    packet = copy.deepcopy(dict(r5 or {}))
    bundle_hash = _hash(source_bundle)
    manifest_input = {"bundle": source_bundle, "r5": packet, "as_of": as_of or source_bundle["created_at"]}
    input_hash = _hash(manifest_input)
    captured_at = as_of or str(source_bundle["created_at"])
    manifest_id = _id("knowledge-basis", source_bundle["bundle_id"], input_hash)
    sources = _rows(source_bundle["sources"])
    versions = _rows(source_bundle["versions"])
    claims = _rows(source_bundle["claim_instances"])
    audits = _rows(source_bundle["coverage_audits"])
    cards = _rows(packet.get("evidence_cards"))
    adjudications = _rows(packet.get("adjudications"))
    dossiers = _rows(packet.get("foundation_dossiers"))
    manifest = {
        "schema_version": "groundrecall.library-argument-bundle-r6.knowledge-basis.v1",
        "manifest_id": manifest_id,
        "bundle_id": str(source_bundle["bundle_id"]),
        "input_hash": input_hash,
        "bundle_hash": bundle_hash,
        "run_id": run_id or _id("run", input_hash),
        "as_of": captured_at,
        "release_level": "private",
        "review_state": "draft",
        "source_ids": sorted(str(row["source_id"]) for row in sources),
        "sources": [{"source_id": str(row["source_id"]), "source_hash": row.get("source_hash"), "version_ids": sorted(str(v["version_id"]) for v in versions if str(v.get("document_id")) in {str(d["document_id"]) for d in _rows(source_bundle["documents"]) if str(d.get("source_id")) == str(row["source_id"])}), "review_state": str(row.get("review_state", "draft")), "release_level": str(row.get("release_level", "private")), "accessed_at": row.get("accessed_at"), "published_at": row.get("published_at"), "rights_note": row.get("rights_note", "")} for row in sources],
        "versions": [{"version_id": str(row["version_id"]), "document_id": str(row["document_id"]), "content_hash": row.get("content_hash"), "captured_at": row.get("captured_at"), "review_state": str(row.get("review_state", "draft")), "release_level": str(row.get("release_level", "private"))} for row in versions],
        "claim_ids": sorted(str(row["claim_id"]) for row in claims),
        "claims": [{"claim_id": str(row["claim_id"]), "source_span_ids": sorted(map(str, row.get("source_span_ids", []))), "review_state": str(row.get("review_state", "draft")), "release_level": str(row.get("release_level", "private"))} for row in claims],
        "evidence_card_ids": sorted(str(row["evidence_card_id"]) for row in cards if row.get("evidence_card_id")),
        "adjudication_ids": sorted(str(row["adjudication_id"]) for row in adjudications if row.get("adjudication_id")),
        "dossier_ids": sorted(str(row["dossier_id"]) for row in dossiers if row.get("dossier_id")),
        "coverage": {"audit_ids": sorted(str(row["coverage_audit_id"]) for row in audits if row.get("coverage_audit_id")), "status": _status(audits, "status"), "gaps": sorted(str(gap) for row in audits for gap in (row.get("gaps") if isinstance(row.get("gaps"), list) else []))},
        "review_status": {"sources": _status(sources, "review_state"), "versions": _status(versions, "review_state"), "claims": _status(claims, "review_state"), "evidence_cards": _status(cards, "review_state"), "adjudications": _status(adjudications, "review_state"), "dossiers": _status(dossiers, "review_state")},
        "freshness_access": {"source_accessed_at": sorted(str(row["accessed_at"]) for row in sources if row.get("accessed_at")), "version_captured_at": sorted(str(row["captured_at"]) for row in versions if row.get("captured_at")), "as_of": captured_at},
        "unresolved_gaps": sorted(set(str(gap) for gap in source_bundle["knowledge_basis_manifest"].get("basis_note", "").split("\n") if gap.strip()) | set(str(gap) for row in audits for gap in (row.get("gaps") if isinstance(row.get("gaps"), list) else []))),
        "provenance": {"origin": "deterministic", "captured_at": captured_at, "agent_or_tool": "groundrecall.r6.knowledge-basis", "input_hash": input_hash, "notes": "read-only manifest; private/draft until a separate preflight passes"},
    }
    return manifest


def preflight_library_argument_bundle(
    bundle: Mapping[str, Any],
    *,
    r5: Mapping[str, Any] | None = None,
    target: str = "public",
    as_of: str | None = None,
    max_age_days: int | None = None,
) -> dict[str, Any]:
    """Return a mechanical release decision; never changes or promotes input."""
    if target not in {"public", "downstream"}:
        raise ValueError("target must be 'public' or 'downstream'")
    manifest = compile_knowledge_basis_manifest(bundle, r5=r5, as_of=as_of)
    b = validate_library_argument_bundle(bundle)
    cards, adjs, dossiers = _rows((r5 or {}).get("evidence_cards")), _rows((r5 or {}).get("adjudications")), _rows((r5 or {}).get("foundation_dossiers"))
    claims, spans, versions = _rows(b["claim_instances"]), {str(x["span_id"]): x for x in _rows(b["spans"])}, {str(x["version_id"]): x for x in _rows(b["versions"])}
    citations = _rows(b["citation_assertions"])
    receipts = {(str(x.get("subject_type")), str(x.get("subject_id"))) for x in _rows(b["review_receipts"])}
    findings: list[dict[str, str]] = []
    def fail(gate: str, reason: str) -> None: findings.append({"gate": gate, "reason": reason})
    review_targets = [("claim", x.get("claim_id"), x) for x in claims] + [("citation_assertion", x.get("citation_assertion_id"), x) for x in citations]
    if r5:
        review_targets += [("evidence_card", x.get("evidence_card_id"), x) for x in cards]
        review_targets += [("adjudication", x.get("adjudication_id"), x) for x in adjs]
        review_targets += [("dossier", x.get("dossier_id"), x) for x in dossiers]
    if any(str(x.get("review_state", "draft")) not in _REVIEWED and (kind, item_id) not in receipts for kind, item_id, x in review_targets): fail("required_review", "one or more required records lack reviewed state or receipt")
    if any(not x.get("provenance") for rows in (_rows(b["sources"]), versions and _rows(b["versions"]), claims, cards, adjs, dossiers) for x in rows): fail("provenance", "required record lacks provenance")
    if any(not x.get("source_hash") for x in _rows(b["sources"])) or any(not x.get("content_hash") for x in versions.values()): fail("provenance", "source/version hash is missing")
    if not citations or any(str(x.get("support_status")) not in _SUPPORT or str(x.get("review_state", "draft")) not in _REVIEWED for x in citations): fail("citation", "citation assertions must be reviewed and supported")
    if any(not x.get("source_span_ids") or any(str(s) not in spans for s in x.get("source_span_ids", [])) for x in claims): fail("span", "claim source span is missing or unresolved")
    if any(float(x.get("start", 0)) > float(x.get("end", 0)) for x in spans.values()): fail("span", "span coordinates are inverted")
    if b["knowledge_basis_manifest"].get("completeness") != "complete" or any(str(x.get("status")) != "complete" or x.get("gaps") for x in _rows(b["coverage_audits"])): fail("completeness", "knowledge basis or coverage audit is incomplete")
    if any(not str(x.get("rights_note", "")).strip() or any(term in str(x).lower() for term in _PRIVATE) for x in _rows(b["sources"])): fail("rights", "source rights are missing or restrictive")
    if str(b.get("release_level")) != "public" or any(str(x.get("release_level", "private")) != "public" for collection in ("sources", "documents", "versions", "spans", "claim_instances", "citation_assertions") for x in _rows(b[collection])): fail("private_records", "bundle or dependency records remain private")
    if max_age_days is not None:
        try:
            cutoff = datetime.fromisoformat(str(as_of or manifest["as_of"]).replace("Z", "+00:00"))
            for stamp in manifest["freshness_access"]["source_accessed_at"]:
                age = (cutoff - datetime.fromisoformat(stamp.replace("Z", "+00:00"))).days
                if age > max_age_days: fail("freshness", f"source access is older than {max_age_days} days")
        except (ValueError, TypeError): fail("freshness", "freshness timestamps are not parseable")
    if any(not x.get("accessed_at") for x in _rows(b["sources"])): fail("freshness", "one or more sources lacks an access timestamp")
    findings.sort(key=lambda x: (x["gate"], x["reason"]))
    return {"schema_version": "groundrecall.library-argument-bundle-r6.preflight.v1", "preflight_id": _id("preflight", manifest["manifest_id"], target), "manifest_id": manifest["manifest_id"], "target": target, "passed": not findings, "release_allowed": not findings, "release_level": "private", "review_state": "draft", "findings": findings, "gates": {gate: not any(f["gate"] == gate for f in findings) for gate in ("required_review", "provenance", "citation", "span", "completeness", "rights", "private_records", "freshness")}, "note": "Report only; no promotion, database write, or publication occurred."}


def _write(value: Mapping[str, Any], path: str | Path) -> None:
    target = Path(path); target.parent.mkdir(parents=True, exist_ok=True); target.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compile R6 knowledge-basis manifests and run release preflight.")
    sub = parser.add_subparsers(dest="action", required=True)
    manifest = sub.add_parser("manifest"); manifest.add_argument("input_json"); manifest.add_argument("output_json"); manifest.add_argument("--r5", default=None); manifest.add_argument("--as-of", default=None); manifest.set_defaults(func="manifest")
    preflight = sub.add_parser("preflight"); preflight.add_argument("input_json"); preflight.add_argument("output_json"); preflight.add_argument("--r5", default=None); preflight.add_argument("--target", choices=("public", "downstream"), default="public"); preflight.add_argument("--as-of", default=None); preflight.add_argument("--max-age-days", type=int, default=None); preflight.set_defaults(func="preflight")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    bundle = json.loads(Path(args.input_json).read_text(encoding="utf-8")); r5 = json.loads(Path(args.r5).read_text(encoding="utf-8")) if args.r5 else None
    result = compile_knowledge_basis_manifest(bundle, r5=r5, as_of=args.as_of) if args.func == "manifest" else preflight_library_argument_bundle(bundle, r5=r5, target=args.target, as_of=args.as_of, max_age_days=args.max_age_days)
    _write(result, args.output_json); print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    if args.func == "preflight" and not result["passed"]: raise SystemExit(2)
