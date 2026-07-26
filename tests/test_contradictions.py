from __future__ import annotations

from groundrecall.contradictions import (
    contradiction_case_id_for_claims,
    generate_contradiction_cases_from_claims,
    sync_contradiction_cases_for_store,
)
from groundrecall.graph_diagnostics import build_graph_diagnostics
from groundrecall.models import ClaimRecord, ContradictionCaseRecord
from groundrecall.store import GroundRecallStore


def test_generate_contradiction_case_from_explicit_claim_links() -> None:
    left = ClaimRecord(
        claim_id="clm_alpha",
        claim_text="Alpha is stable.",
        contradicts_claim_ids=["clm_beta"],
        current_status="promoted",
    )
    right = ClaimRecord(
        claim_id="clm_beta",
        claim_text="Alpha is not stable.",
        current_status="reviewed",
    )

    cases = generate_contradiction_cases_from_claims([left, right], opened_at="2026-07-26T00:00:00Z")

    assert len(cases) == 1
    case = cases[0]
    assert case.case_id == contradiction_case_id_for_claims(["clm_beta", "clm_alpha"])
    assert case.claim_ids == ["clm_alpha", "clm_beta"]
    assert case.status == "open"
    assert case.severity == "high"
    assert case.opened_at == "2026-07-26T00:00:00Z"
    assert case.metadata["generation_method"] == "explicit_contradicts_claim_ids"


def test_generate_contradiction_case_preserves_existing_review_state() -> None:
    left = ClaimRecord(claim_id="clm_alpha", claim_text="Alpha is stable.", contradicts_claim_ids=["clm_beta"])
    right = ClaimRecord(claim_id="clm_beta", claim_text="Alpha is not stable.")
    existing = ContradictionCaseRecord(
        case_id=contradiction_case_id_for_claims(["clm_alpha", "clm_beta"]),
        claim_ids=["clm_alpha", "clm_beta"],
        status="resolved",
        adjudication_id="adj_001",
        rationale="Resolved by reviewer.",
    )

    cases = generate_contradiction_cases_from_claims([left, right], existing_cases=[existing])

    assert cases == [existing]


def test_sync_contradiction_cases_for_store_persists_generated_cases(tmp_path) -> None:
    store = GroundRecallStore(tmp_path / "groundrecall")
    store.save_claim(ClaimRecord(claim_id="clm_alpha", claim_text="Alpha is stable.", contradicts_claim_ids=["clm_beta"]))
    store.save_claim(ClaimRecord(claim_id="clm_beta", claim_text="Alpha is not stable."))

    cases = sync_contradiction_cases_for_store(store.base_dir)

    assert len(cases) == 1
    assert store.get_contradiction_case(cases[0].case_id) is not None
    assert store.build_snapshot("snap", "2026-07-26T00:00:00Z").contradiction_cases[0].case_id == cases[0].case_id


def test_graph_diagnostics_flags_missing_and_open_promoted_contradiction_cases() -> None:
    claims = [
        {"claim_id": "clm_alpha", "claim_text": "Alpha is stable.", "contradicts_claim_ids": ["clm_beta"], "current_status": "promoted"},
        {"claim_id": "clm_beta", "claim_text": "Alpha is not stable.", "current_status": "reviewed"},
    ]

    missing_case = build_graph_diagnostics([], [], claims=claims, observations=[])
    missing_codes = {flag["code"] for flag in missing_case["quality_controls"]["flags"]}
    assert "contradiction_links_without_cases" in missing_codes

    with_case = build_graph_diagnostics(
        [],
        [],
        claims=claims,
        observations=[],
        contradiction_cases=[
            {
                "case_id": contradiction_case_id_for_claims(["clm_alpha", "clm_beta"]),
                "claim_ids": ["clm_alpha", "clm_beta"],
                "status": "open",
                "case_kind": "contradiction",
            }
        ],
    )
    case_codes = {flag["code"] for flag in with_case["quality_controls"]["flags"]}
    assert "contradiction_links_without_cases" not in case_codes
    assert "open_promoted_contradiction_cases" in case_codes
