from __future__ import annotations

import json
from pathlib import Path

import pytest

from groundrecall.models import ArtifactRecord, ClaimRecord, ConceptRecord, ObservationRecord, ProvenanceRecord, RelationRecord
from groundrecall.query import build_search_bundle
from groundrecall.search_index import build_search_index, search_index
from groundrecall.store import GroundRecallStore
from groundrecall.workspace import WORKSPACE_MANIFEST_NAME, WorkspaceConfigurationError, workspace_manifest_payload


def test_index_searches_claims_concepts_and_source_notes(tmp_path: Path) -> None:
    base = tmp_path / "groundrecall" / "store"
    store = GroundRecallStore(base)
    store.save_concept(
        ConceptRecord(
            concept_id="concept::latency-budget",
            title="Latency Budget",
            aliases=["response latency"],
            description="Tracking prefill and decode latency.",
            current_status="promoted",
        )
    )
    store.save_claim(
        ClaimRecord(
            claim_id="claim_latency_001",
            claim_text="Prompt prefill grows with input token count.",
            concept_ids=["concept::latency-budget"],
            provenance=ProvenanceRecord(origin_path="notes/latency.md", grounding_status="grounded"),
            current_status="reviewed",
        )
    )
    notes = base.parent / "source-notes"
    notes.mkdir(parents=True)
    (notes / "sip-agent.md").write_text(
        "# SIP Agent Notes\n\nPrefix caching helps repeated role prompts stay responsive.\n",
        encoding="utf-8",
    )

    result = build_search_index(base)
    assert result["document_count"] == 3

    payload = search_index(base, "prefix caching")
    assert payload["query_type"] == "indexed_search"
    assert payload["matches"][0]["kind"] == "source_note"

    claim_payload = search_index(base, "prefill token count")
    assert any(match["record_id"] == "claim_latency_001" for match in claim_payload["matches"])


def test_query_search_bundle_uses_index(tmp_path: Path) -> None:
    base = tmp_path / "groundrecall"
    store = GroundRecallStore(base)
    store.save_claim(
        ClaimRecord(
            claim_id="claim_state_001",
            claim_text="A next-state prediction must be validated before tool execution.",
            provenance=ProvenanceRecord(origin_path="state-machines.md", grounding_status="grounded"),
            current_status="reviewed",
        )
    )

    payload = build_search_bundle(base, "tool execution")
    assert payload["query_type"] == "indexed_search"
    assert payload["matches"][0]["record_id"] == "claim_state_001"
    assert "index_path" in payload


def test_expansion_surfaces_linked_records(tmp_path: Path) -> None:
    base = tmp_path / "groundrecall"
    store = GroundRecallStore(base)
    store.save_artifact(
        ArtifactRecord(
            artifact_id="artifact_001",
            artifact_kind="source_note",
            title="State Machine Notes",
            path="state-machine-notes.md",
            current_status="reviewed",
        )
    )
    store.save_observation(
        ObservationRecord(
            observation_id="obs_001",
            artifact_id="artifact_001",
            role="claim",
            text="The orchestrator validates predicted next states before tools run.",
            provenance=ProvenanceRecord(origin_path="state-machine-notes.md", grounding_status="grounded"),
            current_status="reviewed",
        )
    )
    store.save_concept(
        ConceptRecord(
            concept_id="concept::state-validation",
            title="State Validation",
            description="Validation of predicted next states.",
            source_artifact_ids=["artifact_001"],
            current_status="promoted",
        )
    )
    store.save_claim(
        ClaimRecord(
            claim_id="claim_state_validation",
            claim_text="Predicted next states must be checked against the allowed transition set.",
            concept_ids=["concept::state-validation"],
            source_observation_ids=["obs_001"],
            provenance=ProvenanceRecord(origin_path="state-machine-notes.md", grounding_status="grounded"),
            current_status="reviewed",
        )
    )
    store.save_relation(
        RelationRecord(
            relation_id="rel_001",
            source_id="concept::state-validation",
            target_id="concept::latency-budget",
            relation_type="supports",
            current_status="reviewed",
        )
    )

    payload = search_index(base, "state validation", expand=True)
    concept_match = next(match for match in payload["matches"] if match["kind"] == "concept")
    associations = payload["associations"][concept_match["doc_key"]]

    assert any(item["record_id"] == "claim_state_validation" for item in associations)
    assert any(item["record_id"] == "artifact_001" for item in associations)
    assert any(item["record_id"] == "rel_001" for item in associations)


def test_kind_filter_is_applied_before_fts_page_limit(tmp_path: Path) -> None:
    base = tmp_path / "groundrecall"
    store = GroundRecallStore(base)
    store.save_concept(
        ConceptRecord(
            concept_id="concept::natural-selection",
            title="Natural Selection",
            description="Differential survival and reproduction.",
            current_status="promoted",
        )
    )
    store.save_concept(
        ConceptRecord(
            concept_id="concept::generic-section",
            title="Generic Section",
            current_status="promoted",
        )
    )
    for index in range(20):
        store.save_claim(
            ClaimRecord(
                claim_id=f"claim_selection_noise_{index}",
                claim_text="Natural selection adaptation appears in this operational note.",
                concept_ids=["concept::generic-section"],
                provenance=ProvenanceRecord(origin_path=f"notes/noise-{index}.md", grounding_status="grounded"),
                current_status="reviewed",
            )
        )

    payload = search_index(base, "natural selection adaptation", kinds=["concept"], limit=1)

    assert [match["record_id"] for match in payload["matches"]] == ["concept::natural-selection"]


def test_index_read_does_not_create_typed_store_directories(tmp_path: Path) -> None:
    base = tmp_path / "uninitialized-store"

    result = build_search_index(base)

    assert result["document_count"] == 0
    assert (base / ".index" / "groundrecall-search.sqlite").is_file()
    assert not (base / "claims").exists()
    assert not (base / "concepts").exists()


def test_manifested_workspace_scopes_exclude_wrong_root_records(tmp_path: Path) -> None:
    from groundrecall.search_index import build_scoped_search_index, search_scoped_index

    workspace = tmp_path / "groundrecall"
    workspace.mkdir()
    canonical = GroundRecallStore(workspace / "store")
    canonical.save_claim(
        ClaimRecord(
            claim_id="claim_canonical",
            claim_text="Canonical alpha evidence.",
            current_status="reviewed",
        )
    )
    wrong_root = GroundRecallStore(workspace)
    wrong_root.save_claim(
        ClaimRecord(
            claim_id="claim_wrong_root",
            claim_text="Wrong-root alpha evidence.",
            current_status="reviewed",
        )
    )
    (workspace / WORKSPACE_MANIFEST_NAME).write_text(
        json.dumps(workspace_manifest_payload(workspace_id="search-test"), indent=2),
        encoding="utf-8",
    )
    notes = workspace / "source-notes"
    notes.mkdir()
    (notes / "orientation.md").write_text("# Orientation\n\nAlpha note evidence.\n", encoding="utf-8")

    notes_result = build_scoped_search_index(workspace, "notes")
    canonical_result = build_scoped_search_index(workspace, "canonical")
    unified_result = build_scoped_search_index(workspace, "unified")

    assert notes_result["document_count"] == 1
    assert canonical_result["document_count"] == 1
    assert unified_result["document_count"] == 2
    payload = search_scoped_index(workspace, "alpha evidence", scope="unified")
    ids = {match["record_id"] for match in payload["matches"]}
    assert ids == {"claim_canonical", "orientation"}
    assert "claim_wrong_root" not in ids

    query_bundle = build_search_bundle(workspace / "store", "alpha evidence")
    assert query_bundle["scope"] == "canonical"
    assert {match["record_id"] for match in query_bundle["matches"]} == {"claim_canonical"}


def test_manifested_workspace_requires_explicit_scope(tmp_path: Path) -> None:
    from groundrecall.search_index import resolve_scoped_search

    workspace = tmp_path / "groundrecall"
    workspace.mkdir()
    (workspace / WORKSPACE_MANIFEST_NAME).write_text(
        json.dumps(workspace_manifest_payload(workspace_id="search-test")),
        encoding="utf-8",
    )

    with pytest.raises(WorkspaceConfigurationError, match="requires --scope"):
        resolve_scoped_search(workspace, None)
