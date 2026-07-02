from __future__ import annotations

from pathlib import Path

from groundrecall.graph_augment import augment_store_relations_from_claims
from groundrecall.models import ClaimRecord, ConceptRecord, ProvenanceRecord
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


def test_augment_store_relations_from_claims_min_evidence_filters_weak_pairs(tmp_path: Path) -> None:
    store = _seed_store(tmp_path / "store")

    payload = augment_store_relations_from_claims(
        store.base_dir,
        concept_prefixes=["concept::evo-edu"],
        min_evidence=4,
        apply=True,
    )

    assert payload["candidate_relation_count"] == 0
    assert store.list_relations() == []


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
