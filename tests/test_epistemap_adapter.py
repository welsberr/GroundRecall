from __future__ import annotations

from groundrecall.epistemap_adapter import g_evaluation_row_from_claim_evaluation


def test_g_evaluation_row_from_claim_evaluation_enriches_explicit_evaluation() -> None:
    claim = {
        "claim_id": "clm_001",
        "claim_text": "Channel capacity bounds reliable communication rate.",
        "concept_ids": ["concept::channel-capacity"],
        "current_status": "promoted",
        "review_confidence": 0.9,
        "metadata": {"challenged_at": "2026-04-20", "source_reliability": "high"},
        "provenance": {
            "origin_path": "wiki/channel-capacity.md",
            "support_kind": "derived_from_page",
            "grounding_status": "grounded",
            "retrieval_date": "2026-04-18",
        },
    }

    row = g_evaluation_row_from_claim_evaluation(
        {
            "y": 1,
            "p": 0.87,
            "env": "K",
            "run_id": "run-1",
            "subject_id": "model-a",
            "condition": "graph-assisted",
            "recognized_at": "2026-04-22",
            "recognition_lag": 2,
            "metadata": {"benchmark": "temporal-claim-check"},
        },
        claim=claim,
    )

    assert row["claim_id"] == "clm_001"
    assert row["item_id"] == "concept::channel-capacity"
    assert row["source_anchor"] == "wiki/channel-capacity.md"
    assert row["contradiction_available_at"] == "2026-04-20"
    assert row["evaluation_target"] == "groundrecall_claim_evaluation"
    assert row["grounding_status"] == "grounded"
    assert row["benchmark"] == "temporal-claim-check"
