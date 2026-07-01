from __future__ import annotations

import json
from pathlib import Path

from groundrecall.assistant_export import export_assistant_bundle
from groundrecall.export import export_canonical_bundle, export_query_bundle
from groundrecall.models import ArtifactRecord, ClaimRecord, ConceptRecord, ObservationRecord, ProvenanceRecord, SourceRecord
from groundrecall.store import GroundRecallStore


PRIVATE_CANARY = "TOP_SECRET_RELEASE_CANARY"
SECRET_VALUE = "password=superSecret123"
DRAFT_CANARY = "DRAFT_RELEASE_CANARY"


def _all_export_text(out_dir: Path) -> str:
    chunks = []
    for path in sorted(item for item in out_dir.rglob("*") if item.is_file()):
        chunks.append(path.read_text(encoding="utf-8"))
    return "\n".join(chunks)


def _seed_public_base(store: GroundRecallStore) -> None:
    store.save_source(SourceRecord(source_id="src_public", title="Public source", current_status="promoted"))
    store.save_artifact(
        ArtifactRecord(
            artifact_id="art_public",
            artifact_kind="compiled_page",
            title="Public artifact",
            path="public/page.md",
            current_status="reviewed",
        )
    )
    store.save_observation(
        ObservationRecord(
            observation_id="obs_public",
            artifact_id="art_public",
            role="claim",
            text="Public support for channel capacity.",
            provenance=ProvenanceRecord(
                origin_artifact_id="art_public",
                origin_path="public/page.md",
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
            description="Public concept.",
            source_artifact_ids=["art_public"],
            current_status="promoted",
        )
    )
    store.save_claim(
        ClaimRecord(
            claim_id="clm_public",
            claim_text="Public claim that may mention password manager locations but no secret values.",
            concept_ids=["concept::channel-capacity"],
            source_observation_ids=["obs_public"],
            current_status="promoted",
            provenance=ProvenanceRecord(
                origin_artifact_id="art_public",
                origin_path="public/page.md",
                support_kind="derived_from_page",
                grounding_status="grounded",
            ),
        )
    )


def _seed_sensitive_records(store: GroundRecallStore) -> None:
    store.save_source(
        SourceRecord(
            source_id="src_private",
            title=f"Private source {PRIVATE_CANARY}",
            metadata={"visibility": "private"},
            current_status="promoted",
        )
    )
    store.save_artifact(
        ArtifactRecord(
            artifact_id="art_private",
            artifact_kind="operator_note",
            title=f"Private artifact {PRIVATE_CANARY}",
            path="private/operator-note.md",
            metadata={"classification": "privileged"},
            current_status="reviewed",
        )
    )
    store.save_observation(
        ObservationRecord(
            observation_id="obs_private",
            artifact_id="art_private",
            role="claim",
            text=f"Private support text {PRIVATE_CANARY}",
            provenance=ProvenanceRecord(
                origin_artifact_id="art_private",
                origin_path="private/operator-note.md",
                support_kind="derived_from_session",
                grounding_status="grounded",
            ),
            current_status="reviewed",
        )
    )
    store.save_concept(
        ConceptRecord(
            concept_id="concept::private-ops",
            title=f"Private operations {PRIVATE_CANARY}",
            description="Must not leave the private store.",
            source_artifact_ids=["art_private"],
            current_status="promoted",
        )
    )
    store.save_claim(
        ClaimRecord(
            claim_id="clm_private",
            claim_text=f"Private claim {PRIVATE_CANARY}",
            concept_ids=["concept::private-ops"],
            source_observation_ids=["obs_private"],
            metadata={"release_status": "no_export"},
            current_status="promoted",
        )
    )
    store.save_claim(
        ClaimRecord(
            claim_id="clm_secret_value",
            claim_text=f"Inline credential test {SECRET_VALUE}",
            concept_ids=["concept::channel-capacity"],
            current_status="promoted",
        )
    )
    store.save_claim(
        ClaimRecord(
            claim_id="clm_draft",
            claim_text=f"Draft claim {DRAFT_CANARY}",
            concept_ids=["concept::channel-capacity"],
            current_status="draft",
        )
    )


def test_canonical_export_filters_private_draft_and_secret_records(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "groundrecall")
    _seed_public_base(store)
    _seed_sensitive_records(store)

    out_dir = tmp_path / "exports"
    export_canonical_bundle(store.base_dir, out_dir, concept_refs=["channel-capacity"], snapshot_id="guardrail-canonical")

    export_text = _all_export_text(out_dir)
    assert "clm_public" in export_text
    assert PRIVATE_CANARY not in export_text
    assert SECRET_VALUE not in export_text
    assert DRAFT_CANARY not in export_text
    assert "clm_private" not in export_text
    assert "clm_secret_value" not in export_text
    assert "clm_draft" not in export_text

    manifest = json.loads((out_dir / "export_manifest.json").read_text(encoding="utf-8"))
    report = manifest["export_guardrails"]
    assert report["enabled"] is True
    assert report["excluded_counts"]["claim"] >= 3
    reasons = {finding["reason"] for finding in report["findings"]}
    assert "metadata:metadata.release_status:no_export" in reasons
    assert "secret_like_content" in reasons
    assert "status:draft" in reasons


def test_query_bundle_prunes_private_support_references(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "groundrecall")
    _seed_public_base(store)
    _seed_sensitive_records(store)
    store.save_concept(
        ConceptRecord(
            concept_id="concept::channel-capacity",
            title="Channel Capacity",
            description="Public concept.",
            source_artifact_ids=["art_public", "art_private"],
            current_status="promoted",
        )
    )
    store.save_claim(
        ClaimRecord(
            claim_id="clm_mixed_support",
            claim_text="Public claim with one public support record and one private support record.",
            concept_ids=["concept::channel-capacity"],
            source_observation_ids=["obs_public", "obs_private"],
            current_status="promoted",
        )
    )

    out_path = tmp_path / "query.json"
    payload = export_query_bundle(store.base_dir, "channel-capacity", out_path)

    export_text = out_path.read_text(encoding="utf-8")
    assert "clm_mixed_support" in export_text
    assert "obs_public" in export_text
    assert "obs_private" not in export_text
    assert "art_private" not in export_text
    assert PRIVATE_CANARY not in export_text

    mixed_claim = next(item for item in payload["relevant_claims"] if item["claim_id"] == "clm_mixed_support")
    assert mixed_claim["source_observation_ids"] == ["obs_public"]
    report = payload["export_guardrails"]
    assert any(
        finding["record_kind"] == "observation" and finding["reason"] == "non_exportable_artifact"
        for finding in report["findings"]
    )


def test_assistant_export_does_not_release_privileged_store_content(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "groundrecall")
    _seed_public_base(store)
    _seed_sensitive_records(store)

    out_dir = tmp_path / "codex"
    manifest = export_assistant_bundle(store.base_dir, "codex", out_dir, concept_refs=["channel-capacity"])

    export_text = _all_export_text(out_dir)
    assert "clm_public" in export_text
    assert PRIVATE_CANARY not in export_text
    assert SECRET_VALUE not in export_text
    assert DRAFT_CANARY not in export_text
    assert manifest["export_guardrails"]["snapshot"]["excluded_total"] >= 1


def test_non_secret_location_guidance_remains_exportable(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "groundrecall")
    _seed_public_base(store)
    store.save_claim(
        ClaimRecord(
            claim_id="clm_secret_location_policy",
            claim_text="Store where secrets live, such as /run/secrets/app, but never store secret values.",
            concept_ids=["concept::channel-capacity"],
            current_status="promoted",
        )
    )

    out_dir = tmp_path / "exports"
    export_canonical_bundle(store.base_dir, out_dir, concept_refs=["channel-capacity"], snapshot_id="guardrail-policy")

    export_text = _all_export_text(out_dir)
    assert "clm_secret_location_policy" in export_text
    assert "/run/secrets/app" in export_text
    manifest = json.loads((out_dir / "export_manifest.json").read_text(encoding="utf-8"))
    assert manifest["export_guardrails"]["excluded_total"] == 0
