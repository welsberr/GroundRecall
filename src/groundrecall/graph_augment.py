from __future__ import annotations

import argparse
from collections import OrderedDict
from dataclasses import dataclass, field
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from .models import ProvenanceRecord, RelationRecord, ReviewCandidateRecord
from .store import GroundRecallStore


DEFAULT_RELATION_TYPE = "co_occurs_with"
EXTRACTOR_NAME = "groundrecall.store_claim_cooccurrence.v1"
SOURCE_FAMILY_EXTRACTOR_NAME = "groundrecall.store_source_family.v1"
VALID_STRATEGIES = {"claim-cooccurrence", "source-family"}


@dataclass
class RelationCandidate:
    source_id: str
    target_id: str
    relation_type: str
    claim_ids: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    origin_paths: list[str] = field(default_factory=list)


def augment_store_relations_from_claims(
    store_dir: str | Path,
    *,
    concept_prefixes: list[str] | None = None,
    relation_type: str = DEFAULT_RELATION_TYPE,
    min_evidence: int = 2,
    strategy: str = "claim-cooccurrence",
    limit: int | None = None,
    apply: bool = False,
) -> dict[str, Any]:
    if strategy not in VALID_STRATEGIES:
        raise ValueError(f"Unknown graph augmentation strategy: {strategy}")
    store = GroundRecallStore(store_dir)
    concepts = {item.concept_id: item for item in store.list_concepts() if item.current_status != "rejected"}
    existing_keys = {
        _relation_key(item.source_id, item.target_id, item.relation_type)
        for item in store.list_relations()
    }
    prefixes = [item for item in (concept_prefixes or []) if item]
    if strategy == "claim-cooccurrence":
        candidates = _claim_cooccurrence_candidates(
            store,
            concepts=concepts,
            existing_keys=existing_keys,
            prefixes=prefixes,
            relation_type=relation_type,
        )
        extractor = EXTRACTOR_NAME
    else:
        relation_type = "same_source_family"
        candidates = _source_family_candidates(
            concepts=concepts,
            existing_keys=existing_keys,
            prefixes=prefixes,
            relation_type=relation_type,
        )
        extractor = SOURCE_FAMILY_EXTRACTOR_NAME

    effective_min_evidence = 1 if strategy == "source-family" else max(1, int(min_evidence))
    selected = [
        candidate
        for candidate in candidates.values()
        if len(candidate.claim_ids) >= effective_min_evidence
    ]
    selected.sort(key=lambda item: (-len(item.claim_ids), item.source_id, item.target_id))
    if limit is not None:
        selected = selected[: max(0, int(limit))]

    relation_payloads = [_candidate_payload(candidate, extractor=extractor) for candidate in selected]
    if apply:
        for candidate in selected:
            relation_id = _relation_id(candidate.source_id, candidate.target_id, candidate.relation_type, extractor=extractor)
            store.save_relation(
                RelationRecord(
                    relation_id=relation_id,
                    source_id=candidate.source_id,
                    target_id=candidate.target_id,
                    relation_type=candidate.relation_type,
                    evidence_ids=candidate.evidence_ids,
                    provenance=ProvenanceRecord(
                        origin_path=candidate.origin_paths[0] if candidate.origin_paths else "",
                        support_kind="inferred",
                        grounding_status="partially_grounded",
                    ),
                    current_status="triaged",
                )
            )
            store.save_review_candidate(
                ReviewCandidateRecord(
                    review_candidate_id=f"rq_{relation_id}",
                    candidate_type="relation",
                    candidate_id=relation_id,
                    triage_lane="relation_review",
                    priority=max(10, 60 - min(len(candidate.claim_ids), 50)),
                    finding_codes=["relation_inferred", strategy.replace("-", "_")],
                    rationale=(
                        f"{candidate.source_id} {candidate.relation_type} {candidate.target_id} "
                        f"| evidence_count={len(candidate.claim_ids)} | extractor={extractor}"
                    ),
                    current_status="triaged",
                )
            )

    return {
        "operation": "augment_store_relations_from_claims",
        "store_dir": str(store.base_dir),
        "applied": apply,
        "extractor": extractor,
        "strategy": strategy,
        "relation_type": relation_type,
        "concept_prefixes": prefixes,
        "min_evidence": effective_min_evidence,
        "candidate_relation_count": len(relation_payloads),
        "relations": relation_payloads,
    }


def _claim_cooccurrence_candidates(
    store: GroundRecallStore,
    *,
    concepts: dict[str, Any],
    existing_keys: set[tuple[str, str, str]],
    prefixes: list[str],
    relation_type: str,
) -> OrderedDict[tuple[str, str, str], RelationCandidate]:
    candidates: OrderedDict[tuple[str, str, str], RelationCandidate] = OrderedDict()

    for claim in store.list_claims():
        if claim.current_status == "rejected":
            continue
        concept_ids = [
            concept_id
            for concept_id in claim.concept_ids
            if concept_id in concepts and _matches_prefixes(concept_id, prefixes)
        ]
        if len(concept_ids) < 2:
            continue
        for source_id, target_id in _concept_pairs(sorted(set(concept_ids))):
            key = _relation_key(source_id, target_id, relation_type)
            if key in existing_keys:
                continue
            candidate = candidates.get(key)
            if candidate is None:
                candidate = RelationCandidate(source_id=source_id, target_id=target_id, relation_type=relation_type)
                candidates[key] = candidate
            candidate.claim_ids.append(claim.claim_id)
            for evidence_id in claim.source_observation_ids or [claim.claim_id]:
                if evidence_id not in candidate.evidence_ids:
                    candidate.evidence_ids.append(evidence_id)
            origin_path = claim.provenance.origin_path
            if origin_path and origin_path not in candidate.origin_paths:
                candidate.origin_paths.append(origin_path)
    return candidates


def _source_family_candidates(
    *,
    concepts: dict[str, Any],
    existing_keys: set[tuple[str, str, str]],
    prefixes: list[str],
    relation_type: str,
) -> OrderedDict[tuple[str, str, str], RelationCandidate]:
    by_family: dict[str, list[Any]] = {}
    for concept in concepts.values():
        if not _matches_prefixes(concept.concept_id, prefixes):
            continue
        family = _source_family(concept)
        if not family:
            continue
        by_family.setdefault(family, []).append(concept)

    candidates: OrderedDict[tuple[str, str, str], RelationCandidate] = OrderedDict()
    for family, items in by_family.items():
        sorted_items = sorted(items, key=lambda item: item.concept_id)
        for source, target in _concept_pairs([item.concept_id for item in sorted_items]):
            key = _relation_key(source, target, relation_type)
            if key in existing_keys:
                continue
            source_concept = concepts[source]
            target_concept = concepts[target]
            candidates[key] = RelationCandidate(
                source_id=source,
                target_id=target,
                relation_type=relation_type,
                claim_ids=[family],
                evidence_ids=list(dict.fromkeys(source_concept.source_artifact_ids + target_concept.source_artifact_ids)),
                origin_paths=[],
            )
    return candidates


def _candidate_payload(candidate: RelationCandidate, *, extractor: str) -> dict[str, Any]:
    return {
        "relation_id": _relation_id(candidate.source_id, candidate.target_id, candidate.relation_type, extractor=extractor),
        "source_id": candidate.source_id,
        "target_id": candidate.target_id,
        "relation_type": candidate.relation_type,
        "evidence_ids": candidate.evidence_ids,
        "evidence_count": len(candidate.claim_ids),
        "claim_ids": candidate.claim_ids[:25],
        "origin_paths": candidate.origin_paths[:10],
        "support_kind": "inferred",
        "grounding_status": "partially_grounded",
        "current_status": "triaged",
    }


def _relation_key(source_id: str, target_id: str, relation_type: str) -> tuple[str, str, str]:
    left, right = sorted([source_id, target_id])
    return (left, right, relation_type)


def _relation_id(source_id: str, target_id: str, relation_type: str, *, extractor: str = EXTRACTOR_NAME) -> str:
    left, right, normalized_type = _relation_key(source_id, target_id, relation_type)
    digest = sha256(f"{left}|{right}|{normalized_type}|{extractor}".encode("utf-8")).hexdigest()[:16]
    return f"rel_store_xg_{digest}"


def _matches_prefixes(concept_id: str, prefixes: list[str]) -> bool:
    return not prefixes or any(concept_id.startswith(prefix) for prefix in prefixes)


def _concept_pairs(concept_ids: list[str]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for index, source_id in enumerate(concept_ids):
        for target_id in concept_ids[index + 1 :]:
            if source_id != target_id:
                pairs.append((source_id, target_id))
    return pairs


def _source_family(concept: Any) -> str:
    tokens = _concept_tokens(concept)
    if len(tokens) >= 4 and tokens[:3] == ["evo", "edu", "notebook"]:
        index = 3
        if index < len(tokens) and tokens[index] in {"source", "ingestion", "ingest"}:
            index += 1
        if index < len(tokens) and tokens[index] == "note":
            index += 1
        if index < len(tokens) and tokens[index] in {"note", "src"}:
            index += 1
        if index < len(tokens) and _is_family_token(tokens[index]):
            family = tokens[index]
            if family == "eldredge" and index + 1 < len(tokens) and tokens[index + 1] == "gould":
                return "eldredge-gould"
            return family
    return ""


def _concept_tokens(concept: Any) -> list[str]:
    text = f"{getattr(concept, 'concept_id', '')} {getattr(concept, 'title', '')}".replace("concept::", "")
    return [token for token in text.lower().replace("_", "-").split("-") for token in token.split() if token]


def _is_family_token(token: str) -> bool:
    return token not in {
        "and",
        "automatic",
        "autonomous",
        "current",
        "ingest",
        "ingestion",
        "math",
        "notebook",
        "source",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Augment a GroundRecall store with inferred graph relations.")
    parser.add_argument("store_dir")
    parser.add_argument("--concept-prefix", action="append", default=[])
    parser.add_argument("--strategy", choices=sorted(VALID_STRATEGIES), default="claim-cooccurrence")
    parser.add_argument("--relation-type", default=DEFAULT_RELATION_TYPE)
    parser.add_argument("--min-evidence", type=int, default=2)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--apply", action="store_true", help="Write inferred relations and review candidates to the store")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    payload = augment_store_relations_from_claims(
        args.store_dir,
        concept_prefixes=list(args.concept_prefix or []),
        relation_type=args.relation_type,
        min_evidence=args.min_evidence,
        strategy=args.strategy,
        limit=args.limit,
        apply=args.apply,
    )
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
