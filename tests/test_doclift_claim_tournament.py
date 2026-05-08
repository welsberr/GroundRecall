from __future__ import annotations

import json
from pathlib import Path

from groundrecall.doclift_claim_tournament import evaluate_doclift_claim_tracks
from groundrecall.groundrecall_source_adapters.doclift_bundle import DocliftBundleSourceAdapter


def _fixture_root() -> Path:
    return Path(__file__).parent / "fixtures" / "doclift_claim_eval"


def _pilot_fixture_root() -> Path:
    return Path(__file__).parent / "fixtures" / "doclift_claim_eval_pilot"


def test_doclift_claim_tournament_scores_two_tracks() -> None:
    root = _fixture_root()
    result = evaluate_doclift_claim_tracks(root, root / "benchmark.json")

    assert result["judge_summary"]["winner"] in {"conservative", "balanced", "broad"}
    assert set(result["judge_summary"]["tracks"].keys()) == {"conservative", "balanced", "broad"}
    assert len(result["per_document"]) == 2
    intro = next(item for item in result["per_document"] if item["document_id"] == "intro-essay")
    assert len(intro["tracks"]) == 3
    assert intro["tracks"][0]["predicted_claims"]
    assert intro["tracks"][1]["predicted_claims"]
    assert intro["tracks"][2]["predicted_claims"]


def test_doclift_claim_tournament_broad_track_improves_recall_on_fixture() -> None:
    root = _fixture_root()
    result = evaluate_doclift_claim_tracks(root, root / "benchmark.json")
    tracks = result["judge_summary"]["tracks"]

    assert tracks["broad"]["recall"] >= tracks["conservative"]["recall"]
    assert tracks["broad"]["matches"] >= tracks["conservative"]["matches"]
    assert tracks["balanced"]["precision"] >= tracks["conservative"]["precision"]


def test_doclift_claim_tournament_runs_on_real_corpus_fixture() -> None:
    root = _pilot_fixture_root()
    result = evaluate_doclift_claim_tracks(root, root / "benchmark.json")
    tracks = result["judge_summary"]["tracks"]

    assert len(result["per_document"]) == 2
    assert tracks["conservative"]["gold_claims"] == 4
    assert tracks["balanced"]["gold_claims"] == 4
    assert tracks["broad"]["gold_claims"] == 4
    assert tracks["broad"]["matches"] >= 1
    assert tracks["balanced"]["matches"] >= 1
    assert tracks["balanced"]["recall"] >= tracks["broad"]["recall"]
    assert tracks["balanced"]["f1"] >= tracks["broad"]["f1"]


def test_doclift_auto_bundle_strategy_prefers_balanced_on_real_corpus_fixture() -> None:
    root = _pilot_fixture_root()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    adapter = DocliftBundleSourceAdapter()
    documents = [item for item in manifest["documents"]]

    strategy = adapter.select_bundle_claim_strategy(
        root,
        documents,
        limit=6,
    )
    assert strategy == "balanced"


def test_doclift_auto_strategy_returns_available_track_on_synthetic_fixture() -> None:
    root = _fixture_root()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    adapter = DocliftBundleSourceAdapter()
    documents = {str(item["document_id"]): item for item in manifest["documents"]}

    strategy = adapter.select_document_claim_strategy(root, documents["drift-essay"], limit=6)
    assert strategy in {"conservative", "balanced", "broad"}
