"""Bounded, read-only discovery of Codex handoff proposals.

This is intentionally an explicit startup-wrapper API.  Discovery never claims,
executes, or changes a handoff; a later, separately authorized lifecycle call
must accept it.
"""
from __future__ import annotations

import argparse
import json
from typing import Any

from .handoff import AssistantHandoff, list_handoffs
from .policy import PolicyDecision, PolicyRequest, RELEASE_RANK, load_policy_plugins

ACTIVE_STATUSES = ("proposed", "accepted", "executing", "blocked")
SCHEMA_VERSION = "groundrecall.codex_handoff_discovery.v1"


def _bounded(value: str, maximum: int = 512) -> str:
    value = str(value or "")
    return value if len(value) <= maximum else value[: maximum - 1] + "…"


def _summary(item: AssistantHandoff) -> dict[str, Any]:
    """Return a startup-safe summary rather than copying arbitrary context."""
    return {
        "handoff_id": item.handoff_id,
        "task_id": item.task_id,
        "project": item.project,
        "objective": _bounded(item.objective, 1000),
        "status": item.status,
        "host_id": item.host_id,
        "subject_id": item.subject_id,
        "realm_id": item.realm_id,
        "release_level": item.release_level,
        "requested_action": _bounded(item.requested_action),
        "acceptance_criteria": [_bounded(v) for v in item.acceptance_criteria[:20]],
        "context_refs": [_bounded(v) for v in item.context_refs[:20]],
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def discover_handoffs(
    store_dir: str,
    *,
    policy_config: str | None = None,
    subject_id: str = "",
    realm_id: str = "",
    project: str = "",
    host_id: str = "",
    statuses: list[str] | None = None,
    maximum_release_level: str = "private",
    limit: int = 20,
) -> dict[str, Any]:
    """Return policy-visible active handoff summaries.

    A configured policy provider is evaluated separately for every candidate;
    denied and hard-gated records are omitted.  The default provider is the
    normal GroundRecall allow policy, while deployments should pass their
    server-owned policy configuration.
    """
    if maximum_release_level not in RELEASE_RANK:
        raise ValueError(f"unsupported maximum release level: {maximum_release_level}")
    requested = list(statuses or ACTIVE_STATUSES)
    invalid = [status for status in requested if status not in ACTIVE_STATUSES]
    if invalid:
        raise ValueError(f"unsupported active handoff status: {invalid[0]}")
    cap = max(1, min(int(limit), 100))
    provider = load_policy_plugins(policy_config) if policy_config else None
    candidates = list_handoffs(
        store_dir,
        subject_id=subject_id,
        realm_id=realm_id,
        project=project,
        host_id=host_id,
        maximum_release_level=maximum_release_level,
        limit=100,
    )
    candidates = [item for item in candidates if item.status in requested]
    visible: list[dict[str, Any]] = []
    denied = 0
    decisions: list[dict[str, Any]] = []
    for item in candidates:
        decision: PolicyDecision | None = None
        if provider:
            decision = provider.evaluate(
                PolicyRequest(
                    decision_point="query",
                    subject_id=subject_id or item.subject_id,
                    action="handoff_discover",
                    record_kind="assistant_handoff",
                    record_id=item.handoff_id,
                    release_level=item.release_level,
                    target_release_level=item.release_level,
                    scope_id=item.project,
                    metadata={
                        "groundrecall.realm_id": item.realm_id,
                        "groundrecall.host_id": item.host_id,
                        "groundrecall.handoff_status": item.status,
                    },
                )
            )
            decisions.append({
                "decision": decision.decision,
                "policy_id": decision.policy_id,
                "policy_version": decision.policy_version,
                "provider_id": decision.provider_id,
            })
            if decision.decision in {"deny", "hard_gate"}:
                denied += 1
                continue
        visible.append(_summary(item))
        if len(visible) >= cap:
            break
    return {
        "schema_version": SCHEMA_VERSION,
        "handoffs": visible,
        "visible_total": len(visible),
        "truncated": len(visible) >= cap and len(candidates) > len(visible),
        "filters": {
            "subject_id": subject_id,
            "realm_id": realm_id,
            "project": project,
            "host_id": host_id,
            "statuses": requested,
            "maximum_release_level": maximum_release_level,
        },
        "denied_count": denied,
        "canonical_write": False,
        "execution_performed": False,
        "policy_decisions": decisions,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Discover policy-visible active GroundRecall handoffs for a Codex startup wrapper.")
    parser.add_argument("store_dir")
    parser.add_argument("--policy-config", default=None, help="Server-owned policy-plugin YAML")
    parser.add_argument("--subject-id", default="")
    parser.add_argument("--realm-id", default="")
    parser.add_argument("--project", default="")
    parser.add_argument("--host-id", default="")
    parser.add_argument("--status", action="append", dest="statuses", choices=ACTIVE_STATUSES, default=[])
    parser.add_argument("--maximum-release-level", choices=tuple(RELEASE_RANK), default="private")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--format", choices=("json", "text"), default="text")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    payload = discover_handoffs(
        args.store_dir,
        policy_config=args.policy_config,
        subject_id=args.subject_id,
        realm_id=args.realm_id,
        project=args.project,
        host_id=args.host_id,
        statuses=args.statuses or None,
        maximum_release_level=args.maximum_release_level,
        limit=args.limit,
    )
    if args.format == "json":
        print(json.dumps(payload, indent=2))
        return
    print(f"GroundRecall active handoffs: {payload['visible_total']} visible")
    for item in payload["handoffs"]:
        print(f"- {item['status']} {item['handoff_id']} project={item['project']} host={item['host_id']} objective={item['objective']}")
