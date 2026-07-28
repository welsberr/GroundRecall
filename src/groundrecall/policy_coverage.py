from __future__ import annotations

from collections import Counter
from typing import Any, Literal

from pydantic import BaseModel, Field


POLICY_COVERAGE_SCHEMA_VERSION = "groundrecall.policy_coverage.v1"

PolicyCoverageStatus = Literal["covered", "partial", "intentionally_ungated", "future"]
PolicyCoverageSurface = Literal["cli", "mcp", "python_api", "derived_projection", "future"]


class PolicyCoverageEntry(BaseModel):
    route_id: str
    surface: PolicyCoverageSurface
    operation: str
    decision_point: str
    status: PolicyCoverageStatus
    durable_memory_change: bool = False
    read_or_export_effect: bool = False
    enforcement: list[str] = Field(default_factory=list)
    audit: list[str] = Field(default_factory=list)
    tests: list[str] = Field(default_factory=list)
    caveat: str = ""


POLICY_COVERAGE_ENTRIES: tuple[PolicyCoverageEntry, ...] = (
    PolicyCoverageEntry(
        route_id="mcp.inspect_store",
        surface="mcp",
        operation="inspect_store",
        decision_point="read",
        status="covered",
        read_or_export_effect=True,
        enforcement=["optional policy_config denies/hard-gates before store inspection"],
        audit=["blocked MCP read returns structured policy decision; no durable audit log for read-only denial"],
        tests=["tests/test_mcp.py"],
        caveat="Read-only MCP denials are returned to the caller rather than written as durable audit events.",
    ),
    PolicyCoverageEntry(
        route_id="mcp.query_memory",
        surface="mcp",
        operation="query_memory",
        decision_point="query",
        status="covered",
        read_or_export_effect=True,
        enforcement=["optional policy_config denies/hard-gates before query execution"],
        audit=["blocked MCP query returns structured policy decision; no durable audit log for read-only denial"],
        tests=["tests/test_mcp.py"],
        caveat="Read-only MCP denials are returned to the caller rather than written as durable audit events.",
    ),
    PolicyCoverageEntry(
        route_id="mcp.search_index",
        surface="mcp",
        operation="search_index",
        decision_point="query",
        status="covered",
        read_or_export_effect=True,
        enforcement=["optional policy_config denies/hard-gates before search execution"],
        audit=["blocked MCP search returns structured policy decision; no durable audit log for read-only denial"],
        tests=["tests/test_mcp.py"],
        caveat="Read-only MCP denials are returned to the caller rather than written as durable audit events.",
    ),
    PolicyCoverageEntry(
        route_id="mcp.export_bundle",
        surface="mcp",
        operation="export_bundle",
        decision_point="export",
        status="covered",
        read_or_export_effect=True,
        enforcement=["optional policy_config denies/hard-gates before export side effects"],
        audit=["blocked MCP export returns structured policy decision"],
        tests=["tests/test_mcp.py", "tests/test_export_guardrails.py"],
        caveat="Durable audit output for canonical export remains manifest/provenance metadata rather than a separate append-only audit log.",
    ),
    PolicyCoverageEntry(
        route_id="mcp.evaluate_policy",
        surface="mcp",
        operation="evaluate_policy",
        decision_point="read",
        status="intentionally_ungated",
        enforcement=["evaluates a bounded request against a supplied policy config"],
        audit=["no durable memory change"],
        tests=["tests/test_mcp.py", "tests/test_policy_plugins.py"],
        caveat="The route is policy introspection, not a protected memory mutation.",
    ),
    PolicyCoverageEntry(
        route_id="cli.promote",
        surface="cli",
        operation="promote_import_to_store",
        decision_point="promote",
        status="covered",
        durable_memory_change=True,
        enforcement=["--policy-plugins denies/hard-gates before canonical store writes"],
        audit=["soft decisions recorded in snapshot metadata; hard-gates return structured error payload without writes"],
        tests=["tests/test_groundrecall_promotion.py"],
        caveat="No standalone durable audit log is written for blocked direct promotion outside the returned error payload.",
    ),
    PolicyCoverageEntry(
        route_id="cli.relation_review.apply",
        surface="cli",
        operation="apply_relation_review_batch",
        decision_point="review",
        status="covered",
        durable_memory_change=True,
        enforcement=["--policy-plugins preflight blocks deny/hard_gate before relation or candidate writes"],
        audit=["soft decisions recorded with applied rows; hard-gates return structured error payload without writes"],
        tests=["tests/test_relation_review.py"],
        caveat="No standalone durable audit log is written for blocked direct relation-review application outside the returned error payload.",
    ),
    PolicyCoverageEntry(
        route_id="cli.contradictions.adjudicate",
        surface="cli",
        operation="adjudicate_contradiction_case",
        decision_point="adjudicate",
        status="covered",
        durable_memory_change=True,
        enforcement=["--policy-plugins blocks deny/hard_gate before adjudication and case writes"],
        audit=["soft decisions recorded in adjudication and case metadata; hard-gates return structured error payload without writes"],
        tests=["tests/test_contradictions.py"],
        caveat="No standalone durable audit log is written for blocked direct adjudication outside the returned error payload.",
    ),
    PolicyCoverageEntry(
        route_id="cli.export.canonical_public",
        surface="cli",
        operation="export_canonical_bundle",
        decision_point="export",
        status="covered",
        read_or_export_effect=True,
        enforcement=["--policy-plugins denies/hard-gates before output directories are created", "public export guardrails filter release levels and sensitive records"],
        audit=["policy decision recorded in export manifest and provenance manifest for completed exports"],
        tests=["tests/test_export_guardrails.py", "tests/test_groundrecall_export.py"],
        caveat="Blocked direct public export does not yet append a separate durable audit log.",
    ),
    PolicyCoverageEntry(
        route_id="cli.federation.export",
        surface="cli",
        operation="export_federation_bundle",
        decision_point="federate_export",
        status="covered",
        read_or_export_effect=True,
        enforcement=["local federation policy and generic policy-plugin checks block unauthorized export"],
        audit=["federation audit log records local-policy and policy-plugin export decisions when audit path is supplied"],
        tests=["tests/test_federation.py"],
        caveat="Audit durability depends on callers supplying an audit log path.",
    ),
    PolicyCoverageEntry(
        route_id="cli.federation.import_quarantine",
        surface="cli",
        operation="import_federation_bundle_to_quarantine",
        decision_point="federate_import",
        status="covered",
        durable_memory_change=True,
        enforcement=["signature/content-hash verification, local federation policy, and generic policy-plugin checks block unauthorized quarantine import"],
        audit=["federation audit log records quarantine/rejection decisions when audit path is supplied"],
        tests=["tests/test_federation.py"],
        caveat="Audit durability depends on callers supplying an audit log path.",
    ),
    PolicyCoverageEntry(
        route_id="cli.federation.promote_quarantine",
        surface="cli",
        operation="promote_quarantine_bundle",
        decision_point="promote",
        status="covered",
        durable_memory_change=True,
        enforcement=["local federation policy, conflict planning, and generic policy-plugin checks block unauthorized promotion"],
        audit=["federation audit log records promotion/rejection decisions when audit path is supplied"],
        tests=["tests/test_federation.py"],
        caveat="Audit durability depends on callers supplying an audit log path.",
    ),
    PolicyCoverageEntry(
        route_id="cli.graph_augment.write_candidates",
        surface="cli",
        operation="augment_store_relations_from_claims",
        decision_point="propose",
        status="covered",
        durable_memory_change=True,
        enforcement=["dry-run by default", "sensitive/private/no-export records are screened before candidate generation", "--policy-plugins blocks deny/hard_gate before candidate relation or review-candidate writes"],
        audit=["soft decisions recorded in write_summary", "--audit-log writes JSONL graph policy preflight events for allowed and blocked policy decisions"],
        tests=["tests/test_graph_augment.py", "tests/test_graph_maintenance.py", "tests/test_export_guardrails.py"],
        caveat="Durable audit output depends on callers supplying an audit log path.",
    ),
    PolicyCoverageEntry(
        route_id="cli.graph_maintenance.apply",
        surface="cli",
        operation="run_graph_maintenance_slice",
        decision_point="propose",
        status="covered",
        durable_memory_change=True,
        enforcement=["dry-run unless --apply is supplied", "bounded profiles, state files, locks, stale-lock recovery", "delegates sensitive-record screening and policy-plugin write gating to graph backfill"],
        audit=["soft decisions recorded in write_summary and maintenance run history when state advances", "--audit-log writes JSONL graph policy preflight events for allowed and blocked policy decisions"],
        tests=["tests/test_graph_maintenance.py"],
        caveat="Durable audit output depends on callers supplying an audit log path.",
    ),
    PolicyCoverageEntry(
        route_id="cli.import",
        surface="cli",
        operation="run_groundrecall_import",
        decision_point="propose",
        status="partial",
        durable_memory_change=True,
        enforcement=["imports create review candidates/proposals rather than canonical truth"],
        audit=["import output contains provenance, graph diagnostics, and candidate files"],
        tests=["tests/test_groundrecall_import.py", "tests/test_groundrecall_source_adapters.py"],
        caveat="Import proposal generation is not yet policy-plugin gated; canonical promotion is separately gated.",
    ),
    PolicyCoverageEntry(
        route_id="cli.index.rebuild",
        surface="derived_projection",
        operation="build_search_index",
        decision_point="read",
        status="intentionally_ungated",
        read_or_export_effect=True,
        enforcement=["index is a rebuildable local projection over existing store state"],
        audit=["no durable memory change"],
        tests=["tests/test_search_index.py"],
        caveat="Index rebuilding should remain constrained by filesystem access and release-filtered query/export surfaces.",
    ),
    PolicyCoverageEntry(
        route_id="cli.query",
        surface="cli",
        operation="query_store",
        decision_point="query",
        status="partial",
        read_or_export_effect=True,
        enforcement=["query output carries provenance, contradiction, supersession, release, graph, and confidence context where available"],
        audit=["no policy-plugin gate or durable read audit for direct CLI query"],
        tests=["tests/test_groundrecall_query.py", "tests/test_groundrecall_namespace.py"],
        caveat="Direct CLI query does not yet accept policy-plugin configs; MCP query does.",
    ),
    PolicyCoverageEntry(
        route_id="future.exceptional_erasure",
        surface="future",
        operation="exceptional_erasure",
        decision_point="delete",
        status="future",
        durable_memory_change=True,
        enforcement=["planned destructive-operation policy gate"],
        audit=["planned minimal non-sensitive tombstone and denied-write audit"],
        tests=[],
        caveat="No exceptional-erasure execution path exists yet.",
    ),
)


def build_policy_coverage_report(*, compact: bool = False) -> dict[str, Any]:
    entries = [entry.model_dump(mode="json") for entry in POLICY_COVERAGE_ENTRIES]
    status_counts = Counter(entry["status"] for entry in entries)
    surface_counts = Counter(entry["surface"] for entry in entries)
    durable_entries = [entry for entry in entries if entry["durable_memory_change"]]
    durable_status_counts = Counter(entry["status"] for entry in durable_entries)
    partial_or_future = [entry for entry in entries if entry["status"] in {"partial", "future"}]
    payload: dict[str, Any] = {
        "schema_version": POLICY_COVERAGE_SCHEMA_VERSION,
        "summary": {
            "route_count": len(entries),
            "covered_route_count": status_counts.get("covered", 0),
            "partial_route_count": status_counts.get("partial", 0),
            "intentionally_ungated_route_count": status_counts.get("intentionally_ungated", 0),
            "future_route_count": status_counts.get("future", 0),
            "durable_mutation_route_count": len(durable_entries),
            "covered_durable_mutation_route_count": durable_status_counts.get("covered", 0),
            "partial_durable_mutation_route_count": durable_status_counts.get("partial", 0),
            "future_durable_mutation_route_count": durable_status_counts.get("future", 0),
            "read_or_export_route_count": sum(1 for entry in entries if entry["read_or_export_effect"]),
        },
        "status_counts": dict(sorted(status_counts.items())),
        "surface_counts": dict(sorted(surface_counts.items())),
        "open_items": [
            {
                "route_id": entry["route_id"],
                "status": entry["status"],
                "operation": entry["operation"],
                "caveat": entry["caveat"],
            }
            for entry in partial_or_future
        ],
    }
    if not compact:
        payload["routes"] = entries
    return payload
