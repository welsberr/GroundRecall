from __future__ import annotations

from collections import OrderedDict
from hashlib import sha256
import re
from typing import Any


EXTRACTOR_NAME = "groundrecall.heuristic_cooccurrence.v1"


def extract_heuristic_graph_relations(
    concept_rows: list[dict[str, Any]],
    observation_rows: list[dict[str, Any]],
    *,
    import_id: str,
    machine_id: str = "",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build draft relation candidates from concept co-mentions in observations."""

    concept_patterns = _concept_patterns(concept_rows)
    candidates: OrderedDict[tuple[str, str, str], dict[str, Any]] = OrderedDict()

    for observation in observation_rows:
        text = str(observation.get("text", "") or "")
        if not text.strip():
            continue
        mentioned = sorted(
            concept_id
            for concept_id, patterns in concept_patterns.items()
            if any(pattern.search(text) for pattern in patterns)
        )
        if len(mentioned) < 2:
            continue
        for source_id, target_id in _concept_pairs(mentioned):
            key = (source_id, target_id, "co_occurs_with")
            candidate = candidates.get(key)
            if candidate is None:
                relation_id = _relation_id(import_id, source_id, target_id)
                candidate = {
                    "relation_id": relation_id,
                    "import_id": import_id,
                    "source_id": source_id,
                    "target_id": target_id,
                    "relation_type": "co_occurs_with",
                    "evidence_ids": [],
                    "origin_artifact_id": observation.get("artifact_id", ""),
                    "origin_path": observation.get("origin_path", ""),
                    "origin_section": observation.get("origin_section", ""),
                    "machine_id": machine_id,
                    "support_kind": "inferred",
                    "grounding_status": "partially_grounded",
                    "extraction_method": EXTRACTOR_NAME,
                    "current_status": "draft",
                }
                candidates[key] = candidate
            observation_id = str(observation.get("observation_id", "") or "")
            if observation_id and observation_id not in candidate["evidence_ids"]:
                candidate["evidence_ids"].append(observation_id)

    relation_rows = list(candidates.values())
    summary = {
        "mode": "heuristic",
        "extractor": EXTRACTOR_NAME,
        "candidate_relation_count": len(relation_rows),
        "candidate_relations": [
            {
                "relation_id": item["relation_id"],
                "source_id": item["source_id"],
                "target_id": item["target_id"],
                "relation_type": item["relation_type"],
                "evidence_ids": list(item["evidence_ids"]),
                "rationale": "Concepts were mentioned together in at least one imported observation.",
            }
            for item in relation_rows
        ],
    }
    return relation_rows, summary


def _concept_patterns(concept_rows: list[dict[str, Any]]) -> dict[str, list[re.Pattern[str]]]:
    patterns: dict[str, list[re.Pattern[str]]] = {}
    for concept in concept_rows:
        concept_id = str(concept.get("concept_id", "") or "")
        if not concept_id:
            continue
        forms = [
            str(concept.get("title", "") or ""),
            concept_id.replace("concept::", "", 1).replace("-", " "),
        ]
        forms.extend(str(alias) for alias in concept.get("aliases", []) if str(alias).strip())
        compiled = [_surface_pattern(form) for form in forms]
        patterns[concept_id] = [pattern for pattern in compiled if pattern is not None]
    return {concept_id: value for concept_id, value in patterns.items() if value}


def _surface_pattern(value: str) -> re.Pattern[str] | None:
    tokens = [token for token in re.split(r"[\s_-]+", value.strip()) if token]
    if not tokens or len("".join(tokens)) < 4:
        return None
    body = r"[\s_-]+".join(re.escape(token) for token in tokens)
    return re.compile(rf"(?<![A-Za-z0-9]){body}(?![A-Za-z0-9])", re.IGNORECASE)


def _concept_pairs(concept_ids: list[str]) -> list[tuple[str, str]]:
    pairs = []
    for index, source_id in enumerate(concept_ids):
        for target_id in concept_ids[index + 1 :]:
            if source_id != target_id:
                pairs.append((source_id, target_id))
    return pairs


def _relation_id(import_id: str, source_id: str, target_id: str) -> str:
    digest = sha256(f"{import_id}|{source_id}|{target_id}|co_occurs_with".encode("utf-8")).hexdigest()[:16]
    return f"rel_xg_{digest}"
