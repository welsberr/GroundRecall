from __future__ import annotations

import json
from pathlib import Path
import sys

from groundrecall.graph_maintenance import run_graph_maintenance_slice
from groundrecall.models import ClaimRecord, ConceptRecord, ObservationRecord, ProvenanceRecord
from groundrecall.store import GroundRecallStore


def _seed_claim_cooccurrence_store(base: Path) -> GroundRecallStore:
    store = GroundRecallStore(base)
    for concept_id, title in [
        ("concept::selection", "Selection"),
        ("concept::adaptation", "Adaptation"),
        ("concept::fitness", "Fitness"),
    ]:
        store.save_concept(ConceptRecord(concept_id=concept_id, title=title, current_status="promoted"))
    for index in range(2):
        store.save_claim(
            ClaimRecord(
                claim_id=f"claim_pair_{index}",
                claim_text="Selection and adaptation are linked.",
                concept_ids=["concept::selection", "concept::adaptation"],
                source_observation_ids=[f"obs_pair_{index}"],
                provenance=ProvenanceRecord(origin_path="sources/pairs.md", grounding_status="grounded"),
                current_status="reviewed",
            )
        )
    return store


def test_graph_maintenance_dry_run_does_not_write_or_advance_state(tmp_path: Path) -> None:
    store = _seed_claim_cooccurrence_store(tmp_path / "store")
    state_path = tmp_path / "state.json"

    payload = run_graph_maintenance_slice(
        store.base_dir,
        state_path=state_path,
        strategies=["claim-cooccurrence"],
        limit=1,
        apply=False,
    )

    assert payload["state_advanced"] is False
    assert payload["selected_strategy"] == "claim-cooccurrence"
    assert payload["augmentation"]["candidate_relation_count"] == 1
    assert store.list_relations() == []
    assert not state_path.exists()


def test_graph_maintenance_apply_writes_bounded_slice_and_advances_state(tmp_path: Path) -> None:
    store = _seed_claim_cooccurrence_store(tmp_path / "store")
    state_path = tmp_path / "state.json"

    payload = run_graph_maintenance_slice(
        store.base_dir,
        state_path=state_path,
        strategies=["claim-cooccurrence", "source-family"],
        limit=1,
        apply=True,
    )

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload["state_advanced"] is True
    assert payload["selected_strategy"] == "claim-cooccurrence"
    assert payload["next_strategy"] == "source-family"
    assert len(store.list_relations()) == 1
    assert len(store.list_review_candidates()) == 1
    assert state["run_count"] == 1
    assert state["next_strategy_index"] == 1
    assert state["last_run"]["candidate_relation_count"] == 1
    assert state["last_run"]["filter_summary"]["skipped_duplicate_relation_count"] == 0


def test_graph_maintenance_resumes_strategy_rotation(tmp_path: Path) -> None:
    store = _seed_claim_cooccurrence_store(tmp_path / "store")
    state_path = tmp_path / "state.json"
    run_graph_maintenance_slice(
        store.base_dir,
        state_path=state_path,
        strategies=["claim-cooccurrence", "observation-cooccurrence"],
        limit=1,
        apply=True,
    )
    store.save_observation(
        ObservationRecord(
            observation_id="obs_existing_1",
            artifact_id="art_existing",
            role="evidence",
            text="Selection can shape adaptation.",
            provenance=ProvenanceRecord(origin_path="sources/existing.md", grounding_status="grounded"),
            current_status="reviewed",
        )
    )
    store.save_observation(
        ObservationRecord(
            observation_id="obs_existing_2",
            artifact_id="art_existing",
            role="evidence",
            text="Adaptation may reflect selection.",
            provenance=ProvenanceRecord(origin_path="sources/existing.md", grounding_status="grounded"),
            current_status="reviewed",
        )
    )

    payload = run_graph_maintenance_slice(
        store.base_dir,
        state_path=state_path,
        strategies=["claim-cooccurrence", "observation-cooccurrence"],
        limit=1,
        apply=True,
    )

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload["selected_strategy"] == "observation-cooccurrence"
    assert state["run_count"] == 2
    assert state["next_strategy_index"] == 0
    assert len(state["history"]) == 2


def test_groundrecall_cli_graph_maintenance_dispatches(tmp_path: Path, capsys) -> None:
    store = _seed_claim_cooccurrence_store(tmp_path / "store")
    from groundrecall import cli

    original = sys.argv
    try:
        sys.argv = [
            "groundrecall.cli",
            "graph-maintenance",
            str(store.base_dir),
            "--strategy",
            "claim-cooccurrence",
            "--limit",
            "1",
        ]
        cli.main()
    finally:
        sys.argv = original

    output = capsys.readouterr().out
    assert '"operation": "run_graph_maintenance_slice"' in output
    assert '"state_advanced": false' in output


def test_graph_maintenance_can_run_claim_links_strategy(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    store.save_claim(
        ClaimRecord(
            claim_id="claim_a",
            claim_text="A.",
            contradicts_claim_ids=["claim_b"],
            current_status="reviewed",
        )
    )
    store.save_claim(ClaimRecord(claim_id="claim_b", claim_text="B.", current_status="reviewed"))

    payload = run_graph_maintenance_slice(
        store.base_dir,
        strategies=["claim-links"],
        limit=1,
        apply=True,
    )

    assert payload["selected_strategy"] == "claim-links"
    assert payload["run_record"]["relation_type_counts"] == {"claim_contradicts_claim": 1}
    assert len(store.list_relations()) == 1
