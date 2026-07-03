from __future__ import annotations

from pathlib import Path

from groundrecall.models import (
    ArtifactRecord,
    ClaimRecord,
    ConceptRecord,
    ObservationRecord,
    ProvenanceRecord,
    RelationRecord,
    ReviewCandidateRecord,
)
from groundrecall.query import (
    build_query_bundle_for_concept,
    query_concept,
    query_provenance,
    search_claims,
)
from groundrecall.store import GroundRecallStore


def _seed_store(store: GroundRecallStore) -> None:
    store.save_artifact(
        ArtifactRecord(
            artifact_id="ia_001",
            artifact_kind="compiled_page",
            title="Channel Capacity",
            path="wiki/channel-capacity.md",
            metadata={"source_role": "mechanism"},
            current_status="reviewed",
        )
    )
    store.save_observation(
        ObservationRecord(
            observation_id="obs_001",
            artifact_id="ia_001",
            role="claim",
            text="Reliable communication rate is bounded by channel capacity.",
            provenance=ProvenanceRecord(
                origin_artifact_id="ia_001",
                origin_path="wiki/channel-capacity.md",
                support_kind="derived_from_page",
                grounding_status="grounded",
            ),
            current_status="reviewed",
        )
    )
    store.save_concept(
        ConceptRecord(
            concept_id="concept::channel-capacity",
            title="Channel Capacity",
            description="Reliable communication limit.",
            source_artifact_ids=["ia_001"],
            current_status="promoted",
        )
    )
    store.save_concept(
        ConceptRecord(
            concept_id="concept::shannon-entropy",
            title="Shannon Entropy",
            description="Average uncertainty.",
            current_status="promoted",
        )
    )
    store.save_claim(
        ClaimRecord(
            claim_id="clm_001",
            claim_text="Channel capacity bounds reliable communication rate.",
            concept_ids=["concept::channel-capacity"],
            source_observation_ids=["obs_001"],
            confidence_hint=0.8,
            review_confidence=0.9,
            provenance=ProvenanceRecord(
                origin_artifact_id="ia_001",
                origin_path="wiki/channel-capacity.md",
                support_kind="derived_from_page",
                grounding_status="grounded",
            ),
            current_status="promoted",
        )
    )
    store.save_claim(
        ClaimRecord(
            claim_id="clm_002",
            claim_text="Channel capacity does not imply error-free transmission without coding.",
            concept_ids=["concept::channel-capacity"],
            source_observation_ids=["obs_001"],
            provenance=ProvenanceRecord(
                origin_artifact_id="ia_001",
                origin_path="wiki/channel-capacity.md",
                support_kind="derived_from_page",
                grounding_status="partially_grounded",
            ),
            current_status="reviewed",
        )
    )
    store.save_claim(
        ClaimRecord(
            claim_id="clm_003",
            claim_text="Shannon entropy can inform channel coding intuition.",
            concept_ids=["concept::shannon-entropy"],
            contradicts_claim_ids=["clm_999"],
            provenance=ProvenanceRecord(
                origin_artifact_id="ia_001",
                origin_path="wiki/channel-capacity.md",
                support_kind="derived_from_page",
                grounding_status="partially_grounded",
            ),
            current_status="reviewed",
        )
    )
    store.save_relation(
        RelationRecord(
            relation_id="rel_001",
            source_id="concept::channel-capacity",
            target_id="concept::shannon-entropy",
            relation_type="references",
            current_status="promoted",
        )
    )
    store.save_review_candidate(
        ReviewCandidateRecord(
            review_candidate_id="rq_concept_channel",
            candidate_type="concept",
            candidate_id="concept::channel-capacity",
            triage_lane="conflict_resolution",
            priority=12,
            finding_codes=["bridge_concept"],
            rationale="Channel Capacity | lane=conflict_resolution | priority=12 | graph=bridge_concept",
            current_status="reviewed",
        )
    )
    store.save_review_candidate(
        ReviewCandidateRecord(
            review_candidate_id="rq_claim_channel",
            candidate_type="claim",
            candidate_id="clm_001",
            triage_lane="knowledge_capture",
            priority=20,
            finding_codes=["claim_missing_concept"],
            rationale="Channel capacity bounds reliable communication rate. | lane=knowledge_capture | priority=20",
            current_status="reviewed",
        )
    )


def test_query_concept_returns_neighborhood_and_support(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "groundrecall")
    _seed_store(store)

    payload = query_concept(store.base_dir, "channel-capacity")
    assert payload is not None
    assert payload["concept"]["concept_id"] == "concept::channel-capacity"
    assert len(payload["claims"]) == 2
    assert len(payload["relations"]) == 1
    assert any(item["concept_id"] == "concept::shannon-entropy" for item in payload["related_concepts"])
    assert payload["supporting_observations"][0]["origin_path"] == "wiki/channel-capacity.md"
    assert payload["supporting_observations"][0]["source_role"] == "mechanism"
    assert len(payload["review_candidates"]) == 2
    assert any(item["candidate_id"] == "concept::channel-capacity" for item in payload["review_candidates"])
    assert any("graph=bridge_concept" in item["rationale"] for item in payload["review_candidates"])


def test_search_claims_matches_text_and_concept_titles(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "groundrecall")
    _seed_store(store)

    payload = search_claims(store.base_dir, "entropy")
    assert payload["query_type"] == "claim_search"
    assert any(match["claim"]["claim_id"] == "clm_003" for match in payload["matches"])


def test_query_provenance_filters_by_origin_path(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "groundrecall")
    _seed_store(store)

    payload = query_provenance(store.base_dir, origin_path="wiki/channel-capacity.md")
    assert len(payload["claims"]) == 3
    assert len(payload["observations"]) == 1


def test_build_query_bundle_for_concept_is_assistant_neutral(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "groundrecall")
    _seed_store(store)

    payload = build_query_bundle_for_concept(store.base_dir, "channel capacity")
    assert payload is not None
    assert payload["bundle_kind"] == "groundrecall_query_bundle"
    assert payload["concept"]["concept_id"] == "concept::channel-capacity"
    assert len(payload["relations"]) == 1
    assert payload["source_artifacts"][0]["artifact_id"] == "ia_001"
    assert payload["source_artifacts"][0]["source_role"] == "mechanism"
    assert payload["source_role_summary"]["mechanism"] == 2
    assert payload["key_distinctions"][0]["distinction_type"] == "non_implication"
    assert payload["relevant_claims"][0]["source_roles"] == ["mechanism"]
    assert len(payload["review_candidates"]) == 2
    assert payload["epistemap_graph"]["bundle_kind"] == "epistemap_graph_bundle"
    graph_edges = {(edge["source"], edge["target"], edge["type"]) for edge in payload["epistemap_graph"]["edges"]}
    assert ("clm_001", "concept::channel-capacity", "about_concept") in graph_edges
    assert ("obs_001", "clm_001", "supports_claim") in graph_edges
    assert payload["epistemic_summary"]["node_id"] == "concept::channel-capacity"
    assert payload["epistemic_summary"]["summary"]["direct_support_count"] >= 1
    assert payload["epistemic_summary"]["reliability"]["band"] in {"moderate", "strong"}
    assert payload["epistemic_summary"]["reliability"]["components"]["grounding"] > 0
    assert isinstance(payload["suggested_next_actions"], list)
    forbidden = {"assistant", "codex", "claude", "prompt_text"}
    assert set(payload).isdisjoint(forbidden)


def test_query_bundle_surfaces_contradictions_and_supersessions(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "groundrecall")
    _seed_store(store)
    store.save_claim(
        ClaimRecord(
            claim_id="clm_004",
            claim_text="Channel capacity is undefined in practice.",
            concept_ids=["concept::channel-capacity"],
            contradicts_claim_ids=["clm_001"],
            provenance=ProvenanceRecord(
                origin_artifact_id="ia_001",
                origin_path="wiki/channel-capacity.md",
                support_kind="derived_from_page",
                grounding_status="partially_grounded",
            ),
            current_status="reviewed",
        )
    )
    store.save_claim(
        ClaimRecord(
            claim_id="clm_005",
            claim_text="Channel capacity should be interpreted relative to a specific channel model.",
            concept_ids=["concept::channel-capacity"],
            supersedes_claim_ids=["clm_001"],
            provenance=ProvenanceRecord(
                origin_artifact_id="ia_001",
                origin_path="wiki/channel-capacity.md",
                support_kind="derived_from_page",
                grounding_status="grounded",
            ),
            current_status="reviewed",
        )
    )

    payload = build_query_bundle_for_concept(store.base_dir, "channel-capacity")
    assert payload is not None
    contradiction_ids = {item["claim_id"] for item in payload["contradictions"]}
    supersession_ids = {item["claim_id"] for item in payload["supersessions"]}
    assert "clm_004" in contradiction_ids
    assert "clm_005" in supersession_ids
    assert "challenged" in payload["epistemic_summary"]["flags"]
    assert payload["epistemic_summary"]["reliability"]["components"]["challenge_penalty"] > 0
