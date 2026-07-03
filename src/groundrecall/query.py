from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any

from epistemap import epistemic_summary

from .epistemap_adapter import graph_bundle_from_query_payload
from .store import GroundRecallStore


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def _matches(query: str, *values: str) -> bool:
    needle = _normalize(query)
    return any(needle in _normalize(value) for value in values if value)


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
    concept = next(
        (
            item
            for item in concepts
            if concept_ref == item.concept_id
            or concept_ref == item.concept_id.replace("concept::", "", 1)
            or _matches(concept_ref, item.title, item.description, *item.aliases)
        ),
        None,
    )
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
                        "grounding_status": observation.provenance.grounding_status,
                        "source_role": _role_from_observation_or_claim(
                            _infer_source_role(artifact) if artifact is not None else "",
                            observation,
                            claim,
                        ),
                        **_source_signal_metadata(artifact_metadata),
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
        "epistemic_summary": epistemic_summary(graph_bundle, concept_id) if concept_id else {},
        "suggested_next_actions": [
            "Review promoted claims with low review confidence.",
            "Inspect supporting observations before exporting assistant context.",
            "Check related concepts for hidden prerequisite or contradiction edges.",
        ],
    }


def build_search_bundle(
    store_dir: str | Path,
    text: str,
    corpora: list[str] | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    payload = search_documents(store_dir, text=text, corpora=corpora, limit=limit)
    return {
        "bundle_kind": "groundrecall_search_bundle",
        "query_type": "document_search",
        "query": text,
        "active_corpora": payload["active_corpora"],
        "matches": payload["matches"],
        "suggested_next_actions": [
            "Open the matching documents and review the artifact metadata.",
            "Tighten the corpus filter when the result set is too broad.",
            "Use corpus defaults for a site-specific search preset and add others only when needed.",
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Query canonical GroundRecall objects.")
    parser.add_argument("store_dir")
    parser.add_argument("query")
    parser.add_argument("--kind", choices=["concept", "claim", "provenance", "bundle", "search"], default="concept")
    parser.add_argument("--source-url", default=None)
    parser.add_argument("--corpus", action="append", default=[])
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
        payload = build_search_bundle(args.store_dir, args.query, corpora=list(args.corpus or []))
    else:
        payload = build_query_bundle_for_concept(args.store_dir, args.query)
    print(json.dumps(payload, indent=2))
