from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    return [json.loads(line) for line in text.splitlines()]


def _triage_lane(item: dict[str, Any], finding_codes: set[str], graph_codes: set[str] | None = None) -> str:
    graph_codes = graph_codes or set()
    if {"claim_ungrounded", "ungrounded_summary"} & finding_codes:
        return "source_cleanup"
    if {"bridge_concept", "isolated_concept", "small_component"} & graph_codes:
        return "conflict_resolution"
    if {"relation_missing_source", "relation_missing_target", "orphan_concept"} & finding_codes:
        return "conflict_resolution"
    return "knowledge_capture"


def _priority(item: dict[str, Any], finding_codes: set[str], graph_codes: set[str] | None = None) -> int:
    graph_codes = graph_codes or set()
    priority = 50
    if item.get("grounding_status") == "grounded":
        priority -= 10
    if item.get("current_status") == "triaged":
        priority -= 5
    if any(code.startswith("claim_") or code.startswith("relation_") for code in finding_codes):
        priority += 20
    priority -= min(len(finding_codes) * 2, 10)
    if "bridge_concept" in graph_codes:
        priority -= 10
    if "isolated_concept" in graph_codes:
        priority -= 6
    if "small_component" in graph_codes:
        priority -= 4
    return max(priority, 1)


def build_review_queue(import_dir: str | Path) -> dict[str, Any]:
    base = Path(import_dir)
    manifest = _read_json(base / "manifest.json")
    lint_payload = _read_json(base / "lint_findings.json")
    graph_payload = _read_json(base / "graph_diagnostics.json")
    standardization_payload = _read_json(base / "concept_standardization.json") if (base / "concept_standardization.json").exists() else {}
    claims = _read_jsonl(base / "claims.jsonl")
    concepts = _read_jsonl(base / "concepts.jsonl")
    relations = _read_jsonl(base / "relations.jsonl")

    findings_by_target: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for finding in lint_payload.get("findings", []):
        findings_by_target[finding["target_id"]].append(finding)
    graph_codes_by_concept = _graph_codes_by_concept(graph_payload)
    standardization_codes_by_concept = _standardization_codes_by_concept(standardization_payload)

    queue: list[dict[str, Any]] = []

    for claim in claims:
        related = findings_by_target.get(claim["claim_id"], [])
        finding_codes = {item["code"] for item in related}
        queue.append(
            {
                "queue_id": f"rq_{claim['claim_id']}",
                "candidate_type": "claim",
                "candidate_id": claim["claim_id"],
                "title": claim["claim_text"][:100],
                "triage_lane": _triage_lane(claim, finding_codes),
                "priority": _priority(claim, finding_codes),
                "grounding_status": claim.get("grounding_status"),
                "status": "needs_review",
                "finding_codes": sorted(finding_codes),
                "concept_ids": list(claim.get("concept_ids", [])),
            }
        )

    for concept in concepts:
        related = findings_by_target.get(concept["concept_id"], [])
        finding_codes = {item["code"] for item in related}
        graph_codes = graph_codes_by_concept.get(concept["concept_id"], set())
        standardization_codes = standardization_codes_by_concept.get(concept["concept_id"], set())
        if not finding_codes and not graph_codes and not standardization_codes:
            continue
        queue.append(
            {
                "queue_id": f"rq_{concept['concept_id'].replace('::', '_')}",
                "candidate_type": "concept",
                "candidate_id": concept["concept_id"],
                "title": concept["title"],
                "triage_lane": _triage_lane(concept, finding_codes | standardization_codes, graph_codes),
                "priority": _priority(concept, finding_codes | standardization_codes, graph_codes),
                "grounding_status": concept.get("grounding_status", "triaged"),
                "status": "needs_review",
                "finding_codes": sorted(finding_codes | graph_codes | standardization_codes),
                "concept_ids": [concept["concept_id"]],
                "graph_codes": sorted(graph_codes),
            }
        )

    for relation in relations:
        related = findings_by_target.get(relation["relation_id"], [])
        finding_codes = {item["code"] for item in related}
        if relation.get("support_kind") == "inferred" or relation.get("extraction_method"):
            finding_codes.add("relation_inferred")
        queue.append(
            {
                "queue_id": f"rq_{relation['relation_id']}",
                "candidate_type": "relation",
                "candidate_id": relation["relation_id"],
                "title": (
                    f"{relation.get('source_id', '')} "
                    f"{relation.get('relation_type', 'references')} "
                    f"{relation.get('target_id', '')}"
                )[:100],
                "triage_lane": _triage_lane(relation, finding_codes),
                "priority": _priority(relation, finding_codes),
                "grounding_status": relation.get("grounding_status", "partially_grounded"),
                "status": "needs_review",
                "finding_codes": sorted(finding_codes),
                "concept_ids": [relation.get("source_id", ""), relation.get("target_id", "")],
                "relation_type": relation.get("relation_type", "references"),
                "evidence_ids": list(relation.get("evidence_ids", [])),
            }
        )

    queue.sort(key=lambda item: (item["priority"], item["candidate_type"], item["candidate_id"]))
    return {
        "import_id": manifest["import_id"],
        "queue_length": len(queue),
        "items": queue,
    }


def _graph_codes_by_concept(graph_payload: dict[str, Any]) -> dict[str, set[str]]:
    codes: defaultdict[str, set[str]] = defaultdict(set)
    components = graph_payload.get("components", [])
    for component in components:
        concept_ids = [str(item) for item in component.get("concept_ids", [])]
        size = int(component.get("size", len(concept_ids)))
        if size == 1 and concept_ids:
            codes[concept_ids[0]].add("isolated_concept")
        elif 1 < size <= 2:
            for concept_id in concept_ids:
                codes[concept_id].add("small_component")
    for bridge in graph_payload.get("bridge_concepts", []):
        concept_id = str(bridge.get("concept_id", ""))
        if concept_id:
            codes[concept_id].add("bridge_concept")
    for concept in graph_payload.get("concept_quality", {}).get("high_fanout_concepts", []):
        concept_id = str(concept.get("concept_id", ""))
        if concept_id:
            codes[concept_id].add("high_fanout_concept")
    return codes


def _standardization_codes_by_concept(standardization_payload: dict[str, Any]) -> dict[str, set[str]]:
    codes: defaultdict[str, set[str]] = defaultdict(set)
    for group in standardization_payload.get("deterministic_merge_groups", []):
        concept_id = str(group.get("canonical_concept_id", ""))
        if concept_id:
            codes[concept_id].add("concept_deterministic_merge")
    for candidate in standardization_payload.get("ambiguous_alias_candidates", []):
        for key in ("left_concept_id", "right_concept_id"):
            concept_id = str(candidate.get(key, ""))
            if concept_id:
                codes[concept_id].add("concept_alias_candidate")
    return codes


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a GroundRecall review queue from import artifacts.")
    parser.add_argument("import_dir")
    parser.add_argument("--out", default=None)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    payload = build_review_queue(args.import_dir)
    out_path = Path(args.out) if args.out else Path(args.import_dir) / "review_queue.json"
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")
