from __future__ import annotations

from pathlib import Path

from groundrecall.models import ArtifactRecord, ClaimRecord, ConceptRecord, ObservationRecord, ProvenanceRecord, RelationRecord
from groundrecall.query import build_search_bundle
from groundrecall.search_index import build_search_index, search_index
from groundrecall.store import GroundRecallStore


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
