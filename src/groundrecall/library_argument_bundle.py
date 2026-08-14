"""R1 handoff validation and deterministic export for library argument bundles."""
from __future__ import annotations

import argparse
import copy
import json
import re
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator, FormatChecker

SCHEMA_VERSION = "library.argument_bundle.v1"
_SCHEMA_PATH = Path(__file__).parents[2] / "docs" / "schemas" / "library.argument_bundle.v1.schema.json"
_LEGACY_REVIEW_STATES = {"candidate": "draft", "accepted": "promoted", "rejected": "deprecated"}
_COLLECTION_IDS = {
    "sources": "source_id", "documents": "document_id", "versions": "version_id", "spans": "span_id",
    "claim_instances": "claim_id", "canonical_claim_references": "canonical_claim_ref_id",
    "argument_relations": "relation_id", "citation_assertions": "citation_assertion_id",
    "lineage_candidates": "lineage_candidate_id", "coverage_audits": "coverage_audit_id", "review_receipts": "receipt_id",
}
_LOCAL_PATH = re.compile(r"(?:^[/~]|^[A-Za-z]:[\\/]|^\\\\|^file://)")


class LibraryArgumentBundleError(ValueError):
    """Raised when a library.argument_bundle.v1 handoff is not safe to use."""


def _schema() -> dict[str, Any]:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def adapt_library_argument_bundle(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Copy a producer payload and normalize the three R0 legacy states."""
    if not isinstance(payload, Mapping):
        raise LibraryArgumentBundleError("bundle must be a JSON object")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise LibraryArgumentBundleError(f"unsupported schema_version: {payload.get('schema_version', '')!r}")
    adapted = copy.deepcopy(dict(payload))
    for value in adapted.values():
        if isinstance(value, list):
            for record in value:
                if isinstance(record, dict) and record.get("review_state") in _LEGACY_REVIEW_STATES:
                    record["review_state"] = _LEGACY_REVIEW_STATES[record["review_state"]]
    return adapted


def validate_library_argument_bundle(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate shape, stable identity, and all inter-record references."""
    bundle = adapt_library_argument_bundle(payload)
    validator = Draft202012Validator(_schema(), format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(bundle), key=lambda error: list(error.absolute_path))
    if errors:
        location = ".".join(str(part) for part in errors[0].absolute_path) or "bundle"
        raise LibraryArgumentBundleError(f"{location}: {errors[0].message}")

    ids: dict[str, set[str]] = {}
    for collection, id_key in _COLLECTION_IDS.items():
        seen: set[str] = set()
        for record in bundle[collection]:
            record_id = record[id_key]
            if record_id in seen:
                raise LibraryArgumentBundleError(f"duplicate {collection} id: {record_id}")
            seen.add(record_id)
        ids[collection] = seen
    _check_reference_integrity(bundle, ids)
    return bundle


def _check_reference_integrity(bundle: Mapping[str, Any], ids: Mapping[str, set[str]]) -> None:
    def require(collection: str, value: str, context: str) -> None:
        if value not in ids[collection]:
            raise LibraryArgumentBundleError(f"{context} references unknown {collection[:-1]}: {value}")

    for item in bundle["documents"]:
        require("sources", item["source_id"], "document")
    for item in bundle["versions"]:
        require("documents", item["document_id"], "version")
    for item in bundle["spans"]:
        require("versions", item["version_id"], "span")
        if item["start"] > item["end"]:
            raise LibraryArgumentBundleError(f"span has start after end: {item['span_id']}")
    for item in bundle["claim_instances"]:
        for value in item["source_span_ids"]:
            require("spans", value, f"claim {item['claim_id']}")
        for value in item.get("canonical_claim_ref_ids", []):
            require("canonical_claim_references", value, f"claim {item['claim_id']}")
    for item in bundle["argument_relations"]:
        require("claim_instances", item["from_claim_id"], "argument relation")
        require("claim_instances", item["to_claim_id"], "argument relation")
    for item in bundle["citation_assertions"]:
        require("claim_instances", item["claim_id"], "citation assertion")
        require("sources", item["target_source_id"], "citation assertion")
        for value in item.get("target_span_ids", []):
            require("spans", value, "citation assertion")
    for item in bundle["lineage_candidates"]:
        require("documents", item["from_document_id"], "lineage candidate")
        require("documents", item["to_document_id"], "lineage candidate")
        for value in item["evidence_span_ids"]:
            require("spans", value, "lineage candidate")
    for item in bundle["coverage_audits"]:
        for value in item["expected_span_ids"]:
            require("spans", value, "coverage audit")
        for value in item["covered_claim_ids"]:
            require("claim_instances", value, "coverage audit")
    manifest = bundle["knowledge_basis_manifest"]
    for value in manifest["source_ids"]:
        require("sources", value, "knowledge basis manifest")
    for value in manifest["claim_ids"]:
        require("claim_instances", value, "knowledge basis manifest")
    for value in manifest["coverage_audit_ids"]:
        require("coverage_audits", value, "knowledge basis manifest")
    subject_collections = {
        "source": "sources", "document": "documents", "version": "versions", "span": "spans",
        "claim": "claim_instances", "canonical_claim_reference": "canonical_claim_references",
        "argument_relation": "argument_relations", "citation_assertion": "citation_assertions",
        "lineage_candidate": "lineage_candidates", "coverage_audit": "coverage_audits",
        "knowledge_basis_manifest": None,
    }
    for item in bundle["review_receipts"]:
        collection = subject_collections[item["subject_type"]]
        if collection is None and item["subject_id"] != manifest["manifest_id"]:
            raise LibraryArgumentBundleError("review receipt references unknown knowledge basis manifest")
        if collection is not None:
            require(collection, item["subject_id"], "review receipt")


def _contains_local_path(value: Any, location: str = "bundle") -> str | None:
    if isinstance(value, str) and _LOCAL_PATH.search(value):
        return location
    if isinstance(value, Mapping):
        for key in sorted(value):
            found = _contains_local_path(value[key], f"{location}.{key}")
            if found:
                return found
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found = _contains_local_path(item, f"{location}[{index}]")
            if found:
                return found
    return None


def serialize_library_argument_bundle(payload: Mapping[str, Any], *, public: bool = False) -> str:
    """Return canonical JSON suitable for a stable handoff or public export."""
    bundle = validate_library_argument_bundle(payload)
    if public:
        if bundle["release_level"] != "public":
            raise LibraryArgumentBundleError("public export requires a public bundle release_level")
        if any(record["release_level"] != "public" for collection in _COLLECTION_IDS for record in bundle[collection]):
            raise LibraryArgumentBundleError("public export contains a non-public record")
        path = _contains_local_path(bundle)
        if path:
            raise LibraryArgumentBundleError(f"public export contains a local filesystem path at {path}")
    return json.dumps(bundle, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def export_library_argument_bundle(input_path: str | Path, output_path: str | Path, *, public: bool = False) -> dict[str, Any]:
    """Validate and write one deterministic bundle; returns the adapted payload."""
    payload = json.loads(Path(input_path).read_text(encoding="utf-8"))
    serialized = serialize_library_argument_bundle(payload, public=public)
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(serialized, encoding="utf-8")
    return json.loads(serialized)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate and deterministically export a library.argument_bundle.v1 handoff.")
    parser.add_argument("input_json")
    parser.add_argument("output_json")
    parser.add_argument("--public", action="store_true", help="Apply public-release and local-path guardrails.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    print(json.dumps(export_library_argument_bundle(args.input_json, args.output_json, public=args.public), indent=2, sort_keys=True))
