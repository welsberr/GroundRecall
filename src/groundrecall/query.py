from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any

from epistemap import (
    epistemic_summary,
    fair_play_diagnostic,
    first_contradiction_time,
    stale_claims_after,
    tenability_window,
    timeline_events,
)

from .epistemap_adapter import graph_bundle_from_query_payload
from .graph_diagnostics import PROVENANCE_RELATION_TYPES, build_graph_diagnostics
from .search_index import search_index
from .store import GroundRecallStore


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def _matches(query: str, *values: str) -> bool:
    needle = _normalize(query)
    return any(needle in _normalize(value) for value in values if value)


def _resolve_concept(concepts: list[Any], concept_ref: str) -> Any | None:
    return next(
        (
            item
            for item in concepts
            if concept_ref == item.concept_id
            or concept_ref == item.concept_id.replace("concept::", "", 1)
            or _matches(concept_ref, item.title, item.description, *item.aliases)
        ),
        None,
    )


_SOURCE_ROLE_ORDER = ["overview", "mechanism", "nuance", "controversy", "argumentation"]
_SOURCE_SIGNAL_KEYS = (
    "source_quality",
    "source_reliability",
    "trust_status",
    "source_stance",
    "stance",
    "adversarial_intent",
    "adversarial",
    "denialist",
)
_TEMPORAL_SIGNAL_KEYS = (
    "available_at",
    "validated_at",
    "published_at",
    "observed_at",
    "introduced_at",
    "created_at",
    "challenged_at",
    "superseded_at",
    "rejected_at",
    "timestep",
)


def _infer_source_role(artifact) -> str:
    metadata = artifact.metadata if isinstance(getattr(artifact, "metadata", None), dict) else {}
    explicit = str(metadata.get("source_role", "") or metadata.get("source_role_hint", "")).strip().lower()
    if explicit in _SOURCE_ROLE_ORDER:
        return explicit

    title = str(getattr(artifact, "title", "") or "").lower()
    path = str(getattr(artifact, "path", "") or "").lower()
    corpus = str(metadata.get("corpus", "") or "").lower()
    document_kind = str(metadata.get("document_kind", "") or "").lower()
    joined = " ".join(part for part in (title, path, corpus, document_kind) if part)

    if any(token in joined for token in ("pandasthumb", "indexcc", "talkorigins", "evidence", "rebuttal", "argument", "critique")):
        return "argumentation"
    if any(token in joined for token in ("controvers", "debate", "dispute", "polemic")):
        return "controversy"
    if any(token in joined for token in ("introduction", "overview", "chapter", "textbook", "handbook", "evolutionary biology", "ecology")):
        return "overview"
    if any(token in joined for token in ("mechanism", "model", "testing", "test", "how", "rate", "process")):
        return "mechanism"
    if any(token in joined for token in ("nuance", "qualification", "constraint", "plasticity", "epigenetic", "drift")):
        return "nuance"
    return "overview"


def _source_signal_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {key: metadata[key] for key in _SOURCE_SIGNAL_KEYS if key in metadata}


def _temporal_signal_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {key: metadata[key] for key in _TEMPORAL_SIGNAL_KEYS if key in metadata}


def _claim_distinction_payload(claim: dict[str, Any]) -> dict[str, Any] | None:
    text = str(claim.get("claim_text", "")).strip()
    lowered = text.lower()
    if not text:
        return None

    patterns = [
        ("contrast", r"\bcompare\b", "compare"),
        ("non_implication", r"\bdoes not imply\b", "does not imply"),
        ("decoupling", r"\b(can|may)\s+occur\s+without\b", "can or may occur without"),
        ("contrast", r"\bversus\b|\bvs\.\b|\bvs\b", "versus"),
        ("contrast", r"\brather than\b", "rather than"),
        ("contrast", r"\bdiffer(?:s|ed|ent)? from\b|\bdiffers?\b", "differs from"),
        ("contrast", r"\bdifferent from\b|\bdistinguish(?:ed)? from\b", "different from"),
        ("contrast", r"\bnot\b.+\bbut\b", "not ... but"),
    ]
    for distinction_type, pattern, cue in patterns:
        if re.search(pattern, lowered):
            return {
                "claim_id": claim.get("claim_id", ""),
                "distinction_type": distinction_type,
                "cue": cue,
                "text": text,
            }
    return None


def _role_from_observation_or_claim(artifact_role: str, observation: Any | None, claim: Any | dict[str, Any] | None) -> str:
    observation_role = str(getattr(observation, "role", "") or "").lower() if observation is not None else ""
    claim_kind = str(getattr(claim, "claim_kind", "") or (claim.get("claim_kind", "") if isinstance(claim, dict) else "")).lower()
    claim_text = str(getattr(claim, "claim_text", "") or (claim.get("claim_text", "") if isinstance(claim, dict) else "")).lower()

    if observation_role in {"distinction", "qualification", "constraint"} or claim_kind in {"distinction", "qualification", "constraint"}:
        return "nuance"
    if observation_role == "definition" or claim_kind == "definition":
        return "overview"
    if claim_kind == "mastery_signal" and re.search(r"\b(build|compute|derive|detect|protect|repair|compare|contrast|state why)\b", claim_text):
        return "mechanism"
    return artifact_role


def query_concept(store_dir: str | Path, concept_ref: str) -> dict[str, Any] | None:
    store = GroundRecallStore(store_dir)
    concepts = store.list_concepts()
    concept = _resolve_concept(concepts, concept_ref)
    if concept is None:
        return None

    claims = [item for item in store.list_claims() if concept.concept_id in item.concept_ids and item.current_status != "rejected"]
    relations = [
        item
        for item in store.list_relations()
        if (item.source_id == concept.concept_id or item.target_id == concept.concept_id) and item.current_status != "rejected"
    ]
    artifacts = {item.artifact_id: item for item in store.list_artifacts()}
    observations = {item.observation_id: item for item in store.list_observations()}
    review_candidates = store.list_review_candidates()

    supporting_observations = []
    for claim in claims:
        for observation_id in claim.source_observation_ids:
            observation = observations.get(observation_id)
            if observation is not None:
                artifact = artifacts.get(observation.artifact_id)
                artifact_metadata = artifact.metadata if artifact is not None and isinstance(artifact.metadata, dict) else {}
                supporting_observations.append(
                    {
                        "observation_id": observation.observation_id,
                        "artifact_id": observation.artifact_id,
                        "text": observation.text,
                        "role": observation.role,
                        "origin_path": observation.provenance.origin_path,
                        "source_url": observation.provenance.source_url,
                        "retrieval_date": observation.provenance.retrieval_date,
                        "grounding_status": observation.provenance.grounding_status,
                        "source_role": _role_from_observation_or_claim(
                            _infer_source_role(artifact) if artifact is not None else "",
                            observation,
                            claim,
                        ),
                        "created_at": getattr(artifact, "created_at", "") if artifact is not None else "",
                        **_source_signal_metadata(artifact_metadata),
                        **_temporal_signal_metadata(artifact_metadata),
                    }
                )

    related_concept_ids = sorted(
        {
            relation.target_id if relation.source_id == concept.concept_id else relation.source_id
            for relation in relations
            if relation.source_id != relation.target_id
        }
    )
    related_concepts = [item.model_dump() for item in concepts if item.concept_id in related_concept_ids]

    source_artifacts = []
    for artifact in artifacts.values():
        if artifact.artifact_id not in set(concept.source_artifact_ids):
            continue
        payload = artifact.model_dump()
        payload["source_role"] = _infer_source_role(artifact)
        source_artifacts.append(payload)

    claim_payloads: list[dict[str, Any]] = []
    for claim in claims:
        payload = claim.model_dump()
        source_roles = sorted(
            {
                _role_from_observation_or_claim(
                    _infer_source_role(artifacts[observations[item].artifact_id]),
                    observations[item],
                    claim,
                )
                for item in claim.source_observation_ids
                if item in observations and observations[item].artifact_id in artifacts
            }
        )
        if source_roles:
            payload["source_roles"] = source_roles
        distinction = _claim_distinction_payload(payload)
        if distinction is not None:
            payload["distinction"] = distinction
        claim_payloads.append(payload)
    related_review_candidates = [
        item.model_dump()
        for item in review_candidates
        if item.candidate_id == concept.concept_id
        or (item.candidate_type == "claim" and any(claim.claim_id == item.candidate_id for claim in claims))
    ]

    return {
        "query_type": "concept",
        "concept": concept.model_dump(),
        "claims": claim_payloads,
        "relations": [item.model_dump() for item in relations],
        "related_concepts": related_concepts,
        "supporting_observations": supporting_observations,
        "source_artifacts": source_artifacts,
        "review_candidates": related_review_candidates,
    }


def search_claims(
    store_dir: str | Path,
    text: str,
    include_rejected: bool = False,
    limit: int = 20,
) -> dict[str, Any]:
    store = GroundRecallStore(store_dir)
    concepts = {item.concept_id: item for item in store.list_concepts()}
    matches = []
    for claim in store.list_claims():
        if not include_rejected and claim.current_status == "rejected":
            continue
        concept_titles = [concepts[concept_id].title for concept_id in claim.concept_ids if concept_id in concepts]
        if _matches(text, claim.claim_text, *concept_titles):
            matches.append(
                {
                    "claim": claim.model_dump(),
                    "concept_titles": concept_titles,
                    "provenance": claim.provenance.model_dump(),
                }
            )
        if len(matches) >= limit:
            break
    return {
        "query_type": "claim_search",
        "query": text,
        "matches": matches,
    }


def _artifact_corpus(artifact) -> str:
    corpus = artifact.metadata.get("corpus") if isinstance(getattr(artifact, "metadata", None), dict) else ""
    return str(corpus or "")


def search_documents(
    store_dir: str | Path,
    text: str,
    corpora: list[str] | None = None,
    include_rejected: bool = False,
    limit: int = 20,
) -> dict[str, Any]:
    store = GroundRecallStore(store_dir)
    artifacts = {item.artifact_id: item for item in store.list_artifacts()}
    observations_by_artifact: dict[str, list[Any]] = {}
    for observation in store.list_observations():
        observations_by_artifact.setdefault(observation.artifact_id, []).append(observation)

    active_corpora = {value for value in (corpora or []) if value}
    matches: list[dict[str, Any]] = []

    for artifact in artifacts.values():
        corpus = _artifact_corpus(artifact)
        if active_corpora and corpus not in active_corpora:
            continue
        if not include_rejected and artifact.current_status == "rejected":
            continue

        artifact_observations = observations_by_artifact.get(artifact.artifact_id, [])
        haystack_parts = [
            artifact.title,
            artifact.path,
            corpus,
            str(artifact.metadata.get("document_kind", "")),
            str(artifact.metadata.get("author", "")),
            str(artifact.metadata.get("canonical_url", "")),
            str(artifact.metadata.get("published_at", "")),
        ]
        haystack_parts.extend(observation.text for observation in artifact_observations)
        haystack = " ".join(part for part in haystack_parts if part)
        if _matches(text, haystack):
            matches.append(
                {
                    "artifact": artifact.model_dump(),
                    "corpus": corpus,
                    "observation_count": len(artifact_observations),
                    "matching_text": haystack[:800],
                }
            )
        if len(matches) >= limit:
            break

    return {
        "query_type": "document_search",
        "query": text,
        "active_corpora": sorted(active_corpora),
        "matches": matches,
    }


def query_provenance(
    store_dir: str | Path,
    origin_path: str | None = None,
    source_url: str | None = None,
) -> dict[str, Any]:
    store = GroundRecallStore(store_dir)
    claims = []
    observations = []
    for claim in store.list_claims():
        if origin_path and claim.provenance.origin_path == origin_path:
            claims.append(claim.model_dump())
            continue
        if source_url and claim.provenance.source_url == source_url:
            claims.append(claim.model_dump())
    for observation in store.list_observations():
        if origin_path and observation.provenance.origin_path == origin_path:
            observations.append(observation.model_dump())
            continue
        if source_url and observation.provenance.source_url == source_url:
            observations.append(observation.model_dump())
    return {
        "query_type": "provenance",
        "origin_path": origin_path or "",
        "source_url": source_url or "",
        "claims": claims,
        "observations": observations,
    }


def build_query_bundle_for_concept(store_dir: str | Path, concept_ref: str) -> dict[str, Any] | None:
    payload = query_concept(store_dir, concept_ref)
    if payload is None:
        return None
    claims = payload["claims"]
    relations = payload["relations"]
    contradictions = [item for item in claims if item.get("contradicts_claim_ids")]
    supersessions = [item for item in claims if item.get("supersedes_claim_ids")]
    source_role_summary: dict[str, int] = {}
    for artifact in payload["source_artifacts"]:
        role = str(artifact.get("source_role", "")).strip()
        if role:
            source_role_summary[role] = source_role_summary.get(role, 0) + 1
    claim_role_summary: dict[str, int] = {}
    for claim in claims:
        for role in claim.get("source_roles", []) or []:
            role = str(role).strip()
            if role:
                claim_role_summary[role] = claim_role_summary.get(role, 0) + 1
    if claim_role_summary:
        source_role_summary = dict(sorted(claim_role_summary.items()))
    key_distinctions = [item["distinction"] for item in claims if isinstance(item.get("distinction"), dict)]
    graph_bundle = graph_bundle_from_query_payload(payload)
    concept_id = str(payload["concept"].get("concept_id", ""))
    epistemic = epistemic_summary(graph_bundle, concept_id) if concept_id else {}
    temporal_summary = _temporal_summary(graph_bundle, claims)
    return {
        "bundle_kind": "groundrecall_query_bundle",
        "query_type": "concept",
        "concept": payload["concept"],
        "relevant_claims": claims,
        "relations": relations,
        "supporting_observations": payload["supporting_observations"],
        "source_artifacts": payload["source_artifacts"],
        "source_role_summary": dict(sorted(source_role_summary.items())),
        "key_distinctions": key_distinctions[:8],
        "related_concepts": payload["related_concepts"],
        "review_candidates": payload["review_candidates"],
        "contradictions": contradictions,
        "supersessions": supersessions,
        "epistemap_graph": graph_bundle.model_dump_legacy(),
        "epistemic_summary": epistemic,
        "assessment_summary": _assessment_summary(epistemic, temporal_summary),
        "temporal_summary": temporal_summary,
        "suggested_next_actions": [
            "Review promoted claims with low review confidence.",
            "Inspect supporting observations before exporting assistant context.",
            "Check related concepts for hidden prerequisite or contradiction edges.",
        ],
    }


def _assessment_summary(epistemic: dict[str, Any], temporal_summary: dict[str, Any]) -> dict[str, Any]:
    bayesian = epistemic.get("bayesian_reliability", {}) if isinstance(epistemic, dict) else {}
    classification = bayesian.get("classification", {}) if isinstance(bayesian, dict) else {}
    posterior = bayesian.get("posterior", {}) if isinstance(bayesian, dict) else {}
    sensitivity = bayesian.get("prior_sensitivity", {}) if isinstance(bayesian, dict) else {}
    reliability = epistemic.get("reliability", {}) if isinstance(epistemic, dict) else {}
    fair_play = temporal_summary.get("fair_play_diagnostic", {}) if isinstance(temporal_summary, dict) else {}
    return {
        "reliability_band": reliability.get("band", ""),
        "bayesian_label": classification.get("label", ""),
        "bayesian_flags": list(classification.get("flags", []) or []),
        "bayesian_posterior_mean": posterior.get("mean"),
        "prior_sensitivity_range": sensitivity.get("mean_range"),
        "temporal_rating": fair_play.get("rating", ""),
    }


def _temporal_summary(graph_bundle, claims: list[dict[str, Any]]) -> dict[str, Any]:
    claim_ids = [str(claim.get("claim_id", "")) for claim in claims if claim.get("claim_id")]
    windows = {claim_id: tenability_window(graph_bundle, claim_id) for claim_id in claim_ids}
    first_contradictions = {
        claim_id: contradiction
        for claim_id in claim_ids
        for contradiction in [first_contradiction_time(graph_bundle, claim_id)]
        if contradiction is not None
    }
    events = timeline_events(graph_bundle)
    reveal_at = events[-1]["time"] if events else None
    return {
        "summary": {
            "claim_count": len(claim_ids),
            "timeline_event_count": len(events),
            "bounded_claim_count": sum(1 for window in windows.values() if window["status"] == "bounded"),
            "first_contradiction_count": len(first_contradictions),
        },
        "claim_windows": windows,
        "first_contradictions": first_contradictions,
        "stale_claims": stale_claims_after(graph_bundle, reveal_at) if reveal_at else [],
        "fair_play_diagnostic": (
            fair_play_diagnostic(graph_bundle, claim_ids=claim_ids, reveal_at=reveal_at)
            if reveal_at
            else {"rating": "no_timeline", "summary": {"claim_count": len(claim_ids)}, "claims": []}
        ),
        "events": events[:24],
    }


def build_graph_bundle_for_concept(
    store_dir: str | Path,
    concept_ref: str,
    *,
    depth: int = 1,
    include_rejected: bool = False,
) -> dict[str, Any] | None:
    store = GroundRecallStore(store_dir)
    concepts = store.list_concepts()
    root = _resolve_concept(concepts, concept_ref)
    if root is None:
        return None

    max_depth = max(0, int(depth))
    concept_by_id = {item.concept_id: item for item in concepts if include_rejected or item.current_status != "rejected"}
    if root.concept_id not in concept_by_id:
        return None

    relations = [item for item in store.list_relations() if include_rejected or item.current_status != "rejected"]
    semantic_relations = [item for item in relations if item.relation_type not in PROVENANCE_RELATION_TYPES]
    provenance_relations = [item for item in relations if item.relation_type in PROVENANCE_RELATION_TYPES]
    adjacency: dict[str, list[Any]] = {concept_id: [] for concept_id in concept_by_id}
    for relation in semantic_relations:
        if relation.source_id not in concept_by_id or relation.target_id not in concept_by_id:
            continue
        adjacency.setdefault(relation.source_id, []).append(relation)
        adjacency.setdefault(relation.target_id, []).append(relation)

    selected_ids = {root.concept_id}
    frontier = {root.concept_id}
    for _ in range(max_depth):
        next_frontier: set[str] = set()
        for concept_id in frontier:
            for relation in adjacency.get(concept_id, []):
                neighbor_id = relation.target_id if relation.source_id == concept_id else relation.source_id
                if neighbor_id not in selected_ids:
                    selected_ids.add(neighbor_id)
                    next_frontier.add(neighbor_id)
        frontier = next_frontier
        if not frontier:
            break

    selected_concepts = [concept_by_id[concept_id] for concept_id in sorted(selected_ids)]
    selected_relations = [
        relation
        for relation in semantic_relations
        if relation.source_id in selected_ids and relation.target_id in selected_ids
    ]
    selected_provenance_relations = [
        relation
        for relation in provenance_relations
        if relation.source_id in selected_ids and relation.target_id in selected_ids
    ]
    selected_claims = [
        claim
        for claim in store.list_claims()
        if (include_rejected or claim.current_status != "rejected")
        and any(concept_id in selected_ids for concept_id in claim.concept_ids)
    ]

    observation_ids = {
        observation_id
        for claim in selected_claims
        for observation_id in claim.source_observation_ids
    }
    observations = [
        observation
        for observation in store.list_observations()
        if observation.observation_id in observation_ids and (include_rejected or observation.current_status != "rejected")
    ]
    artifacts = {item.artifact_id: item for item in store.list_artifacts()}
    source_artifact_ids = sorted(
        {
            artifact_id
            for concept in selected_concepts
            for artifact_id in concept.source_artifact_ids
        }
        | {observation.artifact_id for observation in observations if observation.artifact_id}
    )
    source_artifacts = [
        artifacts[artifact_id].model_dump()
        for artifact_id in source_artifact_ids
        if artifact_id in artifacts and (include_rejected or artifacts[artifact_id].current_status != "rejected")
    ]

    concept_rows = [item.model_dump() for item in selected_concepts]
    relation_rows = [item.model_dump() for item in [*selected_relations, *selected_provenance_relations]]
    return {
        "bundle_kind": "groundrecall_graph_bundle",
        "query_type": "graph",
        "root_concept": root.model_dump(),
        "depth": max_depth,
        "include_rejected": include_rejected,
        "nodes": [
            {
                "node_id": concept.concept_id,
                "node_kind": "concept",
                "title": concept.title,
                "status": concept.current_status,
                "record": concept.model_dump(),
            }
            for concept in selected_concepts
        ],
        "edges": [
            {
                "edge_id": relation.relation_id,
                "edge_kind": "relation",
                "source_id": relation.source_id,
                "target_id": relation.target_id,
                "relation_type": relation.relation_type,
                "status": relation.current_status,
                "evidence_ids": relation.evidence_ids,
                "provenance": relation.provenance.model_dump(),
                "record": relation.model_dump(),
            }
            for relation in selected_relations
        ],
        "provenance_edges": [
            {
                "edge_id": relation.relation_id,
                "edge_kind": "relation",
                "source_id": relation.source_id,
                "target_id": relation.target_id,
                "relation_type": relation.relation_type,
                "status": relation.current_status,
                "evidence_ids": relation.evidence_ids,
                "provenance": relation.provenance.model_dump(),
                "record": relation.model_dump(),
            }
            for relation in selected_provenance_relations
        ],
        "relevant_claims": [claim.model_dump() for claim in selected_claims],
        "supporting_observations": [observation.model_dump() for observation in observations],
        "source_artifacts": source_artifacts,
        "graph_diagnostics": build_graph_diagnostics(
            concept_rows,
            relation_rows,
            claims=[claim.model_dump() for claim in selected_claims],
            observations=[observation.model_dump() for observation in observations],
        ),
        "suggested_next_actions": [
            "Inspect inferred or weakly grounded edges before relying on graph structure.",
            "Increase --depth only when the neighborhood remains small enough to review.",
            "Review contradiction and supersession links for selected claims before exporting downstream.",
        ],
    }


def build_search_bundle(
    store_dir: str | Path,
    text: str,
    corpora: list[str] | None = None,
    object_kinds: list[str] | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    payload = search_index(store_dir, text, corpora=corpora, kinds=object_kinds, limit=limit, expand=True)
    return {
        "bundle_kind": "groundrecall_search_bundle",
        "query_type": payload["query_type"],
        "query": text,
        "index_path": payload["index_path"],
        "active_corpora": payload["active_corpora"],
        "active_object_kinds": payload["active_kinds"],
        "matches": payload["matches"],
        "associations": payload.get("associations", {}),
        "suggested_next_actions": [
            "Open the highest-ranked source note or canonical object before relying on it.",
            "Use --corpus or --object-kind filters when the result set is too broad.",
            "Inspect associations for linked claims, concepts, observations, artifacts, and review candidates.",
            "Rebuild the index after bulk imports or source-note edits.",
        ],
    }


def build_graph_search_bundle(
    store_dir: str | Path,
    text: str,
    *,
    corpora: list[str] | None = None,
    object_kinds: list[str] | None = None,
    limit: int = 20,
    graph_limit: int = 5,
    depth: int = 1,
) -> dict[str, Any]:
    search_payload = search_index(
        store_dir,
        text,
        corpora=corpora,
        kinds=object_kinds,
        limit=limit,
        expand=True,
        association_limit=12,
    )
    store = GroundRecallStore(store_dir)
    claims = {item.claim_id: item for item in store.list_claims()}
    relations = {item.relation_id: item for item in store.list_relations()}
    concepts = {item.concept_id: item for item in store.list_concepts()}

    concept_sources: dict[str, list[dict[str, Any]]] = {}
    query_terms = _query_terms(text)
    supplemental_concept_matches: list[dict[str, Any]] = []
    for match in search_payload["matches"]:
        doc_key = str(match.get("doc_key", ""))
        candidate_ids = _concept_ids_from_match(match, claims=claims, relations=relations)
        for concept_id in candidate_ids:
            if concept_id not in concepts:
                continue
            _append_concept_source(concept_sources, concept_id, match, root_match_kind="direct")

        for association in search_payload.get("associations", {}).get(doc_key, []):
            for concept_id in _concept_ids_from_association(association, claims=claims, relations=relations):
                if concept_id not in concepts:
                    continue
                _append_concept_source(
                    concept_sources,
                    concept_id,
                    match,
                    root_match_kind="association",
                    association=association,
                )

    if _should_include_supplemental_concepts(object_kinds):
        supplemental_payload = search_index(
            store_dir,
            text,
            kinds=["concept"],
            limit=max(limit, graph_limit * 4, 8),
            expand=False,
        )
        supplemental_concept_matches = supplemental_payload["matches"]
        for match in supplemental_concept_matches:
            for concept_id in _concept_ids_from_match(match, claims=claims, relations=relations):
                if concept_id not in concepts:
                    continue
                _append_concept_source(
                    concept_sources,
                    concept_id,
                    match,
                    root_match_kind="direct",
                    supplemental=True,
                )

    ranked_concept_ids = sorted(
        concept_sources,
        key=lambda concept_id: _graph_search_rank_key(concept_id, concepts[concept_id], concept_sources[concept_id], query_terms),
    )[: max(0, int(graph_limit))]

    graph_bundles = [
        bundle
        for concept_id in ranked_concept_ids
        if (bundle := build_graph_bundle_for_concept(store_dir, concept_id, depth=depth)) is not None
    ]
    return {
        "bundle_kind": "groundrecall_graph_search_bundle",
        "query_type": "graph_search",
        "query": text,
        "index_path": search_payload["index_path"],
        "active_corpora": search_payload["active_corpora"],
        "active_object_kinds": search_payload["active_kinds"],
        "match_count": len(search_payload["matches"]),
        "graph_limit": max(0, int(graph_limit)),
        "depth": max(0, int(depth)),
        "matches": search_payload["matches"],
        "associations": search_payload.get("associations", {}),
        "supplemental_concept_matches": supplemental_concept_matches,
        "root_concepts": [
            {
                "concept_id": concept_id,
                "title": concepts[concept_id].title,
                "status": concepts[concept_id].current_status,
                "match_summary": _concept_match_summary(concepts[concept_id], concept_sources[concept_id], query_terms),
                "match_sources": concept_sources[concept_id][:8],
            }
            for concept_id in ranked_concept_ids
        ],
        "graph_bundles": graph_bundles,
        "unresolved_matches": [
            {
                "doc_key": match.get("doc_key", ""),
                "kind": match.get("kind", ""),
                "record_id": match.get("record_id", ""),
                "title": match.get("title", ""),
            }
            for match in search_payload["matches"]
            if not _concept_ids_from_match(match, claims=claims, relations=relations)
            and not any(
                _concept_ids_from_association(association, claims=claims, relations=relations)
                for association in search_payload.get("associations", {}).get(str(match.get("doc_key", "")), [])
            )
        ],
        "suggested_next_actions": [
            "Inspect root_concepts before treating a full-text hit as graph-relevant.",
            "Use --object-kind concept or --corpus filters when text search finds too many candidate roots.",
            "Review graph diagnostics in each bundle before relying on inferred or weakly grounded relations.",
        ],
    }


def _append_concept_source(
    concept_sources: dict[str, list[dict[str, Any]]],
    concept_id: str,
    match: dict[str, Any],
    *,
    root_match_kind: str,
    association: dict[str, Any] | None = None,
    supplemental: bool = False,
) -> None:
    payload = {
        "root_match_kind": root_match_kind,
        "supplemental": supplemental,
        "doc_key": match.get("doc_key", ""),
        "kind": match.get("kind", ""),
        "record_id": match.get("record_id", ""),
        "title": match.get("title", ""),
        "score": match.get("score"),
        "snippet": match.get("snippet", ""),
    }
    if association is not None:
        payload["association"] = association
    concept_sources.setdefault(concept_id, []).append(payload)


def _should_include_supplemental_concepts(object_kinds: list[str] | None) -> bool:
    active_kinds = {item for item in (object_kinds or []) if item}
    return not active_kinds or "concept" in active_kinds


def _concept_ids_from_match(
    match: dict[str, Any],
    *,
    claims: dict[str, Any],
    relations: dict[str, Any],
) -> list[str]:
    kind = str(match.get("kind", ""))
    record_id = str(match.get("record_id", ""))
    metadata = match.get("metadata", {}) if isinstance(match.get("metadata"), dict) else {}
    if kind == "concept":
        return [record_id]
    if kind == "claim":
        claim = claims.get(record_id)
        if claim is not None:
            return list(claim.concept_ids)
        return [str(item) for item in metadata.get("concept_ids", []) if str(item).startswith("concept::")]
    if kind == "relation":
        relation = relations.get(record_id)
        if relation is not None:
            return [relation.source_id, relation.target_id]
        return [
            str(metadata.get("source_id", "")),
            str(metadata.get("target_id", "")),
        ]
    return []


def _concept_ids_from_association(
    association: dict[str, Any],
    *,
    claims: dict[str, Any],
    relations: dict[str, Any],
) -> list[str]:
    kind = str(association.get("kind", ""))
    record_id = str(association.get("record_id", ""))
    if kind == "concept":
        return [record_id]
    if kind == "claim" and record_id in claims:
        return list(claims[record_id].concept_ids)
    if kind == "relation" and record_id in relations:
        relation = relations[record_id]
        return [relation.source_id, relation.target_id]
    return []


def _graph_search_rank_key(
    concept_id: str,
    concept: Any,
    sources: list[dict[str, Any]],
    query_terms: set[str],
) -> tuple[Any, ...]:
    summary = _concept_match_summary(concept, sources, query_terms)
    return (
        -summary["direct_concept_match_count"],
        -summary["query_token_overlap"],
        -summary["direct_match_count"],
        summary["association_match_count"],
        _minimum_match_score(sources),
        -len(sources),
        concept.title.lower(),
        concept_id,
    )


def _concept_match_summary(concept: Any, sources: list[dict[str, Any]], query_terms: set[str]) -> dict[str, Any]:
    direct_match_count = sum(1 for item in sources if item.get("root_match_kind") == "direct")
    association_match_count = sum(1 for item in sources if item.get("root_match_kind") == "association")
    direct_concept_match_count = sum(
        1
        for item in sources
        if item.get("root_match_kind") == "direct" and item.get("kind") == "concept"
    )
    return {
        "direct_match_count": direct_match_count,
        "association_match_count": association_match_count,
        "direct_concept_match_count": direct_concept_match_count,
        "query_token_overlap": _concept_query_overlap(concept, query_terms),
    }


def _concept_query_overlap(concept: Any, query_terms: set[str]) -> int:
    if not query_terms:
        return 0
    aliases = getattr(concept, "aliases", []) or []
    parts = [
        getattr(concept, "concept_id", ""),
        getattr(concept, "title", ""),
        getattr(concept, "description", ""),
        *aliases,
    ]
    concept_terms = _query_terms(" ".join(str(part) for part in parts))
    return len(query_terms & concept_terms)


def _query_terms(text: str) -> set[str]:
    stop_words = {
        "and",
        "are",
        "for",
        "from",
        "into",
        "note",
        "notebook",
        "the",
        "with",
    }
    return {
        token
        for token in re.findall(r"[a-z0-9][a-z0-9-]*", text.lower())
        if len(token) > 2 and token not in stop_words
    }


def _minimum_match_score(sources: list[dict[str, Any]]) -> float:
    scores = [float(item["score"]) for item in sources if isinstance(item.get("score"), (int, float))]
    return min(scores) if scores else 0.0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Query canonical GroundRecall objects.")
    parser.add_argument("store_dir")
    parser.add_argument("query")
    parser.add_argument(
        "--kind",
        choices=["concept", "claim", "provenance", "bundle", "graph", "search", "graph-search"],
        default="concept",
    )
    parser.add_argument("--source-url", default=None)
    parser.add_argument("--corpus", action="append", default=[])
    parser.add_argument("--object-kind", action="append", default=[])
    parser.add_argument("--depth", type=int, default=1, help="Graph traversal depth for --kind graph")
    parser.add_argument("--limit", type=int, default=20, help="Search result limit for search and graph-search queries")
    parser.add_argument("--graph-limit", type=int, default=5, help="Maximum root concepts for --kind graph-search")
    parser.add_argument("--include-rejected", action="store_true", help="Include rejected records when supported by the query kind")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.kind == "concept":
        payload = query_concept(args.store_dir, args.query)
    elif args.kind == "claim":
        payload = search_claims(args.store_dir, args.query)
    elif args.kind == "provenance":
        payload = query_provenance(args.store_dir, origin_path=args.query, source_url=args.source_url)
    elif args.kind == "search":
        payload = build_search_bundle(
            args.store_dir,
            args.query,
            corpora=list(args.corpus or []),
            object_kinds=list(args.object_kind or []),
            limit=args.limit,
        )
    elif args.kind == "graph-search":
        payload = build_graph_search_bundle(
            args.store_dir,
            args.query,
            corpora=list(args.corpus or []),
            object_kinds=list(args.object_kind or []),
            limit=args.limit,
            graph_limit=args.graph_limit,
            depth=args.depth,
        )
    elif args.kind == "graph":
        payload = build_graph_bundle_for_concept(
            args.store_dir,
            args.query,
            depth=args.depth,
            include_rejected=args.include_rejected,
        )
    else:
        payload = build_query_bundle_for_concept(args.store_dir, args.query)
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
