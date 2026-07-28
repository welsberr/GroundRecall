from __future__ import annotations

from pathlib import Path
import sys

import pytest

from groundrecall.graph_augment import GraphAugmentPolicyError, augment_store_relations_from_claims
from groundrecall.models import (
    ArtifactRecord,
    ClaimRecord,
    ConceptRecord,
    FragmentRecord,
    ObservationRecord,
    ProvenanceRecord,
    SourceRecord,
)
from groundrecall.store import GroundRecallStore


def _seed_store(base: Path) -> GroundRecallStore:
    store = GroundRecallStore(base)
    for concept_id, title in [
        ("concept::evo-edu-selection", "Selection"),
        ("concept::evo-edu-adaptation", "Adaptation"),
        ("concept::operational-boundary", "Boundary"),
    ]:
        store.save_concept(ConceptRecord(concept_id=concept_id, title=title, current_status="promoted"))
    for index in range(3):
        store.save_claim(
            ClaimRecord(
                claim_id=f"claim_evo_{index}",
                claim_text="Selection and adaptation are linked in this source.",
                concept_ids=["concept::evo-edu-selection", "concept::evo-edu-adaptation", "concept::operational-boundary"],
                source_observation_ids=[f"obs_{index}"],
                provenance=ProvenanceRecord(origin_path="sources/evo.md", support_kind="derived_from_page", grounding_status="grounded"),
                current_status="reviewed",
            )
        )
    return store


def _write_static_policy_config(path: Path, *, decision: str, policy_id: str = "graph.policy.test") -> Path:
    path.write_text(
        "\n".join(
            [
                "schema_version: groundrecall.policy_plugins.v1",
                f"policy_id: {policy_id}",
                "providers:",
                "  - type: static",
                f"    policy_id: {policy_id}.provider",
                f"    default_decision: {decision}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return path


def test_augment_store_relations_from_claims_dry_run_does_not_write(tmp_path: Path) -> None:
    store = _seed_store(tmp_path / "store")

    payload = augment_store_relations_from_claims(
        store.base_dir,
        concept_prefixes=["concept::evo-edu"],
        min_evidence=2,
        apply=False,
    )

    assert payload["applied"] is False
    assert payload["candidate_relation_count"] == 1
    assert payload["raw_candidate_relation_count"] == 1
    assert payload["relation_examples"][0]["relation_type"] == "co_occurs_with"
    assert payload["relation_examples"][0]["evidence_count"] == 3
    assert "support_kind=inferred" in payload["relation_examples"][0]["review_rationale"]
    assert payload["filter_summary"]["below_min_evidence_count"] == 0
    assert payload["filter_summary"]["skipped_duplicate_relation_count"] == 0
    assert payload["relations"][0]["source_id"] == "concept::evo-edu-adaptation"
    assert payload["relations"][0]["target_id"] == "concept::evo-edu-selection"
    assert store.list_relations() == []


def test_augment_store_relations_from_claims_apply_writes_reviewable_relation(tmp_path: Path) -> None:
    store = _seed_store(tmp_path / "store")

    payload = augment_store_relations_from_claims(
        store.base_dir,
        concept_prefixes=["concept::evo-edu"],
        min_evidence=2,
        apply=True,
    )

    relations = store.list_relations()
    review_candidates = store.list_review_candidates()
    assert payload["applied"] is True
    assert len(relations) == 1
    assert relations[0].relation_type == "co_occurs_with"
    assert relations[0].provenance.support_kind == "inferred"
    assert relations[0].current_status == "triaged"
    assert len(review_candidates) == 1
    assert review_candidates[0].candidate_type == "relation"
    assert "claim_cooccurrence" in review_candidates[0].finding_codes
    assert payload["write_summary"]["relation_write_count"] == 1
    assert payload["diagnostic_layers"]["candidate_semantic_relations"] == 1


def test_augment_store_relations_soft_policy_plugin_records_decision(tmp_path: Path) -> None:
    store = _seed_store(tmp_path / "store")
    policy_config = _write_static_policy_config(tmp_path / "policy.yaml", decision="soft_gate")

    payload = augment_store_relations_from_claims(
        store.base_dir,
        concept_prefixes=["concept::evo-edu"],
        min_evidence=2,
        apply=True,
        policy_plugins_path=policy_config,
        policy_subject_id="agent-1",
    )

    assert payload["write_summary"]["relation_write_count"] == 1
    assert payload["write_summary"]["policy_plugin_decision"]["decision"] == "soft_gate"
    assert payload["write_summary"]["policy_plugin_decision"]["subject_id"] == "agent-1"


def test_augment_store_relations_hard_policy_plugin_blocks_without_writes(tmp_path: Path) -> None:
    store = _seed_store(tmp_path / "store")
    policy_config = _write_static_policy_config(tmp_path / "policy.yaml", decision="hard_gate")

    with pytest.raises(GraphAugmentPolicyError) as excinfo:
        augment_store_relations_from_claims(
            store.base_dir,
            concept_prefixes=["concept::evo-edu"],
            min_evidence=2,
            apply=True,
            policy_plugins_path=policy_config,
            policy_subject_id="agent-1",
        )

    assert excinfo.value.payload["blocked_by_policy"] is True
    assert excinfo.value.payload["policy_plugin_decision"]["decision"] == "hard_gate"
    assert store.list_relations() == []
    assert store.list_review_candidates() == []


def test_augment_store_relations_extractor_mode_none_disables_candidate_generation(tmp_path: Path) -> None:
    store = _seed_store(tmp_path / "store")

    payload = augment_store_relations_from_claims(
        store.base_dir,
        concept_prefixes=["concept::evo-edu"],
        min_evidence=2,
        extractor_mode="none",
        apply=True,
    )

    assert payload["extractor_mode"] == "none"
    assert payload["extractor"] == "none"
    assert payload["candidate_relation_count"] == 0
    assert payload["relation_examples"] == []
    assert payload["write_summary"]["relation_write_count"] == 0
    assert store.list_relations() == []


def test_augment_store_relations_from_claims_is_idempotent(tmp_path: Path) -> None:
    store = _seed_store(tmp_path / "store")

    first = augment_store_relations_from_claims(
        store.base_dir,
        concept_prefixes=["concept::evo-edu"],
        min_evidence=2,
        apply=True,
    )
    second = augment_store_relations_from_claims(
        store.base_dir,
        concept_prefixes=["concept::evo-edu"],
        min_evidence=2,
        apply=True,
    )

    assert first["candidate_relation_count"] == 1
    assert second["candidate_relation_count"] == 0
    assert second["filter_summary"]["skipped_duplicate_relation_count"] == 1
    assert second["filter_summary"]["skipped_duplicate_relation_type_counts"] == {"co_occurs_with": 1}
    assert len(store.list_relations()) == 1
    assert len(store.list_review_candidates()) == 1


def test_augment_store_relations_from_claims_min_evidence_filters_weak_pairs(tmp_path: Path) -> None:
    store = _seed_store(tmp_path / "store")

    payload = augment_store_relations_from_claims(
        store.base_dir,
        concept_prefixes=["concept::evo-edu"],
        min_evidence=4,
        apply=True,
    )

    assert payload["candidate_relation_count"] == 0
    assert payload["raw_candidate_relation_count"] == 1
    assert payload["filter_summary"]["below_min_evidence_count"] == 1
    assert store.list_relations() == []


def test_augment_store_relations_skips_private_claims_and_concepts(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    store.save_concept(ConceptRecord(concept_id="concept::public-a", title="Public A", current_status="reviewed"))
    store.save_concept(ConceptRecord(concept_id="concept::public-b", title="Public B", current_status="reviewed"))
    store.save_concept(
        ConceptRecord(
            concept_id="concept::private-c",
            title="Private C",
            metadata={"release_status": "no_export"},
            current_status="reviewed",
        )
    )
    store.save_claim(
        ClaimRecord(
            claim_id="claim_private",
            claim_text="Private claim should not seed graph edges.",
            concept_ids=["concept::public-a", "concept::public-b"],
            metadata={"release_level": "private"},
            current_status="reviewed",
        )
    )
    store.save_claim(
        ClaimRecord(
            claim_id="claim_private_concept",
            claim_text="A public claim to a private concept should not seed that private endpoint.",
            concept_ids=["concept::public-a", "concept::private-c"],
            current_status="reviewed",
        )
    )

    payload = augment_store_relations_from_claims(store.base_dir, min_evidence=1, apply=True)

    assert payload["candidate_relation_count"] == 0
    assert store.list_relations() == []


def test_augment_store_relations_reports_limit_omissions(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    for concept_id in ["concept::a", "concept::b", "concept::c"]:
        store.save_concept(ConceptRecord(concept_id=concept_id, title=concept_id.removeprefix("concept::").upper(), current_status="promoted"))
    store.save_claim(
        ClaimRecord(
            claim_id="claim_many_pairs",
            claim_text="A, B, and C are linked.",
            concept_ids=["concept::a", "concept::b", "concept::c"],
            source_observation_ids=["obs_many_pairs"],
            provenance=ProvenanceRecord(origin_path="sources/many.md", grounding_status="grounded"),
            current_status="reviewed",
        )
    )

    payload = augment_store_relations_from_claims(
        store.base_dir,
        min_evidence=1,
        limit=1,
        apply=False,
    )

    assert payload["raw_candidate_relation_count"] == 3
    assert payload["candidate_relation_count"] == 1
    assert payload["filter_summary"]["omitted_by_limit_count"] == 2


def test_augment_store_relations_from_source_family(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    store.save_concept(
        ConceptRecord(
            concept_id="concept::evo-edu-notebook-futuyma-selection-ingestion",
            title="Evo Edu Notebook Futuyma Selection Ingestion",
            source_artifact_ids=["artifact_selection"],
            current_status="promoted",
        )
    )
    store.save_concept(
        ConceptRecord(
            concept_id="concept::evo-edu-notebook-futuyma-soft-selection-ingestion",
            title="Evo Edu Notebook Futuyma Soft Selection Ingestion",
            source_artifact_ids=["artifact_soft_selection"],
            current_status="promoted",
        )
    )
    store.save_concept(
        ConceptRecord(
            concept_id="concept::evo-edu-notebook-pianka-species-area-ingestion",
            title="Evo Edu Notebook Pianka Species Area Ingestion",
            source_artifact_ids=["artifact_species_area"],
            current_status="promoted",
        )
    )

    payload = augment_store_relations_from_claims(
        store.base_dir,
        concept_prefixes=["concept::evo-edu-notebook"],
        strategy="source-family",
        apply=True,
    )

    relations = store.list_relations()
    assert payload["candidate_relation_count"] == 1
    assert relations[0].relation_type == "same_source_family"
    assert relations[0].source_id == "concept::evo-edu-notebook-futuyma-selection-ingestion"
    assert relations[0].target_id == "concept::evo-edu-notebook-futuyma-soft-selection-ingestion"
    assert set(relations[0].evidence_ids) == {"artifact_selection", "artifact_soft_selection"}


def test_augment_store_relations_from_claim_mentions(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    store.save_concept(
        ConceptRecord(
            concept_id="concept::evo-edu-notebook-darwin-homologous-limbs-ingestion",
            title="Evo Edu Notebook Darwin Homologous Limbs Ingestion",
            current_status="promoted",
        )
    )
    store.save_concept(
        ConceptRecord(
            concept_id="concept::evo-edu-notebook-futuyma-common-descent-evidence-ingestion",
            title="Evo Edu Notebook Futuyma Common Descent Evidence Ingestion",
            current_status="promoted",
        )
    )
    store.save_concept(
        ConceptRecord(
            concept_id="concept::evo-edu-notebook-current-processing-state",
            title="Evo Edu Notebook Current Processing State",
            current_status="promoted",
        )
    )
    store.save_claim(
        ClaimRecord(
            claim_id="claim_homologous_evidence",
            claim_text="A common descent evidence question can be based on homologous vertebrate limbs.",
            concept_ids=["concept::evo-edu-notebook-darwin-homologous-limbs-ingestion"],
            source_observation_ids=["obs_homologous_evidence"],
            provenance=ProvenanceRecord(origin_path="sources/darwin.md", grounding_status="grounded"),
            current_status="reviewed",
        )
    )
    store.save_claim(
        ClaimRecord(
            claim_id="claim_processing_state",
            claim_text="Current processing state records mention common descent evidence while tracking queue progress.",
            concept_ids=["concept::evo-edu-notebook-current-processing-state"],
            source_observation_ids=["obs_processing_state"],
            provenance=ProvenanceRecord(origin_path="sources/current-processing-state.md", grounding_status="grounded"),
            current_status="reviewed",
        )
    )

    payload = augment_store_relations_from_claims(
        store.base_dir,
        concept_prefixes=["concept::evo-edu-notebook"],
        strategy="claim-mentions",
        apply=True,
    )

    relations = store.list_relations()
    assert payload["candidate_relation_count"] == 1
    assert relations[0].source_id == "concept::evo-edu-notebook-darwin-homologous-limbs-ingestion"
    assert relations[0].target_id == "concept::evo-edu-notebook-futuyma-common-descent-evidence-ingestion"
    assert relations[0].relation_type == "provides_evidence_for"
    assert relations[0].evidence_ids == ["obs_homologous_evidence"]


def test_augment_store_relations_from_claim_links(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    store.save_claim(
        ClaimRecord(
            claim_id="claim_old",
            claim_text="The old claim.",
            source_observation_ids=["obs_old"],
            provenance=ProvenanceRecord(origin_path="sources/old.md", grounding_status="grounded"),
            current_status="reviewed",
        )
    )
    store.save_claim(
        ClaimRecord(
            claim_id="claim_new",
            claim_text="The new claim.",
            source_observation_ids=["obs_new"],
            supersedes_claim_ids=["claim_old"],
            provenance=ProvenanceRecord(origin_path="sources/new.md", grounding_status="grounded"),
            current_status="reviewed",
        )
    )
    store.save_claim(
        ClaimRecord(
            claim_id="claim_challenge",
            claim_text="The challenge claim.",
            source_observation_ids=["obs_challenge"],
            contradicts_claim_ids=["claim_new"],
            provenance=ProvenanceRecord(origin_path="sources/challenge.md", grounding_status="grounded"),
            current_status="reviewed",
        )
    )

    payload = augment_store_relations_from_claims(
        store.base_dir,
        strategy="claim-links",
        apply=True,
    )

    relations = sorted(store.list_relations(), key=lambda item: item.relation_type)
    assert payload["candidate_relation_count"] == 2
    assert payload["relation_type_counts"] == {
        "claim_contradicts_claim": 1,
        "claim_supersedes_claim": 1,
    }
    assert [(relation.source_id, relation.target_id, relation.relation_type) for relation in relations] == [
        ("claim_challenge", "claim_new", "claim_contradicts_claim"),
        ("claim_new", "claim_old", "claim_supersedes_claim"),
    ]
    assert all(relation.current_status == "triaged" for relation in relations)
    assert {candidate.finding_codes[-1] for candidate in store.list_review_candidates()} == {"claim_links"}


def test_augment_store_relations_from_claim_links_reports_directed_duplicates(tmp_path: Path) -> None:
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
    augment_store_relations_from_claims(store.base_dir, strategy="claim-links", apply=True)

    second = augment_store_relations_from_claims(store.base_dir, strategy="claim-links", apply=False)

    assert second["candidate_relation_count"] == 0
    assert second["filter_summary"]["skipped_duplicate_relation_count"] == 1
    assert second["filter_summary"]["skipped_duplicate_relation_type_counts"] == {"claim_contradicts_claim": 1}


def test_augment_store_relations_from_claim_contradiction_cues(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    store.save_concept(ConceptRecord(concept_id="concept::selection", title="Selection", current_status="promoted"))
    store.save_claim(
        ClaimRecord(
            claim_id="claim_affirm",
            claim_text="Selection increases adaptation in populations.",
            concept_ids=["concept::selection"],
            source_observation_ids=["obs_affirm"],
            provenance=ProvenanceRecord(origin_path="sources/affirm.md", grounding_status="grounded"),
            current_status="reviewed",
        )
    )
    store.save_claim(
        ClaimRecord(
            claim_id="claim_negate",
            claim_text="Selection does not increase adaptation in populations.",
            concept_ids=["concept::selection"],
            source_observation_ids=["obs_negate"],
            provenance=ProvenanceRecord(origin_path="sources/negate.md", grounding_status="grounded"),
            current_status="reviewed",
        )
    )
    store.save_claim(
        ClaimRecord(
            claim_id="claim_other",
            claim_text="Selection changes allele frequencies.",
            concept_ids=["concept::selection"],
            source_observation_ids=["obs_other"],
            current_status="reviewed",
        )
    )

    payload = augment_store_relations_from_claims(
        store.base_dir,
        strategy="claim-contradiction-cues",
        apply=True,
    )

    relations = store.list_relations()
    assert payload["candidate_relation_count"] == 1
    assert payload["relation_type_counts"] == {"claim_may_contradict_claim": 1}
    assert relations[0].source_id == "claim_affirm"
    assert relations[0].target_id == "claim_negate"
    assert relations[0].relation_type == "claim_may_contradict_claim"
    assert relations[0].evidence_ids == ["obs_affirm", "obs_negate"]
    assert store.list_review_candidates()[0].finding_codes == ["relation_inferred", "claim_contradiction_cues"]


def test_augment_store_relations_from_claim_contradiction_cues_skips_explicit_links(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    store.save_concept(ConceptRecord(concept_id="concept::selection", title="Selection", current_status="promoted"))
    store.save_claim(
        ClaimRecord(
            claim_id="claim_affirm",
            claim_text="Selection increases adaptation in populations.",
            concept_ids=["concept::selection"],
            current_status="reviewed",
        )
    )
    store.save_claim(
        ClaimRecord(
            claim_id="claim_negate",
            claim_text="Selection does not increase adaptation in populations.",
            concept_ids=["concept::selection"],
            contradicts_claim_ids=["claim_affirm"],
            current_status="reviewed",
        )
    )

    payload = augment_store_relations_from_claims(
        store.base_dir,
        strategy="claim-contradiction-cues",
        apply=False,
    )

    assert payload["candidate_relation_count"] == 0


def test_augment_store_relations_from_claim_contradiction_cues_respects_pair_budget(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    store.save_concept(ConceptRecord(concept_id="concept::selection", title="Selection", current_status="promoted"))
    for index in range(3):
        store.save_claim(
            ClaimRecord(
                claim_id=f"claim_affirm_{index}",
                claim_text="Selection changes adaptation in populations.",
                concept_ids=["concept::selection"],
                current_status="reviewed",
            )
        )
    for index in range(3):
        store.save_claim(
            ClaimRecord(
                claim_id=f"claim_negate_{index}",
                claim_text="Selection does not change adaptation in populations.",
                concept_ids=["concept::selection"],
                current_status="reviewed",
            )
        )

    payload = augment_store_relations_from_claims(
        store.base_dir,
        strategy="claim-contradiction-cues",
        max_pair_checks=3,
        apply=False,
    )

    assert payload["filter_summary"]["pair_check_count"] == 3
    assert payload["filter_summary"]["pair_check_limit_reached"] is True


def test_augment_store_relations_from_claim_contradiction_cues_buckets_pairs(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    store.save_concept(ConceptRecord(concept_id="concept::selection", title="Selection", current_status="promoted"))
    for index in range(20):
        store.save_claim(
            ClaimRecord(
                claim_id=f"claim_unrelated_{index}",
                claim_text=f"Selection changes marker {index} in unrelated notes.",
                concept_ids=["concept::selection"],
                current_status="reviewed",
            )
        )

    payload = augment_store_relations_from_claims(
        store.base_dir,
        strategy="claim-contradiction-cues",
        max_pair_checks=5,
        apply=False,
    )

    assert payload["filter_summary"]["pair_bucket_count"] == 0
    assert payload["filter_summary"]["pair_check_count"] == 0
    assert payload["filter_summary"]["pair_check_limit_reached"] is False


def test_augment_store_relations_from_claim_support_anchors(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    store.save_observation(
        ObservationRecord(
            observation_id="obs_support",
            artifact_id="art_support",
            role="evidence",
            text="Observed support.",
            provenance=ProvenanceRecord(origin_path="sources/support.md", grounding_status="grounded"),
            current_status="reviewed",
        )
    )
    store.save_claim(
        ClaimRecord(
            claim_id="claim_supported",
            claim_text="A supported claim.",
            source_observation_ids=["obs_support", "obs_missing"],
            provenance=ProvenanceRecord(origin_path="sources/claim.md", grounding_status="grounded"),
            current_status="reviewed",
        )
    )

    payload = augment_store_relations_from_claims(
        store.base_dir,
        strategy="claim-support-anchors",
        apply=True,
    )

    relations = store.list_relations()
    assert payload["candidate_relation_count"] == 1
    assert payload["relation_type_counts"] == {"observation_supports_claim": 1}
    assert relations[0].source_id == "obs_support"
    assert relations[0].target_id == "claim_supported"
    assert relations[0].relation_type == "observation_supports_claim"
    assert relations[0].evidence_ids == ["obs_support"]
    assert relations[0].provenance.origin_path == "sources/support.md"
    assert store.list_review_candidates()[0].finding_codes == ["relation_inferred", "claim_support_anchors"]


def test_augment_store_relations_from_claim_support_anchors_reports_duplicates(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    store.save_observation(
        ObservationRecord(
            observation_id="obs_support",
            artifact_id="art_support",
            role="evidence",
            text="Observed support.",
            current_status="reviewed",
        )
    )
    store.save_claim(
        ClaimRecord(
            claim_id="claim_supported",
            claim_text="A supported claim.",
            source_observation_ids=["obs_support"],
            current_status="reviewed",
        )
    )
    augment_store_relations_from_claims(store.base_dir, strategy="claim-support-anchors", apply=True)

    second = augment_store_relations_from_claims(store.base_dir, strategy="claim-support-anchors", apply=False)

    assert second["candidate_relation_count"] == 0
    assert second["filter_summary"]["skipped_duplicate_relation_count"] == 1
    assert second["filter_summary"]["skipped_duplicate_relation_type_counts"] == {"observation_supports_claim": 1}


def test_augment_store_relations_from_observation_artifact_anchors(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    store.save_artifact(
        ArtifactRecord(
            artifact_id="art_source",
            artifact_kind="source_note",
            title="Source Note",
            path="sources/source.md",
            current_status="reviewed",
        )
    )
    store.save_observation(
        ObservationRecord(
            observation_id="obs_source",
            artifact_id="art_source",
            role="evidence",
            text="Observed support.",
            provenance=ProvenanceRecord(origin_path="sources/source.md", grounding_status="grounded"),
            current_status="reviewed",
        )
    )
    store.save_observation(
        ObservationRecord(
            observation_id="obs_missing_artifact",
            artifact_id="art_missing",
            role="evidence",
            text="Missing artifact.",
            current_status="reviewed",
        )
    )

    payload = augment_store_relations_from_claims(
        store.base_dir,
        strategy="observation-artifact-anchors",
        apply=True,
    )

    relations = store.list_relations()
    assert payload["candidate_relation_count"] == 1
    assert payload["relation_type_counts"] == {"artifact_contains_observation": 1}
    assert relations[0].source_id == "art_source"
    assert relations[0].target_id == "obs_source"
    assert relations[0].relation_type == "artifact_contains_observation"
    assert relations[0].evidence_ids == ["obs_source"]
    assert relations[0].provenance.origin_path == "sources/source.md"
    assert store.list_review_candidates()[0].finding_codes == ["relation_inferred", "observation_artifact_anchors"]


def test_augment_store_relations_from_observation_artifact_anchors_reports_duplicates(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "store")
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
    augment_store_relations_from_claims(store.base_dir, strategy="observation-artifact-anchors", apply=True)

    second = augment_store_relations_from_claims(store.base_dir, strategy="observation-artifact-anchors", apply=False)

    assert second["candidate_relation_count"] == 0
    assert second["filter_summary"]["skipped_duplicate_relation_count"] == 1
    assert second["filter_summary"]["skipped_duplicate_relation_type_counts"] == {"artifact_contains_observation": 1}


def test_augment_store_relations_from_observation_artifact_anchors_skips_private_records(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    store.save_artifact(
        ArtifactRecord(
            artifact_id="art_private",
            artifact_kind="source_note",
            metadata={"visibility": "private"},
            current_status="reviewed",
        )
    )
    store.save_observation(
        ObservationRecord(
            observation_id="obs_private_artifact",
            artifact_id="art_private",
            role="evidence",
            text="Private artifact support.",
            current_status="reviewed",
        )
    )
    store.save_artifact(
        ArtifactRecord(
            artifact_id="art_public",
            artifact_kind="source_note",
            current_status="reviewed",
        )
    )
    store.save_observation(
        ObservationRecord(
            observation_id="obs_private",
            artifact_id="art_public",
            role="evidence",
            text="Private observation support.",
            metadata={"classification": "confidential"},
            current_status="reviewed",
        )
    )

    payload = augment_store_relations_from_claims(store.base_dir, strategy="observation-artifact-anchors", apply=True)

    assert payload["candidate_relation_count"] == 0
    assert store.list_relations() == []


def test_augment_store_relations_from_source_anchors(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    store.save_source(
        SourceRecord(
            source_id="src_evo",
            title="Evolution Source",
            path="sources/evo.md",
            current_status="reviewed",
        )
    )
    store.save_fragment(
        FragmentRecord(
            fragment_id="frag_evo_selection",
            source_id="src_evo",
            text="Selection changes populations.",
            current_status="reviewed",
        )
    )
    store.save_claim(
        ClaimRecord(
            claim_id="claim_selection",
            claim_text="Selection changes populations.",
            supporting_fragment_ids=["frag_evo_selection", "frag_missing"],
            provenance=ProvenanceRecord(origin_path="sources/claim.md", grounding_status="grounded"),
            current_status="reviewed",
        )
    )

    payload = augment_store_relations_from_claims(
        store.base_dir,
        strategy="source-anchors",
        apply=True,
    )

    relations = sorted(store.list_relations(), key=lambda item: item.relation_type)
    assert payload["candidate_relation_count"] == 2
    assert payload["relation_type_counts"] == {
        "fragment_supports_claim": 1,
        "source_contains_fragment": 1,
    }
    assert [(relation.source_id, relation.target_id, relation.relation_type) for relation in relations] == [
        ("frag_evo_selection", "claim_selection", "fragment_supports_claim"),
        ("src_evo", "frag_evo_selection", "source_contains_fragment"),
    ]
    assert relations[0].evidence_ids == ["frag_evo_selection"]
    assert relations[0].provenance.origin_path == "sources/claim.md"
    assert {candidate.finding_codes[-1] for candidate in store.list_review_candidates()} == {"source_anchors"}


def test_augment_store_relations_from_source_anchors_skips_rejected_records(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    store.save_source(SourceRecord(source_id="src_rejected", title="Rejected", current_status="rejected"))
    store.save_fragment(
        FragmentRecord(
            fragment_id="frag_rejected_source",
            source_id="src_rejected",
            text="Should not anchor.",
            current_status="reviewed",
        )
    )
    store.save_source(SourceRecord(source_id="src_ok", title="OK", current_status="reviewed"))
    store.save_fragment(
        FragmentRecord(
            fragment_id="frag_rejected",
            source_id="src_ok",
            text="Should not anchor.",
            current_status="rejected",
        )
    )
    store.save_claim(
        ClaimRecord(
            claim_id="claim_rejected",
            claim_text="Rejected claim.",
            supporting_fragment_ids=["frag_rejected_source", "frag_rejected"],
            current_status="rejected",
        )
    )

    payload = augment_store_relations_from_claims(
        store.base_dir,
        strategy="source-anchors",
        apply=True,
    )

    assert payload["candidate_relation_count"] == 0
    assert store.list_relations() == []


def test_augment_store_relations_from_source_anchors_reports_duplicates(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    store.save_source(SourceRecord(source_id="src_evo", title="Evolution Source", current_status="reviewed"))
    store.save_fragment(
        FragmentRecord(
            fragment_id="frag_evo_selection",
            source_id="src_evo",
            text="Selection changes populations.",
            current_status="reviewed",
        )
    )
    store.save_claim(
        ClaimRecord(
            claim_id="claim_selection",
            claim_text="Selection changes populations.",
            supporting_fragment_ids=["frag_evo_selection"],
            current_status="reviewed",
        )
    )
    augment_store_relations_from_claims(store.base_dir, strategy="source-anchors", apply=True)

    second = augment_store_relations_from_claims(store.base_dir, strategy="source-anchors", apply=False)

    assert second["candidate_relation_count"] == 0
    assert second["filter_summary"]["skipped_duplicate_relation_count"] == 2
    assert second["filter_summary"]["skipped_duplicate_relation_type_counts"] == {
        "fragment_supports_claim": 1,
        "source_contains_fragment": 1,
    }


def test_augment_store_relations_from_source_anchors_skips_private_records(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    store.save_source(
        SourceRecord(
            source_id="src_private",
            title="Private Source",
            metadata={"release_level": "private"},
            current_status="reviewed",
        )
    )
    store.save_fragment(
        FragmentRecord(
            fragment_id="frag_private_source",
            source_id="src_private",
            text="Private source fragment.",
            current_status="reviewed",
        )
    )
    store.save_source(SourceRecord(source_id="src_public", title="Public Source", current_status="reviewed"))
    store.save_fragment(
        FragmentRecord(
            fragment_id="frag_private",
            source_id="src_public",
            text="Private fragment.",
            metadata={"export_policy": "do_not_export"},
            current_status="reviewed",
        )
    )
    store.save_claim(
        ClaimRecord(
            claim_id="claim_private_fragment",
            claim_text="Claim backed only by private fragments.",
            supporting_fragment_ids=["frag_private_source", "frag_private"],
            current_status="reviewed",
        )
    )

    payload = augment_store_relations_from_claims(store.base_dir, strategy="source-anchors", apply=True)

    assert payload["candidate_relation_count"] == 0
    assert store.list_relations() == []


def test_augment_store_relations_from_claim_semantic_cues(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    store.save_concept(ConceptRecord(concept_id="concept::selection", title="Selection", current_status="promoted"))
    store.save_concept(ConceptRecord(concept_id="concept::adaptation", title="Adaptation", current_status="promoted"))
    store.save_claim(
        ClaimRecord(
            claim_id="claim_definition",
            claim_text="Selection is differential survival and reproduction.",
            claim_kind="definition",
            concept_ids=["concept::selection"],
            source_observation_ids=["obs_definition"],
            provenance=ProvenanceRecord(origin_path="sources/definition.md", grounding_status="grounded"),
            current_status="reviewed",
        )
    )
    store.save_claim(
        ClaimRecord(
            claim_id="claim_qualification",
            claim_text="Selection generally shapes adaptation, although drift may dominate in some cases.",
            claim_kind="qualification",
            concept_ids=["concept::selection", "concept::adaptation"],
            source_observation_ids=["obs_qualification"],
            provenance=ProvenanceRecord(origin_path="sources/qualification.md", grounding_status="grounded"),
            current_status="reviewed",
        )
    )
    store.save_claim(
        ClaimRecord(
            claim_id="claim_distinction",
            claim_text="Selection differs from adaptation in role and explanatory scope.",
            claim_kind="distinction",
            concept_ids=["concept::selection", "concept::adaptation"],
            source_observation_ids=["obs_distinction"],
            provenance=ProvenanceRecord(origin_path="sources/distinction.md", grounding_status="grounded"),
            current_status="reviewed",
        )
    )

    payload = augment_store_relations_from_claims(
        store.base_dir,
        strategy="claim-semantic-cues",
        apply=True,
    )

    relations = sorted(store.list_relations(), key=lambda item: (item.relation_type, item.source_id, item.target_id))
    assert payload["candidate_relation_count"] == 4
    assert payload["relation_type_counts"] == {
        "claim_defines_concept": 1,
        "claim_qualifies_concept": 2,
        "distinguishes": 1,
    }
    assert ("claim_definition", "concept::selection", "claim_defines_concept") in [
        (relation.source_id, relation.target_id, relation.relation_type) for relation in relations
    ]
    assert ("claim_qualification", "concept::adaptation", "claim_qualifies_concept") in [
        (relation.source_id, relation.target_id, relation.relation_type) for relation in relations
    ]
    assert ("concept::adaptation", "concept::selection", "distinguishes") in [
        (relation.source_id, relation.target_id, relation.relation_type) for relation in relations
    ]
    assert all(relation.current_status == "triaged" for relation in relations)
    assert {candidate.finding_codes[-1] for candidate in store.list_review_candidates()} == {"claim_semantic_cues"}


def test_augment_store_relations_from_claim_semantic_cues_handles_constraints_and_duplicates(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    store.save_concept(ConceptRecord(concept_id="concept::selection", title="Selection", current_status="promoted"))
    store.save_claim(
        ClaimRecord(
            claim_id="claim_constraint",
            claim_text="Selection requires heritable variation.",
            claim_kind="constraint",
            concept_ids=["concept::selection"],
            current_status="reviewed",
        )
    )
    first = augment_store_relations_from_claims(store.base_dir, strategy="claim-semantic-cues", apply=True)
    second = augment_store_relations_from_claims(store.base_dir, strategy="claim-semantic-cues", apply=False)

    assert first["relation_type_counts"] == {"claim_constrains_concept": 1}
    assert second["candidate_relation_count"] == 0
    assert second["filter_summary"]["skipped_duplicate_relation_type_counts"] == {"claim_constrains_concept": 1}


def test_augment_store_relations_from_claim_semantic_cues_handles_dependency_and_temporal_scope(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    store.save_concept(ConceptRecord(concept_id="concept::selection", title="Selection", current_status="promoted"))
    store.save_concept(ConceptRecord(concept_id="concept::variation", title="Variation", current_status="promoted"))
    store.save_claim(
        ClaimRecord(
            claim_id="claim_dependency",
            claim_text="Selection depends on heritable variation under these conditions.",
            concept_ids=["concept::selection", "concept::variation"],
            metadata={"valid_at": "2026-01-01T00:00:00Z", "valid_until": "2026-12-31T00:00:00Z"},
            last_confirmed_at="2026-02-01T00:00:00Z",
            source_observation_ids=["obs_dependency"],
            current_status="reviewed",
        )
    )

    payload = augment_store_relations_from_claims(store.base_dir, strategy="claim-semantic-cues", apply=True)

    relations = sorted(store.list_relations(), key=lambda item: (item.relation_type, item.target_id))
    assert payload["relation_type_counts"] == {
        "claim_depends_on_concept": 2,
        "claim_has_temporal_scope": 2,
        "claim_qualifies_concept": 2,
    }
    temporal = [relation for relation in relations if relation.relation_type == "claim_has_temporal_scope"]
    assert len(temporal) == 2
    assert temporal[0].source_id == "claim_dependency"
    assert temporal[0].evidence_ids == ["obs_dependency"]
    assert store.list_review_candidates()[0].finding_codes == ["relation_inferred", "claim_semantic_cues"]


def test_augment_store_relations_from_claim_semantic_cues_temporal_scope_reports_duplicates(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    store.save_concept(ConceptRecord(concept_id="concept::selection", title="Selection", current_status="promoted"))
    store.save_claim(
        ClaimRecord(
            claim_id="claim_temporal",
            claim_text="Selection was validated for this source.",
            concept_ids=["concept::selection"],
            metadata={"expires_at": "2026-12-31T00:00:00Z"},
            current_status="reviewed",
        )
    )

    first = augment_store_relations_from_claims(store.base_dir, strategy="claim-semantic-cues", apply=True)
    second = augment_store_relations_from_claims(store.base_dir, strategy="claim-semantic-cues", apply=False)

    assert first["relation_type_counts"] == {"claim_has_temporal_scope": 1}
    assert second["candidate_relation_count"] == 0
    assert second["filter_summary"]["skipped_duplicate_relation_type_counts"] == {"claim_has_temporal_scope": 1}


def test_augment_store_relations_from_claim_semantic_cues_skips_rejected_claims_and_concepts(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    store.save_concept(ConceptRecord(concept_id="concept::rejected", title="Rejected", current_status="rejected"))
    store.save_concept(ConceptRecord(concept_id="concept::accepted", title="Accepted", current_status="reviewed"))
    store.save_claim(
        ClaimRecord(
            claim_id="claim_rejected",
            claim_text="Accepted is a rejected claim.",
            claim_kind="definition",
            concept_ids=["concept::accepted"],
            current_status="rejected",
        )
    )
    store.save_claim(
        ClaimRecord(
            claim_id="claim_rejected_concept",
            claim_text="Rejected is a rejected concept.",
            claim_kind="definition",
            concept_ids=["concept::rejected"],
            current_status="reviewed",
        )
    )

    payload = augment_store_relations_from_claims(store.base_dir, strategy="claim-semantic-cues", apply=True)

    assert payload["candidate_relation_count"] == 0
    assert store.list_relations() == []


def test_augment_store_relations_from_observation_cooccurrence_without_reingest(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    store.save_concept(ConceptRecord(concept_id="concept::selection", title="Selection", current_status="promoted"))
    store.save_concept(ConceptRecord(concept_id="concept::adaptation", title="Adaptation", current_status="promoted"))
    store.save_concept(ConceptRecord(concept_id="concept::source", title="Source", current_status="promoted"))
    store.save_observation(
        ObservationRecord(
            observation_id="obs_existing_1",
            artifact_id="art_existing",
            role="evidence",
            text="Selection can shape adaptation in a population according to this source.",
            provenance=ProvenanceRecord(origin_path="sources/existing.md", grounding_status="grounded"),
            current_status="reviewed",
        )
    )
    store.save_observation(
        ObservationRecord(
            observation_id="obs_existing_2",
            artifact_id="art_existing",
            role="evidence",
            text="Adaptation may reflect selection under local environmental conditions in the source.",
            provenance=ProvenanceRecord(origin_path="sources/existing.md", grounding_status="grounded"),
            current_status="reviewed",
        )
    )

    payload = augment_store_relations_from_claims(
        store.base_dir,
        strategy="observation-cooccurrence",
        min_evidence=2,
        apply=True,
    )

    relations = store.list_relations()
    assert payload["candidate_relation_count"] == 1
    assert payload["relation_type_counts"] == {"co_occurs_with": 1}
    assert relations[0].source_id == "concept::adaptation"
    assert relations[0].target_id == "concept::selection"
    assert relations[0].evidence_ids == ["obs_existing_1", "obs_existing_2"]
    assert relations[0].current_status == "triaged"
    assert store.list_review_candidates()[0].finding_codes == ["relation_inferred", "observation_cooccurrence"]


def test_groundrecall_cli_graph_backfill_alias_dispatches(tmp_path: Path, capsys) -> None:
    store = _seed_store(tmp_path / "store")
    from groundrecall import cli

    original = sys.argv
    try:
        sys.argv = [
            "groundrecall.cli",
            "graph-backfill",
            str(store.base_dir),
            "--concept-prefix",
            "concept::evo-edu",
            "--min-evidence",
            "2",
        ]
        cli.main()
    finally:
        sys.argv = original

    output = capsys.readouterr().out
    assert '"operation": "augment_store_relations_from_claims"' in output
    assert '"candidate_relation_count": 1' in output
