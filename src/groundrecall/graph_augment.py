from __future__ import annotations

import argparse
from collections import OrderedDict
from dataclasses import dataclass, field
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

from .graph_extraction import extract_heuristic_graph_relations
from .models import ProvenanceRecord, RelationRecord, ReviewCandidateRecord
from .store import GroundRecallStore


DEFAULT_RELATION_TYPE = "co_occurs_with"
EXTRACTOR_NAME = "groundrecall.store_claim_cooccurrence.v1"
SOURCE_FAMILY_EXTRACTOR_NAME = "groundrecall.store_source_family.v1"
CLAIM_MENTIONS_EXTRACTOR_NAME = "groundrecall.store_claim_mentions.v1"
OBSERVATION_COOCCURRENCE_EXTRACTOR_NAME = "groundrecall.store_observation_cooccurrence.v1"
CLAIM_LINKS_EXTRACTOR_NAME = "groundrecall.store_claim_links.v1"
CLAIM_CONTRADICTION_CUES_EXTRACTOR_NAME = "groundrecall.store_claim_contradiction_cues.v1"
CLAIM_SUPPORT_ANCHORS_EXTRACTOR_NAME = "groundrecall.store_claim_support_anchors.v1"
VALID_STRATEGIES = {
    "claim-contradiction-cues",
    "claim-cooccurrence",
    "claim-links",
    "claim-mentions",
    "claim-support-anchors",
    "observation-cooccurrence",
    "source-family",
}


@dataclass
class RelationCandidate:
    source_id: str
    target_id: str
    relation_type: str
    claim_ids: list[str] = field(default_factory=list)
    support_ids: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    origin_paths: list[str] = field(default_factory=list)


@dataclass
class AugmentStats:
    skipped_duplicate_keys: set[tuple[str, str, str]] = field(default_factory=set)
    pair_check_count: int = 0
    pair_check_limit_reached: bool = False
    pair_bucket_count: int = 0

    def record_duplicate(self, key: tuple[str, str, str]) -> None:
        self.skipped_duplicate_keys.add(key)

    def skipped_duplicate_counts(self) -> dict[str, Any]:
        by_type: dict[str, int] = {}
        for _source_id, _target_id, relation_type in self.skipped_duplicate_keys:
            by_type[relation_type] = by_type.get(relation_type, 0) + 1
        return {
            "skipped_duplicate_relation_count": len(self.skipped_duplicate_keys),
            "skipped_duplicate_relation_type_counts": dict(sorted(by_type.items())),
        }


def augment_store_relations_from_claims(
    store_dir: str | Path,
    *,
    concept_prefixes: list[str] | None = None,
    relation_type: str = DEFAULT_RELATION_TYPE,
    min_evidence: int = 2,
    strategy: str = "claim-cooccurrence",
    limit: int | None = None,
    max_pair_checks: int = 50000,
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
    stats = AugmentStats()
    prefixes = [item for item in (concept_prefixes or []) if item]
    if strategy == "claim-cooccurrence":
        candidates = _claim_cooccurrence_candidates(
            store,
            concepts=concepts,
            existing_keys=existing_keys,
            stats=stats,
            prefixes=prefixes,
            relation_type=relation_type,
        )
        extractor = EXTRACTOR_NAME
    elif strategy == "claim-links":
        candidates = _claim_link_candidates(
            store,
            existing_keys=existing_keys,
            stats=stats,
        )
        extractor = CLAIM_LINKS_EXTRACTOR_NAME
    elif strategy == "claim-contradiction-cues":
        relation_type = "claim_may_contradict_claim"
        candidates = _claim_contradiction_cue_candidates(
            store,
            concepts=concepts,
            existing_keys=existing_keys,
            stats=stats,
            prefixes=prefixes,
            relation_type=relation_type,
            max_pair_checks=max(0, int(max_pair_checks)),
        )
        extractor = CLAIM_CONTRADICTION_CUES_EXTRACTOR_NAME
    elif strategy == "claim-support-anchors":
        relation_type = "observation_supports_claim"
        candidates = _claim_support_anchor_candidates(
            store,
            existing_keys=existing_keys,
            stats=stats,
            relation_type=relation_type,
        )
        extractor = CLAIM_SUPPORT_ANCHORS_EXTRACTOR_NAME
    elif strategy == "claim-mentions":
        relation_type = "mentions_topic"
        candidates = _claim_mentions_candidates(
            store,
            concepts=concepts,
            existing_keys=existing_keys,
            stats=stats,
            prefixes=prefixes,
            relation_type=relation_type,
        )
        extractor = CLAIM_MENTIONS_EXTRACTOR_NAME
    elif strategy == "observation-cooccurrence":
        relation_type = DEFAULT_RELATION_TYPE
        candidates = _observation_cooccurrence_candidates(
            store,
            concepts=concepts,
            existing_keys=existing_keys,
            stats=stats,
            prefixes=prefixes,
            relation_type=relation_type,
        )
        extractor = OBSERVATION_COOCCURRENCE_EXTRACTOR_NAME
    else:
        relation_type = "same_source_family"
        candidates = _source_family_candidates(
            concepts=concepts,
            existing_keys=existing_keys,
            stats=stats,
            prefixes=prefixes,
            relation_type=relation_type,
        )
        extractor = SOURCE_FAMILY_EXTRACTOR_NAME

    effective_min_evidence = (
        1
        if strategy in {"claim-contradiction-cues", "claim-links", "claim-mentions", "claim-support-anchors", "source-family"}
        else max(1, int(min_evidence))
    )
    eligible = [
        candidate
        for candidate in candidates.values()
        if _evidence_count(candidate) >= effective_min_evidence
    ]
    selected = list(eligible)
    selected.sort(key=lambda item: (-_evidence_count(item), item.source_id, item.target_id))
    omitted_by_limit_count = 0
    if limit is not None:
        omitted_by_limit_count = max(0, len(selected) - max(0, int(limit)))
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
                    priority=max(10, 60 - min(_evidence_count(candidate), 50)),
                    finding_codes=["relation_inferred", strategy.replace("-", "_")],
                    rationale=(
                        f"{candidate.source_id} {candidate.relation_type} {candidate.target_id} "
                        f"| evidence_count={_evidence_count(candidate)} | extractor={extractor}"
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
        "raw_candidate_relation_count": len(candidates),
        "candidate_relation_count": len(relation_payloads),
        "relation_type_counts": _relation_type_counts(relation_payloads),
        "filter_summary": {
            "below_min_evidence_count": len(candidates) - len(eligible),
            "omitted_by_limit_count": omitted_by_limit_count,
            "pair_bucket_count": stats.pair_bucket_count,
            "pair_check_count": stats.pair_check_count,
            "pair_check_limit_reached": stats.pair_check_limit_reached,
            **stats.skipped_duplicate_counts(),
        },
        "write_summary": {
            "relation_write_count": len(relation_payloads) if apply else 0,
            "review_candidate_write_count": len(relation_payloads) if apply else 0,
            "dry_run": not apply,
        },
        "diagnostic_layers": {
            "reviewed_semantic_relations": sum(
                1
                for relation in store.list_relations()
                if relation.current_status in {"reviewed", "promoted"}
            ),
            "candidate_semantic_relations": sum(
                1
                for relation in store.list_relations()
                if relation.current_status in {"draft", "triaged"}
            ),
            "derived_projection_edges": "query_time",
        },
        "relations": relation_payloads,
    }


def _claim_cooccurrence_candidates(
    store: GroundRecallStore,
    *,
    concepts: dict[str, Any],
    existing_keys: set[tuple[str, str, str]],
    stats: AugmentStats,
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
                stats.record_duplicate(key)
                continue
            candidate = candidates.get(key)
            if candidate is None:
                candidate = RelationCandidate(source_id=source_id, target_id=target_id, relation_type=relation_type)
                candidates[key] = candidate
            candidate.claim_ids.append(claim.claim_id)
            if claim.claim_id not in candidate.support_ids:
                candidate.support_ids.append(claim.claim_id)
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
    stats: AugmentStats,
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
                stats.record_duplicate(key)
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
                support_ids=[family],
            )
    return candidates


def _claim_link_candidates(
    store: GroundRecallStore,
    *,
    existing_keys: set[tuple[str, str, str]],
    stats: AugmentStats,
) -> OrderedDict[tuple[str, str, str], RelationCandidate]:
    claims = {claim.claim_id: claim for claim in store.list_claims() if claim.current_status != "rejected"}
    candidates: OrderedDict[tuple[str, str, str], RelationCandidate] = OrderedDict()
    for claim in claims.values():
        for target_id in claim.contradicts_claim_ids:
            _append_claim_link_candidate(
                candidates,
                existing_keys=existing_keys,
                stats=stats,
                source_claim=claim,
                target_id=target_id,
                relation_type="claim_contradicts_claim",
                claims=claims,
            )
        for target_id in claim.supersedes_claim_ids:
            _append_claim_link_candidate(
                candidates,
                existing_keys=existing_keys,
                stats=stats,
                source_claim=claim,
                target_id=target_id,
                relation_type="claim_supersedes_claim",
                claims=claims,
            )
    return candidates


def _claim_contradiction_cue_candidates(
    store: GroundRecallStore,
    *,
    concepts: dict[str, Any],
    existing_keys: set[tuple[str, str, str]],
    stats: AugmentStats,
    prefixes: list[str],
    relation_type: str,
    max_pair_checks: int,
) -> OrderedDict[tuple[str, str, str], RelationCandidate]:
    claims = [claim for claim in store.list_claims() if claim.current_status != "rejected"]
    claims_by_concept: dict[str, list[Any]] = {}
    for claim in claims:
        for concept_id in claim.concept_ids:
            if concept_id in concepts and _matches_prefixes(concept_id, prefixes):
                claims_by_concept.setdefault(concept_id, []).append(claim)

    candidates: OrderedDict[tuple[str, str, str], RelationCandidate] = OrderedDict()
    seen_pairs: set[tuple[str, str]] = set()
    for concept_claims in claims_by_concept.values():
        buckets = _claim_contradiction_signature_buckets(concept_claims)
        stats.pair_bucket_count += len(buckets)
        for bucket in buckets.values():
            negated_claims = bucket["negated"]
            affirmative_claims = bucket["affirmative"]
            for left in affirmative_claims:
                for right in negated_claims:
                    if stats.pair_check_count >= max_pair_checks:
                        stats.pair_check_limit_reached = True
                        return candidates
                    stats.pair_check_count += 1
                    pair_key = tuple(sorted([left.claim_id, right.claim_id]))
                    if pair_key in seen_pairs or _explicitly_linked_claims(left, right):
                        continue
                    seen_pairs.add(pair_key)
                    if not _looks_like_negation_contradiction(left.claim_text, right.claim_text):
                        continue
                    source_id, target_id = pair_key
                    key = _relation_key(source_id, target_id, relation_type)
                    if key in existing_keys:
                        stats.record_duplicate(key)
                        continue
                    candidate = RelationCandidate(
                        source_id=source_id,
                        target_id=target_id,
                        relation_type=relation_type,
                        claim_ids=[source_id, target_id],
                        support_ids=[f"{source_id}<->{target_id}"],
                        evidence_ids=_claim_pair_evidence_ids(left, right),
                        origin_paths=_claim_pair_origin_paths(left, right),
                    )
                    candidates[key] = candidate
    return candidates


def _claim_support_anchor_candidates(
    store: GroundRecallStore,
    *,
    existing_keys: set[tuple[str, str, str]],
    stats: AugmentStats,
    relation_type: str,
) -> OrderedDict[tuple[str, str, str], RelationCandidate]:
    observations = {
        observation.observation_id: observation
        for observation in store.list_observations()
        if observation.current_status != "rejected"
    }
    candidates: OrderedDict[tuple[str, str, str], RelationCandidate] = OrderedDict()
    for claim in store.list_claims():
        if claim.current_status == "rejected":
            continue
        for observation_id in claim.source_observation_ids:
            if observation_id not in observations:
                continue
            key = _relation_key(observation_id, claim.claim_id, relation_type)
            if key in existing_keys:
                stats.record_duplicate(key)
                continue
            observation = observations[observation_id]
            candidates[key] = RelationCandidate(
                source_id=observation_id,
                target_id=claim.claim_id,
                relation_type=relation_type,
                claim_ids=[claim.claim_id],
                support_ids=[f"{observation_id}->{claim.claim_id}"],
                evidence_ids=[observation_id],
                origin_paths=_support_anchor_origin_paths(observation, claim),
            )
    return candidates


def _support_anchor_origin_paths(observation: Any, claim: Any) -> list[str]:
    values: list[str] = []
    for origin_path in (observation.provenance.origin_path, claim.provenance.origin_path):
        if origin_path and origin_path not in values:
            values.append(origin_path)
    return values


def _claim_contradiction_signature_buckets(claims: list[Any]) -> dict[tuple[str, ...], dict[str, list[Any]]]:
    buckets: dict[tuple[str, ...], dict[str, list[Any]]] = {}
    for claim in sorted(claims, key=lambda item: item.claim_id):
        signature = tuple(sorted(_claim_signature_tokens(claim.claim_text)))
        if len(signature) < 4:
            continue
        bucket = buckets.setdefault(signature, {"affirmative": [], "negated": []})
        if _has_negation_cue(claim.claim_text):
            bucket["negated"].append(claim)
        else:
            bucket["affirmative"].append(claim)
    return {
        signature: bucket
        for signature, bucket in buckets.items()
        if bucket["affirmative"] and bucket["negated"]
    }


def _explicitly_linked_claims(left: Any, right: Any) -> bool:
    left_links = set(left.contradicts_claim_ids) | set(left.supersedes_claim_ids)
    right_links = set(right.contradicts_claim_ids) | set(right.supersedes_claim_ids)
    return right.claim_id in left_links or left.claim_id in right_links


def _claim_pair_evidence_ids(left: Any, right: Any) -> list[str]:
    values: list[str] = []
    for claim in (left, right):
        for evidence_id in claim.source_observation_ids or [claim.claim_id]:
            if evidence_id not in values:
                values.append(evidence_id)
    return values


def _claim_pair_origin_paths(left: Any, right: Any) -> list[str]:
    values: list[str] = []
    for claim in (left, right):
        origin_path = claim.provenance.origin_path
        if origin_path and origin_path not in values:
            values.append(origin_path)
    return values


def _append_claim_link_candidate(
    candidates: OrderedDict[tuple[str, str, str], RelationCandidate],
    *,
    existing_keys: set[tuple[str, str, str]],
    stats: AugmentStats,
    source_claim: Any,
    target_id: str,
    relation_type: str,
    claims: dict[str, Any],
) -> None:
    if target_id not in claims or target_id == source_claim.claim_id:
        return
    key = _relation_key(source_claim.claim_id, target_id, relation_type)
    if key in existing_keys:
        stats.record_duplicate(key)
        return
    candidate = candidates.get(key)
    if candidate is None:
        candidate = RelationCandidate(
            source_id=source_claim.claim_id,
            target_id=target_id,
            relation_type=relation_type,
        )
        candidates[key] = candidate
    if source_claim.claim_id not in candidate.claim_ids:
        candidate.claim_ids.append(source_claim.claim_id)
    if target_id not in candidate.claim_ids:
        candidate.claim_ids.append(target_id)
    support_key = f"{source_claim.claim_id}->{target_id}"
    if support_key not in candidate.support_ids:
        candidate.support_ids.append(support_key)
    for evidence_id in source_claim.source_observation_ids or [source_claim.claim_id]:
        if evidence_id not in candidate.evidence_ids:
            candidate.evidence_ids.append(evidence_id)
    origin_path = source_claim.provenance.origin_path
    if origin_path and origin_path not in candidate.origin_paths:
        candidate.origin_paths.append(origin_path)


def _claim_mentions_candidates(
    store: GroundRecallStore,
    *,
    concepts: dict[str, Any],
    existing_keys: set[tuple[str, str, str]],
    stats: AugmentStats,
    prefixes: list[str],
    relation_type: str,
) -> OrderedDict[tuple[str, str, str], RelationCandidate]:
    eligible_concepts = {
        concept_id: concept
        for concept_id, concept in concepts.items()
        if _matches_prefixes(concept_id, prefixes) and not _is_operational_concept(concept)
    }
    topic_patterns = {
        concept_id: pattern
        for concept_id, concept in eligible_concepts.items()
        if (pattern := _topic_pattern(_topic_tokens(concept)))
    }
    candidates: OrderedDict[tuple[str, str, str], RelationCandidate] = OrderedDict()
    for claim in store.list_claims():
        if claim.current_status == "rejected":
            continue
        source_ids = [
            concept_id
            for concept_id in claim.concept_ids
            if concept_id in eligible_concepts
        ]
        if not source_ids:
            continue
        text = claim.claim_text
        for target_id, pattern in topic_patterns.items():
            if target_id in source_ids or not pattern.search(text):
                continue
            for source_id in source_ids:
                inferred_type = _claim_mention_relation_type(source_id, target_id, text, eligible_concepts)
                key = _relation_key(source_id, target_id, inferred_type)
                if key in existing_keys:
                    stats.record_duplicate(key)
                    continue
                candidate = candidates.get(key)
                if candidate is None:
                    candidate = RelationCandidate(source_id=source_id, target_id=target_id, relation_type=inferred_type)
                    candidates[key] = candidate
                candidate.claim_ids.append(claim.claim_id)
                if claim.claim_id not in candidate.support_ids:
                    candidate.support_ids.append(claim.claim_id)
                for evidence_id in claim.source_observation_ids or [claim.claim_id]:
                    if evidence_id not in candidate.evidence_ids:
                        candidate.evidence_ids.append(evidence_id)
                origin_path = claim.provenance.origin_path
                if origin_path and origin_path not in candidate.origin_paths:
                    candidate.origin_paths.append(origin_path)
    return candidates


def _observation_cooccurrence_candidates(
    store: GroundRecallStore,
    *,
    concepts: dict[str, Any],
    existing_keys: set[tuple[str, str, str]],
    stats: AugmentStats,
    prefixes: list[str],
    relation_type: str,
) -> OrderedDict[tuple[str, str, str], RelationCandidate]:
    concept_rows = [
        concept.model_dump()
        for concept in concepts.values()
        if _matches_prefixes(concept.concept_id, prefixes)
        and not _is_operational_concept(concept)
        and not _is_generic_backfill_concept(concept)
    ]
    observation_rows = [
        {
            **observation.model_dump(),
            "origin_path": observation.provenance.origin_path,
            "origin_section": observation.provenance.origin_section,
        }
        for observation in store.list_observations()
        if observation.current_status != "rejected"
    ]
    relation_rows, _summary = extract_heuristic_graph_relations(
        concept_rows,
        observation_rows,
        import_id="store-backfill",
    )
    candidates: OrderedDict[tuple[str, str, str], RelationCandidate] = OrderedDict()
    for row in relation_rows:
        source_id = str(row.get("source_id", ""))
        target_id = str(row.get("target_id", ""))
        if source_id not in concepts or target_id not in concepts:
            continue
        key = _relation_key(source_id, target_id, relation_type)
        if key in existing_keys:
            stats.record_duplicate(key)
            continue
        evidence_ids = [str(value) for value in row.get("evidence_ids", []) if str(value)]
        candidates[key] = RelationCandidate(
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
            support_ids=evidence_ids,
            evidence_ids=evidence_ids,
            origin_paths=[str(row.get("origin_path", ""))] if row.get("origin_path") else [],
        )
    return candidates


def _candidate_payload(candidate: RelationCandidate, *, extractor: str) -> dict[str, Any]:
    return {
        "relation_id": _relation_id(candidate.source_id, candidate.target_id, candidate.relation_type, extractor=extractor),
        "source_id": candidate.source_id,
        "target_id": candidate.target_id,
        "relation_type": candidate.relation_type,
        "evidence_ids": candidate.evidence_ids,
        "evidence_count": _evidence_count(candidate),
        "claim_ids": candidate.claim_ids[:25],
        "support_ids": candidate.support_ids[:25],
        "origin_paths": candidate.origin_paths[:10],
        "support_kind": "inferred",
        "grounding_status": "partially_grounded",
        "current_status": "triaged",
    }


def _evidence_count(candidate: RelationCandidate) -> int:
    return len(candidate.support_ids or candidate.claim_ids or candidate.evidence_ids)


def _relation_type_counts(relation_payloads: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in relation_payloads:
        relation_type = str(item.get("relation_type", ""))
        if relation_type:
            counts[relation_type] = counts.get(relation_type, 0) + 1
    return dict(sorted(counts.items()))


_NEGATION_PATTERNS = [
    re.compile(r"\bdoes\s+not\b", re.IGNORECASE),
    re.compile(r"\bdo\s+not\b", re.IGNORECASE),
    re.compile(r"\bdid\s+not\b", re.IGNORECASE),
    re.compile(r"\bis\s+not\b", re.IGNORECASE),
    re.compile(r"\bare\s+not\b", re.IGNORECASE),
    re.compile(r"\bwas\s+not\b", re.IGNORECASE),
    re.compile(r"\bwere\s+not\b", re.IGNORECASE),
    re.compile(r"\bcannot\b", re.IGNORECASE),
    re.compile(r"\bcan\s+not\b", re.IGNORECASE),
    re.compile(r"\bwill\s+not\b", re.IGNORECASE),
    re.compile(r"\bno\b", re.IGNORECASE),
    re.compile(r"\bnot\b", re.IGNORECASE),
]

_NEGATION_REMOVAL_PATTERN = re.compile(
    r"\b(does|do|did|is|are|was|were|can|will)\s+not\b|\bcannot\b|\bno\b|\bnot\b",
    re.IGNORECASE,
)


def _looks_like_negation_contradiction(left_text: str, right_text: str) -> bool:
    left_negated = _has_negation_cue(left_text)
    right_negated = _has_negation_cue(right_text)
    if left_negated == right_negated:
        return False
    left_tokens = _claim_signature_tokens(left_text)
    right_tokens = _claim_signature_tokens(right_text)
    if len(left_tokens | right_tokens) < 4:
        return False
    overlap = len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
    return overlap >= 0.72


def _has_negation_cue(text: str) -> bool:
    return any(pattern.search(text) for pattern in _NEGATION_PATTERNS)


def _claim_signature_tokens(text: str) -> set[str]:
    stripped = _NEGATION_REMOVAL_PATTERN.sub(" ", text.lower())
    stop_words = {
        "a",
        "an",
        "and",
        "are",
        "as",
        "be",
        "by",
        "can",
        "does",
        "do",
        "did",
        "for",
        "from",
        "in",
        "is",
        "it",
        "may",
        "of",
        "or",
        "that",
        "the",
        "to",
        "was",
        "were",
        "will",
        "with",
    }
    return {
        normalized
        for token in re.findall(r"[a-z0-9][a-z0-9-]*", stripped)
        for normalized in [_normalize_claim_token(token)]
        if len(normalized) > 2 and normalized not in stop_words
    }


def _normalize_claim_token(token: str) -> str:
    if len(token) > 5 and token.endswith("ies"):
        return f"{token[:-3]}y"
    if len(token) > 5 and token.endswith("es"):
        return token[:-1]
    if len(token) > 4 and token.endswith("s"):
        return token[:-1]
    return token


def _relation_key(source_id: str, target_id: str, relation_type: str) -> tuple[str, str, str]:
    if relation_type in {
        "claim_contradicts_claim",
        "claim_may_contradict_claim",
        "claim_supersedes_claim",
        "observation_supports_claim",
        "provides_evidence_for",
        "distinguishes",
        "qualifies",
    }:
        return (source_id, target_id, relation_type)
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


def _topic_tokens(concept: Any) -> list[str]:
    tokens = _concept_tokens(concept)
    stop_tokens = {
        "and",
        "edu",
        "evo",
        "ingest",
        "ingestion",
        "notebook",
        "note",
        "source",
    }
    family = _source_family(concept)
    cleaned = [token for token in tokens if token not in stop_tokens and token != family and not token.isdigit()]
    while cleaned and re.fullmatch(r"20\d{2}", cleaned[-1]):
        cleaned.pop()
    while cleaned and cleaned[-1] in {"guardrail", "model"} and len(cleaned) > 2:
        # Keep model when it is part of a two-token concept such as fossil model.
        cleaned.pop()
    return list(dict.fromkeys(cleaned))


def _is_operational_concept(concept: Any) -> bool:
    tokens = set(_concept_tokens(concept))
    if "checkpoint" in tokens or "queue" in tokens:
        return True
    if {"current", "processing", "state"} <= tokens:
        return True
    if {"source", "ingest", "batch"} <= tokens or {"source", "ingestion", "batch"} <= tokens:
        return True
    if {"ingestion", "batch"} <= tokens:
        return True
    if "ingestion" in tokens and ("automatic" in tokens or "autonomous" in tokens):
        return True
    if {"math", "aware", "review", "applied"} <= tokens:
        return True
    return False


def _is_generic_backfill_concept(concept: Any) -> bool:
    tokens = set(_concept_tokens(concept))
    generic_tokens = {
        "background",
        "command",
        "commands",
        "deployment",
        "file",
        "files",
        "goal",
        "netuser",
        "note",
        "notes",
        "performed",
        "project",
        "repo",
        "repository",
        "result",
        "results",
        "run",
        "source",
        "task",
        "todo",
        "validation",
        "verification",
    }
    return bool(tokens) and tokens <= generic_tokens


def _topic_pattern(tokens: list[str]) -> re.Pattern[str] | None:
    meaningful = [token for token in tokens if len(token) > 2]
    if not meaningful:
        return None
    if len(meaningful) == 1 and len(meaningful[0]) < 7:
        return None
    phrase = r"[\s_-]+".join(re.escape(token) for token in meaningful[:5])
    return re.compile(rf"(?<![A-Za-z0-9]){phrase}(?![A-Za-z0-9])", re.IGNORECASE)


def _claim_mention_relation_type(source_id: str, target_id: str, text: str, concepts: dict[str, Any]) -> str:
    source_topic = set(_topic_tokens(concepts[source_id]))
    target_topic = set(_topic_tokens(concepts[target_id]))
    lowered = text.lower()
    if {"evidence", "common", "descent"} <= target_topic or "common-descent evidence" in lowered:
        return "provides_evidence_for"
    if "distinguish" in lowered or "distinction" in lowered:
        return "distinguishes"
    if "guardrail" in source_id or "guardrail" in target_id:
        return "qualifies"
    if source_topic & target_topic:
        return "related_topic"
    return "mentions_topic"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Augment a GroundRecall store with inferred graph relations.")
    parser.add_argument("store_dir")
    parser.add_argument("--concept-prefix", action="append", default=[])
    parser.add_argument("--strategy", choices=sorted(VALID_STRATEGIES), default="claim-cooccurrence")
    parser.add_argument("--relation-type", default=DEFAULT_RELATION_TYPE)
    parser.add_argument("--min-evidence", type=int, default=2)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--max-pair-checks", type=int, default=50000, help="Maximum claim-pair checks for semantic pair-scanning strategies.")
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
        max_pair_checks=args.max_pair_checks,
        apply=args.apply,
    )
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
