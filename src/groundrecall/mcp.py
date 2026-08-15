from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable

from epistemap import GraphBundle, bayesian_assessment_report, diagnostics, epistemic_report, validate_assessment_readiness

from .catalog import query_federation_catalog
from .change_feed import load_subscription
from .export import export_canonical_snapshot
from .inspect import inspect_store
from .institutional_custody import orphan_stewardship_report
from .institutional_views import change_impact_report, stewardship_view
from .policy import PolicyDecision, PolicyRequest, load_policy_plugins
from .prior_work import prior_work_search
from .query import query_concept
from .search_index import search_index
from .review_backlog import BacklogPolicyError, aggregate_backlog, record_interaction
from .review_dashboard import dashboard_item_detail
from .handoff import (
    accept_handoff,
    complete_handoff,
    confirm_handoff_promotion,
    apply_handoff_promotion_request,
    appeal_handoff_review,
    request_handoff_assignment,
    accept_handoff_assignment,
    request_handoff_rejection,
    resolve_handoff_rejection,
    apply_handoff_rejection,
    start_handoff_execution,
    block_handoff,
    unblock_handoff,
    append_handoff_progress,
    claim_handoff,
    get_handoff,
    list_handoff_events,
    list_handoffs,
    propose_handoff,
    propose_handoff_result,
    review_handoff_result,
    request_handoff_promotion,
    list_handoff_promotion_actions,
    release_handoff,
    update_handoff_status,
)


SERVER_INFO = {"name": "groundrecall-mcp", "version": "0.1.0a1"}

POLICY_ARGUMENT_PROPERTIES: dict[str, Any] = {
    "policy_config": {"type": "string"},
    "policy_request": {"type": "object"},
    "subject_id": {"type": "string"},
}


def _json_text(payload: Any) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(payload, indent=2)}]}


def _evaluate_optional_policy(arguments: dict[str, Any], default_request: dict[str, Any]) -> PolicyDecision | None:
    policy_config = arguments.get("policy_config")
    if not policy_config:
        return None
    request_payload = dict(default_request)
    request_payload.update(dict(arguments.get("policy_request") or {}))
    provider = load_policy_plugins(policy_config)
    return provider.evaluate(PolicyRequest(**request_payload))


def _blocked_policy_result(decision: PolicyDecision) -> dict[str, Any] | None:
    if decision.decision not in {"deny", "hard_gate"}:
        return None
    return _json_text({"ok": False, "blocked_by_policy": True, "policy_decision": decision.model_dump(mode="json")})


def _attach_policy(payload: Any, decision: PolicyDecision | None) -> Any:
    if decision is None:
        return payload
    if isinstance(payload, dict):
        result = dict(payload)
        result["policy_decision"] = decision.model_dump(mode="json")
        return result
    return {"ok": True, "payload": payload, "policy_decision": decision.model_dump(mode="json")}


def _review_backlog(arguments: dict[str, Any]) -> dict[str, Any]:
    decision = _evaluate_optional_policy(arguments, {"decision_point": "read", "action": "review_backlog.list", "subject_id": str(arguments.get("subject_id", ""))})
    blocked = _blocked_policy_result(decision) if decision else None
    if blocked is not None: return blocked
    payload = aggregate_backlog(arguments["workspace"], subject_id=str(arguments.get("subject_id", "")), policy_config=arguments.get("policy_config"), maximum_release_level=str(arguments.get("maximum_release_level", "private")), limit=int(arguments.get("limit", 20)))
    return _json_text(_attach_policy(payload.model_dump(mode="json"), decision))


def _review_backlog_item(arguments: dict[str, Any]) -> dict[str, Any]:
    decision = _evaluate_optional_policy(arguments, {"decision_point": "read", "action": "review_backlog.read_item", "subject_id": str(arguments.get("subject_id", "")), "record_kind": "review_backlog", "record_id": str(arguments.get("backlog_id", ""))})
    blocked = _blocked_policy_result(decision) if decision else None
    if blocked is not None: return blocked
    payload = dashboard_item_detail(arguments["workspace"], arguments["backlog_id"], subject_id=str(arguments.get("subject_id", "")), policy_config=arguments.get("policy_config"), maximum_release_level=str(arguments.get("maximum_release_level", "private")))
    return _json_text(_attach_policy(payload.model_dump(mode="json"), decision))


def _review_interaction(arguments: dict[str, Any], event_type: str) -> dict[str, Any]:
    action = f"review_backlog.{event_type}"
    decision = _evaluate_optional_policy(arguments, {"decision_point": "review", "action": action, "subject_id": str(arguments.get("actor", arguments.get("subject_id", ""))), "record_kind": "review_backlog", "record_id": str(arguments.get("backlog_id", ""))})
    blocked = _blocked_policy_result(decision) if decision else None
    if blocked is not None:
        # Denials are operational audit events only; they never alter canonical
        # review state or interaction acknowledgement/assignment state.
        from .review_backlog import _append_interaction_event
        audit = _append_interaction_event(arguments["workspace"], event_type="policy_denied", backlog_id=str(arguments.get("backlog_id", "")), actor_subject_id=str(arguments.get("actor", arguments.get("subject_id", ""))), reason=(decision.reasons or [decision.policy_id])[0], policy_decision_ids=[decision.policy_id + ":" + decision.decision])
        return _json_text({"ok": False, "blocked_by_policy": True, "policy_decision": decision.model_dump(mode="json"), "audit_event_id": audit.event_id})
    try:
        event = record_interaction(arguments["workspace"], arguments["backlog_id"], event_type=event_type, actor_subject_id=str(arguments.get("actor", arguments.get("subject_id", ""))), until=str(arguments.get("until", "")), assignment=str(arguments.get("to", "")), reason=str(arguments.get("reason", "")), policy_config=arguments.get("policy_config"))
    except BacklogPolicyError as exc:
        return _json_text({"ok": False, "blocked_by_policy": True, "error": str(exc), "policy_decision": decision.model_dump(mode="json") if decision else {}})
    return _json_text(_attach_policy({"ok": True, "event": event.model_dump(mode="json"), "canonical_write": False}, decision))


def _inspect_store(arguments: dict[str, Any]) -> dict[str, Any]:
    decision = _evaluate_optional_policy(
        arguments,
        {
            "decision_point": "read",
            "action": "inspect_store",
            "subject_id": str(arguments.get("subject_id", "")),
        },
    )
    blocked = _blocked_policy_result(decision) if decision else None
    if blocked is not None:
        return blocked
    payload = inspect_store(
        arguments["store_dir"],
        include_graph=bool(arguments.get("include_graph", False)),
        compact_graph=bool(arguments.get("compact_graph", False)),
    )
    return _json_text(_attach_policy(payload, decision))


def _query_concept(arguments: dict[str, Any]) -> dict[str, Any]:
    decision = _evaluate_optional_policy(
        arguments,
        {
            "decision_point": "query",
            "action": "query_concept",
            "subject_id": str(arguments.get("subject_id", "")),
            "record_kind": "concept",
            "record_id": str(arguments.get("concept", "")),
        },
    )
    blocked = _blocked_policy_result(decision) if decision else None
    if blocked is not None:
        return blocked
    payload = query_concept(arguments["store_dir"], arguments["concept"])
    if payload is None:
        payload = {"ok": False, "error": "concept not found", "concept": arguments["concept"]}
    return _json_text(_attach_policy(payload, decision))


def _search_store(arguments: dict[str, Any]) -> dict[str, Any]:
    decision = _evaluate_optional_policy(
        arguments,
        {
            "decision_point": "query",
            "action": "search_store",
            "subject_id": str(arguments.get("subject_id", "")),
        },
    )
    blocked = _blocked_policy_result(decision) if decision else None
    if blocked is not None:
        return blocked
    payload = search_index(
        arguments["store_dir"],
        arguments["query"],
        limit=int(arguments.get("limit", 20)),
        kinds=list(arguments.get("kinds", []) or []),
        corpora=list(arguments.get("corpora", []) or []),
        rebuild=bool(arguments.get("rebuild", False)),
        expand=bool(arguments.get("expand", False)),
    )
    return _json_text(_attach_policy(payload, decision))


def _export_snapshot(arguments: dict[str, Any]) -> dict[str, Any]:
    decision = _evaluate_optional_policy(
        arguments,
        {
            "decision_point": "publish",
            "action": "export_snapshot",
            "subject_id": str(arguments.get("subject_id", "")),
            "target_release_level": "public",
            "public_facing": True,
        },
    )
    blocked = _blocked_policy_result(decision) if decision else None
    if blocked is not None:
        return blocked
    payload = export_canonical_snapshot(
        arguments["store_dir"],
        arguments["out_dir"],
        snapshot_id=arguments.get("snapshot_id"),
        include_graph_diagnostics=bool(arguments.get("include_graph_diagnostics", False)),
        include_graph_interchange=bool(arguments.get("include_graph_interchange", False)),
    )
    return _json_text(_attach_policy(payload, decision))


def _evaluate_policy(arguments: dict[str, Any]) -> dict[str, Any]:
    provider = load_policy_plugins(arguments["policy_config"])
    request_payload = dict(arguments.get("request") or {})
    decision = provider.evaluate(PolicyRequest(**request_payload))
    return _json_text(decision.model_dump(mode="json"))


def _epistemap_assessment(arguments: dict[str, Any]) -> dict[str, Any]:
    decision = _evaluate_optional_policy(
        arguments,
        {"decision_point": "query", "action": "epistemap_assessment", "subject_id": str(arguments.get("subject_id", "")), "record_kind": "epistemap_graph"},
    )
    blocked = _blocked_policy_result(decision) if decision else None
    if blocked is not None:
        return blocked
    bundle = GraphBundle.model_validate(arguments["graph_bundle"])
    operation = str(arguments.get("operation", "diagnostics"))
    node_types = set(arguments.get("node_types", []) or []) or None
    if operation == "diagnostics":
        payload = diagnostics(bundle, node_types=node_types)
    elif operation == "epistemic_report":
        payload = epistemic_report(bundle, node_types=node_types)
    elif operation == "bayesian_assessment":
        payload = bayesian_assessment_report(bundle, node_types=node_types)
    elif operation == "validate_graph":
        payload = validate_assessment_readiness(bundle)
    else:
        raise ValueError(f"unsupported Epistemap assessment operation: {operation}")
    return _json_text(_attach_policy({"schema_version": "groundrecall.mcp.epistemap_assessment.v1", "operation": operation, "graph_id": bundle.graph_id, "payload": payload}, decision))


def _prior_work(arguments: dict[str, Any]) -> dict[str, Any]:
    decision = _evaluate_optional_policy(
        arguments,
        {
            "decision_point": "query",
            "action": "prior_work_review",
            "subject_id": str(arguments.get("subject_id", "")),
            "scope_id": str(arguments.get("scope_id", "")),
            "target_release_level": str(arguments.get("maximum_release_level", "private")),
        },
    )
    blocked = _blocked_policy_result(decision) if decision else None
    if blocked is not None:
        return blocked
    payload = prior_work_search(
        arguments["store_dir"],
        arguments["query"],
        scope_id=str(arguments.get("scope_id", "")),
        maximum_release_level=str(arguments.get("maximum_release_level", "private")),
        limit=int(arguments.get("limit", 20)),
    ).model_dump(mode="json")
    return _json_text(_attach_policy(payload, decision))


def _catalog_discovery(arguments: dict[str, Any]) -> dict[str, Any]:
    decision = _evaluate_optional_policy(
        arguments,
        {
            "decision_point": "query",
            "action": "discover_federation_catalog",
            "subject_id": str(arguments.get("subject_id", "")),
            "target_release_level": str(arguments.get("target_release_level", "private")),
        },
    )
    blocked = _blocked_policy_result(decision) if decision else None
    if blocked is not None:
        return blocked
    entries = query_federation_catalog(arguments["catalog_path"], str(arguments.get("query", "")), limit=int(arguments.get("limit", 20)))
    payload = {
        "schema_version": "groundrecall.mcp.catalog_discovery.v1",
        "entry_count": len(entries),
        "entries": [entry.model_dump(mode="json") for entry in entries],
    }
    return _json_text(_attach_policy(payload, decision))


def _subscription_status(arguments: dict[str, Any]) -> dict[str, Any]:
    decision = _evaluate_optional_policy(
        arguments,
        {
            "decision_point": "query",
            "action": "manage_federation_subscription",
            "subject_id": str(arguments.get("subject_id", "")),
        },
    )
    blocked = _blocked_policy_result(decision) if decision else None
    if blocked is not None:
        return blocked
    sub = load_subscription(arguments["subscription_path"])
    payload = {
        "schema_version": "groundrecall.mcp.subscription_status.v1",
        "subscription_id": sub.subscription_id,
        "producer_instance_id": sub.producer_instance_id,
        "scope_ids": sub.scope_ids,
        "record_kinds": sub.record_kinds,
        "change_kinds": sub.change_kinds,
        "maximum_release_level": sub.maximum_release_level,
        "cursor": sub.cursor,
        "active": sub.active,
        "purpose": sub.purpose,
    }
    return _json_text(_attach_policy(payload, decision))


def _impact_report(arguments: dict[str, Any]) -> dict[str, Any]:
    decision = _evaluate_optional_policy(
        arguments,
        {
            "decision_point": "query",
            "action": "generate_change_impact_report",
            "subject_id": str(arguments.get("subject_id", "")),
            "record_kind": str(arguments.get("subject_type", "")),
            "record_id": str(arguments.get("subject_record_id", "")),
            "target_release_level": str(arguments.get("release_cap", "private")),
        },
    )
    blocked = _blocked_policy_result(decision) if decision else None
    if blocked is not None:
        return blocked
    payload = change_impact_report(
        arguments["store_dir"],
        subject_type=str(arguments["subject_type"]),
        subject_id=str(arguments["subject_record_id"]),
        release_cap=str(arguments.get("release_cap", "private")),
    ).model_dump(mode="json")
    return _json_text(_attach_policy(payload, decision))


def _stewardship_orphans(arguments: dict[str, Any]) -> dict[str, Any]:
    decision = _evaluate_optional_policy(
        arguments,
        {
            "decision_point": "query",
            "action": "generate_stewardship_view",
            "subject_id": str(arguments.get("subject_id", "")),
            "target_release_level": str(arguments.get("release_cap", "private")),
        },
    )
    blocked = _blocked_policy_result(decision) if decision else None
    if blocked is not None:
        return blocked
    payload = {
        "schema_version": "groundrecall.mcp.stewardship_orphans.v1",
        "stewardship": stewardship_view(arguments["store_dir"], release_cap=str(arguments.get("release_cap", "private"))).model_dump(mode="json"),
        "orphans": orphan_stewardship_report(arguments["store_dir"]).model_dump(mode="json"),
    }
    return _json_text(_attach_policy(payload, decision))


def _propose_contribution(arguments: dict[str, Any]) -> dict[str, Any]:
    decision = _evaluate_optional_policy(
        arguments,
        {
            "decision_point": "propose",
            "action": "propose_group_contribution",
            "subject_id": str(arguments.get("subject_id", "")),
            "scope_id": str(arguments.get("destination_scope_id", "")),
            "target_release_level": str(arguments.get("proposed_release_level", "private")),
            "durable_memory_change": False,
        },
    )
    blocked = _blocked_policy_result(decision) if decision else None
    if blocked is not None:
        return blocked
    payload = {
        "schema_version": "groundrecall.mcp.contribution_proposal.v1",
        "ok": True,
        "writes_performed": False,
        "authority_notice": "Draft proposal only; canonical contribution writes require an explicit policy-gated repository operation.",
        "proposal": {
            "contributor_id": str(arguments["contributor_id"]),
            "destination_scope_id": str(arguments["destination_scope_id"]),
            "contribution_intent": str(arguments["contribution_intent"]),
            "contributed_record_ids": list(arguments.get("contributed_record_ids", []) or []),
            "proposed_release_level": str(arguments.get("proposed_release_level", "private")),
            "provenance_visibility": str(arguments.get("provenance_visibility", "full")),
        },
    }
    return _json_text(_attach_policy(payload, decision))


def _handoff_propose(arguments: dict[str, Any]) -> dict[str, Any]:
    provider = load_policy_plugins(arguments["policy_config"]) if arguments.get("policy_config") else None
    fields = dict(arguments)
    fields.pop("store_dir", None)
    fields.pop("policy_config", None)
    fields.pop("policy_request", None)
    result = propose_handoff(arguments["store_dir"], policy_provider=provider, **fields)
    return _json_text(result.model_dump(mode="json"))


def _handoff_get(arguments: dict[str, Any]) -> dict[str, Any]:
    decision = _evaluate_optional_policy(arguments, {"decision_point": "query", "action": "handoff_get", "subject_id": str(arguments.get("subject_id", "")), "record_kind": "assistant_handoff", "record_id": str(arguments.get("handoff_id", "")), "scope_id": str(arguments.get("project", "")), "target_release_level": str(arguments.get("maximum_release_level", "private"))})
    blocked = _blocked_policy_result(decision) if decision else None
    if blocked is not None:
        return blocked
    item = get_handoff(arguments["store_dir"], arguments["handoff_id"], subject_id=str(arguments.get("subject_id", "")), realm_id=str(arguments.get("realm_id", "")), maximum_release_level=str(arguments.get("maximum_release_level", "private")))
    if item is None:
        return _json_text({"ok": False, "error": "handoff not found"})
    return _json_text(_attach_policy({"ok": True, "handoff": item.model_dump(mode="json")}, decision))


def _handoff_list(arguments: dict[str, Any]) -> dict[str, Any]:
    decision = _evaluate_optional_policy(arguments, {"decision_point": "query", "action": "handoff_list", "subject_id": str(arguments.get("subject_id", "")), "record_kind": "assistant_handoff", "scope_id": str(arguments.get("project", "")), "target_release_level": str(arguments.get("maximum_release_level", "private"))})
    blocked = _blocked_policy_result(decision) if decision else None
    if blocked is not None:
        return blocked
    items = list_handoffs(arguments["store_dir"], subject_id=str(arguments.get("subject_id", "")), realm_id=str(arguments.get("realm_id", "")), project=str(arguments.get("project", "")), status=str(arguments.get("status", "")), maximum_release_level=str(arguments.get("maximum_release_level", "private")), limit=int(arguments.get("limit", 20)))
    return _json_text(_attach_policy({"schema_version": "groundrecall.assistant_handoff_list.v1", "handoffs": [item.model_dump(mode="json") for item in items]}, decision))


def _handoff_update_status(arguments: dict[str, Any]) -> dict[str, Any]:
    provider = load_policy_plugins(arguments["policy_config"]) if arguments.get("policy_config") else None
    fields = dict(arguments)
    for key in ("store_dir", "handoff_id", "status", "policy_config", "policy_request", "subject_id", "realm_id", "maximum_release_level"):
        fields.pop(key, None)
    result = update_handoff_status(arguments["store_dir"], arguments["handoff_id"], arguments["status"], policy_provider=provider, subject_id=str(arguments.get("subject_id", "")), realm_id=str(arguments.get("realm_id", "")), maximum_release_level=str(arguments.get("maximum_release_level", "private")), **fields)
    return _json_text(result.model_dump(mode="json"))


def _handoff_accept(arguments: dict[str, Any]) -> dict[str, Any]:
    provider = load_policy_plugins(arguments["policy_config"]) if arguments.get("policy_config") else None
    result = accept_handoff(arguments["store_dir"], arguments["handoff_id"], subject_id=str(arguments.get("subject_id", "")), host_id=str(arguments.get("host_id", "")), project=str(arguments.get("project", "")), policy_provider=provider, realm_id=str(arguments.get("realm_id", "")), maximum_release_level=str(arguments.get("maximum_release_level", "private")), expected_status=str(arguments.get("expected_status", "proposed")), idempotency_key=str(arguments.get("idempotency_key", "")), provenance=dict(arguments.get("provenance", {}) or {}))
    return _json_text(result.model_dump(mode="json"))


def _handoff_complete(arguments: dict[str, Any]) -> dict[str, Any]:
    provider = load_policy_plugins(arguments["policy_config"]) if arguments.get("policy_config") else None
    result = complete_handoff(arguments["store_dir"], arguments["handoff_id"], subject_id=str(arguments.get("subject_id", "")), host_id=str(arguments.get("host_id", "")), project=str(arguments.get("project", "")), outcome=str(arguments.get("outcome", "")), result_ref=str(arguments.get("result_ref", "")), policy_provider=provider, realm_id=str(arguments.get("realm_id", "")), maximum_release_level=str(arguments.get("maximum_release_level", "private")), expected_status=str(arguments.get("expected_status", "executing")), idempotency_key=str(arguments.get("idempotency_key", "")), provenance=dict(arguments.get("provenance", {}) or {}))
    return _json_text(result.model_dump(mode="json"))


def _handoff_review(arguments: dict[str, Any]) -> dict[str, Any]:
    provider = load_policy_plugins(arguments["policy_config"]) if arguments.get("policy_config") else None
    event = review_handoff_result(arguments["store_dir"], arguments["handoff_id"], reviewer_subject_id=str(arguments.get("reviewer_subject_id", "")), project=str(arguments.get("project", "")), decision=str(arguments.get("decision", "")), rationale=str(arguments.get("rationale", "")), result_ref=str(arguments.get("result_ref", "")), policy_provider=provider, realm_id=str(arguments.get("realm_id", "")), maximum_release_level=str(arguments.get("maximum_release_level", "private")), expected_status=str(arguments.get("expected_status", "completed")), idempotency_key=str(arguments.get("idempotency_key", "")), provenance=dict(arguments.get("provenance", {}) or {}))
    return _json_text({"ok": True, "writes_performed": True, "canonical_write": False, "review": event.model_dump(mode="json")})


def _handoff_promotion_request(arguments: dict[str, Any]) -> dict[str, Any]:
    provider = load_policy_plugins(arguments["policy_config"]) if arguments.get("policy_config") else None
    event = request_handoff_promotion(arguments["store_dir"], arguments["handoff_id"], requester_subject_id=str(arguments.get("requester_subject_id", "")), project=str(arguments.get("project", "")), promotion_target=str(arguments.get("promotion_target", "")), rationale=str(arguments.get("rationale", "")), result_ref=str(arguments.get("result_ref", "")), policy_provider=provider, realm_id=str(arguments.get("realm_id", "")), maximum_release_level=str(arguments.get("maximum_release_level", "private")), expected_status=str(arguments.get("expected_status", "completed")), idempotency_key=str(arguments.get("idempotency_key", "")), provenance=dict(arguments.get("provenance", {}) or {}))
    return _json_text({"ok": True, "writes_performed": True, "canonical_write": False, "promotion_request": event.model_dump(mode="json")})


def _handoff_promotion_confirm(arguments: dict[str, Any]) -> dict[str, Any]:
    provider = load_policy_plugins(arguments["policy_config"]) if arguments.get("policy_config") else None
    event = confirm_handoff_promotion(arguments["store_dir"], arguments["handoff_id"], requester_subject_id=str(arguments.get("requester_subject_id", "")), project=str(arguments.get("project", "")), promotion_target=str(arguments.get("promotion_target", "")), confirm=arguments.get("confirm") is True, rationale=str(arguments.get("rationale", "")), result_ref=str(arguments.get("result_ref", "")), policy_provider=provider, realm_id=str(arguments.get("realm_id", "")), maximum_release_level=str(arguments.get("maximum_release_level", "private")), expected_status=str(arguments.get("expected_status", "completed")), idempotency_key=str(arguments.get("idempotency_key", "")), provenance=dict(arguments.get("provenance", {}) or {}))
    return _json_text({"ok": True, "writes_performed": True, "canonical_write": False, "promotion_confirmation": event.model_dump(mode="json")})


def _handoff_promotion_apply(arguments: dict[str, Any]) -> dict[str, Any]:
    provider = load_policy_plugins(arguments["policy_config"]) if arguments.get("policy_config") else None
    event = apply_handoff_promotion_request(arguments["store_dir"], arguments["handoff_id"], requester_subject_id=str(arguments.get("requester_subject_id", "")), project=str(arguments.get("project", "")), promotion_target=str(arguments.get("promotion_target", "")), policy_provider=provider, realm_id=str(arguments.get("realm_id", "")), maximum_release_level=str(arguments.get("maximum_release_level", "private")), expected_status=str(arguments.get("expected_status", "completed")), idempotency_key=str(arguments.get("idempotency_key", "")), provenance=dict(arguments.get("provenance", {}) or {}))
    return _json_text({"ok": True, "writes_performed": True, "canonical_write": False, "promotion_action": event.model_dump(mode="json")})


def _handoff_promotion_actions(arguments: dict[str, Any]) -> dict[str, Any]:
    decision = _evaluate_optional_policy(arguments, {"decision_point": "query", "action": "handoff_promotion_actions", "subject_id": str(arguments.get("subject_id", "")), "record_kind": "assistant_handoff_promotion_action", "scope_id": str(arguments.get("project", "")), "target_release_level": str(arguments.get("maximum_release_level", "private"))})
    blocked = _blocked_policy_result(decision) if decision else None
    if blocked is not None:
        return blocked
    actions = list_handoff_promotion_actions(arguments["store_dir"], subject_id=str(arguments.get("subject_id", "")), project=str(arguments.get("project", "")), realm_id=str(arguments.get("realm_id", "")), maximum_release_level=str(arguments.get("maximum_release_level", "private")), limit=int(arguments.get("limit", 20)))
    return _json_text(_attach_policy({"schema_version": "groundrecall.assistant_handoff_promotion_action_list.v1", "actions": actions}, decision))


def _handoff_review_appeal(arguments: dict[str, Any]) -> dict[str, Any]:
    provider = load_policy_plugins(arguments["policy_config"]) if arguments.get("policy_config") else None
    event = appeal_handoff_review(arguments["store_dir"], arguments["handoff_id"], requester_subject_id=str(arguments.get("requester_subject_id", "")), project=str(arguments.get("project", "")), target_review_event_id=str(arguments.get("target_review_event_id", "")), rationale=str(arguments.get("rationale", "")), result_ref=str(arguments.get("result_ref", "")), policy_provider=provider, realm_id=str(arguments.get("realm_id", "")), maximum_release_level=str(arguments.get("maximum_release_level", "private")), idempotency_key=str(arguments.get("idempotency_key", "")), provenance=dict(arguments.get("provenance", {}) or {}))
    return _json_text({"ok": True, "writes_performed": True, "canonical_write": False, "review_appeal": event.model_dump(mode="json")})


def _handoff_assignment_request(arguments: dict[str, Any]) -> dict[str, Any]:
    provider = load_policy_plugins(arguments["policy_config"]) if arguments.get("policy_config") else None
    event = request_handoff_assignment(arguments["store_dir"], arguments["handoff_id"], requester_subject_id=str(arguments.get("requester_subject_id", "")), assignee_subject_id=str(arguments.get("assignee_subject_id", "")), project=str(arguments.get("project", "")), rationale=str(arguments.get("rationale", "")), acceptance_context=str(arguments.get("acceptance_context", "")), policy_provider=provider, realm_id=str(arguments.get("realm_id", "")), maximum_release_level=str(arguments.get("maximum_release_level", "private")), idempotency_key=str(arguments.get("idempotency_key", "")), provenance=dict(arguments.get("provenance", {}) or {}))
    return _json_text({"ok": True, "writes_performed": True, "canonical_write": False, "assignment_request": event.model_dump(mode="json")})


def _handoff_assignment_accept(arguments: dict[str, Any]) -> dict[str, Any]:
    provider = load_policy_plugins(arguments["policy_config"]) if arguments.get("policy_config") else None
    event = accept_handoff_assignment(arguments["store_dir"], arguments["handoff_id"], assignee_subject_id=str(arguments.get("assignee_subject_id", "")), project=str(arguments.get("project", "")), target_assignment_event_id=str(arguments.get("target_assignment_event_id", "")), rationale=str(arguments.get("rationale", "")), acceptance_context=str(arguments.get("acceptance_context", "")), policy_provider=provider, realm_id=str(arguments.get("realm_id", "")), maximum_release_level=str(arguments.get("maximum_release_level", "private")), idempotency_key=str(arguments.get("idempotency_key", "")), provenance=dict(arguments.get("provenance", {}) or {}))
    return _json_text({"ok": True, "writes_performed": True, "canonical_write": False, "assignment_acceptance": event.model_dump(mode="json")})


def _handoff_rejection_request(arguments: dict[str, Any]) -> dict[str, Any]:
    provider = load_policy_plugins(arguments["policy_config"]) if arguments.get("policy_config") else None
    event = request_handoff_rejection(arguments["store_dir"], arguments["handoff_id"], requester_subject_id=str(arguments.get("requester_subject_id", "")), project=str(arguments.get("project", "")), action=str(arguments.get("action", "reject")), reason=str(arguments.get("reason", "")), evidence_ref=str(arguments.get("evidence_ref", "")), policy_provider=provider, realm_id=str(arguments.get("realm_id", "")), maximum_release_level=str(arguments.get("maximum_release_level", "private")), idempotency_key=str(arguments.get("idempotency_key", "")), provenance=dict(arguments.get("provenance", {}) or {}))
    return _json_text({"ok": True, "writes_performed": True, "canonical_write": False, "rejection_request": event.model_dump(mode="json")})


def _handoff_rejection_resolve(arguments: dict[str, Any]) -> dict[str, Any]:
    provider = load_policy_plugins(arguments["policy_config"]) if arguments.get("policy_config") else None
    event = resolve_handoff_rejection(arguments["store_dir"], arguments["handoff_id"], resolver_subject_id=str(arguments.get("resolver_subject_id", "")), project=str(arguments.get("project", "")), target_request_event_id=str(arguments.get("target_request_event_id", "")), decision=str(arguments.get("decision", "")), rationale=str(arguments.get("rationale", "")), evidence_ref=str(arguments.get("evidence_ref", "")), policy_provider=provider, realm_id=str(arguments.get("realm_id", "")), maximum_release_level=str(arguments.get("maximum_release_level", "private")), idempotency_key=str(arguments.get("idempotency_key", "")), provenance=dict(arguments.get("provenance", {}) or {}))
    return _json_text({"ok": True, "writes_performed": True, "canonical_write": False, "rejection_resolution": event.model_dump(mode="json")})


def _handoff_rejection_apply(arguments: dict[str, Any]) -> dict[str, Any]:
    provider = load_policy_plugins(arguments["policy_config"]) if arguments.get("policy_config") else None
    result = apply_handoff_rejection(arguments["store_dir"], arguments["handoff_id"], resolver_subject_id=str(arguments.get("resolver_subject_id", "")), project=str(arguments.get("project", "")), target_request_event_id=str(arguments.get("target_request_event_id", "")), target_resolution_event_id=str(arguments.get("target_resolution_event_id", "")), confirm=bool(arguments.get("confirm", False)), subject_id=str(arguments.get("subject_id", "")), host_id=str(arguments.get("host_id", "")), lease_id=str(arguments.get("lease_id", "")), reason=str(arguments.get("reason", "")), evidence_ref=str(arguments.get("evidence_ref", "")), policy_provider=provider, realm_id=str(arguments.get("realm_id", "")), maximum_release_level=str(arguments.get("maximum_release_level", "private")), expected_status=str(arguments.get("expected_status", "accepted")), idempotency_key=str(arguments.get("idempotency_key", "")), provenance=dict(arguments.get("provenance", {}) or {}))
    return _json_text(result.model_dump(mode="json"))


def _handoff_start(arguments: dict[str, Any]) -> dict[str, Any]:
    provider = load_policy_plugins(arguments["policy_config"]) if arguments.get("policy_config") else None
    result = start_handoff_execution(arguments["store_dir"], arguments["handoff_id"], subject_id=str(arguments.get("subject_id", "")), host_id=str(arguments.get("host_id", "")), project=str(arguments.get("project", "")), lease_id=str(arguments.get("lease_id", "")), policy_provider=provider, realm_id=str(arguments.get("realm_id", "")), maximum_release_level=str(arguments.get("maximum_release_level", "private")), expected_status=str(arguments.get("expected_status", "accepted")), idempotency_key=str(arguments.get("idempotency_key", "")), provenance=dict(arguments.get("provenance", {}) or {}))
    return _json_text(result.model_dump(mode="json"))


def _handoff_block(arguments: dict[str, Any]) -> dict[str, Any]:
    provider = load_policy_plugins(arguments["policy_config"]) if arguments.get("policy_config") else None
    result = block_handoff(arguments["store_dir"], arguments["handoff_id"], subject_id=str(arguments.get("subject_id", "")), host_id=str(arguments.get("host_id", "")), project=str(arguments.get("project", "")), lease_id=str(arguments.get("lease_id", "")), reason=str(arguments.get("reason", "")), evidence_ref=str(arguments.get("evidence_ref", "")), policy_provider=provider, realm_id=str(arguments.get("realm_id", "")), maximum_release_level=str(arguments.get("maximum_release_level", "private")), expected_status=str(arguments.get("expected_status", "executing")), idempotency_key=str(arguments.get("idempotency_key", "")), provenance=dict(arguments.get("provenance", {}) or {}))
    return _json_text(result.model_dump(mode="json"))


def _handoff_unblock(arguments: dict[str, Any]) -> dict[str, Any]:
    provider = load_policy_plugins(arguments["policy_config"]) if arguments.get("policy_config") else None
    result = unblock_handoff(arguments["store_dir"], arguments["handoff_id"], subject_id=str(arguments.get("subject_id", "")), host_id=str(arguments.get("host_id", "")), project=str(arguments.get("project", "")), lease_id=str(arguments.get("lease_id", "")), resolution=str(arguments.get("resolution", "")), evidence_ref=str(arguments.get("evidence_ref", "")), policy_provider=provider, realm_id=str(arguments.get("realm_id", "")), maximum_release_level=str(arguments.get("maximum_release_level", "private")), expected_status=str(arguments.get("expected_status", "blocked")), idempotency_key=str(arguments.get("idempotency_key", "")), provenance=dict(arguments.get("provenance", {}) or {}))
    return _json_text(result.model_dump(mode="json"))


def _handoff_claim(arguments: dict[str, Any]) -> dict[str, Any]:
    provider = load_policy_plugins(arguments["policy_config"]) if arguments.get("policy_config") else None
    result = claim_handoff(
        arguments["store_dir"], arguments["handoff_id"], subject_id=str(arguments.get("subject_id", "")),
        host_id=str(arguments.get("host_id", "")), project=str(arguments.get("project", "")),
        lease_seconds=int(arguments.get("lease_seconds", 900)), policy_provider=provider,
        realm_id=str(arguments.get("realm_id", "")), maximum_release_level=str(arguments.get("maximum_release_level", "private")),
        expected_status=str(arguments.get("expected_status", "")), idempotency_key=str(arguments.get("idempotency_key", "")),
        provenance=dict(arguments.get("provenance", {}) or {}),
    )
    return _json_text(result.model_dump(mode="json"))


def _handoff_release(arguments: dict[str, Any]) -> dict[str, Any]:
    provider = load_policy_plugins(arguments["policy_config"]) if arguments.get("policy_config") else None
    result = release_handoff(
        arguments["store_dir"], arguments["handoff_id"], subject_id=str(arguments.get("subject_id", "")),
        host_id=str(arguments.get("host_id", "")), project=str(arguments.get("project", "")),
        lease_id=str(arguments.get("lease_id", "")), policy_provider=provider,
        realm_id=str(arguments.get("realm_id", "")), maximum_release_level=str(arguments.get("maximum_release_level", "private")),
        expected_status=str(arguments.get("expected_status", "")), idempotency_key=str(arguments.get("idempotency_key", "")),
        provenance=dict(arguments.get("provenance", {}) or {}),
    )
    return _json_text(result.model_dump(mode="json"))


def _handoff_progress(arguments: dict[str, Any]) -> dict[str, Any]:
    provider = load_policy_plugins(arguments["policy_config"]) if arguments.get("policy_config") else None
    event = append_handoff_progress(arguments["store_dir"], arguments["handoff_id"], state=str(arguments.get("state", "")), observations=list(arguments.get("observations", []) or []), next_action=str(arguments.get("next_action", "")), policy_provider=provider, subject_id=str(arguments.get("subject_id", "")), realm_id=str(arguments.get("realm_id", "")), maximum_release_level=str(arguments.get("maximum_release_level", "private")), idempotency_key=str(arguments.get("idempotency_key", "")), provenance=dict(arguments.get("provenance", {}) or {}), lease_id=str(arguments.get("lease_id", "")), host_id=str(arguments.get("host_id", "")), project=str(arguments.get("project", "")), expected_status=str(arguments.get("expected_status", "executing")), require_lease=True)
    return _json_text({"ok": True, "writes_performed": True, "canonical_write": False, "progress": event.model_dump(mode="json")})


def _handoff_result(arguments: dict[str, Any]) -> dict[str, Any]:
    provider = load_policy_plugins(arguments["policy_config"]) if arguments.get("policy_config") else None
    event = propose_handoff_result(arguments["store_dir"], arguments["handoff_id"], outcome=str(arguments.get("outcome", "")), changes=list(arguments.get("changes", []) or []), tests=list(arguments.get("tests", []) or []), artifacts=list(arguments.get("artifacts", []) or []), unresolved=list(arguments.get("unresolved", []) or []), next_safe_action=str(arguments.get("next_safe_action", "")), policy_provider=provider, subject_id=str(arguments.get("subject_id", "")), realm_id=str(arguments.get("realm_id", "")), maximum_release_level=str(arguments.get("maximum_release_level", "private")), idempotency_key=str(arguments.get("idempotency_key", "")), provenance=dict(arguments.get("provenance", {}) or {}), lease_id=str(arguments.get("lease_id", "")), host_id=str(arguments.get("host_id", "")), project=str(arguments.get("project", "")), expected_status=str(arguments.get("expected_status", "executing")), require_lease=True)
    return _json_text({"ok": True, "writes_performed": True, "canonical_write": False, "result": event.model_dump(mode="json")})


def _handoff_events(arguments: dict[str, Any]) -> dict[str, Any]:
    decision = _evaluate_optional_policy(arguments, {"decision_point": "query", "action": "handoff_events", "subject_id": str(arguments.get("subject_id", "")), "record_kind": "assistant_handoff_event", "record_id": str(arguments.get("handoff_id", "")), "target_release_level": str(arguments.get("maximum_release_level", "private"))})
    blocked = _blocked_policy_result(decision) if decision else None
    if blocked is not None:
        return blocked
    events = list_handoff_events(arguments["store_dir"], arguments["handoff_id"], subject_id=str(arguments.get("subject_id", "")), realm_id=str(arguments.get("realm_id", "")), maximum_release_level=str(arguments.get("maximum_release_level", "private")), limit=int(arguments.get("limit", 100)))
    return _json_text(_attach_policy({"schema_version": "groundrecall.assistant_handoff_event_list.v1", "events": [event.model_dump(mode="json") for event in events]}, decision))


TOOLS: dict[str, dict[str, Any]] = {
    "review_backlog": {
        "description": "Read a policy-filtered, bounded local review backlog digest; never promotes or adjudicates records.",
        "inputSchema": {"type": "object", "properties": {"workspace": {"type": "string"}, "limit": {"type": "integer", "default": 20}, "maximum_release_level": {"type": "string", "default": "private"}, **POLICY_ARGUMENT_PROPERTIES}, "required": ["workspace"]},
        "handler": _review_backlog,
    },
    "review_backlog_item": {
        "description": "Read one authorized metadata-only review backlog item and provenance availability.",
        "inputSchema": {"type": "object", "properties": {"workspace": {"type": "string"}, "backlog_id": {"type": "string"}, "maximum_release_level": {"type": "string", "default": "private"}, **POLICY_ARGUMENT_PROPERTIES}, "required": ["workspace", "backlog_id"]},
        "handler": _review_backlog_item,
    },
    "acknowledge_review_reminder": {
        "description": "Acknowledge a reminder in the operational interaction ledger only; does not accept evidence.",
        "inputSchema": {"type": "object", "properties": {"workspace": {"type": "string"}, "backlog_id": {"type": "string"}, "actor": {"type": "string"}, **POLICY_ARGUMENT_PROPERTIES}, "required": ["workspace", "backlog_id", "actor"]},
        "handler": lambda arguments: _review_interaction(arguments, "acknowledged"),
    },
    "defer_review_reminder": {
        "description": "Defer a reminder in the operational interaction ledger only.",
        "inputSchema": {"type": "object", "properties": {"workspace": {"type": "string"}, "backlog_id": {"type": "string"}, "actor": {"type": "string"}, "until": {"type": "string"}, "reason": {"type": "string"}, **POLICY_ARGUMENT_PROPERTIES}, "required": ["workspace", "backlog_id", "actor", "until"]},
        "handler": lambda arguments: _review_interaction(arguments, "deferred"),
    },
    "assign_review_item": {
        "description": "Assign a review item in the operational interaction ledger only.",
        "inputSchema": {"type": "object", "properties": {"workspace": {"type": "string"}, "backlog_id": {"type": "string"}, "actor": {"type": "string"}, "to": {"type": "string"}, **POLICY_ARGUMENT_PROPERTIES}, "required": ["workspace", "backlog_id", "actor", "to"]},
        "handler": lambda arguments: _review_interaction(arguments, "assigned"),
    },
    "inspect_store": {
        "description": "Summarize a canonical GroundRecall store.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "store_dir": {"type": "string"},
                "include_graph": {"type": "boolean", "default": False},
                "compact_graph": {"type": "boolean", "default": False},
                **POLICY_ARGUMENT_PROPERTIES,
            },
            "required": ["store_dir"],
        },
        "handler": _inspect_store,
    },
    "query_concept": {
        "description": "Fetch a concept-centered GroundRecall query bundle.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "store_dir": {"type": "string"},
                "concept": {"type": "string"},
                **POLICY_ARGUMENT_PROPERTIES,
            },
            "required": ["store_dir", "concept"],
        },
        "handler": _query_concept,
    },
    "search_store": {
        "description": "Search the GroundRecall FTS index, rebuilding it if absent or requested.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "store_dir": {"type": "string"},
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 20},
                "kinds": {"type": "array", "items": {"type": "string"}},
                "corpora": {"type": "array", "items": {"type": "string"}},
                "rebuild": {"type": "boolean", "default": False},
                "expand": {"type": "boolean", "default": False},
                **POLICY_ARGUMENT_PROPERTIES,
            },
            "required": ["store_dir", "query"],
        },
        "handler": _search_store,
    },
    "export_snapshot": {
        "description": "Export a public-guardrailed canonical GroundRecall snapshot.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "store_dir": {"type": "string"},
                "out_dir": {"type": "string"},
                "snapshot_id": {"type": "string"},
                "include_graph_diagnostics": {"type": "boolean", "default": False},
                "include_graph_interchange": {"type": "boolean", "default": False},
                **POLICY_ARGUMENT_PROPERTIES,
            },
            "required": ["store_dir", "out_dir"],
        },
        "handler": _export_snapshot,
    },
    "evaluate_policy": {
        "description": "Evaluate a GroundRecall policy-plugin config against a bounded policy request.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "policy_config": {"type": "string"},
                "request": {
                    "type": "object",
                    "properties": {
                        "decision_point": {"type": "string"},
                        "subject_id": {"type": "string"},
                        "action": {"type": "string"},
                        "record_kind": {"type": "string"},
                        "record_id": {"type": "string"},
                        "release_level": {"type": "string"},
                        "target_release_level": {"type": "string"},
                        "scope_id": {"type": "string"},
                        "claim_state": {"type": "string"},
                        "evidence_state": {"type": "string"},
                        "citation_state": {"type": "string"},
                        "contradiction_state": {"type": "string"},
                        "stale": {"type": "boolean"},
                        "destructive": {"type": "boolean"},
                        "public_facing": {"type": "boolean"},
                        "durable_memory_change": {"type": "boolean"},
                        "metadata": {"type": "object"},
                    },
                    "required": ["decision_point"],
                },
            },
            "required": ["policy_config", "request"],
        },
        "handler": _evaluate_policy,
    },
    "epistemap_assessment": {
        "description": "Run a read-only Epistemap graph assessment over a supplied GroundRecall-compatible graph bundle.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "graph_bundle": {"type": "object"},
                "operation": {"type": "string", "enum": ["diagnostics", "epistemic_report", "bayesian_assessment", "validate_graph"], "default": "diagnostics"},
                "node_types": {"type": "array", "items": {"type": "string"}},
                **POLICY_ARGUMENT_PROPERTIES,
            },
            "required": ["graph_bundle"],
        },
        "handler": _epistemap_assessment,
    },
    "prior_work_review": {
        "description": "Run a policy-aware prior-work review over a GroundRecall store without writing results.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "store_dir": {"type": "string"},
                "query": {"type": "string"},
                "scope_id": {"type": "string"},
                "maximum_release_level": {"type": "string", "default": "private"},
                "limit": {"type": "integer", "default": 20},
                **POLICY_ARGUMENT_PROPERTIES,
            },
            "required": ["store_dir", "query"],
        },
        "handler": _prior_work,
    },
    "catalog_discovery": {
        "description": "Query a signed federation catalog for discoverable scope entries.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "catalog_path": {"type": "string"},
                "query": {"type": "string", "default": ""},
                "limit": {"type": "integer", "default": 20},
                "target_release_level": {"type": "string", "default": "private"},
                **POLICY_ARGUMENT_PROPERTIES,
            },
            "required": ["catalog_path"],
        },
        "handler": _catalog_discovery,
    },
    "subscription_status": {
        "description": "Read receiver-local federation subscription status and cursor metadata.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "subscription_path": {"type": "string"},
                **POLICY_ARGUMENT_PROPERTIES,
            },
            "required": ["subscription_path"],
        },
        "handler": _subscription_status,
    },
    "impact_report": {
        "description": "Generate a release-capped change-impact report with contradiction and confidence state.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "store_dir": {"type": "string"},
                "subject_type": {"type": "string"},
                "subject_record_id": {"type": "string"},
                "release_cap": {"type": "string", "default": "private"},
                **POLICY_ARGUMENT_PROPERTIES,
            },
            "required": ["store_dir", "subject_type", "subject_record_id"],
        },
        "handler": _impact_report,
    },
    "stewardship_orphans": {
        "description": "Generate explicit stewardship and orphan-review views without activity ranking.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "store_dir": {"type": "string"},
                "release_cap": {"type": "string", "default": "private"},
                **POLICY_ARGUMENT_PROPERTIES,
            },
            "required": ["store_dir"],
        },
        "handler": _stewardship_orphans,
    },
    "propose_contribution": {
        "description": "Prepare a draft contribution proposal; this tool performs no canonical store writes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "contributor_id": {"type": "string"},
                "destination_scope_id": {"type": "string"},
                "contribution_intent": {"type": "string"},
                "contributed_record_ids": {"type": "array", "items": {"type": "string"}},
                "proposed_release_level": {"type": "string", "default": "private"},
                "provenance_visibility": {"type": "string", "default": "full"},
                **POLICY_ARGUMENT_PROPERTIES,
            },
            "required": ["contributor_id", "destination_scope_id", "contribution_intent"],
        },
        "handler": _propose_contribution,
    },
    "handoff_propose": {
        "description": "Create a governed cross-assistant handoff proposal; never performs canonical memory writes or host execution.",
        "inputSchema": {"type": "object", "properties": {"store_dir": {"type": "string"}, "project": {"type": "string"}, "objective": {"type": "string"}, "task_id": {"type": "string"}, "handoff_id": {"type": "string"}, "constraints": {"type": "array", "items": {"type": "string"}}, "acceptance_criteria": {"type": "array", "items": {"type": "string"}}, "context_refs": {"type": "array", "items": {"type": "string"}}, "requested_action": {"type": "string"}, "from_surface": {"type": "string"}, "to_surface": {"type": "string"}, "host_id": {"type": "string"}, "realm_id": {"type": "string"}, "release_level": {"type": "string", "default": "private"}, "provenance": {"type": "object"}, "idempotency_key": {"type": "string"}, **POLICY_ARGUMENT_PROPERTIES}, "required": ["store_dir", "project", "objective"]},
        "handler": _handoff_propose,
    },
    "handoff_get": {
        "description": "Read one subject- and realm-scoped cross-assistant handoff proposal.",
        "inputSchema": {"type": "object", "properties": {"store_dir": {"type": "string"}, "handoff_id": {"type": "string"}, "realm_id": {"type": "string"}, "maximum_release_level": {"type": "string", "default": "private"}, **POLICY_ARGUMENT_PROPERTIES}, "required": ["store_dir", "handoff_id"]},
        "handler": _handoff_get,
    },
    "handoff_list": {
        "description": "List bounded subject- and realm-scoped cross-assistant handoff proposals.",
        "inputSchema": {"type": "object", "properties": {"store_dir": {"type": "string"}, "project": {"type": "string"}, "realm_id": {"type": "string"}, "status": {"type": "string"}, "maximum_release_level": {"type": "string", "default": "private"}, "limit": {"type": "integer", "default": 20}, **POLICY_ARGUMENT_PROPERTIES}, "required": ["store_dir"]},
        "handler": _handoff_list,
    },
    "handoff_events": {
        "description": "Read bounded, subject- and realm-scoped append-only handoff status, progress, and result records.",
        "inputSchema": {"type": "object", "properties": {"store_dir": {"type": "string"}, "handoff_id": {"type": "string"}, "realm_id": {"type": "string"}, "maximum_release_level": {"type": "string", "default": "private"}, "limit": {"type": "integer", "default": 100}, **POLICY_ARGUMENT_PROPERTIES}, "required": ["store_dir", "handoff_id"]},
        "handler": _handoff_events,
    },
    "handoff_update_status": {
        "description": "Policy-gated operational handoff status transition; never executes host work or promotes canonical memory.",
        "inputSchema": {"type": "object", "properties": {"store_dir": {"type": "string"}, "handoff_id": {"type": "string"}, "status": {"type": "string", "enum": ["proposed", "accepted", "executing", "blocked", "completed"]}, "expected_status": {"type": "string"}, "realm_id": {"type": "string"}, "maximum_release_level": {"type": "string", "default": "private"}, "provenance": {"type": "object"}, "idempotency_key": {"type": "string"}, **POLICY_ARGUMENT_PROPERTIES}, "required": ["store_dir", "handoff_id", "status"]},
        "handler": _handoff_update_status,
    },
    "handoff_accept": {
        "description": "Accept a proposed handoff only from its active subject/host/project/realm-scoped lease; never executes work or writes canonical memory.",
        "inputSchema": {"type": "object", "properties": {"store_dir": {"type": "string"}, "handoff_id": {"type": "string"}, "host_id": {"type": "string"}, "project": {"type": "string"}, "expected_status": {"type": "string", "default": "proposed"}, "realm_id": {"type": "string"}, "maximum_release_level": {"type": "string", "default": "private"}, "provenance": {"type": "object"}, "idempotency_key": {"type": "string"}, **POLICY_ARGUMENT_PROPERTIES}, "required": ["store_dir", "handoff_id", "host_id", "project"]},
        "handler": _handoff_accept,
    },
    "handoff_complete": {
        "description": "Complete a handoff only from its active lease owner with an outcome or result reference; never executes work or writes canonical memory.",
        "inputSchema": {"type": "object", "properties": {"store_dir": {"type": "string"}, "handoff_id": {"type": "string"}, "host_id": {"type": "string"}, "project": {"type": "string"}, "outcome": {"type": "string"}, "result_ref": {"type": "string"}, "expected_status": {"type": "string", "default": "executing"}, "realm_id": {"type": "string"}, "maximum_release_level": {"type": "string", "default": "private"}, "provenance": {"type": "object"}, "idempotency_key": {"type": "string"}, **POLICY_ARGUMENT_PROPERTIES}, "required": ["store_dir", "handoff_id", "host_id", "project"]},
        "handler": _handoff_complete,
    },
    "handoff_review": {
        "description": "Append a policy-gated review decision for a completed handoff; never promotes canonical memory or executes work.",
        "inputSchema": {"type": "object", "properties": {"store_dir": {"type": "string"}, "handoff_id": {"type": "string"}, "reviewer_subject_id": {"type": "string"}, "project": {"type": "string"}, "decision": {"type": "string", "enum": ["accept", "reject", "defer"]}, "rationale": {"type": "string"}, "result_ref": {"type": "string"}, "expected_status": {"type": "string", "default": "completed"}, "realm_id": {"type": "string"}, "maximum_release_level": {"type": "string", "default": "private"}, "provenance": {"type": "object"}, "idempotency_key": {"type": "string"}, **POLICY_ARGUMENT_PROPERTIES}, "required": ["store_dir", "handoff_id", "reviewer_subject_id", "project", "decision"]},
        "handler": _handoff_review,
    },
    "handoff_promotion_request": {
        "description": "Request governed promotion after an accepted handoff review; appends a quarantine request and never mutates canonical memory.",
        "inputSchema": {"type": "object", "properties": {"store_dir": {"type": "string"}, "handoff_id": {"type": "string"}, "requester_subject_id": {"type": "string"}, "project": {"type": "string"}, "promotion_target": {"type": "string"}, "rationale": {"type": "string"}, "result_ref": {"type": "string"}, "expected_status": {"type": "string", "default": "completed"}, "realm_id": {"type": "string"}, "maximum_release_level": {"type": "string", "default": "private"}, "provenance": {"type": "object"}, "idempotency_key": {"type": "string"}, **POLICY_ARGUMENT_PROPERTIES}, "required": ["store_dir", "handoff_id", "requester_subject_id", "project", "promotion_target"]},
        "handler": _handoff_promotion_request,
    },
    "handoff_promotion_confirm": {
        "description": "Confirm a matching promotion request with explicit confirm=true; records provenance only and never mutates canonical memory.",
        "inputSchema": {"type": "object", "properties": {"store_dir": {"type": "string"}, "handoff_id": {"type": "string"}, "requester_subject_id": {"type": "string"}, "project": {"type": "string"}, "promotion_target": {"type": "string"}, "confirm": {"type": "boolean"}, "rationale": {"type": "string"}, "result_ref": {"type": "string"}, "expected_status": {"type": "string", "default": "completed"}, "realm_id": {"type": "string"}, "maximum_release_level": {"type": "string", "default": "private"}, "provenance": {"type": "object"}, "idempotency_key": {"type": "string"}, **POLICY_ARGUMENT_PROPERTIES}, "required": ["store_dir", "handoff_id", "requester_subject_id", "project", "promotion_target", "confirm"]},
        "handler": _handoff_promotion_confirm,
    },
    "handoff_promotion_apply": {
        "description": "Record a bounded quarantined promotion action after confirmation; never mutates canonical memory.",
        "inputSchema": {"type": "object", "properties": {"store_dir": {"type": "string"}, "handoff_id": {"type": "string"}, "requester_subject_id": {"type": "string"}, "project": {"type": "string"}, "promotion_target": {"type": "string"}, "expected_status": {"type": "string", "default": "completed"}, "realm_id": {"type": "string"}, "maximum_release_level": {"type": "string", "default": "private"}, "provenance": {"type": "object"}, "idempotency_key": {"type": "string"}, **POLICY_ARGUMENT_PROPERTIES}, "required": ["store_dir", "handoff_id", "requester_subject_id", "project", "promotion_target"]},
        "handler": _handoff_promotion_apply,
    },
    "handoff_promotion_actions": {
        "description": "List bounded metadata-only quarantined handoff promotion actions filtered by subject/project/realm/release.",
        "inputSchema": {"type": "object", "properties": {"store_dir": {"type": "string"}, "subject_id": {"type": "string"}, "project": {"type": "string"}, "realm_id": {"type": "string"}, "maximum_release_level": {"type": "string", "default": "private"}, "limit": {"type": "integer", "default": 20}, **POLICY_ARGUMENT_PROPERTIES}, "required": ["store_dir"]},
        "handler": _handoff_promotion_actions,
    },
    "handoff_review_appeal": {
        "description": "Append a policy-gated appeal/correction request for an existing handoff review; never changes status or canonical memory.",
        "inputSchema": {"type": "object", "properties": {"store_dir": {"type": "string"}, "handoff_id": {"type": "string"}, "requester_subject_id": {"type": "string"}, "project": {"type": "string"}, "target_review_event_id": {"type": "string"}, "rationale": {"type": "string"}, "result_ref": {"type": "string"}, "realm_id": {"type": "string"}, "maximum_release_level": {"type": "string", "default": "private"}, "provenance": {"type": "object"}, "idempotency_key": {"type": "string"}, **POLICY_ARGUMENT_PROPERTIES}, "required": ["store_dir", "handoff_id", "requester_subject_id", "project", "target_review_event_id"]},
        "handler": _handoff_review_appeal,
    },
    "handoff_assignment_request": {
        "description": "Append a policy-gated scoped assignment request; never changes handoff status or canonical memory.",
        "inputSchema": {"type": "object", "properties": {"store_dir": {"type": "string"}, "handoff_id": {"type": "string"}, "requester_subject_id": {"type": "string"}, "assignee_subject_id": {"type": "string"}, "project": {"type": "string"}, "rationale": {"type": "string"}, "acceptance_context": {"type": "string"}, "realm_id": {"type": "string"}, "maximum_release_level": {"type": "string", "default": "private"}, "provenance": {"type": "object"}, "idempotency_key": {"type": "string"}, **POLICY_ARGUMENT_PROPERTIES}, "required": ["store_dir", "handoff_id", "requester_subject_id", "assignee_subject_id", "project"]},
        "handler": _handoff_assignment_request,
    },
    "handoff_assignment_accept": {
        "description": "Append acceptance of a matching assignment request; never changes handoff status or canonical memory.",
        "inputSchema": {"type": "object", "properties": {"store_dir": {"type": "string"}, "handoff_id": {"type": "string"}, "assignee_subject_id": {"type": "string"}, "project": {"type": "string"}, "target_assignment_event_id": {"type": "string"}, "rationale": {"type": "string"}, "acceptance_context": {"type": "string"}, "realm_id": {"type": "string"}, "maximum_release_level": {"type": "string", "default": "private"}, "provenance": {"type": "object"}, "idempotency_key": {"type": "string"}, **POLICY_ARGUMENT_PROPERTIES}, "required": ["store_dir", "handoff_id", "assignee_subject_id", "project", "target_assignment_event_id"]},
        "handler": _handoff_assignment_accept,
    },
    "handoff_rejection_request": {
        "description": "Append a policy-gated scoped reject/withdraw request with rationale or evidence; never changes handoff status, canonical memory, or executes work.",
        "inputSchema": {"type": "object", "properties": {"store_dir": {"type": "string"}, "handoff_id": {"type": "string"}, "requester_subject_id": {"type": "string"}, "project": {"type": "string"}, "action": {"type": "string", "enum": ["reject", "withdraw"], "default": "reject"}, "reason": {"type": "string"}, "evidence_ref": {"type": "string"}, "realm_id": {"type": "string"}, "maximum_release_level": {"type": "string", "default": "private"}, "provenance": {"type": "object"}, "idempotency_key": {"type": "string"}, **POLICY_ARGUMENT_PROPERTIES}, "required": ["store_dir", "handoff_id", "requester_subject_id", "project", "action"]},
        "handler": _handoff_rejection_request,
    },
    "handoff_rejection_resolve": {
        "description": "Append a policy-gated resolution of an existing reject/withdraw request; never changes handoff status, canonical memory, or executes work.",
        "inputSchema": {"type": "object", "properties": {"store_dir": {"type": "string"}, "handoff_id": {"type": "string"}, "resolver_subject_id": {"type": "string"}, "project": {"type": "string"}, "target_request_event_id": {"type": "string"}, "decision": {"type": "string", "enum": ["uphold", "dismiss", "supersede"]}, "rationale": {"type": "string"}, "evidence_ref": {"type": "string"}, "realm_id": {"type": "string"}, "maximum_release_level": {"type": "string", "default": "private"}, "provenance": {"type": "object"}, "idempotency_key": {"type": "string"}, **POLICY_ARGUMENT_PROPERTIES}, "required": ["store_dir", "handoff_id", "resolver_subject_id", "project", "target_request_event_id", "decision"]},
        "handler": _handoff_rejection_resolve,
    },
    "handoff_rejection_apply": {
        "description": "Consume an upheld rejection resolution into blocked status with explicit confirmation; requires matching scope and active lease when present, never writes canonical memory or executes work.",
        "inputSchema": {"type": "object", "properties": {"store_dir": {"type": "string"}, "handoff_id": {"type": "string"}, "resolver_subject_id": {"type": "string"}, "project": {"type": "string"}, "target_request_event_id": {"type": "string"}, "target_resolution_event_id": {"type": "string"}, "confirm": {"type": "boolean"}, "subject_id": {"type": "string"}, "host_id": {"type": "string"}, "lease_id": {"type": "string"}, "reason": {"type": "string"}, "evidence_ref": {"type": "string"}, "expected_status": {"type": "string", "default": "accepted"}, "realm_id": {"type": "string"}, "maximum_release_level": {"type": "string", "default": "private"}, "provenance": {"type": "object"}, "idempotency_key": {"type": "string"}, **POLICY_ARGUMENT_PROPERTIES}, "required": ["store_dir", "handoff_id", "resolver_subject_id", "project", "target_request_event_id", "target_resolution_event_id", "confirm"]},
        "handler": _handoff_rejection_apply,
    },
    "handoff_start": {
        "description": "Start an accepted, assigned, actively leased handoff; transitions only to executing and never runs host work.",
        "inputSchema": {"type": "object", "properties": {"store_dir": {"type": "string"}, "handoff_id": {"type": "string"}, "subject_id": {"type": "string"}, "host_id": {"type": "string"}, "project": {"type": "string"}, "lease_id": {"type": "string"}, "expected_status": {"type": "string", "default": "accepted"}, "realm_id": {"type": "string"}, "maximum_release_level": {"type": "string", "default": "private"}, "provenance": {"type": "object"}, "idempotency_key": {"type": "string"}, **POLICY_ARGUMENT_PROPERTIES}, "required": ["store_dir", "handoff_id", "subject_id", "host_id", "project", "lease_id"]},
        "handler": _handoff_start,
    },
    "handoff_block": {
        "description": "Block an accepted/executing handoff with an active lease and reason/evidence; never executes work or writes canonical memory.",
        "inputSchema": {"type": "object", "properties": {"store_dir": {"type": "string"}, "handoff_id": {"type": "string"}, "subject_id": {"type": "string"}, "host_id": {"type": "string"}, "project": {"type": "string"}, "lease_id": {"type": "string"}, "reason": {"type": "string"}, "evidence_ref": {"type": "string"}, "expected_status": {"type": "string", "default": "executing"}, "realm_id": {"type": "string"}, "maximum_release_level": {"type": "string", "default": "private"}, "provenance": {"type": "object"}, "idempotency_key": {"type": "string"}, **POLICY_ARGUMENT_PROPERTIES}, "required": ["store_dir", "handoff_id", "subject_id", "host_id", "project", "lease_id"]},
        "handler": _handoff_block,
    },
    "handoff_unblock": {
        "description": "Resolve a blocked handoff back to accepted under its active lease; never executes work or writes canonical memory.",
        "inputSchema": {"type": "object", "properties": {"store_dir": {"type": "string"}, "handoff_id": {"type": "string"}, "subject_id": {"type": "string"}, "host_id": {"type": "string"}, "project": {"type": "string"}, "lease_id": {"type": "string"}, "resolution": {"type": "string"}, "evidence_ref": {"type": "string"}, "expected_status": {"type": "string", "default": "blocked"}, "realm_id": {"type": "string"}, "maximum_release_level": {"type": "string", "default": "private"}, "provenance": {"type": "object"}, "idempotency_key": {"type": "string"}, **POLICY_ARGUMENT_PROPERTIES}, "required": ["store_dir", "handoff_id", "subject_id", "host_id", "project", "lease_id"]},
        "handler": _handoff_unblock,
    },
    "handoff_claim": {
        "description": "Claim a scoped handoff for a bounded lease; never executes host work or writes canonical memory.",
        "inputSchema": {"type": "object", "properties": {"store_dir": {"type": "string"}, "handoff_id": {"type": "string"}, "subject_id": {"type": "string"}, "host_id": {"type": "string"}, "project": {"type": "string"}, "expected_status": {"type": "string"}, "lease_seconds": {"type": "integer", "minimum": 1, "maximum": 3600, "default": 900}, "realm_id": {"type": "string"}, "maximum_release_level": {"type": "string", "default": "private"}, "provenance": {"type": "object"}, "idempotency_key": {"type": "string"}, **POLICY_ARGUMENT_PROPERTIES}, "required": ["store_dir", "handoff_id", "subject_id", "host_id", "project", "expected_status"]},
        "handler": _handoff_claim,
    },
    "handoff_release": {
        "description": "Release a caller-owned or expired scoped handoff lease; never changes status, executes host work, or writes canonical memory.",
        "inputSchema": {"type": "object", "properties": {"store_dir": {"type": "string"}, "handoff_id": {"type": "string"}, "subject_id": {"type": "string"}, "host_id": {"type": "string"}, "project": {"type": "string"}, "lease_id": {"type": "string"}, "expected_status": {"type": "string"}, "realm_id": {"type": "string"}, "maximum_release_level": {"type": "string", "default": "private"}, "provenance": {"type": "object"}, "idempotency_key": {"type": "string"}, **POLICY_ARGUMENT_PROPERTIES}, "required": ["store_dir", "handoff_id", "subject_id", "host_id", "project"]},
        "handler": _handoff_release,
    },
    "progress_append": {
        "description": "Append a policy-gated, proposal-only progress record to a handoff.",
        "inputSchema": {"type": "object", "properties": {"store_dir": {"type": "string"}, "handoff_id": {"type": "string"}, "state": {"type": "string"}, "observations": {"type": "array", "items": {"type": "string"}}, "next_action": {"type": "string"}, "lease_id": {"type": "string"}, "host_id": {"type": "string"}, "project": {"type": "string"}, "expected_status": {"type": "string", "default": "executing"}, "realm_id": {"type": "string"}, "maximum_release_level": {"type": "string", "default": "private"}, "provenance": {"type": "object"}, "idempotency_key": {"type": "string"}, **POLICY_ARGUMENT_PROPERTIES}, "required": ["store_dir", "handoff_id", "lease_id", "host_id", "project"]},
        "handler": _handoff_progress,
    },
    "result_propose": {
        "description": "Append a policy-gated, proposal-only result record to a handoff.",
        "inputSchema": {"type": "object", "properties": {"store_dir": {"type": "string"}, "handoff_id": {"type": "string"}, "outcome": {"type": "string"}, "changes": {"type": "array", "items": {"type": "string"}}, "tests": {"type": "array", "items": {"type": "string"}}, "artifacts": {"type": "array", "items": {"type": "string"}}, "unresolved": {"type": "array", "items": {"type": "string"}}, "next_safe_action": {"type": "string"}, "lease_id": {"type": "string"}, "host_id": {"type": "string"}, "project": {"type": "string"}, "expected_status": {"type": "string", "default": "executing"}, "realm_id": {"type": "string"}, "maximum_release_level": {"type": "string", "default": "private"}, "provenance": {"type": "object"}, "idempotency_key": {"type": "string"}, **POLICY_ARGUMENT_PROPERTIES}, "required": ["store_dir", "handoff_id", "lease_id", "host_id", "project"]},
        "handler": _handoff_result,
    },
}


def list_tools() -> list[dict[str, Any]]:
    return [
        {key: value for key, value in tool.items() if key != "handler"} | {"name": name}
        for name, tool in TOOLS.items()
    ]


REVIEWER_TOOLS = frozenset({"handoff_review", "handoff_review_appeal", "handoff_rejection_resolve", "handoff_promotion_request", "handoff_promotion_confirm", "handoff_promotion_apply"})


def handle_request(request: dict[str, Any], *, reviewer_role: str = "", server_roles: frozenset[str] = frozenset()) -> dict[str, Any] | None:
    request_id = request.get("id")
    method = request.get("method")
    params = request.get("params") or {}
    try:
        if method == "initialize":
            result = {
                "protocolVersion": params.get("protocolVersion", "2024-11-05"),
                "capabilities": {"tools": {}},
                "serverInfo": SERVER_INFO,
            }
        elif method == "notifications/initialized":
            return None
        elif method == "tools/list":
            result = {"tools": list_tools()}
        elif method == "tools/call":
            name = params.get("name")
            tool = TOOLS.get(name)
            if tool is None:
                raise ValueError(f"Unknown tool: {name}")
            if reviewer_role and name in REVIEWER_TOOLS and reviewer_role not in server_roles:
                raise PermissionError("required reviewer role is not assigned")
            handler: Callable[[dict[str, Any]], dict[str, Any]] = tool["handler"]
            result = handler(params.get("arguments") or {})
        else:
            raise ValueError(f"Unsupported method: {method}")
        return {"jsonrpc": "2.0", "id": request_id, "result": result}
    except Exception as exc:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32000, "message": str(exc)},
        }


def serve(input_stream=sys.stdin, output_stream=sys.stdout, *, reviewer_role: str = "", server_roles: frozenset[str] = frozenset()) -> None:
    for line in input_stream:
        if not line.strip():
            continue
        response = handle_request(json.loads(line), reviewer_role=reviewer_role, server_roles=server_roles)
        if response is not None:
            output_stream.write(json.dumps(response) + "\n")
            output_stream.flush()


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="GroundRecall stdio MCP server")
    parser.add_argument("--reviewer-role", default="", help="server-required reviewer role; empty is local-dev compatibility mode")
    parser.add_argument("--roles-file", default="", help="server-owned JSON file containing {\"roles\": [...]}")
    args = parser.parse_args()
    roles: frozenset[str] = frozenset()
    if args.roles_file:
        payload = json.loads(Path(args.roles_file).read_text(encoding="utf-8"))
        roles = frozenset(str(role) for role in (payload.get("roles") or []))
    serve(reviewer_role=args.reviewer_role, server_roles=roles)


if __name__ == "__main__":
    main()
