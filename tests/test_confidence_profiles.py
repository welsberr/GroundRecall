from __future__ import annotations

from pathlib import Path

from groundrecall.confidence import (
    append_reviewer_endorsement,
    apply_adapter_confidence_policy,
    confidence_migration_report,
    save_adjudication,
)
from groundrecall.export import export_groundrecall_query_bundle
from groundrecall.models import ArtifactRecord, ClaimRecord, ConceptRecord, ObservationRecord
from groundrecall.query import build_query_bundle_for_concept
from groundrecall.store import GroundRecallStore


def _seed_profile_store(base: Path) -> GroundRecallStore:
    store = GroundRecallStore(base)
    store.save_artifact(
        ArtifactRecord(
            artifact_id="ia_1",
            artifact_kind="compiled_page",
            title="Channel Capacity",
            path="wiki/channel-capacity.md",
            current_status="reviewed",
        )
    )
    store.save_concept(
        ConceptRecord(
            concept_id="concept::channel-capacity",
            title="Channel Capacity",
            source_artifact_ids=["ia_1"],
            current_status="promoted",
        )
    )
    observation_row = {
        "observation_id": "obs_1",
        "artifact_id": "ia_1",
        "role": "claim",
        "text": "Reliable communication rate is bounded by channel capacity.",
        "confidence_hint": 0.72,
        "metadata": {},
        "provenance": {
            "origin_artifact_id": "ia_1",
            "support_kind": "direct_source",
            "grounding_status": "grounded",
            "origin_path": "wiki/channel-capacity.md",
        },
        "current_status": "reviewed",
    }
    claim_row = {
        "claim_id": "clm_1",
        "claim_text": "Channel capacity bounds reliable communication rate.",
        "source_observation_ids": ["obs_1"],
        "supporting_fragment_ids": [],
        "concept_ids": ["concept::channel-capacity"],
        "confidence_hint": 0.84,
        "metadata": {
            "valid_at": "2026-01-01T00:00:00Z",
            "expires_at": "2026-02-01T00:00:00Z",
        },
        "provenance": {
            "support_kind": "direct_source",
            "grounding_status": "grounded",
            "origin_path": "wiki/channel-capacity.md",
        },
        "current_status": "draft",
    }
    apply_adapter_confidence_policy(
        [observation_row],
        adapter_name="test_adapter",
        row_kind="observation",
        recorded_at="2026-01-02T00:00:00Z",
    )
    apply_adapter_confidence_policy(
        [claim_row],
        adapter_name="test_adapter",
        row_kind="claim",
        recorded_at="2026-01-02T00:00:00Z",
    )
    store.save_observation(ObservationRecord.model_validate(observation_row))
    store.save_claim(ClaimRecord.model_validate(claim_row))
    confidence_migration_report(store.base_dir, apply=True, backup_dir=base.parent / "backup")
    zero = append_reviewer_endorsement(
        store.base_dir,
        "clm_1",
        reviewer_id="reviewer-a",
        value=0.0,
        scope="claim_text_and_source",
        rationale="Explicit disagreement: source was inspected but claim framing is rejected.",
        evidence_inspected=["obs_1"],
        recorded_at="2026-01-03T00:00:00Z",
    )
    high = append_reviewer_endorsement(
        store.base_dir,
        "clm_1",
        reviewer_id="reviewer-b",
        value=0.95,
        scope="claim_text_and_source",
        rationale="Reviewer accepts the source-grounded statement.",
        evidence_inspected=["obs_1"],
        recorded_at="2026-01-04T00:00:00Z",
    )
    save_adjudication(
        store.base_dir,
        adjudication_id="adj_1",
        subject_id="clm_1",
        considered_assessment_ids=[zero.assessment_id, high.assessment_id],
        selected_assessment_ids=[high.assessment_id],
        adjudicator="lead-reviewer",
        rationale="Select the endorsement that matches inspected source context; preserve the dissent.",
        decided_at="2026-01-05T00:00:00Z",
    )
    return store


def test_query_confidence_profile_preserves_disagreement_and_explicit_zero(tmp_path: Path) -> None:
    store = _seed_profile_store(tmp_path / "store")

    bundle = build_query_bundle_for_concept(store.base_dir, "channel-capacity")

    profile = bundle["confidence_profile"]
    claim_profile = profile["claims"][0]
    reviewer_values = [
        item["value"]
        for item in claim_profile["assessments"]["by_dimension"]["reviewer_endorsement"]
    ]
    assert reviewer_values == [0.0, 0.95]
    assert claim_profile["adjudication"]["selection_explanation"]["mode"] == "explicit_adjudication"
    assert claim_profile["adjudication"]["records"][0]["considered_assessment_ids"]
    assert claim_profile["promotion_authority"]["confidence_can_promote"] is False
    assert store.get_claim("clm_1").current_status == "draft"


def test_confidence_profile_exports_temporal_and_reconstructable_posterior_blocks(tmp_path: Path) -> None:
    store = _seed_profile_store(tmp_path / "store")
    claim = store.get_claim("clm_1")
    claim.current_status = "reviewed"
    store.save_claim(claim)

    output = export_groundrecall_query_bundle(store.base_dir, "channel-capacity", tmp_path / "export")

    profile_path = Path(output["confidence_profile_json_path"])
    assert profile_path.exists()
    claim_profile = output["bundle"]["confidence_profile"]["claims"][0]
    assert claim_profile["temporal_applicability"]["historical_support_preserved"] is True
    assert claim_profile["posterior_support"]["available"] is True
    assert claim_profile["posterior_support"]["reconstructable"] is True
    assert "ledger" in claim_profile["posterior_support"]


def test_expiry_changes_current_applicability_without_erasing_support(tmp_path: Path) -> None:
    store = _seed_profile_store(tmp_path / "store")
    claim = store.get_claim("clm_1")
    claim.metadata["expires_at"] = "2020-01-01T00:00:00Z"
    store.save_claim(claim)

    bundle = build_query_bundle_for_concept(store.base_dir, "channel-capacity")

    applicability = bundle["confidence_profile"]["claims"][0]["temporal_applicability"]
    assert applicability["applicability"] == "expired"
    assert applicability["historical_support_preserved"] is True
