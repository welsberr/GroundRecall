from __future__ import annotations

import json

import pytest

from groundrecall.contradictions import (
    ContradictionPolicyError,
    accept_contradiction_candidate,
    adjudicate_contradiction_case,
    contradiction_case_id_for_claims,
    generate_contradiction_cases_from_claims,
    list_contradiction_candidate_batch,
    list_contradiction_case_batch,
    reject_contradiction_candidate,
    sync_contradiction_cases_for_store,
)
from groundrecall.cli import main as groundrecall_cli_main
from groundrecall.graph_diagnostics import build_graph_diagnostics
from groundrecall.models import ClaimRecord, ContradictionCaseRecord, RelationRecord
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


def test_list_contradiction_candidate_batch_exposes_graph_cues(tmp_path) -> None:
    store = GroundRecallStore(tmp_path / "groundrecall")
    store.save_claim(ClaimRecord(claim_id="clm_alpha", claim_text="Alpha is stable.", current_status="reviewed"))
    store.save_claim(ClaimRecord(claim_id="clm_beta", claim_text="Alpha is not stable.", current_status="triaged"))
    store.save_relation(
        RelationRecord(
            relation_id="rel_alpha_beta_contradiction_candidate",
            source_id="clm_alpha",
            target_id="clm_beta",
            relation_type="claim_may_contradict_claim",
            evidence_ids=["frag_1"],
            current_status="triaged",
        )
    )

    payload = list_contradiction_candidate_batch(store.base_dir)

    assert payload["workflow_kind"] == "groundrecall_contradiction_candidate_review"
    assert payload["schema_version"] == "groundrecall.contradiction_candidates.v1"
    assert payload["candidate_count"] == 1
    candidate = payload["candidates"][0]
    assert candidate["relation_id"] == "rel_alpha_beta_contradiction_candidate"
    assert candidate["claim_ids"] == ["clm_alpha", "clm_beta"]
    assert candidate["evidence_ids"] == ["frag_1"]
    assert candidate["claims"][0]["claim_text"] == "Alpha is stable."
    assert candidate["claims"][1]["current_status"] == "triaged"
    assert candidate["review_actions"][0] == "accept-candidate"


def test_accept_contradiction_candidate_materializes_case(tmp_path) -> None:
    store = GroundRecallStore(tmp_path / "groundrecall")
    store.save_claim(ClaimRecord(claim_id="clm_alpha", claim_text="Alpha is stable.", current_status="reviewed"))
    store.save_claim(ClaimRecord(claim_id="clm_beta", claim_text="Alpha is not stable.", current_status="triaged"))
    store.save_relation(
        RelationRecord(
            relation_id="rel_alpha_beta_contradiction_candidate",
            source_id="clm_alpha",
            target_id="clm_beta",
            relation_type="claim_may_contradict_claim",
            evidence_ids=["frag_1"],
            current_status="triaged",
        )
    )

    result = accept_contradiction_candidate(
        store.base_dir,
        relation_id="rel_alpha_beta_contradiction_candidate",
        reviewer="unit-test",
        rationale="The statements cannot both be true in the same scope.",
        reviewed_at="2026-07-28T00:00:00Z",
    )

    left = store.get_claim("clm_alpha")
    right = store.get_claim("clm_beta")
    relation = store.get_relation("rel_alpha_beta_contradiction_candidate")
    case = store.get_contradiction_case(contradiction_case_id_for_claims(["clm_alpha", "clm_beta"]))
    assert result["decision"] == "accepted_contradiction_candidate"
    assert left is not None
    assert right is not None
    assert "clm_beta" in left.contradicts_claim_ids
    assert "clm_alpha" in right.contradicts_claim_ids
    assert relation is not None
    assert relation.current_status == "reviewed"
    assert case is not None
    assert case.metadata["accepted_candidate_relation_id"] == "rel_alpha_beta_contradiction_candidate"
    assert case.metadata["accepted_candidate_reviewer"] == "unit-test"


def test_accept_contradiction_candidate_writes_audit_event(tmp_path) -> None:
    store = GroundRecallStore(tmp_path / "groundrecall")
    store.save_claim(ClaimRecord(claim_id="clm_alpha", claim_text="Alpha is stable."))
    store.save_claim(ClaimRecord(claim_id="clm_beta", claim_text="Alpha is not stable."))
    store.save_relation(
        RelationRecord(
            relation_id="rel_alpha_beta_contradiction_candidate",
            source_id="clm_alpha",
            target_id="clm_beta",
            relation_type="claim_may_contradict_claim",
        )
    )
    audit_log = tmp_path / "audit" / "contradictions.jsonl"

    result = accept_contradiction_candidate(
        store.base_dir,
        relation_id="rel_alpha_beta_contradiction_candidate",
        reviewer="unit-test",
        rationale="The statements cannot both be true in the same scope.",
        reviewed_at="2026-07-28T00:00:00Z",
        audit_log_path=audit_log,
    )

    event = json.loads(audit_log.read_text(encoding="utf-8"))
    assert event["schema_version"] == "groundrecall.contradiction_candidate_audit.v1"
    assert event["action"] == "accept_contradiction_candidate"
    assert event["decision"] == "accepted"
    assert event["case_id"] == result["case"]["case_id"]
    assert event["relation_status"] == "reviewed"


def test_accept_contradiction_candidate_blocks_hard_policy_plugin_decision(tmp_path) -> None:
    store = GroundRecallStore(tmp_path / "groundrecall")
    store.save_claim(ClaimRecord(claim_id="clm_alpha", claim_text="Alpha is stable."))
    store.save_claim(ClaimRecord(claim_id="clm_beta", claim_text="Alpha is not stable."))
    store.save_relation(
        RelationRecord(
            relation_id="rel_alpha_beta_contradiction_candidate",
            source_id="clm_alpha",
            target_id="clm_beta",
            relation_type="claim_may_contradict_claim",
        )
    )
    config = tmp_path / "policy.yaml"
    config.write_text(
        "\n".join(
            [
                "schema_version: groundrecall.policy_plugins.v1",
                "policy_id: candidate.block.policy",
                "providers:",
                "  - type: groundrecall.static",
                "    policy_id: candidate.block.provider",
                "    default_decision: hard_gate",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ContradictionPolicyError) as excinfo:
        accept_contradiction_candidate(
            store.base_dir,
            relation_id="rel_alpha_beta_contradiction_candidate",
            reviewer="unit-test",
            rationale="The statements cannot both be true in the same scope.",
            policy_plugins_path=config,
            policy_subject_id="agent-1",
        )

    assert excinfo.value.payload["policy_plugin_decision"]["action"] == "accept_contradiction_candidate"
    assert excinfo.value.payload["policy_plugin_decision"]["decision"] == "hard_gate"
    assert store.get_claim("clm_alpha").contradicts_claim_ids == []
    assert store.get_contradiction_case(contradiction_case_id_for_claims(["clm_alpha", "clm_beta"])) is None


def test_accept_contradiction_candidate_writes_blocked_policy_audit_event(tmp_path) -> None:
    store = GroundRecallStore(tmp_path / "groundrecall")
    store.save_claim(ClaimRecord(claim_id="clm_alpha", claim_text="Alpha is stable."))
    store.save_claim(ClaimRecord(claim_id="clm_beta", claim_text="Alpha is not stable."))
    store.save_relation(
        RelationRecord(
            relation_id="rel_alpha_beta_contradiction_candidate",
            source_id="clm_alpha",
            target_id="clm_beta",
            relation_type="claim_may_contradict_claim",
        )
    )
    config = tmp_path / "policy.yaml"
    config.write_text(
        "\n".join(
            [
                "schema_version: groundrecall.policy_plugins.v1",
                "policy_id: candidate.block.policy",
                "providers:",
                "  - type: groundrecall.static",
                "    policy_id: candidate.block.provider",
                "    default_decision: hard_gate",
            ]
        ),
        encoding="utf-8",
    )
    audit_log = tmp_path / "audit" / "contradictions.jsonl"

    with pytest.raises(ContradictionPolicyError):
        accept_contradiction_candidate(
            store.base_dir,
            relation_id="rel_alpha_beta_contradiction_candidate",
            reviewer="unit-test",
            rationale="The statements cannot both be true in the same scope.",
            reviewed_at="2026-07-28T00:00:00Z",
            policy_plugins_path=config,
            audit_log_path=audit_log,
        )

    event = json.loads(audit_log.read_text(encoding="utf-8"))
    assert event["decision"] == "blocked"
    assert event["policy_plugin_decision"]["decision"] == "hard_gate"
    assert store.get_relation("rel_alpha_beta_contradiction_candidate").current_status == "draft"


def test_reject_contradiction_candidate_marks_relation_rejected_without_case(tmp_path) -> None:
    store = GroundRecallStore(tmp_path / "groundrecall")
    store.save_claim(ClaimRecord(claim_id="clm_alpha", claim_text="Alpha is stable."))
    store.save_claim(ClaimRecord(claim_id="clm_beta", claim_text="Alpha is not stable."))
    store.save_relation(
        RelationRecord(
            relation_id="rel_alpha_beta_contradiction_candidate",
            source_id="clm_alpha",
            target_id="clm_beta",
            relation_type="claim_may_contradict_claim",
        )
    )
    audit_log = tmp_path / "audit" / "contradictions.jsonl"

    result = reject_contradiction_candidate(
        store.base_dir,
        relation_id="rel_alpha_beta_contradiction_candidate",
        reviewer="unit-test",
        rationale="The cue is only a scope distinction.",
        reviewed_at="2026-07-28T00:00:00Z",
        audit_log_path=audit_log,
    )

    relation = store.get_relation("rel_alpha_beta_contradiction_candidate")
    assert result["decision"] == "rejected_contradiction_candidate"
    assert relation is not None
    assert relation.current_status == "rejected"
    assert store.get_claim("clm_alpha").contradicts_claim_ids == []
    assert store.get_contradiction_case(contradiction_case_id_for_claims(["clm_alpha", "clm_beta"])) is None
    event = json.loads(audit_log.read_text(encoding="utf-8"))
    assert event["action"] == "reject_contradiction_candidate"
    assert event["decision"] == "rejected"


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


def test_adjudicate_contradiction_case_records_soft_policy_plugin_decision(tmp_path) -> None:
    store = GroundRecallStore(tmp_path / "groundrecall")
    store.save_claim(ClaimRecord(claim_id="clm_alpha", claim_text="Alpha is stable.", contradicts_claim_ids=["clm_beta"], current_status="promoted"))
    store.save_claim(ClaimRecord(claim_id="clm_beta", claim_text="Alpha is not stable.", current_status="reviewed"))
    case = sync_contradiction_cases_for_store(store.base_dir)[0]
    config = tmp_path / "policy.yaml"
    config.write_text(
        "\n".join(
            [
                "schema_version: groundrecall.policy_plugins.v1",
                "policy_id: adjudication.soft.policy",
                "providers:",
                "  - type: groundrecall.static",
                "    policy_id: adjudication.soft.provider",
                "    default_decision: require_review",
            ]
        ),
        encoding="utf-8",
    )

    result = adjudicate_contradiction_case(
        store.base_dir,
        case_id=case.case_id,
        status="resolved",
        adjudicator="unit-test",
        rationale="Alpha is stable in scoped conditions.",
        selected_claim_ids=["clm_alpha"],
        decided_at="2026-07-26T00:00:00Z",
        adjudication_id="adj_policy_soft",
        policy_plugins_path=config,
        policy_subject_id="agent-1",
    )

    adjudication = store.get_adjudication("adj_policy_soft")
    assert result["policy_plugin_decision"]["decision"] == "require_review"
    assert adjudication is not None
    assert adjudication.metadata["policy_plugin_decision"]["subject_id"] == "agent-1"


def test_adjudicate_contradiction_case_blocks_hard_policy_plugin_decision(tmp_path) -> None:
    store = GroundRecallStore(tmp_path / "groundrecall")
    store.save_claim(ClaimRecord(claim_id="clm_alpha", claim_text="Alpha is stable.", contradicts_claim_ids=["clm_beta"], current_status="promoted"))
    store.save_claim(ClaimRecord(claim_id="clm_beta", claim_text="Alpha is not stable.", current_status="reviewed"))
    case = sync_contradiction_cases_for_store(store.base_dir)[0]
    config = tmp_path / "policy.yaml"
    config.write_text(
        "\n".join(
            [
                "schema_version: groundrecall.policy_plugins.v1",
                "policy_id: adjudication.block.policy",
                "providers:",
                "  - type: groundrecall.static",
                "    policy_id: adjudication.block.provider",
                "    default_decision: hard_gate",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ContradictionPolicyError) as excinfo:
        adjudicate_contradiction_case(
            store.base_dir,
            case_id=case.case_id,
            status="resolved",
            adjudicator="unit-test",
            rationale="Alpha is stable in scoped conditions.",
            selected_claim_ids=["clm_alpha"],
            decided_at="2026-07-26T00:00:00Z",
            adjudication_id="adj_policy_blocked",
            policy_plugins_path=config,
            policy_subject_id="agent-1",
        )

    assert excinfo.value.payload["policy_plugin_decision"]["decision"] == "hard_gate"
    assert store.get_adjudication("adj_policy_blocked") is None
    assert store.get_contradiction_case(case.case_id).status == "open"


def test_groundrecall_cli_routes_contradiction_sync(tmp_path, monkeypatch, capsys) -> None:
    store = GroundRecallStore(tmp_path / "groundrecall")
    store.save_claim(ClaimRecord(claim_id="clm_alpha", claim_text="Alpha is stable.", contradicts_claim_ids=["clm_beta"]))
    store.save_claim(ClaimRecord(claim_id="clm_beta", claim_text="Alpha is not stable."))
    monkeypatch.setattr("sys.argv", ["groundrecall", "contradictions", "sync", str(store.base_dir)])

    groundrecall_cli_main()

    output = capsys.readouterr().out
    assert '"decision": "synced"' in output
    assert store.list_contradiction_cases()


def test_groundrecall_cli_routes_contradiction_candidates(tmp_path, monkeypatch, capsys) -> None:
    store = GroundRecallStore(tmp_path / "groundrecall")
    store.save_claim(ClaimRecord(claim_id="clm_alpha", claim_text="Alpha is stable."))
    store.save_claim(ClaimRecord(claim_id="clm_beta", claim_text="Alpha is not stable."))
    store.save_relation(
        RelationRecord(
            relation_id="rel_alpha_beta_contradiction_candidate",
            source_id="clm_alpha",
            target_id="clm_beta",
            relation_type="claim_may_contradict_claim",
        )
    )
    monkeypatch.setattr("sys.argv", ["groundrecall", "contradictions", "candidates", str(store.base_dir)])

    groundrecall_cli_main()

    output = capsys.readouterr().out
    assert '"workflow_kind": "groundrecall_contradiction_candidate_review"' in output
    assert '"rel_alpha_beta_contradiction_candidate"' in output


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
