from __future__ import annotations

import json
from pathlib import Path

from groundrecall.export import (
    export_canonical_bundle,
    export_graph_bundle,
    export_groundrecall_graph_bundle,
    export_groundrecall_query_bundle,
    export_query_bundle,
)
from groundrecall.models import (
    ArtifactRecord,
    ClaimRecord,
    ConceptRecord,
    ObservationRecord,
    ProvenanceRecord,
    RelationRecord,
    SourceRecord,
)
from groundrecall.store import GroundRecallStore


def _read_jsonl(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    return [json.loads(line) for line in text.splitlines()]


def _seed_store(store: GroundRecallStore) -> None:
    store.save_source(SourceRecord(source_id="src_001", title="Source", current_status="promoted"))
    store.save_artifact(
        ArtifactRecord(
            artifact_id="ia_001",
            artifact_kind="compiled_page",
            title="Channel Capacity",
            path="wiki/channel-capacity.md",
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
    store.save_relation(
        RelationRecord(
            relation_id="rel_001",
            source_id="concept::channel-capacity",
            target_id="concept::shannon-entropy",
            relation_type="references",
            current_status="promoted",
        )
    )


def test_export_canonical_bundle_writes_expected_files(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "groundrecall")
    _seed_store(store)

    out_dir = tmp_path / "exports"
    payload = export_canonical_bundle(
        store_dir=store.base_dir,
        out_dir=out_dir,
        concept_refs=["channel-capacity"],
        graph_concept_refs=["channel-capacity"],
        snapshot_id="snap_export_001",
        pack_ready_concept="channel-capacity",
    )

    assert (out_dir / "groundrecall_snapshot.json").exists()
    assert (out_dir / "claims.jsonl").exists()
    assert (out_dir / "concepts.jsonl").exists()
    assert (out_dir / "relations.jsonl").exists()
    assert (out_dir / "provenance_manifest.json").exists()
    assert (out_dir / "export_manifest.json").exists()
    assert (out_dir / "query_bundle__channel-capacity.json").exists()
    assert (out_dir / "graph_bundle__channel-capacity.json").exists()
    assert (out_dir / "groundrecall_query_bundle.json").exists()
    assert (out_dir / "epistemap_graph.json").exists()
    assert (out_dir / "bayesian_reliability.md").exists()

    snapshot = json.loads((out_dir / "groundrecall_snapshot.json").read_text(encoding="utf-8"))
    manifest = json.loads((out_dir / "export_manifest.json").read_text(encoding="utf-8"))
    claims = _read_jsonl(out_dir / "claims.jsonl")
    assert snapshot["snapshot_id"] == "snap_export_001"
    assert manifest["export_kind"] == "canonical"
    assert len(manifest["query_bundles"]) == 1
    assert len(manifest["graph_bundles"]) == 1
    assert manifest["groundrecall_query_bundle"].endswith("groundrecall_query_bundle.json")
    assert manifest["epistemap_graph"].endswith("epistemap_graph.json")
    assert manifest["bayesian_reliability_markdown"].endswith("bayesian_reliability.md")
    assert claims[0]["claim_id"] == "clm_001"
    assert payload["query_bundles"]
    assert payload["graph_bundles"]
    assert payload["groundrecall_query_bundle"] is not None


def test_export_query_bundle_is_assistant_neutral(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "groundrecall")
    _seed_store(store)

    out_path = tmp_path / "bundle.json"
    payload = export_query_bundle(store.base_dir, "channel capacity", out_path)
    assert out_path.exists()
    assert payload["bundle_kind"] == "groundrecall_query_bundle"
    forbidden = {"assistant", "codex", "claude", "prompt_text"}
    assert set(payload).isdisjoint(forbidden)


def test_export_groundrecall_query_bundle_uses_pack_ready_filename(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "groundrecall")
    _seed_store(store)

    out_dir = tmp_path / "pack-ready"
    payload = export_groundrecall_query_bundle(store.base_dir, "channel-capacity", out_dir)

    assert (out_dir / "groundrecall_query_bundle.json").exists()
    assert (out_dir / "epistemap_graph.json").exists()
    assert (out_dir / "bayesian_assessment.json").exists()
    assert (out_dir / "bayesian_assessment.md").exists()
    assert (out_dir / "bayesian_reliability.md").exists()
    assert payload["bundle_path"].endswith("groundrecall_query_bundle.json")
    assert payload["epistemap_graph_path"].endswith("epistemap_graph.json")
    assert payload["bayesian_assessment_json_path"].endswith("bayesian_assessment.json")
    assert payload["bayesian_assessment_markdown_path"].endswith("bayesian_assessment.md")
    assert payload["bayesian_reliability_markdown_path"].endswith("bayesian_reliability.md")
    assert payload["bayesian_reliability_label"]
    assert payload["bundle"]["assessment_summary"]["bayesian_label"] == payload["bayesian_reliability_label"]
    assert payload["bundle"]["bundle_kind"] == "groundrecall_query_bundle"
    assert "# Epistemap Bayesian Assessment" in (out_dir / "bayesian_assessment.md").read_text(encoding="utf-8")
    assert "# Epistemap Bayesian Reliability" in (out_dir / "bayesian_reliability.md").read_text(encoding="utf-8")


def test_export_graph_bundle_is_assistant_neutral(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "groundrecall")
    _seed_store(store)

    out_path = tmp_path / "graph-bundle.json"
    payload = export_graph_bundle(store.base_dir, "channel capacity", out_path, depth=1)

    assert out_path.exists()
    assert payload["bundle_kind"] == "groundrecall_graph_bundle"
    assert payload["nodes"]
    assert payload["edges"]
    assert payload["source_artifacts"]
    assert payload["graph_diagnostics"]["summary"]["concept_count"] == len(payload["nodes"])
    forbidden = {"assistant", "codex", "claude", "prompt_text"}
    assert set(payload).isdisjoint(forbidden)


def test_export_groundrecall_graph_bundle_uses_pack_ready_filename(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "groundrecall")
    _seed_store(store)

    out_dir = tmp_path / "pack-ready-graph"
    payload = export_groundrecall_graph_bundle(store.base_dir, "channel-capacity", out_dir, depth=1)

    assert (out_dir / "groundrecall_graph_bundle.json").exists()
    assert payload["bundle_path"].endswith("groundrecall_graph_bundle.json")
    assert payload["bundle"]["bundle_kind"] == "groundrecall_graph_bundle"


def test_export_canonical_bundle_can_include_graph_diagnostics(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "groundrecall")
    _seed_store(store)

    out_dir = tmp_path / "exports-with-graph"
    payload = export_canonical_bundle(
        store_dir=store.base_dir,
        out_dir=out_dir,
        snapshot_id="snap_export_graph",
        include_graph_diagnostics=True,
    )

    assert (out_dir / "graph_diagnostics.json").exists()
    manifest = json.loads((out_dir / "export_manifest.json").read_text(encoding="utf-8"))
    diagnostics = json.loads((out_dir / "graph_diagnostics.json").read_text(encoding="utf-8"))
    provenance_manifest = json.loads((out_dir / "provenance_manifest.json").read_text(encoding="utf-8"))

    assert "graph_diagnostics.json" in manifest["files"]
    assert payload["canonical_outputs"]["graph_diagnostics_json"].endswith("graph_diagnostics.json")
    assert provenance_manifest["graph_diagnostics"].endswith("graph_diagnostics.json")
    assert diagnostics["summary"]["concept_count"] == 2
    assert "quality_summary" in diagnostics


def test_export_canonical_bundle_can_include_graph_interchange(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "groundrecall")
    _seed_store(store)

    out_dir = tmp_path / "exports-with-interchange"
    payload = export_canonical_bundle(
        store_dir=store.base_dir,
        out_dir=out_dir,
        snapshot_id="snap_export_interchange",
        include_graph_interchange=True,
    )

    assert (out_dir / "graph_interchange.json").exists()
    manifest = json.loads((out_dir / "export_manifest.json").read_text(encoding="utf-8"))
    bundle = json.loads((out_dir / "graph_interchange.json").read_text(encoding="utf-8"))
    provenance_manifest = json.loads((out_dir / "provenance_manifest.json").read_text(encoding="utf-8"))

    assert "graph_interchange.json" in manifest["files"]
    assert payload["canonical_outputs"]["graph_interchange_json"].endswith("graph_interchange.json")
    assert provenance_manifest["graph_interchange"].endswith("graph_interchange.json")
    assert bundle["bundle_kind"] == "groundrecall_graph_interchange"
    assert bundle["schema_version"] == "groundrecall.graph_interchange.v1"
    assert {node["node_id"] for node in bundle["nodes"]} == {"concept::channel-capacity", "concept::shannon-entropy"}
    assert bundle["edges"][0]["edge_id"] == "rel_001"
    assert "quality_summary" in bundle["diagnostics"]
