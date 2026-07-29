"""Conformance scenarios for institutional federation paper evidence.

The report in this module is intentionally conservative.  It ties manuscript
and roadmap claims to implemented files, tests, policy actions, and explicit
future-work caveats; it is not a production-readiness certification.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from .institutional_federation import build_institutional_federation_capability_report
from .policy_coverage import build_policy_coverage_report


INSTITUTIONAL_CONFORMANCE_SCHEMA_VERSION = "groundrecall.institutional_conformance.v1"


SCENARIOS: tuple[dict[str, Any], ...] = (
    {
        "scenario_id": "group_knowledge_propagation",
        "issue": "Reviewed individual work can become group-visible knowledge without equating contribution with authority.",
        "status": "partial",
        "capability_ids": [
            "institutional_scope_and_work_records",
            "multi_party_review_feedback",
            "mcp_and_adapter_coverage",
        ],
        "policy_actions": [
            "propose_group_contribution",
            "review_group_contribution",
            "accept_group_contribution",
        ],
        "policy_routes": ["mcp.propose_contribution", "cli.review.quorum", "cli.review.feedback_bundle"],
        "evidence": [
            "src/groundrecall/models.py",
            "src/groundrecall/institutional_review.py",
            "src/groundrecall/mcp.py",
            "tests/test_institutional_review.py",
            "tests/test_mcp.py",
        ],
        "caveat": "MCP contribution proposals are no-write drafts; durable promotion remains separately gated.",
    },
    {
        "scenario_id": "silo_reduction_and_discovery",
        "issue": "Federation catalogs, subscriptions, and MCP discovery expose that relevant knowledge exists with release caps.",
        "status": "partial",
        "capability_ids": [
            "signed_federation_catalogs",
            "incremental_change_subscriptions",
            "mcp_and_adapter_coverage",
        ],
        "policy_actions": [
            "discover_federation_catalog",
            "read_federation_catalog_entry",
            "manage_federation_subscription",
        ],
        "policy_routes": ["mcp.catalog_discovery", "mcp.subscription_status", "cli.changes.ack"],
        "evidence": [
            "src/groundrecall/catalog.py",
            "src/groundrecall/change_feed.py",
            "src/groundrecall/mcp.py",
            "tests/test_catalog.py",
            "tests/test_change_feed.py",
            "tests/test_mcp.py",
        ],
        "caveat": "File-based exchange is implemented; network transport and protected-topic inference evaluation remain future work.",
    },
    {
        "scenario_id": "duplicate_effort_avoidance",
        "issue": "Prior-work search can surface related, negative, or inconclusive work before new durable effort begins.",
        "status": "partial",
        "capability_ids": ["prior_work_discovery", "mcp_and_adapter_coverage"],
        "policy_actions": ["propose_group_contribution", "generate_scope_orientation"],
        "policy_routes": ["mcp.prior_work_review", "cli.query"],
        "evidence": [
            "src/groundrecall/prior_work.py",
            "src/groundrecall/mcp.py",
            "tests/test_prior_work.py",
            "tests/test_mcp.py",
        ],
        "caveat": "Semantic duplicate confirmation remains review-gated and is not claimed as automatic adjudication.",
    },
    {
        "scenario_id": "knowledge_survival_after_tenancy_or_host_change",
        "issue": "Custody and retirement planning can preserve group knowledge after a person or host leaves.",
        "status": "partial",
        "capability_ids": ["custody_transfer_and_instance_retirement", "institutional_views_and_impact_routing"],
        "policy_actions": ["transfer_knowledge_custody", "retire_federation_instance", "generate_stewardship_view"],
        "policy_routes": ["python_api.custody.record_event", "mcp.stewardship_orphans", "cli.views.stewardship"],
        "evidence": [
            "src/groundrecall/institutional_custody.py",
            "src/groundrecall/institutional_views.py",
            "tests/test_institutional_custody.py",
            "tests/test_institutional_views.py",
            "tests/test_mcp.py",
        ],
        "caveat": "The implemented lifecycle slice is dry-run/planning oriented; destructive apply operations remain future work.",
    },
    {
        "scenario_id": "controlled_reuse_and_public_release",
        "issue": "Release packs and withdrawal notices preserve attribution, license checks, provenance visibility, and withdrawal state.",
        "status": "partial",
        "capability_ids": ["license_aware_release_withdrawal"],
        "policy_actions": ["publish_knowledge_release_pack", "withdraw_knowledge_release"],
        "policy_routes": ["cli.release.pack", "cli.release.withdraw"],
        "evidence": [
            "src/groundrecall/institutional_release.py",
            "tests/test_institutional_release.py",
            "docs/preprint/2026-elsberry-governed-memory-layer-principles-r01-source.md",
        ],
        "caveat": "Publication gatekeeping is represented; this is not a hosted publication workflow.",
    },
    {
        "scenario_id": "policy_governed_assistant_surface",
        "issue": "Assistant-facing tools can return policy findings and avoid treating policy findings as permission grants.",
        "status": "partial",
        "capability_ids": ["policy_plugin_contract", "mcp_and_adapter_coverage"],
        "policy_actions": [
            "discover_federation_catalog",
            "propose_group_contribution",
            "generate_change_impact_report",
            "generate_stewardship_view",
        ],
        "policy_routes": [
            "mcp.catalog_discovery",
            "mcp.propose_contribution",
            "mcp.impact_report",
            "mcp.stewardship_orphans",
        ],
        "evidence": [
            "docs/policy-plugin-spec.md",
            "src/groundrecall/policy.py",
            "src/groundrecall/mcp.py",
            "tests/test_policy_plugins.py",
            "tests/test_mcp.py",
        ],
        "caveat": "MCP policy checks remain caller-supplied in this slice; mandatory server policy configuration remains future work.",
    },
)


def build_institutional_conformance_report(*, compact: bool = False) -> dict[str, Any]:
    """Return deterministic IF-12 conformance evidence for roadmap/preprint use."""

    capability_report = build_institutional_federation_capability_report()
    policy_report = build_policy_coverage_report()
    capability_status = {item["capability_id"]: item["status"] for item in capability_report["capabilities"]}
    route_status = {item["route_id"]: item["status"] for item in policy_report["routes"]}

    scenarios = []
    for scenario in SCENARIOS:
        scenario_payload = dict(scenario)
        scenario_payload["capability_status"] = {
            capability_id: capability_status.get(capability_id, "unknown")
            for capability_id in scenario["capability_ids"]
        }
        scenario_payload["policy_route_status"] = {
            route_id: route_status.get(route_id, "unknown") for route_id in scenario["policy_routes"]
        }
        scenarios.append(scenario_payload)

    status_counts = Counter(item["status"] for item in scenarios)
    summary = {
        "scenario_count": len(scenarios),
        "partial_scenario_count": status_counts.get("partial", 0),
        "covered_policy_action_count": len({action for item in scenarios for action in item["policy_actions"]}),
        "evidence_file_count": len({path for item in scenarios for path in item["evidence"]}),
    }
    if compact:
        return {
            "schema_version": INSTITUTIONAL_CONFORMANCE_SCHEMA_VERSION,
            "summary": summary,
        }
    return {
        "schema_version": INSTITUTIONAL_CONFORMANCE_SCHEMA_VERSION,
        "roadmap_package": "IF-12",
        "claim_boundary": (
            "Conformance scenarios record implemented engineering evidence and explicit caveats; "
            "they do not certify production deployment, complete security, or benchmark superiority."
        ),
        "summary": summary,
        "scenarios": scenarios,
    }
