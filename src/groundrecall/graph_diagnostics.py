from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from epistemap import diagnostics

from .epistemap_adapter import graph_bundle_from_rows


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    return [json.loads(line) for line in text.splitlines()]


def build_graph_diagnostics(
    concepts: list[dict[str, Any]],
    relations: list[dict[str, Any]],
) -> dict[str, Any]:
    bundle = graph_bundle_from_rows(concepts, relations)
    payload = diagnostics(bundle, node_types={"concept"})
    return {
        "summary": {
            "concept_count": len(concepts),
            "relation_count": payload["summary"]["edge_count"],
            "connected_component_count": payload["summary"]["connected_component_count"],
            "largest_component_size": payload["summary"]["largest_component_size"],
            "isolated_concept_count": payload["summary"]["isolated_node_count"],
            "bridge_concept_count": payload["summary"]["bridge_node_count"],
        },
        "components": [
            {
                "component_id": item["component_id"],
                "size": item["size"],
                "concept_ids": item["node_ids"],
            }
            for item in payload["components"]
        ],
        "bridge_concepts": [
            {
                "concept_id": item["node_id"],
                "component_size": item["component_size"],
                "reachable_after_removal": item["reachable_after_removal"],
            }
            for item in payload["bridge_nodes"]
        ],
        "top_connected_concepts": [
            {
                "concept_id": item["node_id"],
                "degree": item["degree"],
                "inbound_count": item["inbound_count"],
                "outbound_count": item["outbound_count"],
            }
            for item in payload["top_connected_nodes"]
        ],
    }


def build_graph_diagnostics_from_import(import_dir: str | Path) -> dict[str, Any]:
    base = Path(import_dir)
    concepts = _read_jsonl(base / "concepts.jsonl")
    relations = _read_jsonl(base / "relations.jsonl")
    diagnostics = build_graph_diagnostics(concepts, relations)
    manifest_path = base / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        diagnostics["import_id"] = manifest.get("import_id", "")
    return diagnostics
