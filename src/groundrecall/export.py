from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from epistemap import write_bayesian_reliability_markdown

from .export_guardrails import filter_query_payload_for_public_export, filter_snapshot_for_public_export
from .graph_diagnostics import PROVENANCE_RELATION_TYPES, build_graph_diagnostics
from .query import build_graph_bundle_for_concept, build_query_bundle_for_concept
from .store import GroundRecallStore


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    text = "\n".join(json.dumps(row, sort_keys=True) for row in rows)
    if text:
        text += "\n"
    path.write_text(text, encoding="utf-8")


def _graph_interchange_bundle(snapshot, diagnostics: dict[str, Any]) -> dict[str, Any]:
    return {
        "bundle_kind": "groundrecall_graph_interchange",
        "schema_version": "groundrecall.graph_interchange.v1",
        "snapshot_id": snapshot.snapshot_id,
        "created_at": snapshot.created_at,
        "nodes": [
            {
                "node_id": concept.concept_id,
                "node_kind": "concept",
                "title": concept.title,
                "aliases": list(concept.aliases),
                "description": concept.description,
                "source_artifact_ids": list(concept.source_artifact_ids),
                "status": concept.current_status,
            }
            for concept in snapshot.concepts
        ],
        "edges": [
            {
                "edge_id": relation.relation_id,
                "edge_kind": "relation",
                "source_id": relation.source_id,
                "target_id": relation.target_id,
                "relation_type": relation.relation_type,
                "edge_role": "provenance" if relation.relation_type in PROVENANCE_RELATION_TYPES else "semantic",
                "evidence_ids": list(relation.evidence_ids),
                "support_kind": relation.provenance.support_kind,
                "grounding_status": relation.provenance.grounding_status,
                "status": relation.current_status,
            }
            for relation in snapshot.relations
        ],
        "claims": [
            {
                "claim_id": claim.claim_id,
                "claim_text": claim.claim_text,
                "claim_kind": claim.claim_kind,
                "concept_ids": list(claim.concept_ids),
                "source_observation_ids": list(claim.source_observation_ids),
                "support_kind": claim.provenance.support_kind,
                "grounding_status": claim.provenance.grounding_status,
                "status": claim.current_status,
            }
            for claim in snapshot.claims
        ],
        "observations": [
            {
                "observation_id": observation.observation_id,
                "artifact_id": observation.artifact_id,
                "role": observation.role,
                "text": observation.text,
                "support_kind": observation.provenance.support_kind,
                "grounding_status": observation.provenance.grounding_status,
                "origin_path": observation.provenance.origin_path,
                "origin_section": observation.provenance.origin_section,
                "status": observation.current_status,
            }
            for observation in snapshot.observations
        ],
        "diagnostics": diagnostics,
        "consumer_notes": [
            "This bundle is assistant-neutral and intended for downstream graph-aware workbenches.",
            "Nodes and edges are filtered by public export guardrails before serialization.",
            "Inferred edges are candidates unless downstream review confirms them.",
        ],
    }


def export_canonical_snapshot(
    store_dir: str | Path,
    out_dir: str | Path,
    snapshot_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    include_graph_diagnostics: bool = False,
    include_graph_interchange: bool = False,
) -> dict[str, str]:
    store = GroundRecallStore(store_dir)
    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)

    actual_snapshot_id = snapshot_id or f"snapshot-export-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    snapshot = store.build_snapshot(
        snapshot_id=actual_snapshot_id,
        created_at=_now(),
        metadata={"export_kind": "canonical", **(metadata or {})},
    )
    snapshot, guardrail_report = filter_snapshot_for_public_export(snapshot)
    snapshot.metadata["export_guardrails"] = guardrail_report
    store.save_snapshot(snapshot)

    snapshot_path = target / "groundrecall_snapshot.json"
    _write_json(snapshot_path, snapshot.model_dump())
    _write_jsonl(target / "claims.jsonl", [item.model_dump() for item in snapshot.claims])
    _write_jsonl(target / "concepts.jsonl", [item.model_dump() for item in snapshot.concepts])
    _write_jsonl(target / "relations.jsonl", [item.model_dump() for item in snapshot.relations])
    graph_diagnostics_path = target / "graph_diagnostics.json"
    graph_interchange_path = target / "graph_interchange.json"
    graph_diagnostics = build_graph_diagnostics(
        [item.model_dump() for item in snapshot.concepts],
        [item.model_dump() for item in snapshot.relations],
        claims=[item.model_dump() for item in snapshot.claims],
        observations=[item.model_dump() for item in snapshot.observations],
    )
    if include_graph_diagnostics:
        _write_json(graph_diagnostics_path, graph_diagnostics)
    if include_graph_interchange:
        _write_json(
            graph_interchange_path,
            _graph_interchange_bundle(snapshot, graph_diagnostics),
        )
    provenance_manifest = {
        "snapshot_id": snapshot.snapshot_id,
        "created_at": snapshot.created_at,
        "source_count": len(snapshot.sources),
        "artifact_count": len(snapshot.artifacts),
        "observation_count": len(snapshot.observations),
        "export_guardrails": guardrail_report,
        "graph_diagnostics": str(graph_diagnostics_path) if include_graph_diagnostics else "",
        "graph_interchange": str(graph_interchange_path) if include_graph_interchange else "",
    }
    _write_json(target / "provenance_manifest.json", provenance_manifest)
    manifest = {
        "export_kind": "canonical",
        "snapshot_id": snapshot.snapshot_id,
        "export_guardrails": guardrail_report,
        "files": [
            "groundrecall_snapshot.json",
            "claims.jsonl",
            "concepts.jsonl",
            "relations.jsonl",
            "provenance_manifest.json",
        ],
    }
    if include_graph_diagnostics:
        manifest["files"].append("graph_diagnostics.json")
    if include_graph_interchange:
        manifest["files"].append("graph_interchange.json")
    _write_json(target / "export_manifest.json", manifest)
    outputs = {
        "snapshot_json": str(snapshot_path),
        "claims_jsonl": str(target / "claims.jsonl"),
        "concepts_jsonl": str(target / "concepts.jsonl"),
        "relations_jsonl": str(target / "relations.jsonl"),
        "provenance_manifest_json": str(target / "provenance_manifest.json"),
        "export_manifest_json": str(target / "export_manifest.json"),
    }
    if include_graph_diagnostics:
        outputs["graph_diagnostics_json"] = str(graph_diagnostics_path)
    if include_graph_interchange:
        outputs["graph_interchange_json"] = str(graph_interchange_path)
    return outputs


def export_query_bundle(
    store_dir: str | Path,
    concept_ref: str,
    out_path: str | Path,
) -> dict[str, Any]:
    payload = build_query_bundle_for_concept(store_dir, concept_ref)
    if payload is None:
        raise KeyError(f"Unknown concept reference: {concept_ref}")
    payload, guardrail_report = filter_query_payload_for_public_export(payload)
    payload["export_guardrails"] = guardrail_report
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(path, payload)
    return payload


def export_graph_bundle(
    store_dir: str | Path,
    concept_ref: str,
    out_path: str | Path,
    *,
    depth: int = 1,
) -> dict[str, Any]:
    payload = build_graph_bundle_for_concept(store_dir, concept_ref, depth=depth)
    if payload is None:
        raise KeyError(f"Unknown concept reference: {concept_ref}")
    payload, guardrail_report = filter_query_payload_for_public_export(payload)
    payload["export_guardrails"] = guardrail_report
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(path, payload)
    return payload


def export_groundrecall_query_bundle(
    store_dir: str | Path,
    concept_ref: str,
    out_dir: str | Path,
) -> dict[str, Any]:
    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    out_path = target / "groundrecall_query_bundle.json"
    payload = export_query_bundle(store_dir, concept_ref, out_path)
    graph_path = target / "epistemap_graph.json"
    if isinstance(payload.get("epistemap_graph"), dict):
        _write_json(graph_path, payload["epistemap_graph"])
    bayesian_path = target / "bayesian_reliability.md"
    bayesian = payload.get("epistemic_summary", {}).get("bayesian_reliability")
    if isinstance(bayesian, dict):
        write_bayesian_reliability_markdown(bayesian, bayesian_path)
    return {
        "concept_ref": concept_ref,
        "bundle_path": str(out_path),
        "epistemap_graph_path": str(graph_path) if graph_path.exists() else "",
        "bayesian_reliability_markdown_path": str(bayesian_path) if bayesian_path.exists() else "",
        "bundle": payload,
    }


def export_groundrecall_graph_bundle(
    store_dir: str | Path,
    concept_ref: str,
    out_dir: str | Path,
    *,
    depth: int = 1,
) -> dict[str, Any]:
    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    out_path = target / "groundrecall_graph_bundle.json"
    payload = export_graph_bundle(store_dir, concept_ref, out_path, depth=depth)
    return {
        "concept_ref": concept_ref,
        "bundle_path": str(out_path),
        "bundle": payload,
    }


def export_canonical_bundle(
    store_dir: str | Path,
    out_dir: str | Path,
    concept_refs: list[str] | None = None,
    graph_concept_refs: list[str] | None = None,
    graph_depth: int = 1,
    include_graph_diagnostics: bool = False,
    include_graph_interchange: bool = False,
    snapshot_id: str | None = None,
    pack_ready_concept: str | None = None,
) -> dict[str, Any]:
    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    outputs = export_canonical_snapshot(
        store_dir,
        target,
        snapshot_id=snapshot_id,
        include_graph_diagnostics=include_graph_diagnostics,
        include_graph_interchange=include_graph_interchange,
    )
    query_bundle_paths: list[str] = []
    for concept_ref in concept_refs or []:
        safe_name = concept_ref.lower().replace(" ", "-").replace("::", "-")
        bundle_path = target / f"query_bundle__{safe_name}.json"
        export_query_bundle(store_dir, concept_ref, bundle_path)
        query_bundle_paths.append(str(bundle_path))
    graph_bundle_paths: list[str] = []
    for concept_ref in graph_concept_refs or []:
        safe_name = concept_ref.lower().replace(" ", "-").replace("::", "-")
        bundle_path = target / f"graph_bundle__{safe_name}.json"
        export_graph_bundle(store_dir, concept_ref, bundle_path, depth=graph_depth)
        graph_bundle_paths.append(str(bundle_path))
    pack_ready_bundle = None
    if pack_ready_concept:
        pack_ready_bundle = export_groundrecall_query_bundle(store_dir, pack_ready_concept, target)
    manifest = json.loads((target / "export_manifest.json").read_text(encoding="utf-8"))
    manifest["query_bundles"] = query_bundle_paths
    manifest["graph_bundles"] = graph_bundle_paths
    if pack_ready_bundle is not None:
        manifest["groundrecall_query_bundle"] = pack_ready_bundle["bundle_path"]
        if pack_ready_bundle.get("epistemap_graph_path"):
            manifest["epistemap_graph"] = pack_ready_bundle["epistemap_graph_path"]
        if pack_ready_bundle.get("bayesian_reliability_markdown_path"):
            manifest["bayesian_reliability_markdown"] = pack_ready_bundle["bayesian_reliability_markdown_path"]
    _write_json(target / "export_manifest.json", manifest)
    return {
        "canonical_outputs": outputs,
        "query_bundles": query_bundle_paths,
        "graph_bundles": graph_bundle_paths,
        "groundrecall_query_bundle": pack_ready_bundle,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export canonical GroundRecall artifacts.")
    parser.add_argument("store_dir")
    parser.add_argument("out_dir")
    parser.add_argument("--snapshot-id", default=None)
    parser.add_argument("--concept", action="append", default=[])
    parser.add_argument("--graph-concept", action="append", default=[])
    parser.add_argument("--graph-depth", type=int, default=1)
    parser.add_argument("--include-graph-diagnostics", action="store_true")
    parser.add_argument("--include-graph-interchange", action="store_true")
    parser.add_argument("--pack-ready-concept", default=None)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    payload = export_canonical_bundle(
        store_dir=args.store_dir,
        out_dir=args.out_dir,
        concept_refs=list(args.concept or []),
        graph_concept_refs=list(args.graph_concept or []),
        graph_depth=args.graph_depth,
        include_graph_diagnostics=args.include_graph_diagnostics,
        include_graph_interchange=args.include_graph_interchange,
        snapshot_id=args.snapshot_id,
        pack_ready_concept=args.pack_ready_concept,
    )
    print(json.dumps(payload, indent=2))
