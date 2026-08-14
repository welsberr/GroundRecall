import json
from pathlib import Path

from groundrecall.doclift_argument_adapter import extract_doclift_argument_bundle
from groundrecall.library_argument_bundle import serialize_library_argument_bundle


FIXTURE = Path(__file__).parent / "fixtures/doclift_r2_chunks.json"


def test_r2_extracts_draft_candidates_with_exact_anchors_and_closed_references() -> None:
    payload = json.loads(FIXTURE.read_text())
    bundle = extract_doclift_argument_bundle(payload, run_id="run.r2.fixture", created_at="2026-08-13T12:00:00Z")

    assert [item["claim_kind"] for item in bundle["claim_instances"]] == ["premise", "conclusion", "objection", "question"]
    assert bundle["review_state"] == "draft"
    assert bundle["release_level"] == "private"
    assert bundle["versions"][0]["content_hash"].startswith("sha256:")
    assert [(item["start"], item["end"], item["quoted_text"]) for item in bundle["spans"][:4]] == [
        (10, 11, payload["chunks"][0]["text"]), (12, 12, payload["chunks"][1]["text"]),
        (13, 14, payload["chunks"][2]["text"]), (15, 15, payload["chunks"][3]["text"]),
    ]
    assert len(bundle["citation_assertions"]) == 1
    assert bundle["citation_assertions"][0]["support_status"] == "unresolved"
    assert serialize_library_argument_bundle(bundle) == serialize_library_argument_bundle(extract_doclift_argument_bundle(payload, run_id="run.r2.fixture", created_at="2026-08-13T12:00:00Z"))


def test_r2_is_deterministic_for_stable_ids_but_run_metadata_is_explicit() -> None:
    payload = json.loads(FIXTURE.read_text())
    first = extract_doclift_argument_bundle(payload, run_id="run.one", created_at="2026-08-13T12:00:00Z")
    second = extract_doclift_argument_bundle(payload, run_id="run.two", created_at="2026-08-13T12:00:00Z")
    assert [item["claim_id"] for item in first["claim_instances"]] == [item["claim_id"] for item in second["claim_instances"]]
    assert first["claim_instances"][0]["provenance"]["run_id"] == "run.one"
    assert second["claim_instances"][0]["provenance"]["run_id"] == "run.two"
