from __future__ import annotations

import argparse
import re
from collections import Counter
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .models import ClaimRecord, DecisionRecord, WorkRecord
from .policy import PolicyDecision, PolicyRequest, load_policy_plugins
from .store import GroundRecallStore


PRIOR_WORK_SCHEMA_VERSION = "groundrecall.prior_work_report.v1"
_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_-]{1,}")
_RELEASE_RANK = {"public": 0, "internal": 1, "confidential": 2, "privileged": 3, "private": 4}


class PriorWorkCandidate(BaseModel):
    candidate_id: str
    candidate_kind: str
    match_kind: str
    score: float = Field(ge=0.0, le=1.0)
    title: str
    summary: str = ""
    outcome: str = "unknown"
    scope_id: str = ""
    release_level: str = "private"
    current_status: str = "draft"
    provenance_visibility: str = "full"
    review_required: bool = True
    reasons: list[str] = Field(default_factory=list)


class PriorWorkReport(BaseModel):
    schema_version: str = PRIOR_WORK_SCHEMA_VERSION
    query: str
    scope_id: str = ""
    maximum_release_level: str = "private"
    candidate_count: int = 0
    examined_count: int = 0
    inaccessible_count: int = 0
    inaccessible_by_release_level: dict[str, int] = Field(default_factory=dict)
    candidates: list[PriorWorkCandidate] = Field(default_factory=list)
    policy_decision: dict[str, Any] = Field(default_factory=dict)


def _tokens(value: str) -> set[str]:
    return set(_TOKEN_RE.findall(value.lower()))


def _release_level(record: Any) -> str:
    explicit = getattr(record, "release_level", None)
    if explicit in _RELEASE_RANK:
        return explicit
    metadata = getattr(record, "metadata", {})
    if isinstance(metadata, dict):
        value = str(metadata.get("release_level", "private")).lower()
        if value in _RELEASE_RANK:
            return value
    return "private"


def _allowed(level: str, maximum: str) -> bool:
    return _RELEASE_RANK.get(level, 4) <= _RELEASE_RANK.get(maximum, 4)


def _candidate_from_record(
    record: Any,
    *,
    candidate_kind: str,
    query: str,
    scope_id: str,
) -> PriorWorkCandidate | None:
    if isinstance(record, WorkRecord):
        candidate_id = record.work_id
        title = record.title
        summary = record.summary
        outcome = record.outcome
        record_scope = record.scope_id
        related_ids = record.related_work_ids
        provenance_visibility = str(record.metadata.get("provenance_visibility", "full"))
    elif isinstance(record, DecisionRecord):
        candidate_id = record.decision_id
        title = record.question
        summary = record.rationale or record.outcome
        outcome = record.outcome
        record_scope = record.scope_id
        related_ids = []
        provenance_visibility = str(record.metadata.get("provenance_visibility", "full"))
    elif isinstance(record, ClaimRecord):
        candidate_id = record.claim_id
        title = record.claim_text
        summary = record.claim_kind
        outcome = record.current_status
        record_scope = str(record.metadata.get("scope_id", ""))
        related_ids = []
        provenance_visibility = str(record.metadata.get("assessment_basis_visibility", "full"))
    else:  # pragma: no cover - defensive for future record types
        return None
    if scope_id and record_scope != scope_id:
        return None
    query_normalized = query.strip().lower()
    record_id = candidate_id.lower()
    title_tokens = _tokens(title)
    query_tokens = _tokens(query)
    if not query_tokens:
        return None
    exact = query_normalized == record_id or query_normalized == title.strip().lower()
    if exact:
        match_kind = "exact_identity"
        score = 1.0
        reasons = ["exact_id_or_title_match"]
    else:
        overlap = len(title_tokens & query_tokens) / max(len(query_tokens), 1)
        summary_overlap = len(_tokens(summary) & query_tokens) / max(len(query_tokens), 1)
        score = min(0.99, (overlap * 0.75) + (summary_overlap * 0.25))
        if score <= 0:
            return None
        match_kind = "lexical_candidate"
        reasons = ["candidate_requires_review"]
        if candidate_id.lower() in {item.lower() for item in related_ids}:
            match_kind = "graph_related_candidate"
            reasons.append("linked_by_record_relation")
    return PriorWorkCandidate(
        candidate_id=candidate_id,
        candidate_kind=candidate_kind,
        match_kind=match_kind,
        score=round(score, 6),
        title=title,
        summary=summary,
        outcome=outcome,
        scope_id=record_scope,
        release_level=_release_level(record),
        current_status=str(getattr(record, "current_status", "draft")),
        provenance_visibility=provenance_visibility,
        reasons=reasons,
    )


def prior_work_search(
    store_dir: str | Path,
    query: str,
    *,
    scope_id: str = "",
    maximum_release_level: str = "private",
    limit: int = 20,
    policy_plugins_path: str | Path | None = None,
    requester_id: str = "",
) -> PriorWorkReport:
    if maximum_release_level not in _RELEASE_RANK:
        raise ValueError(f"unknown maximum release level: {maximum_release_level}")
    policy_decision: PolicyDecision | None = None
    if policy_plugins_path is not None:
        provider = load_policy_plugins(policy_plugins_path)
        policy_decision = provider.evaluate(
            PolicyRequest(
                decision_point="query",
                subject_id=requester_id,
                action="prior_work_review",
                scope_id=scope_id,
                target_release_level=maximum_release_level,
                metadata={"query_purpose": "prior_work_review"},
            )
        )
        if policy_decision.decision in {"deny", "hard_gate"}:
            return PriorWorkReport(
                query=query,
                scope_id=scope_id,
                maximum_release_level=maximum_release_level,
                policy_decision=policy_decision.model_dump(mode="json"),
            )
    store = GroundRecallStore(store_dir)
    candidates: list[PriorWorkCandidate] = []
    inaccessible = Counter()
    examined = 0
    records: list[tuple[str, Any]] = []
    records.extend(("work", item) for item in store.list_works())
    records.extend(("decision", item) for item in store.list_decisions())
    records.extend(("claim", item) for item in store.list_claims())
    for kind, record in records:
        examined += 1
        level = _release_level(record)
        if not _allowed(level, maximum_release_level):
            inaccessible[level] += 1
            continue
        candidate = _candidate_from_record(record, candidate_kind=kind, query=query, scope_id=scope_id)
        if candidate is not None:
            candidates.append(candidate)
    candidates.sort(key=lambda item: (-item.score, item.candidate_kind, item.candidate_id))
    candidates = candidates[: max(0, limit)]
    return PriorWorkReport(
        query=query,
        scope_id=scope_id,
        maximum_release_level=maximum_release_level,
        candidate_count=len(candidates),
        examined_count=examined,
        inaccessible_count=sum(inaccessible.values()),
        inaccessible_by_release_level=dict(sorted(inaccessible.items())),
        candidates=candidates,
        policy_decision=policy_decision.model_dump(mode="json") if policy_decision is not None else {},
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Find prior work and negative results in a GroundRecall store.")
    parser.add_argument("store_dir")
    parser.add_argument("query")
    parser.add_argument("--scope-id", default="")
    parser.add_argument("--maximum-release-level", choices=tuple(_RELEASE_RANK), default="private")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--policy-plugins", default=None)
    parser.add_argument("--requester-id", default="")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = prior_work_search(
        args.store_dir,
        args.query,
        scope_id=args.scope_id,
        maximum_release_level=args.maximum_release_level,
        limit=args.limit,
        policy_plugins_path=args.policy_plugins,
        requester_id=args.requester_id,
    )
    print(report.model_dump_json(indent=2))
