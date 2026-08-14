import copy
import json
from pathlib import Path

from groundrecall.library_argument_bundle_audit import audit_library_argument_bundle


FIXTURE = Path(__file__).parents[1] / "docs/fixtures/library.argument_bundle.v1.golden.json"


def test_r3_golden_reports_review_and_release_work() -> None:
    bundle = json.loads(FIXTURE.read_text(encoding="utf-8"))
    result = audit_library_argument_bundle(bundle)
    codes = {finding["code"] for finding in result["findings"]}
    assert {"claim_unreviewed", "citation_unresolved", "coverage_incomplete", "public_release_blocker"} <= codes
    assert result["promoted"] is False
    assert result["release_level"] == result["review_state"] == "private" or result["review_state"] == "draft"
    assert all(candidate["current_status"] == "needs_review" for candidate in result["review_candidates"])
    assert all(candidate["release_level"] == "private" and candidate["review_state"] == "draft" for candidate in result["review_candidates"])


def test_r3_reports_missing_and_invalid_spans_and_unresolved_citations() -> None:
    bundle = json.loads(FIXTURE.read_text(encoding="utf-8"))
    broken = copy.deepcopy(bundle)
    broken["claim_instances"][0]["source_span_ids"] = ["span.missing"]
    broken["spans"][0]["start"] = 99
    broken["spans"][0]["end"] = 1
    broken["citation_assertions"][0]["target_span_ids"] = ["span.missing"]
    result = audit_library_argument_bundle(broken)
    codes = {finding["code"] for finding in result["findings"]}
    assert "source_span_missing" in codes
    assert "source_span_invalid" in codes
    assert "citation_invalid_reference" in codes
    assert "citation_unresolved" in codes


def test_r3_reports_missing_argument_links_and_is_deterministic_without_mutation() -> None:
    bundle = json.loads(FIXTURE.read_text(encoding="utf-8"))
    original = copy.deepcopy(bundle)
    bundle["argument_relations"] = []
    first = audit_library_argument_bundle(bundle)
    second = audit_library_argument_bundle(bundle)
    assert first == second
    assert bundle == {**original, "argument_relations": []}
    assert sum(item["code"] == "argument_link_missing" for item in first["findings"]) == 2
    assert len({item["review_candidate_id"] for item in first["review_candidates"]}) == first["candidate_count"]
