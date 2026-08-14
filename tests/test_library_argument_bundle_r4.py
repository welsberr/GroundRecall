import copy
import json
from pathlib import Path

from groundrecall.library_argument_bundle_r4 import generate_r4_candidates


FIXTURE = Path(__file__).parents[1] / "docs/fixtures/library.argument_bundle.v1.golden.json"
REFERENCES = Path(__file__).parent / "fixtures/r4_canonical_references.json"


def test_r4_is_deterministic_and_does_not_mutate_input() -> None:
    bundle = json.loads(FIXTURE.read_text())
    original = copy.deepcopy(bundle)
    first = generate_r4_candidates(bundle)
    second = generate_r4_candidates(bundle)
    assert first == second
    assert bundle == original
    assert first["lineage_candidates"]


def test_r4_lineage_has_exact_spans_and_explicit_non_truth_boundary() -> None:
    bundle = json.loads(FIXTURE.read_text())
    candidate = generate_r4_candidates(bundle)["lineage_candidates"][0]
    assert candidate["evidence_span_ids"] == sorted(candidate["evidence_span_ids"])
    assert set(candidate["evidence_span_ids"]) <= {item["span_id"] for item in bundle["spans"]}
    assert candidate["release_level"] == "private"
    assert candidate["review_state"] == "draft"
    assert candidate["truth_status"] == "not_assessed"
    assert "does not establish" in candidate["rationale"]


def test_r4_matches_supplied_reference_or_emits_unresolved_reference() -> None:
    bundle = json.loads(FIXTURE.read_text())
    result = generate_r4_candidates(bundle, json.loads(REFERENCES.read_text()), threshold=0.5)
    supplied = next(item for item in result["canonical_claim_references"] if item["canonical_claim_ref_id"] == "ref.supplied.population")
    assert supplied["match_status"] == "candidate"
    assert supplied["evidence_span_ids"]
    assert all(item["release_level"] == "private" and item["review_state"] == "draft" for item in result["canonical_claim_references"])
    assert any(item["match_status"] == "unresolved" for item in result["canonical_claim_references"])
