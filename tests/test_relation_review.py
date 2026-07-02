from __future__ import annotations

import json
from pathlib import Path

from groundrecall.models import ConceptRecord, ProvenanceRecord, RelationRecord, ReviewCandidateRecord
from groundrecall.relation_review import apply_relation_review_batch, list_relation_review_batch
from groundrecall.store import GroundRecallStore


def _seed_relation_store(store_dir: Path) -> GroundRecallStore:
    store = GroundRecallStore(store_dir)
    store.save_concept(
        ConceptRecord(
            concept_id="concept::evo-edu-a",
            title="Evo Edu A",
            current_status="reviewed",
        )
    )
    store.save_concept(
        ConceptRecord(
            concept_id="concept::evo-edu-b",
            title="Evo Edu B",
            current_status="reviewed",
        )
    )
    store.save_relation(
        RelationRecord(
            relation_id="rel_review_me",
            source_id="concept::evo-edu-a",
            target_id="concept::evo-edu-b",
            relation_type="mentions_topic",
            evidence_ids=["obs_1", "obs_2"],
            provenance=ProvenanceRecord(support_kind="inferred", grounding_status="partially_grounded"),
            current_status="triaged",
        )
    )
    store.save_review_candidate(
        ReviewCandidateRecord(
            review_candidate_id="rq_rel_review_me",
            candidate_type="relation",
            candidate_id="rel_review_me",
            triage_lane="relation_review",
            priority=12,
            finding_codes=["relation_inferred", "claim_mentions"],
            rationale="reviewable relation",
            current_status="triaged",
        )
    )
    return store


def test_list_relation_review_batch_filters_and_sorts(tmp_path: Path) -> None:
    _seed_relation_store(tmp_path / "store")

    payload = list_relation_review_batch(
        tmp_path / "store",
        concept_prefix="concept::evo-edu",
        support_kind="inferred",
        finding_code="claim_mentions",
    )

    assert payload["candidate_count"] == 1
    assert payload["relations"][0]["relation_id"] == "rel_review_me"
    assert payload["relations"][0]["evidence_count"] == 2
    assert payload["relations"][0]["review_priority"] == 12
    assert payload["decision_file_schema"]["decisions"][0]["status"] == "reviewed|promoted|rejected|triaged"


def test_apply_relation_review_batch_updates_relation_candidate_and_audit(tmp_path: Path) -> None:
    store = _seed_relation_store(tmp_path / "store")
    decision_path = tmp_path / "decisions.json"
    decision_path.write_text(
        json.dumps(
            {
                "reviewer": "Unit Test Reviewer",
                "decisions": [
                    {
                        "relation_id": "rel_review_me",
                        "status": "reviewed",
                        "relation_type": "supports",
                        "notes": "Evidence supports a stronger relation type.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    payload = apply_relation_review_batch(store.base_dir, decision_path)

    relation = store.get_relation("rel_review_me")
    review = store.get_review_candidate("rq_rel_review_me")
    promotions = store.list_promotions()
    assert payload["applied_count"] == 1
    assert payload["skipped_count"] == 0
    assert relation is not None
    assert relation.current_status == "reviewed"
    assert relation.relation_type == "supports"
    assert review is not None
    assert review.current_status == "reviewed"
    assert "Evidence supports" in review.rationale
    assert len(promotions) == 1
    assert promotions[0].candidate_id == "rel_review_me"
    assert promotions[0].verdict == "approved"
