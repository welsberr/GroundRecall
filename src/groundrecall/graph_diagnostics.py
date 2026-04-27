from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any


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
    concept_ids = {str(item["concept_id"]) for item in concepts}
    adjacency: dict[str, set[str]] = {concept_id: set() for concept_id in concept_ids}
    inbound: defaultdict[str, int] = defaultdict(int)
    outbound: defaultdict[str, int] = defaultdict(int)

    for relation in relations:
        source_id = str(relation.get("source_id", ""))
        target_id = str(relation.get("target_id", ""))
        if source_id not in concept_ids or target_id not in concept_ids:
            continue
        adjacency[source_id].add(target_id)
        adjacency[target_id].add(source_id)
        outbound[source_id] += 1
        inbound[target_id] += 1

    components = _connected_components(adjacency)
    bridges = _bridge_concepts(adjacency, components)
    degree_ranked = sorted(
        (
            {
                "concept_id": concept_id,
                "degree": len(neighbors),
                "inbound_count": inbound.get(concept_id, 0),
                "outbound_count": outbound.get(concept_id, 0),
            }
            for concept_id, neighbors in adjacency.items()
        ),
        key=lambda item: (-item["degree"], -item["inbound_count"], item["concept_id"]),
    )

    return {
        "summary": {
            "concept_count": len(concepts),
            "relation_count": len(relations),
            "connected_component_count": len(components),
            "largest_component_size": max((len(component) for component in components), default=0),
            "isolated_concept_count": sum(1 for component in components if len(component) == 1),
            "bridge_concept_count": len(bridges),
        },
        "components": [
            {
                "component_id": f"component-{index}",
                "size": len(component),
                "concept_ids": component,
            }
            for index, component in enumerate(
                sorted(components, key=lambda item: (-len(item), item)),
                start=1,
            )
        ],
        "bridge_concepts": bridges,
        "top_connected_concepts": degree_ranked[:10],
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


def _connected_components(adjacency: dict[str, set[str]]) -> list[list[str]]:
    remaining = set(adjacency)
    components: list[list[str]] = []
    while remaining:
        start = remaining.pop()
        stack = [start]
        component = {start}
        while stack:
            node = stack.pop()
            for neighbor in adjacency.get(node, set()):
                if neighbor in component:
                    continue
                component.add(neighbor)
                remaining.discard(neighbor)
                stack.append(neighbor)
        components.append(sorted(component))
    return components


def _bridge_concepts(adjacency: dict[str, set[str]], components: list[list[str]]) -> list[dict[str, Any]]:
    bridge_payloads: list[dict[str, Any]] = []
    for component in components:
        if len(component) < 3:
            continue
        baseline_size = len(component)
        component_set = set(component)
        for concept_id in component:
            remaining = component_set - {concept_id}
            if not remaining:
                continue
            first = next(iter(remaining))
            visited = _walk_component(first, adjacency, blocked=concept_id, allowed=remaining)
            if len(visited) == len(remaining):
                continue
            bridge_payloads.append(
                {
                    "concept_id": concept_id,
                    "component_size": baseline_size,
                    "reachable_after_removal": len(visited),
                }
            )
    return sorted(bridge_payloads, key=lambda item: (-item["component_size"], item["concept_id"]))


def _walk_component(
    start: str,
    adjacency: dict[str, set[str]],
    *,
    blocked: str,
    allowed: set[str],
) -> set[str]:
    visited = {start}
    stack = [start]
    while stack:
        node = stack.pop()
        for neighbor in adjacency.get(node, set()):
            if neighbor == blocked or neighbor not in allowed or neighbor in visited:
                continue
            visited.add(neighbor)
            stack.append(neighbor)
    return visited
