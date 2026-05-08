from __future__ import annotations

from pathlib import Path

from groundrecall.doclift_claim_tournament import evaluate_doclift_claim_tracks


def _fixture_root() -> Path:
    return Path(__file__).parent / "fixtures" / "doclift_claim_eval"


def _pilot_fixture_root() -> Path:
    return Path(__file__).parent / "fixtures" / "doclift_claim_eval_pilot"


def test_doclift_claim_tournament_scores_two_tracks() -> None:
    root = _fixture_root()
    result = evaluate_doclift_claim_tracks(root, root / "benchmark.json")

    assert result["judge_summary"]["winner"] in {"conservative", "broad"}
    assert set(result["judge_summary"]["tracks"].keys()) == {"conservative", "broad"}
    assert len(result["per_document"]) == 2
    intro = next(item for item in result["per_document"] if item["document_id"] == "intro-essay")
    assert intro["tracks"][0]["predicted_claims"]
    assert intro["tracks"][1]["predicted_claims"]


def test_doclift_claim_tournament_broad_track_improves_recall_on_fixture() -> None:
    root = _fixture_root()
    result = evaluate_doclift_claim_tracks(root, root / "benchmark.json")
    tracks = result["judge_summary"]["tracks"]

    assert tracks["broad"]["recall"] >= tracks["conservative"]["recall"]
    assert tracks["broad"]["matches"] >= tracks["conservative"]["matches"]


def test_doclift_claim_tournament_runs_on_real_corpus_fixture() -> None:
    root = _pilot_fixture_root()
    result = evaluate_doclift_claim_tracks(root, root / "benchmark.json")
    tracks = result["judge_summary"]["tracks"]

    assert len(result["per_document"]) == 2
    assert tracks["conservative"]["gold_claims"] == 4
    assert tracks["broad"]["gold_claims"] == 4
    assert tracks["broad"]["matches"] >= 1
