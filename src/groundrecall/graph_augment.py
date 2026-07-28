from __future__ import annotations

import argparse
from collections import OrderedDict
from dataclasses import dataclass, field
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

from .export_guardrails import is_sensitive_record
from .graph_extraction import extract_heuristic_graph_relations
from .models import ProvenanceRecord, RelationRecord, ReviewCandidateRecord
from .policy import PolicyDecision, PolicyRequest, load_policy_plugins
from .store import GroundRecallStore


DEFAULT_RELATION_TYPE = "co_occurs_with"
EXTRACTOR_NAME = "groundrecall.store_claim_cooccurrence.v1"
SOURCE_FAMILY_EXTRACTOR_NAME = "groundrecall.store_source_family.v1"
CLAIM_MENTIONS_EXTRACTOR_NAME = "groundrecall.store_claim_mentions.v1"
OBSERVATION_COOCCURRENCE_EXTRACTOR_NAME = "groundrecall.store_observation_cooccurrence.v1"
CLAIM_LINKS_EXTRACTOR_NAME = "groundrecall.store_claim_links.v1"
CLAIM_CONTRADICTION_CUES_EXTRACTOR_NAME = "groundrecall.store_claim_contradiction_cues.v1"
CLAIM_SUPPORT_ANCHORS_EXTRACTOR_NAME = "groundrecall.store_claim_support_anchors.v1"
OBSERVATION_ARTIFACT_ANCHORS_EXTRACTOR_NAME = "groundrecall.store_observation_artifact_anchors.v1"
SOURCE_ANCHORS_EXTRACTOR_NAME = "groundrecall.store_source_anchors.v1"
CLAIM_SEMANTIC_CUES_EXTRACTOR_NAME = "groundrecall.store_claim_semantic_cues.v1"
VALID_STRATEGIES = {
    "claim-contradiction-cues",
    "claim-cooccurrence",
    "claim-links",
    "claim-mentions",
    "claim-semantic-cues",
    "claim-support-anchors",
    "observation-artifact-anchors",
    "observation-cooccurrence",
    "source-anchors",
    "source-family",
}
VALID_EXTRACTOR_MODES = {"heuristic", "none"}


class GraphAugmentPolicyError(RuntimeError):
    """Raised when a policy plugin blocks graph candidate writes."""

    def __init__(self, message: str, *, payload: dict[str, Any]) -> None:
        super().__init__(message)
        self.payload = payload


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
    extractor_mode: str = "heuristic",
    limit: int | None = None,
    max_pair_checks: int = 50000,
    apply: bool = False,
    policy_plugins_path: str | Path | None = None,
    policy_subject_id: str = "",
) -> dict[str, Any]:
    if strategy not in VALID_STRATEGIES:
        raise ValueError(f"Unknown graph augmentation strategy: {strategy}")
    if extractor_mode not in VALID_EXTRACTOR_MODES:
        raise ValueError(f"Unknown graph augmentation extractor mode: {extractor_mode}")
    store = GroundRecallStore(store_dir)
    concepts = {item.concept_id: item for item in store.list_concepts() if _is_graph_backfill_eligible(item, "concept", item.concept_id)}
    existing_keys = {
        _relation_key(item.source_id, item.target_id, item.relation_type)
        for item in store.list_relations()
    }
    stats = AugmentStats()
    prefixes = [item for item in (concept_prefixes or []) if item]
    if extractor_mode == "none":
        candidates: OrderedDict[tuple[str, str, str], RelationCandidate] = OrderedDict()
        extractor = "none"
    elif strategy == "claim-cooccurrence":
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
    elif strategy == "observation-artifact-anchors":
        relation_type = "artifact_contains_observation"
        candidates = _observation_artifact_anchor_candidates(
            store,
            existing_keys=existing_keys,
            stats=stats,
            relation_type=relation_type,
        )
        extractor = OBSERVATION_ARTIFACT_ANCHORS_EXTRACTOR_NAME
    elif strategy == "source-anchors":
        candidates = _source_anchor_candidates(
            store,
            existing_keys=existing_keys,
            stats=stats,
        )
        extractor = SOURCE_ANCHORS_EXTRACTOR_NAME
    elif strategy == "claim-semantic-cues":
        candidates = _claim_semantic_cue_candidates(
            store,
            concepts=concepts,
            existing_keys=existing_keys,
            stats=stats,
            prefixes=prefixes,
        )
        extractor = CLAIM_SEMANTIC_CUES_EXTRACTOR_NAME
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
        if strategy
        in {
            "claim-contradiction-cues",
            "claim-links",
            "claim-mentions",
            "claim-semantic-cues",
            "claim-support-anchors",
            "observation-artifact-anchors",
            "source-anchors",
            "source-family",
        }
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
    policy_decision = _evaluate_graph_augment_policy(
        policy_plugins_path,
        subject_id=policy_subject_id,
        apply=apply,
        strategy=strategy,
        extractor=extractor,
        relation_type=relation_type,
        candidate_count=len(relation_payloads),
    )
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
        "extractor_mode": extractor_mode,
        "strategy": strategy,
        "relation_type": relation_type,
        "concept_prefixes": prefixes,
        "min_evidence": effective_min_evidence,
        "raw_candidate_relation_count": len(candidates),
        "candidate_relation_count": len(relation_payloads),
        "relation_type_counts": _relation_type_counts(relation_payloads),
        "relation_examples": _relation_examples(relation_payloads),
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
            **({"policy_plugin_decision": policy_decision.model_dump(mode="json")} if policy_decision is not None else {}),
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


def _evaluate_graph_augment_policy(
    policy_plugins_path: str | Path | None,
    *,
    subject_id: str,
    apply: bool,
    strategy: str,
    extractor: str,
    relation_type: str,
    candidate_count: int,
) -> PolicyDecision | None:
    if policy_plugins_path is None or not apply:
        return None
    provider = load_policy_plugins(policy_plugins_path)
    request = PolicyRequest(
        decision_point="propose",
        subject_id=subject_id,
        action="graph_augment_write_candidates",
        record_kind="relation",
        durable_memory_change=True,
        metadata={
            "strategy": strategy,
            "extractor": extractor,
            "relation_type": relation_type,
            "candidate_count": candidate_count,
        },
    )
    decision = provider.evaluate(request)
    if decision.decision in {"deny", "hard_gate"}:
        raise GraphAugmentPolicyError(
            "Policy plugin blocked graph augmentation candidate writes.",
            payload={
                "operation": "augment_store_relations_from_claims",
                "blocked_by_policy": True,
                "policy_plugin_decision": decision.model_dump(mode="json"),
            },
        )
    return decision


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
        if not _is_graph_backfill_eligible(claim, "claim", claim.claim_id):
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
    claims = {
        claim.claim_id: claim
        for claim in store.list_claims()
        if _is_graph_backfill_eligible(claim, "claim", claim.claim_id)
    }
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
    claims = [
        claim
        for claim in store.list_claims()
        if _is_graph_backfill_eligible(claim, "claim", claim.claim_id)
    ]
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
        if _is_graph_backfill_eligible(observation, "observation", observation.observation_id)
    }
    candidates: OrderedDict[tuple[str, str, str], RelationCandidate] = OrderedDict()
    for claim in store.list_claims():
        if not _is_graph_backfill_eligible(claim, "claim", claim.claim_id):
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


def _observation_artifact_anchor_candidates(
    store: GroundRecallStore,
    *,
    existing_keys: set[tuple[str, str, str]],
    stats: AugmentStats,
    relation_type: str,
) -> OrderedDict[tuple[str, str, str], RelationCandidate]:
    artifacts = {
        artifact.artifact_id: artifact
        for artifact in store.list_artifacts()
        if _is_graph_backfill_eligible(artifact, "artifact", artifact.artifact_id)
    }
    candidates: OrderedDict[tuple[str, str, str], RelationCandidate] = OrderedDict()
    for observation in store.list_observations():
        if (
            not _is_graph_backfill_eligible(observation, "observation", observation.observation_id)
            or not observation.artifact_id
            or observation.artifact_id not in artifacts
        ):
            continue
        key = _relation_key(observation.artifact_id, observation.observation_id, relation_type)
        if key in existing_keys:
            stats.record_duplicate(key)
            continue
        artifact = artifacts[observation.artifact_id]
        candidates[key] = RelationCandidate(
            source_id=observation.artifact_id,
            target_id=observation.observation_id,
            relation_type=relation_type,
            support_ids=[f"{observation.artifact_id}->{observation.observation_id}"],
            evidence_ids=[observation.observation_id],
            origin_paths=_observation_artifact_origin_paths(observation, artifact),
        )
    return candidates


def _source_anchor_candidates(
    store: GroundRecallStore,
    *,
    existing_keys: set[tuple[str, str, str]],
    stats: AugmentStats,
) -> OrderedDict[tuple[str, str, str], RelationCandidate]:
    sources = {
        source.source_id: source
        for source in store.list_sources()
        if _is_graph_backfill_eligible(source, "source", source.source_id)
    }
    fragments = {
        fragment.fragment_id: fragment
        for fragment in store.list_fragments()
        if _is_graph_backfill_eligible(fragment, "fragment", fragment.fragment_id) and fragment.source_id in sources
    }
    candidates: OrderedDict[tuple[str, str, str], RelationCandidate] = OrderedDict()

    for fragment in fragments.values():
        _set_source_anchor_candidate(
            candidates,
            existing_keys=existing_keys,
            stats=stats,
            source_id=fragment.source_id,
            target_id=fragment.fragment_id,
            relation_type="source_contains_fragment",
            support_ids=[f"{fragment.source_id}->{fragment.fragment_id}"],
            evidence_ids=[fragment.fragment_id],
            origin_paths=_source_fragment_origin_paths(sources[fragment.source_id], fragment),
        )

    for claim in store.list_claims():
        if not _is_graph_backfill_eligible(claim, "claim", claim.claim_id):
            continue
        for fragment_id in claim.supporting_fragment_ids:
            if fragment_id not in fragments:
                continue
            _set_source_anchor_candidate(
                candidates,
                existing_keys=existing_keys,
                stats=stats,
                source_id=fragment_id,
                target_id=claim.claim_id,
                relation_type="fragment_supports_claim",
                claim_ids=[claim.claim_id],
                support_ids=[f"{fragment_id}->{claim.claim_id}"],
                evidence_ids=[fragment_id],
                origin_paths=_claim_fragment_origin_paths(claim, fragments[fragment_id], sources[fragments[fragment_id].source_id]),
            )
    return candidates


def _claim_semantic_cue_candidates(
    store: GroundRecallStore,
    *,
    concepts: dict[str, Any],
    existing_keys: set[tuple[str, str, str]],
    stats: AugmentStats,
    prefixes: list[str],
) -> OrderedDict[tuple[str, str, str], RelationCandidate]:
    candidates: OrderedDict[tuple[str, str, str], RelationCandidate] = OrderedDict()
    for claim in store.list_claims():
        if not _is_graph_backfill_eligible(claim, "claim", claim.claim_id):
            continue
        concept_ids = [
            concept_id
            for concept_id in claim.concept_ids
            if concept_id in concepts and _matches_prefixes(concept_id, prefixes)
        ]
        if not concept_ids:
            continue
        claim_kind = str(claim.claim_kind or "").strip().lower()
        text = str(claim.claim_text or "")
        lowered = text.lower()
        evidence_ids = list(claim.source_observation_ids or [claim.claim_id])
        origin_paths = [claim.provenance.origin_path] if claim.provenance.origin_path else []

        if claim_kind == "definition" or _has_definition_cue(lowered):
            for concept_id in sorted(set(concept_ids)):
                _set_source_anchor_candidate(
                    candidates,
                    existing_keys=existing_keys,
                    stats=stats,
                    source_id=claim.claim_id,
                    target_id=concept_id,
                    relation_type="claim_defines_concept",
                    claim_ids=[claim.claim_id],
                    support_ids=[claim.claim_id],
                    evidence_ids=evidence_ids,
                    origin_paths=origin_paths,
                )

        if claim_kind in {"qualification", "constraint"} or _has_qualification_cue(lowered):
            relation_type = "claim_constrains_concept" if claim_kind == "constraint" or _has_constraint_cue(lowered) else "claim_qualifies_concept"
            for concept_id in sorted(set(concept_ids)):
                _set_source_anchor_candidate(
                    candidates,
                    existing_keys=existing_keys,
                    stats=stats,
                    source_id=claim.claim_id,
                    target_id=concept_id,
                    relation_type=relation_type,
                    claim_ids=[claim.claim_id],
                    support_ids=[claim.claim_id],
                    evidence_ids=evidence_ids,
                    origin_paths=origin_paths,
                )

        if len(set(concept_ids)) >= 2 and (claim_kind == "distinction" or _has_distinction_cue(lowered)):
            for source_id, target_id in _concept_pairs(sorted(set(concept_ids))):
                _set_source_anchor_candidate(
                    candidates,
                    existing_keys=existing_keys,
                    stats=stats,
                    source_id=source_id,
                    target_id=target_id,
                    relation_type="distinguishes",
                    claim_ids=[claim.claim_id],
                    support_ids=[claim.claim_id],
                    evidence_ids=evidence_ids,
                    origin_paths=origin_paths,
                )

        if _has_dependency_cue(lowered):
            for concept_id in sorted(set(concept_ids)):
                _set_source_anchor_candidate(
                    candidates,
                    existing_keys=existing_keys,
                    stats=stats,
                    source_id=claim.claim_id,
                    target_id=concept_id,
                    relation_type="claim_depends_on_concept",
                    claim_ids=[claim.claim_id],
                    support_ids=[claim.claim_id],
                    evidence_ids=evidence_ids,
                    origin_paths=origin_paths,
                )

        temporal_keys = _claim_temporal_scope_keys(claim)
        if temporal_keys:
            for concept_id in sorted(set(concept_ids)):
                _set_source_anchor_candidate(
                    candidates,
                    existing_keys=existing_keys,
                    stats=stats,
                    source_id=claim.claim_id,
                    target_id=concept_id,
                    relation_type="claim_has_temporal_scope",
                    claim_ids=[claim.claim_id],
                    support_ids=[f"{claim.claim_id}:{key}" for key in temporal_keys],
                    evidence_ids=evidence_ids,
                    origin_paths=origin_paths,
                )
    return candidates


def _set_source_anchor_candidate(
    candidates: OrderedDict[tuple[str, str, str], RelationCandidate],
    *,
    existing_keys: set[tuple[str, str, str]],
    stats: AugmentStats,
    source_id: str,
    target_id: str,
    relation_type: str,
    claim_ids: list[str] | None = None,
    support_ids: list[str] | None = None,
    evidence_ids: list[str] | None = None,
    origin_paths: list[str] | None = None,
) -> None:
    key = _relation_key(source_id, target_id, relation_type)
    if key in existing_keys:
        stats.record_duplicate(key)
        return
    candidates[key] = RelationCandidate(
        source_id=source_id,
        target_id=target_id,
        relation_type=relation_type,
        claim_ids=list(claim_ids or []),
        support_ids=list(support_ids or []),
        evidence_ids=list(evidence_ids or []),
        origin_paths=list(origin_paths or []),
    )


def _source_fragment_origin_paths(source: Any, fragment: Any) -> list[str]:
    values: list[str] = []
    for origin_path in (getattr(source, "path", ""), getattr(source, "url", ""), getattr(fragment, "source_id", "")):
        if origin_path and origin_path not in values:
            values.append(origin_path)
    return values


def _claim_fragment_origin_paths(claim: Any, fragment: Any, source: Any) -> list[str]:
    values: list[str] = []
    for origin_path in (claim.provenance.origin_path, getattr(source, "path", ""), getattr(source, "url", ""), getattr(fragment, "source_id", "")):
        if origin_path and origin_path not in values:
            values.append(origin_path)
    return values


def _observation_artifact_origin_paths(observation: Any, artifact: Any) -> list[str]:
    values: list[str] = []
    for origin_path in (observation.provenance.origin_path, artifact.path):
        if origin_path and origin_path not in values:
            values.append(origin_path)
    return values


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
        if not _is_graph_backfill_eligible(claim, "claim", claim.claim_id):
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
        if _is_graph_backfill_eligible(observation, "observation", observation.observation_id)
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


def _is_graph_backfill_eligible(record: Any, record_kind: str, record_id: str) -> bool:
    if str(getattr(record, "current_status", "") or "") == "rejected":
        return False
    sensitive, _finding = is_sensitive_record(record, record_kind, record_id)
    return not sensitive


def _evidence_count(candidate: RelationCandidate) -> int:
    return len(candidate.support_ids or candidate.claim_ids or candidate.evidence_ids)


def _relation_type_counts(relation_payloads: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in relation_payloads:
        relation_type = str(item.get("relation_type", ""))
        if relation_type:
            counts[relation_type] = counts.get(relation_type, 0) + 1
    return dict(sorted(counts.items()))


def _relation_examples(relation_payloads: list[dict[str, Any]], *, limit: int = 5) -> list[dict[str, Any]]:
    examples = []
    for item in relation_payloads[: max(0, int(limit))]:
        evidence_count = int(item.get("evidence_count", 0) or 0)
        examples.append(
            {
                "relation_id": str(item.get("relation_id", "")),
                "source_id": str(item.get("source_id", "")),
                "target_id": str(item.get("target_id", "")),
                "relation_type": str(item.get("relation_type", "")),
                "evidence_count": evidence_count,
                "evidence_ids": list(item.get("evidence_ids", []) or [])[:5],
                "review_rationale": (
                    f"{item.get('source_id', '')} {item.get('relation_type', '')} {item.get('target_id', '')} "
                    f"| evidence_count={evidence_count} | support_kind={item.get('support_kind', '')} "
                    f"| grounding_status={item.get('grounding_status', '')}"
                ),
            }
        )
    return examples


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
        "claim_constrains_concept",
        "claim_defines_concept",
        "claim_depends_on_concept",
        "claim_has_temporal_scope",
        "claim_qualifies_concept",
        "claim_supersedes_claim",
        "artifact_contains_observation",
        "fragment_supports_claim",
        "observation_supports_claim",
        "provides_evidence_for",
        "source_contains_fragment",
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


def _has_definition_cue(lowered: str) -> bool:
    return bool(
        re.search(r"\b(means|refers to|is defined as|are defined as|defined as)\b", lowered)
        or re.search(r"^[a-z0-9][a-z0-9\s_-]{2,80}\s+(is|are)\s+(a|an|the)\b", lowered)
    )


def _has_qualification_cue(lowered: str) -> bool:
    return bool(
        re.search(
            r"\b(however|although|except|unless|only if|in some cases|under some conditions|may not|does not always|not all|not every|typically|generally|often|sometimes|in general|in most cases|under these conditions|under those conditions|can occur without|may occur without)\b",
            lowered,
        )
    )


def _has_constraint_cue(lowered: str) -> bool:
    return bool(
        re.search(
            r"\b(must|requires|required|cannot|limited to|constraint|scope|only when|provided that|without|fails to|will not|does not lead to|does not cause|not sufficient|insufficient)\b",
            lowered,
        )
        or (" if " in lowered and " then " in lowered)
    )


def _has_distinction_cue(lowered: str) -> bool:
    return bool(
        re.search(
            r"\b(compare|does not imply|can occur without|may occur without|versus|vs\.|vs|rather than|differs? from|different from|distinguish(?:ed)? from|not\b.+\bbut)\b",
            lowered,
        )
    )


def _has_dependency_cue(lowered: str) -> bool:
    return bool(
        re.search(
            r"\b(depends on|dependent on|prerequisite|precondition|contingent on)\b",
            lowered,
        )
    )


def _claim_temporal_scope_keys(claim: Any) -> list[str]:
    keys = (
        "available_at",
        "validated_at",
        "valid_at",
        "valid_until",
        "expires_at",
        "superseded_at",
        "retracted_at",
        "challenged_at",
    )
    metadata = claim.metadata if isinstance(getattr(claim, "metadata", None), dict) else {}
    values = [key for key in keys if metadata.get(key) not in {"", None}]
    if getattr(claim, "last_confirmed_at", ""):
        values.append("last_confirmed_at")
    return list(dict.fromkeys(values))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Augment a GroundRecall store with inferred graph relations.")
    parser.add_argument("store_dir")
    parser.add_argument("--concept-prefix", action="append", default=[])
    parser.add_argument("--strategy", choices=sorted(VALID_STRATEGIES), default="claim-cooccurrence")
    parser.add_argument("--extractor-mode", choices=sorted(VALID_EXTRACTOR_MODES), default="heuristic")
    parser.add_argument("--relation-type", default=DEFAULT_RELATION_TYPE)
    parser.add_argument("--min-evidence", type=int, default=2)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--max-pair-checks", type=int, default=50000, help="Maximum claim-pair checks for semantic pair-scanning strategies.")
    parser.add_argument("--apply", action="store_true", help="Write inferred relations and review candidates to the store")
    parser.add_argument("--policy-plugins", default=None, help="Optional GroundRecall policy plugin YAML config for graph candidate write gating.")
    parser.add_argument("--policy-subject-id", default="", help="Subject/principal id to evaluate against policy plugins.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    payload = augment_store_relations_from_claims(
        args.store_dir,
        concept_prefixes=list(args.concept_prefix or []),
        relation_type=args.relation_type,
        min_evidence=args.min_evidence,
        strategy=args.strategy,
        extractor_mode=args.extractor_mode,
        limit=args.limit,
        max_pair_checks=args.max_pair_checks,
        apply=args.apply,
        policy_plugins_path=args.policy_plugins,
        policy_subject_id=args.policy_subject_id,
    )
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
