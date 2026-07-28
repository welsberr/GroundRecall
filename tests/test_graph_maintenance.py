from __future__ import annotations

import json
from pathlib import Path
import sys

from groundrecall.graph_maintenance import default_state_path, run_graph_maintenance_slice
from groundrecall.models import ArtifactRecord, ClaimRecord, ConceptRecord, ObservationRecord, ProvenanceRecord
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


def test_graph_maintenance_default_profile_remains_safe(tmp_path: Path) -> None:
    store = _seed_claim_cooccurrence_store(tmp_path / "store")

    payload = run_graph_maintenance_slice(
        store.base_dir,
        limit=1,
        apply=False,
    )

    assert payload["profile"] == "safe"
    assert payload["strategies"] == ["claim-cooccurrence", "claim-mentions", "observation-cooccurrence", "source-family"]
    assert "claim-support-anchors" not in payload["strategies"]
    assert "observation-artifact-anchors" not in payload["strategies"]


def test_graph_maintenance_default_state_path_is_profile_specific(tmp_path: Path) -> None:
    store = _seed_claim_cooccurrence_store(tmp_path / "store")

    safe = run_graph_maintenance_slice(
        store.base_dir,
        profile="safe",
        limit=1,
        apply=False,
    )
    support = run_graph_maintenance_slice(
        store.base_dir,
        profile="support",
        limit=1,
        apply=False,
    )

    assert safe["state_path"].endswith("graph_maintenance_state__safe.json")
    assert support["state_path"].endswith("graph_maintenance_state__support.json")
    assert safe["state_path"] != support["state_path"]
    assert default_state_path(store.base_dir, "semantic review").name == "graph_maintenance_state__semantic-review.json"


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


def test_graph_maintenance_support_profile_runs_support_anchors(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    state_path = tmp_path / "state.json"
    store.save_artifact(
        ArtifactRecord(
            artifact_id="art_source",
            artifact_kind="source_note",
            current_status="reviewed",
        )
    )
    store.save_observation(
        ObservationRecord(
            observation_id="obs_source",
            artifact_id="art_source",
            role="evidence",
            text="Observed support.",
            current_status="reviewed",
        )
    )
    store.save_claim(
        ClaimRecord(
            claim_id="claim_supported",
            claim_text="A supported claim.",
            source_observation_ids=["obs_source"],
            current_status="reviewed",
        )
    )

    first = run_graph_maintenance_slice(
        store.base_dir,
        state_path=state_path,
        profile="support",
        limit=1,
        apply=True,
    )
    second = run_graph_maintenance_slice(
        store.base_dir,
        state_path=state_path,
        profile="support",
        limit=1,
        apply=True,
    )

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert first["selected_strategy"] == "claim-support-anchors"
    assert second["selected_strategy"] == "observation-artifact-anchors"
    assert state["profile"] == "support"
    assert state["strategies"] == ["claim-support-anchors", "observation-artifact-anchors"]
    assert len(store.list_relations()) == 2


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


def test_groundrecall_cli_graph_maintenance_profile_dispatches(tmp_path: Path, capsys) -> None:
    store = _seed_claim_cooccurrence_store(tmp_path / "store")
    from groundrecall import cli

    original = sys.argv
    try:
        sys.argv = [
            "groundrecall.cli",
            "graph-maintenance",
            str(store.base_dir),
            "--profile",
            "support",
            "--limit",
            "1",
        ]
        cli.main()
    finally:
        sys.argv = original

    output = capsys.readouterr().out
    assert '"profile": "support"' in output
    assert '"claim-support-anchors"' in output


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


def test_graph_maintenance_passes_pair_check_budget(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    store.save_concept(ConceptRecord(concept_id="concept::selection", title="Selection", current_status="promoted"))
    for index in range(2):
        store.save_claim(
            ClaimRecord(
                claim_id=f"claim_affirm_{index}",
                claim_text="Selection changes adaptation in populations.",
                concept_ids=["concept::selection"],
                current_status="reviewed",
            )
        )
    for index in range(2):
        store.save_claim(
            ClaimRecord(
                claim_id=f"claim_negate_{index}",
                claim_text="Selection does not change adaptation in populations.",
                concept_ids=["concept::selection"],
                current_status="reviewed",
            )
        )

    payload = run_graph_maintenance_slice(
        store.base_dir,
        strategies=["claim-contradiction-cues"],
        max_pair_checks=2,
        apply=False,
    )

    assert payload["run_record"]["max_pair_checks"] == 2
    assert payload["run_record"]["filter_summary"]["pair_check_count"] == 2
    assert payload["run_record"]["filter_summary"]["pair_check_limit_reached"] is True
