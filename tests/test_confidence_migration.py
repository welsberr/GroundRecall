from __future__ import annotations

import json

from groundrecall.confidence import (
    apply_adapter_confidence_policy,
    confidence_migration_report,
    confidence_readiness_report,
    restore_confidence_backup,
)
from groundrecall.models import ClaimRecord, ObservationRecord
from groundrecall.store import GroundRecallStore


def test_confidence_readiness_flags_hardcoded_hint_without_method(tmp_path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    store.save_claim(
        ClaimRecord(
            claim_id="clm_legacy",
            claim_text="Legacy hint has no producer contract.",
            confidence_hint=0.8,
        )
    )

    report = confidence_readiness_report(store.base_dir)

    assert report["ready"] is False
    assert report["error_count"] == 1
    assert report["findings"][0]["code"] == "confidence_hint_missing_method"


def test_confidence_migration_dry_run_and_apply_append_assessments(tmp_path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    observation_row = {
        "observation_id": "obs_1",
        "artifact_id": "ia_1",
        "role": "claim",
        "text": "Observed claim.",
        "confidence_hint": 0.7,
        "metadata": {},
    }
    claim_row = {
        "claim_id": "clm_1",
        "claim_text": "Observed claim.",
        "source_observation_ids": ["obs_1"],
        "supporting_fragment_ids": ["frag_1"],
        "confidence_hint": 0.82,
        "metadata": {},
    }
    apply_adapter_confidence_policy([observation_row], adapter_name="test_adapter", row_kind="observation", recorded_at="2026-07-25T00:00:00Z")
    apply_adapter_confidence_policy([claim_row], adapter_name="test_adapter", row_kind="claim", recorded_at="2026-07-25T00:00:00Z")
    store.save_observation(ObservationRecord.model_validate(observation_row))
    store.save_claim(ClaimRecord.model_validate(claim_row))

    dry_run = confidence_migration_report(store.base_dir)
    assert dry_run["candidate_count"] == 2
    assert dry_run["applied_count"] == 0
    assert store.get_claim("clm_1").assessments == []

    backup_dir = tmp_path / "backup"
    applied = confidence_migration_report(store.base_dir, apply=True, backup_dir=backup_dir)
    assert applied["applied_count"] == 2
    migrated_claim = store.get_claim("clm_1")
    assert len(migrated_claim.assessments) == 1
    assessment = migrated_claim.assessments[0]
    assert assessment.dimension == "extraction_fidelity"
    assert assessment.method.policy_id == "groundrecall_adapter_confidence.test_adapter.v1"
    assert assessment.metadata["not_review_endorsement"] is True
    assert assessment.metadata["not_promotion_authority"] is True
    assert backup_dir.exists()

    restore_confidence_backup(store.base_dir, backup_dir)
    restored_claim = store.get_claim("clm_1")
    assert restored_claim.assessments == []


def test_confidence_migration_skips_ambiguous_legacy_zero(tmp_path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    row = {
        "claim_id": "clm_zero",
        "claim_text": "Zero may be missing-data sentinel in legacy stores.",
        "confidence_hint": 0.0,
        "metadata": {},
    }
    apply_adapter_confidence_policy([row], adapter_name="test_adapter", row_kind="claim", recorded_at="2026-07-25T00:00:00Z")
    row["metadata"].pop("confidence_zero_explicit", None)
    store.save_claim(ClaimRecord.model_validate(row))

    report = confidence_migration_report(store.base_dir)

    assert report["candidate_count"] == 0
    assert report["skipped"][0]["code"] == "legacy_zero_ambiguous"
    readiness = confidence_readiness_report(store.base_dir)
    assert any(finding["code"] == "legacy_zero_ambiguous" for finding in readiness["findings"])


def test_confidence_cli_reports_are_json_serializable(tmp_path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    store.save_observation(ObservationRecord(observation_id="obs_1", role="summary", text="No confidence."))

    payload = confidence_readiness_report(store.base_dir)

    assert json.loads(json.dumps(payload))["ready"] is True
