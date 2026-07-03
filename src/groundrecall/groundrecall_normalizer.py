from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from .groundrecall_discovery import DiscoveredArtifact
from .groundrecall_segmenter import SegmentedPage, SegmentedObservation


@dataclass
class ImportContext:
    import_id: str
    import_mode: str
    machine_id: str
    agent_id: str
    source_root: str
    imported_at: str


def _sanitize_claim_key(value: str) -> str:
    text = "".join(ch.lower() if ch.isalnum() else "-" for ch in value).strip("-")
    return text or "claim"


def _claim_id_for_observation(observation_record: dict[str, Any], observation: SegmentedObservation, index: int) -> str:
    if observation.explicit_claim_key:
        return f"clm_{_sanitize_claim_key(observation.explicit_claim_key)}"
    return f"clm_{observation_record['observation_id']}_{index}"


def build_artifact_record(context: ImportContext, artifact: DiscoveredArtifact, page: SegmentedPage | None) -> dict[str, Any]:
    record = {
        "artifact_id": f"ia_{sha256(artifact.relative_path.encode('utf-8')).hexdigest()[:12]}",
        "import_id": context.import_id,
        "artifact_kind": artifact.artifact_kind,
        "path": artifact.relative_path,
        "title": page.title if page else Path(artifact.relative_path).stem,
        "sha256": sha256(artifact.path.read_bytes()).hexdigest(),
        "created_at": context.imported_at,
        "metadata": {
            "frontmatter": page.frontmatter if page else {},
            "headings": page.headings if page else [],
        },
        "current_status": "draft",
    }
    return record


def build_observation_record(
    context: ImportContext,
    artifact_record: dict[str, Any],
    observation: SegmentedObservation,
    index: int,
) -> dict[str, Any]:
    return {
        "observation_id": f"obs_{artifact_record['artifact_id']}_{index}",
        "import_id": context.import_id,
        "artifact_id": artifact_record["artifact_id"],
        "role": observation.role,
        "text": observation.text,
        "origin_path": observation.artifact_relative_path,
        "origin_section": observation.section,
        "line_start": observation.line_start,
        "line_end": observation.line_end,
        "grounding_status": observation.grounding_status,
        "support_kind": observation.support_kind,
        "confidence_hint": observation.confidence_hint,
        "current_status": "draft",
    }


def build_fragment_record(
    context: ImportContext,
    artifact_record: dict[str, Any],
    observation: SegmentedObservation,
    index: int,
) -> dict[str, Any]:
    return {
        "fragment_id": f"frag_{artifact_record['artifact_id']}_{index}",
        "import_id": context.import_id,
        "source_id": artifact_record["artifact_id"],
        "text": observation.text,
        "section": observation.section,
        "line_start": observation.line_start,
        "line_end": observation.line_end,
        "metadata": {
            "artifact_path": observation.artifact_relative_path,
            "role": observation.role,
        },
        "current_status": "draft",
    }


def build_claim_record(
    context: ImportContext,
    observation_record: dict[str, Any],
    observation: SegmentedObservation,
    concept_ids: list[str],
    index: int,
    fragment_ids: list[str] | None = None,
) -> dict[str, Any]:
    claim_kind = "statement" if observation_record["role"] == "claim" else "summary"
    argument_role = "premise" if claim_kind == "statement" else "context"
    risk_flags: list[str] = []
    if observation.contradict_keys:
        argument_role = "counterargument"
        risk_flags.append("contradiction_linked")
    if observation.supersede_keys:
        argument_role = "revision"
        risk_flags.append("supersession_linked")
    return {
        "claim_id": _claim_id_for_observation(observation_record, observation, index),
        "import_id": context.import_id,
        "claim_text": observation_record["text"],
        "claim_kind": claim_kind,
        "metadata": {
            "analysis_lane": "empirical",
            "argument_role": argument_role,
            "risk_flags": risk_flags,
        },
        "source_observation_ids": [observation_record["observation_id"]],
        "supporting_fragment_ids": list(fragment_ids or []),
        "concept_ids": [f"concept::{concept_id}" for concept_id in concept_ids],
        "contradicts_claim_ids": [f"clm_{_sanitize_claim_key(value)}" for value in observation.contradict_keys],
        "supersedes_claim_ids": [f"clm_{_sanitize_claim_key(value)}" for value in observation.supersede_keys],
        "confidence_hint": observation_record["confidence_hint"],
        "grounding_status": observation_record["grounding_status"],
        "current_status": "triaged" if observation_record["grounding_status"] != "ungrounded" else "draft",
    }


def build_concept_records(context: ImportContext, artifact_record: dict[str, Any], concept_ids: list[str]) -> list[dict[str, Any]]:
    records = []
    for concept_id in concept_ids:
        records.append(
            {
                "concept_id": f"concept::{concept_id}",
                "import_id": context.import_id,
                "title": concept_id.replace("-", " ").title(),
                "aliases": [],
                "description": "Imported concept from llmwiki corpus.",
                "source_artifact_ids": [artifact_record["artifact_id"]],
                "current_status": "triaged",
            }
        )
    return records


def build_relation_records(context: ImportContext, artifact_record: dict[str, Any], concept_ids: list[str], links: list[str]) -> list[dict[str, Any]]:
    if not concept_ids:
        return []
    primary = f"concept::{concept_ids[0]}"
    records = []
    for idx, link in enumerate(links, start=1):
        target = f"concept::{link.lower().replace(' ', '-')}"
        records.append(
            {
                "relation_id": f"rel_{artifact_record['artifact_id']}_{idx}",
                "import_id": context.import_id,
                "source_id": primary,
                "target_id": target,
                "relation_type": "references",
                "evidence_ids": [],
                "current_status": "draft",
            }
        )
    return records


def manifest_record(context: ImportContext) -> dict[str, Any]:
    return asdict(context) | {"source_repo_kind": "llmwiki"}


def standardize_concept_rows(
    concept_rows: list[dict[str, Any]],
    claim_rows: list[dict[str, Any]],
    relation_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    alias_map: dict[str, str] = {}
    normalized_index: dict[str, dict[str, Any]] = {}
    standardized_rows: list[dict[str, Any]] = []

    for row in concept_rows:
        normalized_title = _normalize_concept_title(str(row.get("title", "")))
        if not normalized_title:
            standardized_rows.append(row)
            continue

        canonical = normalized_index.get(normalized_title)
        if canonical is None:
            normalized_index[normalized_title] = row
            standardized_rows.append(row)
            continue

        canonical["source_artifact_ids"] = sorted(
            set(canonical.get("source_artifact_ids", [])) | set(row.get("source_artifact_ids", []))
        )
        aliases = set(canonical.get("aliases", []))
        aliases.add(str(row.get("title", "")))
        aliases.update(str(alias) for alias in row.get("aliases", []))
        aliases.discard(str(canonical.get("title", "")))
        canonical["aliases"] = sorted(alias for alias in aliases if alias)
        alias_map[str(row["concept_id"])] = str(canonical["concept_id"])

    if alias_map:
        for row in claim_rows:
            row["concept_ids"] = [alias_map.get(concept_id, concept_id) for concept_id in row.get("concept_ids", [])]
        for row in relation_rows:
            row["source_id"] = alias_map.get(str(row.get("source_id", "")), str(row.get("source_id", "")))
            row["target_id"] = alias_map.get(str(row.get("target_id", "")), str(row.get("target_id", "")))

    return standardized_rows, claim_rows, relation_rows


def build_concept_standardization_report(
    input_concept_rows: list[dict[str, Any]],
    standardized_concept_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    input_groups: dict[str, list[dict[str, Any]]] = {}
    for row in input_concept_rows:
        normalized = _normalize_concept_title(str(row.get("title", "")))
        if not normalized:
            continue
        input_groups.setdefault(normalized, []).append(row)

    canonical_by_normalized = {
        _normalize_concept_title(str(row.get("title", ""))): row
        for row in standardized_concept_rows
        if _normalize_concept_title(str(row.get("title", "")))
    }
    deterministic_merge_groups = []
    for normalized, members in sorted(input_groups.items()):
        if len(members) < 2:
            continue
        canonical = canonical_by_normalized.get(normalized, members[0])
        deterministic_merge_groups.append(
            {
                "normalized_title": normalized,
                "canonical_concept_id": canonical.get("concept_id", ""),
                "member_concept_ids": sorted(str(item.get("concept_id", "")) for item in members if item.get("concept_id")),
                "member_titles": sorted(str(item.get("title", "")) for item in members if item.get("title")),
                "source_artifact_ids": sorted(
                    {
                        str(artifact_id)
                        for item in members
                        for artifact_id in item.get("source_artifact_ids", [])
                        if str(artifact_id)
                    }
                ),
            }
        )

    ambiguous_alias_candidates = _ambiguous_alias_candidates(standardized_concept_rows)
    return {
        "input_concept_count": len(input_concept_rows),
        "standardized_concept_count": len(standardized_concept_rows),
        "deterministic_merge_group_count": len(deterministic_merge_groups),
        "ambiguous_alias_candidate_count": len(ambiguous_alias_candidates),
        "deterministic_merge_groups": deterministic_merge_groups,
        "ambiguous_alias_candidates": ambiguous_alias_candidates,
    }


def _normalize_concept_title(value: str) -> str:
    normalized = "".join(ch.lower() if ch.isalnum() else " " for ch in value)
    tokens = [token for token in normalized.split() if token not in {"a", "an", "the"}]
    return " ".join(tokens)


def _ambiguous_alias_candidates(concept_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = []
    for index, left in enumerate(concept_rows):
        left_tokens = _concept_tokens(str(left.get("title", "")))
        if len(left_tokens) < 2:
            continue
        for right in concept_rows[index + 1 :]:
            right_tokens = _concept_tokens(str(right.get("title", "")))
            if len(right_tokens) < 2:
                continue
            overlap = left_tokens & right_tokens
            if len(overlap) < 2:
                continue
            score = len(overlap) / len(left_tokens | right_tokens)
            if score < 0.66:
                continue
            candidates.append(
                {
                    "candidate_id": _alias_candidate_id(str(left.get("concept_id", "")), str(right.get("concept_id", ""))),
                    "left_concept_id": left.get("concept_id", ""),
                    "left_title": left.get("title", ""),
                    "right_concept_id": right.get("concept_id", ""),
                    "right_title": right.get("title", ""),
                    "shared_tokens": sorted(overlap),
                    "score": round(score, 3),
                    "rationale": "High token overlap suggests a possible alias or near-duplicate concept, but it was not auto-merged.",
                }
            )
    return sorted(candidates, key=lambda item: (-item["score"], item["left_concept_id"], item["right_concept_id"]))


def _concept_tokens(value: str) -> set[str]:
    return set(_normalize_concept_title(value).split())


def _alias_candidate_id(left_concept_id: str, right_concept_id: str) -> str:
    left, right = sorted([left_concept_id, right_concept_id])
    return f"alias::{left.replace('concept::', '')}::{right.replace('concept::', '')}"
