from __future__ import annotations

from groundrecall.contradictions import (
    adjudicate_contradiction_case,
    contradiction_case_id_for_claims,
    generate_contradiction_cases_from_claims,
    list_contradiction_case_batch,
    sync_contradiction_cases_for_store,
)
from groundrecall.cli import main as groundrecall_cli_main
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


def test_list_contradiction_case_batch_includes_claim_previews_and_schema(tmp_path) -> None:
    store = GroundRecallStore(tmp_path / "groundrecall")
    store.save_claim(ClaimRecord(claim_id="clm_alpha", claim_text="Alpha is stable.", contradicts_claim_ids=["clm_beta"], current_status="promoted"))
    store.save_claim(ClaimRecord(claim_id="clm_beta", claim_text="Alpha is not stable.", current_status="reviewed"))

    payload = list_contradiction_case_batch(store.base_dir, sync=True)

    assert payload["workflow_kind"] == "groundrecall_contradiction_case_review"
    assert payload["case_count"] == 1
    assert payload["cases"][0]["severity"] == "high"
    assert payload["cases"][0]["claims"][0]["claim_text"] == "Alpha is stable."
    assert payload["adjudication_schema"]["status"] == "open|under_review|resolved|superseded|rejected"


def test_adjudicate_contradiction_case_records_decision_and_updates_case(tmp_path) -> None:
    store = GroundRecallStore(tmp_path / "groundrecall")
    store.save_claim(ClaimRecord(claim_id="clm_alpha", claim_text="Alpha is stable.", contradicts_claim_ids=["clm_beta"], current_status="promoted"))
    store.save_claim(ClaimRecord(claim_id="clm_beta", claim_text="Alpha is not stable.", current_status="reviewed"))
    case = sync_contradiction_cases_for_store(store.base_dir)[0]

    result = adjudicate_contradiction_case(
        store.base_dir,
        case_id=case.case_id,
        status="resolved",
        adjudicator="unit-test",
        rationale="Alpha is stable in scoped conditions.",
        resolution="scope_qualified_resolution",
        selected_claim_ids=["clm_alpha"],
        decided_at="2026-07-26T00:00:00Z",
        adjudication_id="adj_case_alpha",
    )

    updated = store.get_contradiction_case(case.case_id)
    adjudication = store.get_adjudication("adj_case_alpha")
    assert result["decision"] == "adjudicated"
    assert updated is not None
    assert updated.status == "resolved"
    assert updated.current_status == "reviewed"
    assert updated.resolved_at == "2026-07-26T00:00:00Z"
    assert updated.metadata["selected_claim_ids"] == ["clm_alpha"]
    assert adjudication is not None
    assert adjudication.subject_type == "contradiction_case"
    assert adjudication.metadata["disagreement_preserved"] is True


def test_groundrecall_cli_routes_contradiction_sync(tmp_path, monkeypatch, capsys) -> None:
    store = GroundRecallStore(tmp_path / "groundrecall")
    store.save_claim(ClaimRecord(claim_id="clm_alpha", claim_text="Alpha is stable.", contradicts_claim_ids=["clm_beta"]))
    store.save_claim(ClaimRecord(claim_id="clm_beta", claim_text="Alpha is not stable."))
    monkeypatch.setattr("sys.argv", ["groundrecall", "contradictions", "sync", str(store.base_dir)])

    groundrecall_cli_main()

    output = capsys.readouterr().out
    assert '"decision": "synced"' in output
    assert store.list_contradiction_cases()


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
