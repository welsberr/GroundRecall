from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


PROVENANCE_RELATION_TYPES = {"same_source_family"}


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
    claims: list[dict[str, Any]] | None = None,
    observations: list[dict[str, Any]] | None = None,
    contradiction_cases: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    claims = claims or []
    observations = observations or []
    contradiction_cases = contradiction_cases or []
    concept_ids = {str(item["concept_id"]) for item in concepts}
    relation_partitions = _partition_relations(relations)
    semantic_relations = relation_partitions["semantic_relations"]
    provenance_relations = relation_partitions["provenance_relations"]
    adjacency: dict[str, set[str]] = {concept_id: set() for concept_id in concept_ids}
    inbound: defaultdict[str, int] = defaultdict(int)
    outbound: defaultdict[str, int] = defaultdict(int)

    for relation in semantic_relations:
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
    claim_concept_summary = _claim_concept_summary(concept_ids, claims)
    semantic_relation_type_counts = Counter(str(item.get("relation_type", "") or "unknown") for item in semantic_relations)
    semantic_relation_status_counts = Counter(str(item.get("current_status", "") or "unknown") for item in semantic_relations)
    degree_sum = sum(len(neighbors) for neighbors in adjacency.values())
    possible_undirected_edges = len(concept_ids) * (len(concept_ids) - 1) / 2

    return {
        "summary": {
            "concept_count": len(concepts),
            "relation_count": len(semantic_relations),
            "total_relation_count": len(relations),
            "provenance_relation_count": len(provenance_relations),
            "connected_component_count": len(components),
            "largest_component_size": max((len(component) for component in components), default=0),
            "isolated_concept_count": sum(1 for component in components if len(component) == 1),
            "bridge_concept_count": len(bridges),
            "average_degree": round(degree_sum / len(concept_ids), 3) if concept_ids else 0.0,
            "edge_density": round(len(semantic_relations) / possible_undirected_edges, 6) if possible_undirected_edges else 0.0,
            "claim_concept_link_count": claim_concept_summary["claim_concept_link_count"],
            "claims_without_concept_count": claim_concept_summary["claims_without_concept_count"],
            "concepts_with_claim_count": claim_concept_summary["concepts_with_claim_count"],
            "concepts_without_claim_count": claim_concept_summary["concepts_without_claim_count"],
        },
        "density": {
            "average_degree": round(degree_sum / len(concept_ids), 3) if concept_ids else 0.0,
            "edge_density": round(len(semantic_relations) / possible_undirected_edges, 6) if possible_undirected_edges else 0.0,
            "degree_sum": degree_sum,
            "possible_undirected_edges": int(possible_undirected_edges),
            "isolated_concept_ratio": round(sum(1 for component in components if len(component) == 1) / len(concept_ids), 3) if concept_ids else 0.0,
            "concepts_with_claim_ratio": round(claim_concept_summary["concepts_with_claim_count"] / len(concept_ids), 3) if concept_ids else 0.0,
            "relation_type_counts": dict(sorted(semantic_relation_type_counts.items())),
            "relation_status_counts": dict(sorted(semantic_relation_status_counts.items())),
            **claim_concept_summary,
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
        "quality_summary": _quality_summary(concepts, semantic_relations, claims, observations, degree_ranked, contradiction_cases),
        "relation_quality": _relation_quality(semantic_relations),
        "provenance_relation_quality": _relation_quality(provenance_relations),
        "claim_quality": _claim_quality(claims, observations, contradiction_cases),
        "concept_quality": _concept_quality(degree_ranked, claims),
        "quality_controls": _quality_controls(concepts, semantic_relations, claims, observations, degree_ranked, contradiction_cases),
    }


def build_graph_diagnostics_from_import(import_dir: str | Path) -> dict[str, Any]:
    base = Path(import_dir)
    concepts = _read_jsonl(base / "concepts.jsonl")
    relations = _read_jsonl(base / "relations.jsonl")
    claims = _read_jsonl(base / "claims.jsonl")
    observations = _read_jsonl(base / "observations.jsonl")
    contradiction_cases = _read_jsonl(base / "contradiction_cases.jsonl")
    diagnostics = build_graph_diagnostics(
        concepts,
        relations,
        claims=claims,
        observations=observations,
        contradiction_cases=contradiction_cases,
    )
    manifest_path = base / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        diagnostics["import_id"] = manifest.get("import_id", "")
    return diagnostics


def compact_graph_diagnostics(diagnostics: dict[str, Any]) -> dict[str, Any]:
    relation_quality = diagnostics.get("relation_quality", {})
    concept_quality = diagnostics.get("concept_quality", {})
    quality_controls = diagnostics.get("quality_controls", {})
    components = diagnostics.get("components", [])
    return {
        "summary": diagnostics.get("summary", {}),
        "density": diagnostics.get("density", {}),
        "quality_summary": diagnostics.get("quality_summary", {}),
        "relation_quality": {
            "support_kind_counts": relation_quality.get("support_kind_counts", {}),
            "grounding_status_counts": relation_quality.get("grounding_status_counts", {}),
            "inferred_relation_count": relation_quality.get("inferred_relation_count", 0),
            "inferred_relation_ratio": relation_quality.get("inferred_relation_ratio", 0.0),
            "weakly_grounded_relation_count": relation_quality.get("weakly_grounded_relation_count", 0),
        },
        "provenance_relation_quality": diagnostics.get("provenance_relation_quality", {}),
        "claim_quality": {
            key: diagnostics.get("claim_quality", {}).get(key, 0)
            for key in [
                "unsupported_claim_count",
                "contradiction_link_count",
                "contradiction_case_count",
                "open_contradiction_case_count",
                "contradiction_links_without_case_count",
                "contradiction_cases_with_missing_claim_count",
                "open_promoted_contradiction_case_count",
                "supersession_link_count",
                "unresolved_conflict_link_count",
            ]
        },
        "concept_quality": {
            "high_fanout_degree_threshold": concept_quality.get("high_fanout_degree_threshold", 0),
            "high_fanout_concept_count": concept_quality.get("high_fanout_concept_count", 0),
            "top_high_fanout_concepts": concept_quality.get("high_fanout_concepts", [])[:10],
        },
        "largest_components": [
            {
                "component_id": item.get("component_id", ""),
                "size": item.get("size", 0),
                "sample_concept_ids": list(item.get("concept_ids", []))[:10],
            }
            for item in components[:10]
        ],
        "top_connected_concepts": diagnostics.get("top_connected_concepts", [])[:10],
        "quality_controls": {
            "thresholds": quality_controls.get("thresholds", {}),
            "flag_count": quality_controls.get("flag_count", 0),
            "flags": quality_controls.get("flags", []),
        },
    }


def _partition_relations(relations: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    semantic_relations = []
    provenance_relations = []
    for relation in relations:
        relation_type = str(relation.get("relation_type", "") or "").strip()
        if relation_type in PROVENANCE_RELATION_TYPES:
            provenance_relations.append(relation)
        else:
            semantic_relations.append(relation)
    return {
        "semantic_relations": semantic_relations,
        "provenance_relations": provenance_relations,
    }


def _quality_summary(
    concepts: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    observations: list[dict[str, Any]],
    degree_ranked: list[dict[str, Any]],
    contradiction_cases: list[dict[str, Any]],
) -> dict[str, Any]:
    relation_quality = _relation_quality(relations)
    claim_quality = _claim_quality(claims, observations, contradiction_cases)
    concept_quality = _concept_quality(degree_ranked, claims)
    relation_count = len(relations)
    inferred_relation_count = relation_quality["inferred_relation_count"]
    weakly_grounded_relation_count = relation_quality["weakly_grounded_relation_count"]
    return {
        "concept_count": len(concepts),
        "claim_count": len(claims),
        "relation_count": relation_count,
        "inferred_relation_count": inferred_relation_count,
        "inferred_relation_ratio": round(inferred_relation_count / relation_count, 3) if relation_count else 0.0,
        "weakly_grounded_relation_count": weakly_grounded_relation_count,
        "unsupported_claim_count": claim_quality["unsupported_claim_count"],
        "contradiction_link_count": claim_quality["contradiction_link_count"],
        "contradiction_case_count": claim_quality["contradiction_case_count"],
        "open_contradiction_case_count": claim_quality["open_contradiction_case_count"],
        "supersession_link_count": claim_quality["supersession_link_count"],
        "high_fanout_concept_count": concept_quality["high_fanout_concept_count"],
    }


def _relation_quality(relations: list[dict[str, Any]]) -> dict[str, Any]:
    support_counts: Counter[str] = Counter()
    grounding_counts: Counter[str] = Counter()
    inferred_relations = []
    weakly_grounded_relations = []

    for relation in relations:
        support_kind = _support_kind(relation)
        grounding_status = _grounding_status(relation)
        support_counts[support_kind] += 1
        grounding_counts[grounding_status] += 1
        is_inferred = support_kind == "inferred" or bool(relation.get("extraction_method"))
        if is_inferred:
            inferred_relations.append(_relation_ref(relation, support_kind, grounding_status))
        weak_reasons = []
        if support_kind in {"unknown", "inferred"}:
            weak_reasons.append(f"support_kind:{support_kind}")
        if grounding_status in {"unknown", "ungrounded", "partially_grounded"}:
            weak_reasons.append(f"grounding_status:{grounding_status}")
        if weak_reasons:
            payload = _relation_ref(relation, support_kind, grounding_status)
            payload["reasons"] = weak_reasons
            weakly_grounded_relations.append(payload)

    relation_count = len(relations)
    return {
        "support_kind_counts": dict(sorted(support_counts.items())),
        "grounding_status_counts": dict(sorted(grounding_counts.items())),
        "inferred_relation_count": len(inferred_relations),
        "inferred_relation_ratio": round(len(inferred_relations) / relation_count, 3) if relation_count else 0.0,
        "weakly_grounded_relation_count": len(weakly_grounded_relations),
        "inferred_relations": inferred_relations[:25],
        "weakly_grounded_relations": weakly_grounded_relations[:25],
    }


def _claim_concept_summary(concept_ids: set[str], claims: list[dict[str, Any]]) -> dict[str, Any]:
    claim_concept_link_count = 0
    claims_without_concept = []
    concepts_with_claims: set[str] = set()
    for claim in claims:
        claim_id = str(claim.get("claim_id", ""))
        linked_concepts = [str(item) for item in claim.get("concept_ids", []) if str(item)]
        if not linked_concepts:
            claims_without_concept.append(claim_id)
        for concept_id in linked_concepts:
            claim_concept_link_count += 1
            if concept_id in concept_ids:
                concepts_with_claims.add(concept_id)
    concepts_without_claims = sorted(concept_ids - concepts_with_claims)
    return {
        "claim_concept_link_count": claim_concept_link_count,
        "claims_without_concept_count": len(claims_without_concept),
        "claims_without_concept_ids": claims_without_concept[:25],
        "concepts_with_claim_count": len(concepts_with_claims),
        "concepts_without_claim_count": len(concepts_without_claims),
        "concepts_without_claim_ids": concepts_without_claims[:25],
    }


def _claim_quality(claims: list[dict[str, Any]], observations: list[dict[str, Any]], contradiction_cases: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    contradiction_cases = contradiction_cases or []
    observations_by_id = {str(item.get("observation_id", "")): item for item in observations}
    claim_ids = {str(item.get("claim_id", "")) for item in claims}
    claims_by_id = {str(item.get("claim_id", "")): item for item in claims}
    unsupported_claims = []
    contradiction_links = []
    supersession_links = []
    superseded_by_concept: defaultdict[str, set[str]] = defaultdict(set)
    superseding_by_concept: defaultdict[str, set[str]] = defaultdict(set)

    for claim in claims:
        claim_id = str(claim.get("claim_id", ""))
        source_observation_ids = [str(item) for item in claim.get("source_observation_ids", []) if str(item)]
        reasons = []
        if not source_observation_ids:
            reasons.append("missing_source_observation")
        missing_observation_ids = [item for item in source_observation_ids if item not in observations_by_id]
        if missing_observation_ids:
            reasons.append("missing_observation_record")
        grounding_status = _grounding_status(claim)
        if grounding_status == "ungrounded":
            reasons.append("claim_ungrounded")
        elif source_observation_ids:
            observation_grounding = [
                _grounding_status(observations_by_id[item])
                for item in source_observation_ids
                if item in observations_by_id
            ]
            if observation_grounding and all(item == "ungrounded" for item in observation_grounding):
                reasons.append("all_source_observations_ungrounded")
        if reasons:
            unsupported_claims.append(
                {
                    "claim_id": claim_id,
                    "concept_ids": list(claim.get("concept_ids", [])),
                    "reasons": reasons,
                    "source_observation_ids": source_observation_ids,
                }
            )

        for target_claim_id in [str(item) for item in claim.get("contradicts_claim_ids", []) if str(item)]:
            contradiction_links.append(
                {
                    "claim_id": claim_id,
                    "target_claim_id": target_claim_id,
                    "target_exists": target_claim_id in claim_ids,
                }
            )
        for target_claim_id in [str(item) for item in claim.get("supersedes_claim_ids", []) if str(item)]:
            supersession_links.append(
                {
                    "claim_id": claim_id,
                    "target_claim_id": target_claim_id,
                    "target_exists": target_claim_id in claim_ids,
                }
            )
            for concept_id in claim.get("concept_ids", []):
                superseding_by_concept[str(concept_id)].add(claim_id)
                superseded_by_concept[str(concept_id)].add(target_claim_id)

    contradiction_case_pairs = {
        tuple(sorted(str(claim_id) for claim_id in item.get("claim_ids", []) if str(claim_id)))
        for item in contradiction_cases
        if str(item.get("case_kind", "contradiction")) == "contradiction"
    }
    links_without_cases = [
        item
        for item in contradiction_links
        if item["target_exists"] and tuple(sorted((item["claim_id"], item["target_claim_id"]))) not in contradiction_case_pairs
    ]
    cases_with_missing_claims = [
        {
            "case_id": str(item.get("case_id", "")),
            "missing_claim_ids": [str(claim_id) for claim_id in item.get("claim_ids", []) if str(claim_id) not in claim_ids],
        }
        for item in contradiction_cases
        if any(str(claim_id) not in claim_ids for claim_id in item.get("claim_ids", []))
    ]
    open_cases = [item for item in contradiction_cases if str(item.get("status", "open")) in {"open", "under_review"}]
    open_promoted_cases = [
        {
            "case_id": str(item.get("case_id", "")),
            "claim_ids": [str(claim_id) for claim_id in item.get("claim_ids", [])],
        }
        for item in open_cases
        if any(claims_by_id.get(str(claim_id), {}).get("current_status") == "promoted" for claim_id in item.get("claim_ids", []))
    ]
    superseded_neighborhoods = [
        {
            "concept_id": concept_id,
            "superseding_claim_ids": sorted(superseding_by_concept.get(concept_id, set())),
            "superseded_claim_ids": sorted(superseded_claim_ids),
        }
        for concept_id, superseded_claim_ids in sorted(superseded_by_concept.items())
    ]
    return {
        "unsupported_claim_count": len(unsupported_claims),
        "unsupported_claims": unsupported_claims[:25],
        "contradiction_link_count": len(contradiction_links),
        "contradiction_links": contradiction_links[:25],
        "contradiction_case_count": len(contradiction_cases),
        "open_contradiction_case_count": len(open_cases),
        "contradiction_links_without_cases": links_without_cases[:25],
        "contradiction_links_without_case_count": len(links_without_cases),
        "contradiction_cases_with_missing_claims": cases_with_missing_claims[:25],
        "contradiction_cases_with_missing_claim_count": len(cases_with_missing_claims),
        "open_promoted_contradiction_cases": open_promoted_cases[:25],
        "open_promoted_contradiction_case_count": len(open_promoted_cases),
        "supersession_link_count": len(supersession_links),
        "supersession_links": supersession_links[:25],
        "superseded_neighborhoods": superseded_neighborhoods[:25],
        "unresolved_conflict_link_count": sum(1 for item in contradiction_links + supersession_links if not item["target_exists"]),
    }


def _concept_quality(degree_ranked: list[dict[str, Any]], claims: list[dict[str, Any]]) -> dict[str, Any]:
    threshold = 8
    claim_counts: Counter[str] = Counter()
    unsupported_claim_counts: Counter[str] = Counter()
    for claim in claims:
        concept_ids = [str(item) for item in claim.get("concept_ids", []) if str(item)]
        unsupported = not claim.get("source_observation_ids") or _grounding_status(claim) == "ungrounded"
        for concept_id in concept_ids:
            claim_counts[concept_id] += 1
            if unsupported:
                unsupported_claim_counts[concept_id] += 1
    high_fanout = [
        {
            **item,
            "claim_count": claim_counts.get(item["concept_id"], 0),
            "unsupported_claim_count": unsupported_claim_counts.get(item["concept_id"], 0),
            "threshold": threshold,
        }
        for item in degree_ranked
        if int(item.get("degree", 0)) >= threshold
    ]
    return {
        "high_fanout_degree_threshold": threshold,
        "high_fanout_concept_count": len(high_fanout),
        "high_fanout_concepts": high_fanout[:25],
    }


def _quality_controls(
    concepts: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    observations: list[dict[str, Any]],
    degree_ranked: list[dict[str, Any]],
    contradiction_cases: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    contradiction_cases = contradiction_cases or []
    summary = _quality_summary(concepts, relations, claims, observations, degree_ranked, contradiction_cases)
    flags: list[dict[str, Any]] = []
    if summary["relation_count"] and summary["inferred_relation_ratio"] >= 0.5:
        flags.append(
            {
                "code": "high_inferred_relation_density",
                "severity": "warning",
                "message": "At least half of relation edges are inferred and should be reviewed before downstream export.",
                "value": summary["inferred_relation_ratio"],
            }
        )
    if summary["weakly_grounded_relation_count"]:
        flags.append(
            {
                "code": "weak_relation_grounding",
                "severity": "warning",
                "message": "One or more relation edges have inferred, unknown, ungrounded, or partially grounded support.",
                "value": summary["weakly_grounded_relation_count"],
            }
        )
    if summary["unsupported_claim_count"]:
        flags.append(
            {
                "code": "unsupported_claims",
                "severity": "warning",
                "message": "One or more claims are missing source observations or are ungrounded.",
                "value": summary["unsupported_claim_count"],
            }
        )
    if summary["high_fanout_concept_count"]:
        flags.append(
            {
                "code": "high_fanout_concepts",
                "severity": "warning",
                "message": "One or more concepts have unusually high graph fanout and may be noisy hubs.",
                "value": summary["high_fanout_concept_count"],
            }
        )
    claim_quality = _claim_quality(claims, observations, contradiction_cases)
    unresolved = claim_quality["unresolved_conflict_link_count"]
    if unresolved:
        flags.append(
            {
                "code": "unresolved_claim_conflict_links",
                "severity": "warning",
                "message": "Contradiction or supersession links point to missing claim ids.",
                "value": unresolved,
            }
        )
    if claim_quality["contradiction_links_without_case_count"]:
        flags.append(
            {
                "code": "contradiction_links_without_cases",
                "severity": "warning",
                "message": "One or more contradiction links have no first-class contradiction case.",
                "value": claim_quality["contradiction_links_without_case_count"],
            }
        )
    if claim_quality["contradiction_cases_with_missing_claim_count"]:
        flags.append(
            {
                "code": "contradiction_cases_with_missing_claims",
                "severity": "warning",
                "message": "One or more contradiction cases reference missing claim ids.",
                "value": claim_quality["contradiction_cases_with_missing_claim_count"],
            }
        )
    if claim_quality["open_promoted_contradiction_case_count"]:
        flags.append(
            {
                "code": "open_promoted_contradiction_cases",
                "severity": "warning",
                "message": "One or more open contradiction cases involve promoted claims and should be adjudicated.",
                "value": claim_quality["open_promoted_contradiction_case_count"],
            }
        )
    return {
        "thresholds": {
            "high_inferred_relation_ratio": 0.5,
            "high_fanout_degree": 8,
        },
        "flag_count": len(flags),
        "flags": flags,
    }


def _support_kind(row: dict[str, Any]) -> str:
    value = str(row.get("support_kind", "") or "").strip()
    if value:
        return value
    provenance = row.get("provenance", {})
    if isinstance(provenance, dict):
        value = str(provenance.get("support_kind", "") or "").strip()
        if value:
            return value
    return "unknown"


def _grounding_status(row: dict[str, Any]) -> str:
    value = str(row.get("grounding_status", "") or "").strip()
    if value:
        return value
    provenance = row.get("provenance", {})
    if isinstance(provenance, dict):
        value = str(provenance.get("grounding_status", "") or "").strip()
        if value:
            return value
    return "unknown"


def _relation_ref(relation: dict[str, Any], support_kind: str, grounding_status: str) -> dict[str, Any]:
    return {
        "relation_id": relation.get("relation_id", ""),
        "source_id": relation.get("source_id", ""),
        "target_id": relation.get("target_id", ""),
        "relation_type": relation.get("relation_type", ""),
        "support_kind": support_kind,
        "grounding_status": grounding_status,
        "evidence_ids": list(relation.get("evidence_ids", [])),
    }


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
