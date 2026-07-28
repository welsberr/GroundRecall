from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Literal

from .models import AdjudicationRecord, ClaimRecord, ContradictionCaseRecord, RelationRecord
from .policy import PolicyDecision, PolicyRequest, load_policy_plugins


ContradictionCaseStatus = Literal["open", "under_review", "resolved", "superseded", "rejected"]


class ContradictionPolicyError(RuntimeError):
    """Raised when a policy plugin blocks contradiction adjudication."""

    def __init__(self, message: str, payload: dict[str, Any]) -> None:
        super().__init__(message)
        self.payload = payload


def contradiction_case_id_for_claims(claim_ids: Iterable[str]) -> str:
    normalized = sorted({str(claim_id).strip() for claim_id in claim_ids if str(claim_id).strip()})
    digest = hashlib.sha256("\n".join(normalized).encode("utf-8")).hexdigest()[:16]
    readable = "__".join(_safe_id_part(claim_id) for claim_id in normalized[:2])
    return f"contradiction_case::{readable}::{digest}"


def generate_contradiction_cases_from_claims(
    claims: Iterable[ClaimRecord],
    *,
    opened_at: str | None = None,
    existing_cases: Iterable[ContradictionCaseRecord] = (),
) -> list[ContradictionCaseRecord]:
    claim_by_id = {claim.claim_id: claim for claim in claims}
    existing_by_pair = {
        tuple(sorted(case.claim_ids)): case
        for case in existing_cases
        if case.case_kind == "contradiction" and len(case.claim_ids) >= 2
    }
    generated: list[ContradictionCaseRecord] = []
    seen_pairs: set[tuple[str, str]] = set()
    timestamp = opened_at or _now_utc()
    for claim in claim_by_id.values():
        for target_id in claim.contradicts_claim_ids:
            if target_id not in claim_by_id:
                continue
            pair = tuple(sorted((claim.claim_id, target_id)))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            if pair in existing_by_pair:
                generated.append(existing_by_pair[pair])
                continue
            generated.append(
                ContradictionCaseRecord(
                    case_id=contradiction_case_id_for_claims(pair),
                    claim_ids=list(pair),
                    case_kind="contradiction",
                    status="open",
                    severity=_severity_for_claim_pair(claim_by_id[pair[0]], claim_by_id[pair[1]]),
                    opened_at=timestamp,
                    metadata={
                        "generation_method": "explicit_contradicts_claim_ids",
                        "explicit_edges": [
                            {
                                "source_claim_id": claim.claim_id,
                                "target_claim_id": target_id,
                            }
                        ],
                    },
                    current_status="triaged",
                )
            )
    return generated


def contradiction_cases_for_claim_ids(
    cases: Iterable[ContradictionCaseRecord],
    claim_ids: Iterable[str],
) -> list[ContradictionCaseRecord]:
    wanted = {claim_id for claim_id in claim_ids if claim_id}
    return [case for case in cases if wanted.intersection(case.claim_ids)]


def list_contradiction_case_batch(
    store_dir: str | Path,
    *,
    status: str = "",
    include_rejected: bool = False,
    sync: bool = False,
    limit: int = 50,
) -> dict[str, Any]:
    from .store import GroundRecallStore

    store = GroundRecallStore(store_dir)
    if sync:
        sync_contradiction_cases_for_store(store.base_dir)
    claims_by_id = {claim.claim_id: claim for claim in store.list_claims()}
    adjudications_by_id = {item.adjudication_id: item for item in store.list_adjudications()}
    cases = [
        case
        for case in store.list_contradiction_cases()
        if (include_rejected or case.current_status != "rejected")
        and (not status or case.status == status)
    ]
    cases = sorted(cases, key=lambda item: (_status_sort_key(item.status), -_severity_sort_key(item.severity), item.case_id))
    rows = [
        _case_payload(case, claims_by_id=claims_by_id, adjudications_by_id=adjudications_by_id)
        for case in cases[: max(0, limit)]
    ]
    return {
        "workflow_kind": "groundrecall_contradiction_case_review",
        "schema_version": "groundrecall.contradiction_cases.v1",
        "store_dir": str(Path(store_dir)),
        "case_count": len(cases),
        "returned_count": len(rows),
        "filters": {
            "status": status,
            "include_rejected": include_rejected,
            "synced_before_listing": sync,
            "limit": limit,
        },
        "cases": rows,
        "adjudication_schema": {
            "case_id": "contradiction case id",
            "status": "open|under_review|resolved|superseded|rejected",
            "adjudicator": "reviewer id or name",
            "rationale": "decision rationale",
            "resolution": "optional short resolution category",
            "selected_claim_ids": ["optional claim ids treated as best current account"],
        },
    }


def list_contradiction_candidate_batch(
    store_dir: str | Path,
    *,
    include_rejected: bool = False,
    limit: int = 50,
) -> dict[str, Any]:
    """List graph-inferred contradiction cues as a review batch.

    Graph maintenance can infer lightweight `claim_may_contradict_claim` relation
    records before a reviewer is ready to assert an explicit contradiction. This
    queue exposes those cues without silently promoting them into first-class
    contradiction cases.
    """

    from .store import GroundRecallStore

    store = GroundRecallStore(store_dir)
    claims_by_id = {claim.claim_id: claim for claim in store.list_claims()}
    relations = [
        relation
        for relation in store.list_relations()
        if relation.relation_type == "claim_may_contradict_claim"
        and (include_rejected or relation.current_status != "rejected")
    ]
    relations = sorted(relations, key=lambda item: (_status_sort_key(item.current_status), item.relation_id))
    rows = [
        _candidate_payload(relation, claims_by_id=claims_by_id)
        for relation in relations[: max(0, limit)]
    ]
    return {
        "workflow_kind": "groundrecall_contradiction_candidate_review",
        "schema_version": "groundrecall.contradiction_candidates.v1",
        "store_dir": str(Path(store_dir)),
        "candidate_count": len(relations),
        "returned_count": len(rows),
        "filters": {
            "include_rejected": include_rejected,
            "limit": limit,
        },
        "candidates": rows,
        "promotion_schema": {
            "relation_id": "claim_may_contradict_claim relation id",
            "reviewer": "reviewer id or name",
            "rationale": "why the cue should become an explicit contradiction case",
        },
    }


def accept_contradiction_candidate(
    store_dir: str | Path,
    *,
    relation_id: str,
    reviewer: str,
    rationale: str,
    reviewed_at: str | None = None,
    policy_plugins_path: str | Path | None = None,
    policy_subject_id: str = "",
) -> dict[str, Any]:
    """Promote a graph-inferred contradiction cue into explicit claim links and a case."""

    from .store import GroundRecallStore

    store = GroundRecallStore(store_dir)
    relation = store.get_relation(relation_id)
    if relation is None:
        raise KeyError(f"Unknown GroundRecall relation: {relation_id}")
    if relation.relation_type != "claim_may_contradict_claim":
        raise ValueError(f"Relation {relation_id} is not a claim_may_contradict_claim candidate")
    left = store.get_claim(relation.source_id)
    right = store.get_claim(relation.target_id)
    missing = [claim_id for claim_id, claim in [(relation.source_id, left), (relation.target_id, right)] if claim is None]
    if missing:
        raise KeyError(f"Cannot accept contradiction candidate {relation_id}; missing claim ids: {missing}")

    timestamp = reviewed_at or _now_utc()
    assert left is not None
    assert right is not None
    policy_decision = _evaluate_candidate_acceptance_policy(
        policy_plugins_path,
        subject_id=policy_subject_id or reviewer,
        relation=relation,
        reviewer=reviewer,
        rationale=rationale,
    )
    updated_left = _claim_with_contradiction_link(left, right.claim_id)
    updated_right = _claim_with_contradiction_link(right, left.claim_id)
    store.save_claim(updated_left)
    store.save_claim(updated_right)

    updated_relation = relation.model_copy(
        update={
            "current_status": "reviewed",
            "provenance": relation.provenance.model_copy(update={"support_kind": relation.provenance.support_kind or "inferred"}),
        }
    )
    store.save_relation(updated_relation)
    cases = sync_contradiction_cases_for_store(store.base_dir)
    case_id = contradiction_case_id_for_claims([left.claim_id, right.claim_id])
    case = store.get_contradiction_case(case_id)
    if case is None:
        raise RuntimeError(f"Accepted contradiction candidate {relation_id} but case {case_id} was not materialized")
    case = case.model_copy(
        update={
            "metadata": {
                **case.metadata,
                "accepted_candidate_relation_id": relation_id,
                "accepted_candidate_reviewer": reviewer,
                "accepted_candidate_rationale": rationale,
                "accepted_candidate_reviewed_at": timestamp,
            }
        }
    )
    store.save_contradiction_case(case)
    return {
        "decision": "accepted_contradiction_candidate",
        "relation": updated_relation.model_dump(mode="json"),
        "case": case.model_dump(mode="json"),
        "synced_case_count": len(cases),
        **({"policy_plugin_decision": policy_decision.model_dump(mode="json")} if policy_decision is not None else {}),
    }


def sync_contradiction_cases_for_store(store_dir: str | Path) -> list[ContradictionCaseRecord]:
    from .store import GroundRecallStore

    store = GroundRecallStore(store_dir)
    cases = generate_contradiction_cases_from_claims(
        store.list_claims(),
        existing_cases=store.list_contradiction_cases(),
    )
    for case in cases:
        store.save_contradiction_case(case)
    return cases


def adjudicate_contradiction_case(
    store_dir: str | Path,
    *,
    case_id: str,
    status: ContradictionCaseStatus,
    adjudicator: str,
    rationale: str,
    resolution: str = "",
    selected_claim_ids: list[str] | None = None,
    decided_at: str | None = None,
    adjudication_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    policy_plugins_path: str | Path | None = None,
    policy_subject_id: str = "",
) -> dict[str, Any]:
    from .store import GroundRecallStore

    store = GroundRecallStore(store_dir)
    case = store.get_contradiction_case(case_id)
    if case is None:
        raise KeyError(f"Unknown GroundRecall contradiction case: {case_id}")
    selected = [claim_id for claim_id in selected_claim_ids or [] if claim_id]
    missing_selected = [claim_id for claim_id in selected if claim_id not in set(case.claim_ids)]
    if missing_selected:
        raise ValueError(f"selected claim ids are not in contradiction case {case_id}: {missing_selected}")
    timestamp = decided_at or _now_utc()
    actual_adjudication_id = adjudication_id or _adjudication_id_for_case(case_id, timestamp)
    policy_decision = _evaluate_adjudication_policy(
        policy_plugins_path,
        subject_id=policy_subject_id or adjudicator,
        case=case,
        status=status,
        adjudicator=adjudicator,
        selected_claim_ids=selected,
        adjudication_id=actual_adjudication_id,
    )
    adjudication_metadata = {
        "selection_policy": "explicit_contradiction_case_adjudication_no_silent_averaging",
        "disagreement_preserved": True,
        "resolution": resolution,
        "selected_claim_ids": selected,
        **({"policy_plugin_decision": policy_decision.model_dump(mode="json")} if policy_decision is not None else {}),
        **(metadata or {}),
    }
    adjudication = AdjudicationRecord(
        adjudication_id=actual_adjudication_id,
        subject_id=case.case_id,
        subject_type="contradiction_case",
        adjudicator=adjudicator,
        rationale=rationale,
        decided_at=timestamp,
        metadata=adjudication_metadata,
    )
    store.save_adjudication(adjudication)
    updated_metadata = {
        **case.metadata,
        "last_adjudicated_at": timestamp,
        "last_adjudicator": adjudicator,
    }
    if resolution:
        updated_metadata["resolution"] = resolution
    if selected:
        updated_metadata["selected_claim_ids"] = selected
    updated_case = case.model_copy(
        update={
            "status": status,
            "resolved_at": timestamp if status in {"resolved", "superseded", "rejected"} else case.resolved_at,
            "adjudication_id": actual_adjudication_id,
            "rationale": rationale,
            "metadata": updated_metadata,
            "current_status": _lifecycle_for_case_status(status),
        }
    )
    store.save_contradiction_case(updated_case)
    return {
        "decision": "adjudicated",
        "case": updated_case.model_dump(mode="json"),
        "adjudication": adjudication.model_dump(mode="json"),
        **({"policy_plugin_decision": policy_decision.model_dump(mode="json")} if policy_decision is not None else {}),
    }


def _evaluate_adjudication_policy(
    policy_plugins_path: str | Path | None,
    *,
    subject_id: str,
    case: ContradictionCaseRecord,
    status: ContradictionCaseStatus,
    adjudicator: str,
    selected_claim_ids: list[str],
    adjudication_id: str,
) -> PolicyDecision | None:
    if policy_plugins_path is None:
        return None
    provider = load_policy_plugins(policy_plugins_path)
    decision = provider.evaluate(
        PolicyRequest(
            decision_point="adjudicate",
            subject_id=subject_id,
            action="adjudicate_contradiction_case",
            record_kind="contradiction_case",
            record_id=case.case_id,
            contradiction_state=case.status,
            durable_memory_change=True,
            metadata={
                "case_id": case.case_id,
                "case_status": case.status,
                "target_status": status,
                "severity": case.severity,
                "claim_ids": list(case.claim_ids),
                "selected_claim_ids": selected_claim_ids,
                "adjudicator": adjudicator,
                "adjudication_id": adjudication_id,
            },
        )
    )
    if decision.decision in {"deny", "hard_gate"}:
        raise ContradictionPolicyError(
            "Policy plugin blocked contradiction adjudication.",
            {
                "policy_plugin_decision": decision.model_dump(mode="json"),
            },
        )
    return decision


def _evaluate_candidate_acceptance_policy(
    policy_plugins_path: str | Path | None,
    *,
    subject_id: str,
    relation: RelationRecord,
    reviewer: str,
    rationale: str,
) -> PolicyDecision | None:
    if policy_plugins_path is None:
        return None
    provider = load_policy_plugins(policy_plugins_path)
    decision = provider.evaluate(
        PolicyRequest(
            decision_point="adjudicate",
            subject_id=subject_id,
            action="accept_contradiction_candidate",
            record_kind="relation",
            record_id=relation.relation_id,
            contradiction_state="candidate",
            durable_memory_change=True,
            metadata={
                "relation_id": relation.relation_id,
                "relation_type": relation.relation_type,
                "source_claim_id": relation.source_id,
                "target_claim_id": relation.target_id,
                "reviewer": reviewer,
                "rationale": rationale,
            },
        )
    )
    if decision.decision in {"deny", "hard_gate"}:
        raise ContradictionPolicyError(
            "Policy plugin blocked contradiction candidate acceptance.",
            {
                "policy_plugin_decision": decision.model_dump(mode="json"),
            },
        )
    return decision


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="List, sync, and adjudicate GroundRecall contradiction cases.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    sync_parser = subparsers.add_parser("sync", help="Generate first-class cases from explicit contradiction links")
    sync_parser.add_argument("store_dir")

    list_parser = subparsers.add_parser("list", help="List contradiction cases for review")
    list_parser.add_argument("store_dir")
    list_parser.add_argument("--status", default="")
    list_parser.add_argument("--include-rejected", action="store_true")
    list_parser.add_argument("--sync", action="store_true", help="Generate missing cases before listing")
    list_parser.add_argument("--limit", type=int, default=50)

    candidates_parser = subparsers.add_parser("candidates", help="List graph-inferred contradiction relation candidates")
    candidates_parser.add_argument("store_dir")
    candidates_parser.add_argument("--include-rejected", action="store_true")
    candidates_parser.add_argument("--limit", type=int, default=50)

    accept_parser = subparsers.add_parser("accept-candidate", help="Promote a contradiction relation candidate into a case")
    accept_parser.add_argument("store_dir")
    accept_parser.add_argument("relation_id")
    accept_parser.add_argument("--reviewer", required=True)
    accept_parser.add_argument("--rationale", required=True)
    accept_parser.add_argument("--reviewed-at", default=None)
    accept_parser.add_argument("--policy-plugins", default=None, help="Optional GroundRecall policy plugin YAML config for acceptance gating.")
    accept_parser.add_argument("--policy-subject-id", default="", help="Subject/principal id to evaluate against policy plugins.")

    adjudicate_parser = subparsers.add_parser("adjudicate", help="Record an adjudication against a contradiction case")
    adjudicate_parser.add_argument("store_dir")
    adjudicate_parser.add_argument("case_id")
    adjudicate_parser.add_argument("--status", choices=["open", "under_review", "resolved", "superseded", "rejected"], required=True)
    adjudicate_parser.add_argument("--adjudicator", required=True)
    adjudicate_parser.add_argument("--rationale", required=True)
    adjudicate_parser.add_argument("--resolution", default="")
    adjudicate_parser.add_argument("--selected-claim-id", action="append", default=[])
    adjudicate_parser.add_argument("--decided-at", default=None)
    adjudicate_parser.add_argument("--adjudication-id", default=None)
    adjudicate_parser.add_argument("--policy-plugins", default=None, help="Optional GroundRecall policy plugin YAML config for adjudication gating.")
    adjudicate_parser.add_argument("--policy-subject-id", default="", help="Subject/principal id to evaluate against policy plugins.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "sync":
        cases = sync_contradiction_cases_for_store(args.store_dir)
        payload = {
            "decision": "synced",
            "case_count": len(cases),
            "case_ids": [case.case_id for case in cases],
        }
    elif args.command == "list":
        payload = list_contradiction_case_batch(
            args.store_dir,
            status=args.status,
            include_rejected=args.include_rejected,
            sync=args.sync,
            limit=args.limit,
        )
    elif args.command == "candidates":
        payload = list_contradiction_candidate_batch(
            args.store_dir,
            include_rejected=args.include_rejected,
            limit=args.limit,
        )
    elif args.command == "accept-candidate":
        payload = accept_contradiction_candidate(
            args.store_dir,
            relation_id=args.relation_id,
            reviewer=args.reviewer,
            rationale=args.rationale,
            reviewed_at=args.reviewed_at,
            policy_plugins_path=args.policy_plugins,
            policy_subject_id=args.policy_subject_id,
        )
    else:
        try:
            payload = adjudicate_contradiction_case(
                args.store_dir,
                case_id=args.case_id,
                status=args.status,
                adjudicator=args.adjudicator,
                rationale=args.rationale,
                resolution=args.resolution,
                selected_claim_ids=list(args.selected_claim_id or []),
                decided_at=args.decided_at,
                adjudication_id=args.adjudication_id,
                policy_plugins_path=args.policy_plugins,
                policy_subject_id=args.policy_subject_id,
            )
        except ContradictionPolicyError as exc:
            print(json.dumps({"ok": False, "error": str(exc), "gate": exc.payload}, indent=2), file=sys.stderr)
            raise SystemExit(2) from exc
    print(json.dumps(payload, indent=2))


def _severity_for_claim_pair(left: ClaimRecord, right: ClaimRecord) -> str:
    statuses = {left.current_status, right.current_status}
    if "promoted" in statuses:
        return "high"
    if "reviewed" in statuses:
        return "medium"
    return "low"


def _safe_id_part(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")
    return text[:48] or "claim"


def _status_sort_key(status: str) -> int:
    order = {"open": 0, "under_review": 1, "resolved": 2, "superseded": 3, "rejected": 4}
    return order.get(status, 99)


def _severity_sort_key(severity: str) -> int:
    order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    return order.get(severity, 0)


def _case_payload(
    case: ContradictionCaseRecord,
    *,
    claims_by_id: dict[str, ClaimRecord],
    adjudications_by_id: dict[str, AdjudicationRecord],
) -> dict[str, Any]:
    adjudication = adjudications_by_id.get(case.adjudication_id) if case.adjudication_id else None
    return {
        "case_id": case.case_id,
        "case_kind": case.case_kind,
        "status": case.status,
        "severity": case.severity,
        "claim_ids": list(case.claim_ids),
        "opened_at": case.opened_at,
        "resolved_at": case.resolved_at,
        "adjudication_id": case.adjudication_id,
        "rationale": case.rationale,
        "claims": [
            {
                "claim_id": claim_id,
                "claim_text": claims_by_id[claim_id].claim_text if claim_id in claims_by_id else "",
                "current_status": claims_by_id[claim_id].current_status if claim_id in claims_by_id else "missing",
                "concept_ids": list(claims_by_id[claim_id].concept_ids) if claim_id in claims_by_id else [],
            }
            for claim_id in case.claim_ids
        ],
        "adjudication": adjudication.model_dump(mode="json") if adjudication is not None else None,
        "metadata": dict(case.metadata),
        "current_status": case.current_status,
    }


def _candidate_payload(
    relation: RelationRecord,
    *,
    claims_by_id: dict[str, ClaimRecord],
) -> dict[str, Any]:
    missing_claim_ids = [
        claim_id
        for claim_id in [relation.source_id, relation.target_id]
        if claim_id not in claims_by_id
    ]
    return {
        "relation_id": relation.relation_id,
        "relation_type": relation.relation_type,
        "claim_ids": [relation.source_id, relation.target_id],
        "missing_claim_ids": missing_claim_ids,
        "evidence_ids": list(relation.evidence_ids),
        "claims": [
            _claim_reference_payload(claim_id, claims_by_id=claims_by_id)
            for claim_id in [relation.source_id, relation.target_id]
        ],
        "provenance": relation.provenance.model_dump(mode="json"),
        "assessments": [
            assessment.model_dump(mode="json") if hasattr(assessment, "model_dump") else dict(assessment)
            for assessment in relation.assessments
        ],
        "review_actions": ["accept-candidate", "adjudicate-case-after-sync", "reject-relation-candidate"],
        "current_status": relation.current_status,
    }


def _claim_reference_payload(
    claim_id: str,
    *,
    claims_by_id: dict[str, ClaimRecord],
) -> dict[str, Any]:
    claim = claims_by_id.get(claim_id)
    if claim is None:
        return {
            "claim_id": claim_id,
            "claim_text": "",
            "current_status": "missing",
            "concept_ids": [],
            "supporting_fragment_ids": [],
            "source_observation_ids": [],
        }
    return {
        "claim_id": claim.claim_id,
        "claim_text": claim.claim_text,
        "current_status": claim.current_status,
        "concept_ids": list(claim.concept_ids),
        "supporting_fragment_ids": list(claim.supporting_fragment_ids),
        "source_observation_ids": list(claim.source_observation_ids),
    }


def _claim_with_contradiction_link(claim: ClaimRecord, target_claim_id: str) -> ClaimRecord:
    links = list(dict.fromkeys([*claim.contradicts_claim_ids, target_claim_id]))
    return claim.model_copy(update={"contradicts_claim_ids": links})


def _adjudication_id_for_case(case_id: str, timestamp: str) -> str:
    digest = hashlib.sha256(f"{case_id}\n{timestamp}".encode("utf-8")).hexdigest()[:12]
    return f"adj_contradiction_case_{_safe_id_part(case_id)}_{digest}"


def _lifecycle_for_case_status(status: str) -> str:
    if status == "rejected":
        return "rejected"
    if status in {"resolved", "superseded"}:
        return "reviewed"
    return "triaged"


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    main()
