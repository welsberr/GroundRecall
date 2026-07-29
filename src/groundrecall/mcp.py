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


TOOLS: dict[str, dict[str, Any]] = {
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
}


def list_tools() -> list[dict[str, Any]]:
    return [
        {key: value for key, value in tool.items() if key != "handler"} | {"name": name}
        for name, tool in TOOLS.items()
    ]


def handle_request(request: dict[str, Any]) -> dict[str, Any] | None:
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


def serve(input_stream=sys.stdin, output_stream=sys.stdout) -> None:
    for line in input_stream:
        if not line.strip():
            continue
        response = handle_request(json.loads(line))
        if response is not None:
            output_stream.write(json.dumps(response) + "\n")
            output_stream.flush()


def main() -> None:
    serve()


if __name__ == "__main__":
    main()
