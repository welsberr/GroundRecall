import json
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCHEMA = ROOT / "docs/schemas/library.argument_bundle.v1.schema.json"
FIXTURE = ROOT / "docs/fixtures/library.argument_bundle.v1.golden.json"


def test_argument_bundle_schema_and_golden_fixture_are_json() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    bundle = json.loads(FIXTURE.read_text(encoding="utf-8"))

    assert schema["$id"].endswith("library.argument_bundle.v1.schema.json")
    assert bundle["schema_version"] == "library.argument_bundle.v1"
    assert {source["source_kind"] for source in bundle["sources"]} >= {"article", "video"}
    assert any(span["locator_kind"] == "timestamp" for span in bundle["spans"])


def test_argument_bundle_fixture_references_are_closed() -> None:
    bundle = json.loads(FIXTURE.read_text(encoding="utf-8"))
    ids = {
        key: {item[item_key] for item in bundle[key]}
        for key, item_key in (
            ("sources", "source_id"), ("documents", "document_id"),
            ("versions", "version_id"), ("spans", "span_id"),
            ("claim_instances", "claim_id"),
            ("canonical_claim_references", "canonical_claim_ref_id"),
            ("coverage_audits", "coverage_audit_id"),
        )
    }
    assert all(item["source_id"] in ids["sources"] for item in bundle["documents"])
    assert all(item["document_id"] in ids["documents"] for item in bundle["versions"])
    assert all(item["version_id"] in ids["versions"] for item in bundle["spans"])
    assert all(span_id in ids["spans"] for item in bundle["claim_instances"] for span_id in item["source_span_ids"])
    assert all(claim_id in ids["claim_instances"] for item in bundle["argument_relations"] for claim_id in (item["from_claim_id"], item["to_claim_id"]))
    subject_sets = {
        "source": ids["sources"],
        "document": ids["documents"],
        "version": ids["versions"],
        "span": ids["spans"],
        "claim": ids["claim_instances"],
        "coverage_audit": ids["coverage_audits"],
    }
    assert all(item["subject_id"] in subject_sets[item["subject_type"]] for item in bundle["review_receipts"])
