from __future__ import annotations

import json

from groundrecall.epistemap_adapter import (
    export_claim_evaluation_g_package,
    g_evaluation_row_from_claim_evaluation,
    g_evaluation_rows_from_claim_evaluations,
    graph_bundle_from_query_payload,
)


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


def test_g_evaluation_rows_from_claim_evaluations_batches_with_claim_context() -> None:
    claims = {
        "clm_001": {
            "claim_id": "clm_001",
            "claim_text": "Channel capacity bounds reliable communication rate.",
            "concept_ids": ["concept::channel-capacity"],
            "provenance": {"origin_path": "wiki/channel-capacity.md", "grounding_status": "grounded"},
        }
    }

    rows = g_evaluation_rows_from_claim_evaluations(
        [
            {"claim_id": "clm_001", "y": 1, "p": 0.9, "env": "C", "condition": "plain"},
            {"claim_id": "clm_001", "y": 1, "p": 0.8, "env": "K", "condition": "plain"},
        ],
        claims_by_id=claims,
    )

    assert len(rows) == 2
    assert rows[0]["claim_text"] == "Channel capacity bounds reliable communication rate."
    assert rows[1]["source_anchor"] == "wiki/channel-capacity.md"


def test_graph_bundle_preserves_explicit_zero_review_confidence() -> None:
    bundle = graph_bundle_from_query_payload(
        {
            "concept": {"concept_id": "concept::channel-capacity", "title": "Channel capacity"},
            "claims": [
                {
                    "claim_id": "clm_zero",
                    "claim_text": "A reviewed zero must remain explicit.",
                    "concept_ids": ["concept::channel-capacity"],
                    "confidence_hint": 0.8,
                    "review_confidence": 0.0,
                    "metadata": {
                        "review_confidence_explicit": True,
                        "confidence_method": {
                            "name": "groundrecall.test.claim.confidence_hint",
                            "version": "1.0",
                            "policy_id": "groundrecall_adapter_confidence.test.v1",
                        },
                        "confidence_basis_record_ids": ["clm_zero"],
                        "confidence_basis_hash": "test-basis-hash",
                        "confidence_rationale": "Test confidence hint is explicit extraction fidelity.",
                    },
                    "provenance": {"support_kind": "derived_from_page", "grounding_status": "grounded"},
                },
                {
                    "claim_id": "clm_missing",
                    "claim_text": "Missing confidence should remain missing.",
                    "concept_ids": ["concept::channel-capacity"],
                    "provenance": {"support_kind": "derived_from_page", "grounding_status": "grounded"},
                },
            ],
        }
    )

    zero = next(node for node in bundle.nodes if node.id == "clm_zero")
    missing = next(node for node in bundle.nodes if node.id == "clm_missing")
    assert zero.confidence == 0.0
    assert {assessment.dimension for assessment in zero.assessments} == {"reviewer_endorsement", "extraction_fidelity"}
    assert missing.confidence is None
    assert missing.assessments == []


def test_graph_bundle_does_not_turn_legacy_hint_into_assessment_without_method() -> None:
    bundle = graph_bundle_from_query_payload(
        {
            "concept": {"concept_id": "concept::channel-capacity", "title": "Channel capacity"},
            "claims": [
                {
                    "claim_id": "clm_legacy",
                    "claim_text": "Legacy scalar remains readable but not assessment-ready.",
                    "concept_ids": ["concept::channel-capacity"],
                    "confidence_hint": 0.8,
                    "provenance": {"support_kind": "derived_from_page", "grounding_status": "grounded"},
                }
            ],
        }
    )

    legacy = next(node for node in bundle.nodes if node.id == "clm_legacy")
    assert legacy.confidence == 0.8
    assert legacy.assessments == []


def test_export_claim_evaluation_g_package_writes_rows_manifest_and_summary(tmp_path) -> None:
    output = export_claim_evaluation_g_package(
        [
            {"claim_id": "clm_001", "y": 1, "p": 0.9, "env": "C", "condition": "plain"},
            {"claim_id": "clm_001", "y": 1, "p": 0.8, "env": "K", "condition": "plain"},
        ],
        tmp_path,
        claims_by_id={
            "clm_001": {
                "claim_id": "clm_001",
                "claim_text": "Channel capacity bounds reliable communication rate.",
                "concept_ids": ["concept::channel-capacity"],
                "provenance": {"origin_path": "wiki/channel-capacity.md", "grounding_status": "grounded"},
            }
        },
        experiment_id="groundrecall-temporal-check",
        corpus="channel-capacity",
    )

    assert output["row_count"] == 2
    assert (tmp_path / "groundrecall_g_rows.csv").exists()
    assert (tmp_path / "groundrecall_g_manifest.json").exists()
    assert (tmp_path / "groundrecall_g_summary.json").exists()
    assert (tmp_path / "groundrecall_g_summary.md").exists()
    manifest = json.loads((tmp_path / "groundrecall_g_manifest.json").read_text(encoding="utf-8"))
    summary = json.loads((tmp_path / "groundrecall_g_summary.json").read_text(encoding="utf-8"))
    assert manifest["experiment_id"] == "groundrecall-temporal-check"
    assert manifest["corpus"] == "channel-capacity"
    assert summary["summary_kind"] == "epistemap_g_experiment_summary"
    assert "# Epistemap G Summary" in (tmp_path / "groundrecall_g_summary.md").read_text(encoding="utf-8")
