from __future__ import annotations

import json
from pathlib import Path

from groundrecall.cli import main as groundrecall_cli_main
from groundrecall.erasure import ERASURE_SCHEMA_VERSION, plan_exceptional_erasure
from groundrecall.models import (
    AdjudicationRecord,
    ArtifactRecord,
    ClaimRecord,
    ConceptRecord,
    ContradictionCaseRecord,
    ObservationRecord,
    ProvenanceRecord,
    RelationRecord,
    ReviewCandidateRecord,
)
from groundrecall.search_index import build_search_index
from groundrecall.store import GroundRecallStore


SECRET_TEXT = "TOP_SECRET_ERASURE_CANARY"


def _seed_erasure_store(store: GroundRecallStore) -> None:
    store.save_artifact(
        ArtifactRecord(
            artifact_id="art_secret",
            artifact_kind="operator_note",
            title=f"Secret note {SECRET_TEXT}",
            path="private/secret-note.md",
            metadata={"classification": "privileged"},
            current_status="reviewed",
        )
    )
    store.save_observation(
        ObservationRecord(
            observation_id="obs_secret",
            artifact_id="art_secret",
            role="claim",
            text=f"Private observation {SECRET_TEXT}",
            provenance=ProvenanceRecord(
                origin_artifact_id="art_secret",
                origin_path="private/secret-note.md",
                source_url="https://private.example.test/secret",
                retrieval_date="2026-07-28",
                support_kind="derived_from_session",
                grounding_status="grounded",
            ),
            current_status="reviewed",
        )
    )
    store.save_concept(
        ConceptRecord(
            concept_id="concept::secret",
            title="Secret concept",
            source_artifact_ids=["art_secret"],
            current_status="reviewed",
        )
    )
    store.save_claim(
        ClaimRecord(
            claim_id="clm_secret",
            claim_text=f"Secret claim {SECRET_TEXT}",
            concept_ids=["concept::secret"],
            source_observation_ids=["obs_secret"],
            current_status="promoted",
        )
    )
    store.save_claim(
        ClaimRecord(
            claim_id="clm_public",
            claim_text="Public claim that contradicts the secret claim.",
            contradicts_claim_ids=["clm_secret"],
            current_status="reviewed",
        )
    )
    store.save_relation(
        RelationRecord(
            relation_id="rel_secret",
            source_id="clm_secret",
            target_id="clm_public",
            relation_type="claim_may_contradict_claim",
            evidence_ids=["obs_secret"],
            current_status="triaged",
        )
    )
    store.save_review_candidate(
        ReviewCandidateRecord(
            review_candidate_id="rq_secret",
            candidate_type="claim",
            candidate_id="clm_secret",
            current_status="triaged",
        )
    )
    store.save_contradiction_case(
        ContradictionCaseRecord(
            case_id="case_secret",
            claim_ids=["clm_secret", "clm_public"],
            adjudication_id="adj_secret",
            current_status="reviewed",
        )
    )
    store.save_adjudication(
        AdjudicationRecord(
            adjudication_id="adj_secret",
            subject_id="case_secret",
            subject_type="contradiction_case",
            rationale="Secret adjudication.",
        )
    )


def test_plan_exceptional_erasure_expands_dependencies_and_minimal_tombstone(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "groundrecall")
    _seed_erasure_store(store)
    build_search_index(store.base_dir)

    plan = plan_exceptional_erasure(
        store.base_dir,
        targets=["claim:clm_secret"],
        reason_class="secret_exposure",
        authority="security-officer",
        requested_at="2026-07-28T00:00:00Z",
        exports_dir=tmp_path / "exports",
        quarantine_dir=tmp_path / "quarantine",
    )

    affected = {(item["record_kind"], item["record_id"]) for item in plan.affected_records}
    assert plan.schema_version == ERASURE_SCHEMA_VERSION
    assert ("claim", "clm_secret") in affected
    assert ("relation", "rel_secret") in affected
    assert ("review_candidate", "rq_secret") in affected
    assert ("contradiction_case", "case_secret") in affected
    assert ("adjudication", "adj_secret") in affected
    assert plan.tombstone.reason_class == "secret_exposure"
    assert plan.tombstone.authority == "security-officer"
    assert plan.tombstone.affected_counts["claim"] >= 1
    assert plan.tombstone.content_hashes
    assert plan.tombstone.origin_hashes
    assert SECRET_TEXT not in plan.tombstone.model_dump_json()
    derived_kinds = {item["artifact_kind"] for item in plan.derived_artifacts}
    assert {"search_index", "snapshots", "exports", "federation_quarantine"} <= derived_kinds
    assert any(item["artifact_kind"] == "search_index" and item["exists"] is True for item in plan.derived_artifacts)


def test_plan_exceptional_erasure_warns_for_unresolved_targets(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "groundrecall")

    plan = plan_exceptional_erasure(
        store.base_dir,
        targets=["missing_claim"],
        reason_class="privacy_request",
        authority="privacy-officer",
        requested_at="2026-07-28T00:00:00Z",
    )

    assert plan.affected_records == []
    assert plan.tombstone.affected_counts == {}
    assert plan.warnings == ["unresolved_target:missing_claim"]


def test_plan_exceptional_erasure_accepts_bare_colon_bearing_concept_ids(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "groundrecall")
    _seed_erasure_store(store)

    plan = plan_exceptional_erasure(
        store.base_dir,
        targets=["concept::secret"],
        reason_class="privacy_request",
        authority="privacy-officer",
        requested_at="2026-07-28T00:00:00Z",
    )

    assert plan.warnings == []
    assert any(item.record_kind == "concept" and item.record_id == "concept::secret" for item in plan.target_ids)


def test_groundrecall_cli_routes_erasure_plan(tmp_path: Path, monkeypatch, capsys) -> None:
    store = GroundRecallStore(tmp_path / "groundrecall")
    _seed_erasure_store(store)
    monkeypatch.setattr(
        "sys.argv",
        [
            "groundrecall",
            "erasure",
            "plan",
            str(store.base_dir),
            "--target",
            "clm_secret",
            "--reason-class",
            "secret_exposure",
            "--authority",
            "security-officer",
            "--requested-at",
            "2026-07-28T00:00:00Z",
        ],
    )

    groundrecall_cli_main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == ERASURE_SCHEMA_VERSION
    assert payload["tombstone"]["reason_class"] == "secret_exposure"
    assert any(item["record_id"] == "clm_secret" for item in payload["affected_records"])
