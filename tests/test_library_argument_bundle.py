import json
from pathlib import Path

import pytest

from groundrecall.library_argument_bundle import LibraryArgumentBundleError, serialize_library_argument_bundle, validate_library_argument_bundle


ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "docs/fixtures/library.argument_bundle.v1.golden.json"


def bundle() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_r1_validates_fixture_and_preserves_handoff_fields() -> None:
    original = bundle()
    validated = validate_library_argument_bundle(original)
    assert validated["sources"][0]["source_hash"] == original["sources"][0]["source_hash"]
    assert validated["versions"][1]["content_hash"] == original["versions"][1]["content_hash"]
    assert validated["spans"][1]["locator_kind"] == "timestamp"
    assert validated["claim_instances"][0]["provenance"] == original["claim_instances"][0]["provenance"]


def test_r1_rejects_unknown_version_and_reference() -> None:
    unknown = bundle()
    unknown["schema_version"] = "library.argument_bundle.v2"
    with pytest.raises(LibraryArgumentBundleError, match="unsupported schema_version"):
        validate_library_argument_bundle(unknown)

    broken = bundle()
    broken["claim_instances"][0]["source_span_ids"] = ["missing-span"]
    with pytest.raises(LibraryArgumentBundleError, match="unknown spans?"):
        validate_library_argument_bundle(broken)


def test_r1_maps_legacy_states_without_mutating_input() -> None:
    original = bundle()
    original["claim_instances"][0]["review_state"] = "candidate"
    adapted = validate_library_argument_bundle(original)
    assert adapted["claim_instances"][0]["review_state"] == "draft"
    assert original["claim_instances"][0]["review_state"] == "candidate"


def test_r1_export_is_deterministic_and_public_paths_are_rejected() -> None:
    first = serialize_library_argument_bundle(bundle())
    second = serialize_library_argument_bundle(json.loads(first))
    assert first == second

    public = bundle()
    public["release_level"] = "public"
    collections = ("sources", "documents", "versions", "spans", "claim_instances", "canonical_claim_references", "argument_relations", "citation_assertions", "lineage_candidates", "coverage_audits", "review_receipts")
    for collection in collections:
        for record in public[collection]:
            record["release_level"] = "public"
    public["sources"][0]["canonical_uri"] = "file:///private/source.pdf"
    with pytest.raises(LibraryArgumentBundleError, match="local filesystem path"):
        serialize_library_argument_bundle(public, public=True)
