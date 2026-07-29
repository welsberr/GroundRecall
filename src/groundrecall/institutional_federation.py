"""Contract fixtures and capability reporting for institutional federation.

This module deliberately reports roadmap capability; it does not implement the
institutional record types.  Keeping the report versioned gives later work a
stable, machine-readable baseline for the preprint and policy-coverage checks.
"""

from __future__ import annotations

from typing import Any


INSTITUTIONAL_FEDERATION_SCHEMA_VERSION = "groundrecall.institutional_federation_capability.v1"
INSTITUTIONAL_POLICY_FIXTURE_SCHEMA_VERSION = "groundrecall.institutional_policy_fixtures.v1"


INSTITUTIONAL_POLICY_ACTIONS: tuple[dict[str, str], ...] = (
    {"operation": "discover_scope_catalog", "decision_point": "query", "action": "discover_federation_catalog"},
    {"operation": "read_protected_catalog_entry", "decision_point": "read", "action": "read_federation_catalog_entry"},
    {"operation": "propose_group_contribution", "decision_point": "propose", "action": "propose_group_contribution"},
    {"operation": "review_group_contribution", "decision_point": "review", "action": "review_group_contribution"},
    {"operation": "accept_group_contribution", "decision_point": "promote", "action": "accept_group_contribution"},
    {"operation": "publish_scope_catalog", "decision_point": "federate_export", "action": "publish_federation_catalog"},
    {"operation": "import_scope_catalog", "decision_point": "federate_import", "action": "import_federation_catalog"},
    {"operation": "manage_federation_subscription", "decision_point": "act", "action": "manage_federation_subscription"},
    {"operation": "export_incremental_changes", "decision_point": "federate_export", "action": "export_incremental_changes"},
    {"operation": "import_incremental_changes", "decision_point": "federate_import", "action": "import_incremental_changes"},
    {"operation": "record_federation_feedback", "decision_point": "propose", "action": "record_federation_feedback"},
    {"operation": "transfer_knowledge_custody", "decision_point": "act", "action": "transfer_knowledge_custody"},
    {"operation": "retire_federation_instance", "decision_point": "act", "action": "retire_federation_instance"},
    {"operation": "generate_scope_orientation", "decision_point": "query", "action": "generate_scope_orientation"},
    {"operation": "generate_stewardship_view", "decision_point": "query", "action": "generate_stewardship_view"},
    {"operation": "generate_change_impact_report", "decision_point": "query", "action": "generate_change_impact_report"},
    {"operation": "publish_knowledge_release_pack", "decision_point": "publish", "action": "publish_knowledge_release_pack"},
    {"operation": "withdraw_knowledge_release", "decision_point": "supersede", "action": "withdraw_knowledge_release"},
)


def build_institutional_federation_capability_report(*, compact: bool = False) -> dict[str, Any]:
    """Return a deterministic capability baseline for institutional federation."""

    items = [
        {
            "capability_id": "policy_plugin_contract",
            "status": "implemented",
            "evidence": ["docs/policy-plugin-spec.md", "src/groundrecall/policy.py", "tests/test_policy_plugins.py"],
        },
        {
            "capability_id": "signed_bundle_exchange",
            "status": "implemented",
            "evidence": ["src/groundrecall/federation.py", "tests/test_federation.py"],
        },
        {
            "capability_id": "institutional_scope_and_work_records",
            "status": "partial",
            "evidence": [
                "src/groundrecall/models.py",
                "src/groundrecall/store.py",
                "src/groundrecall/institutional_records.py",
                "tests/test_institutional_federation.py",
                "docs/institutional-federation-implementation-roadmap.md#IF-01",
            ],
        },
        {
            "capability_id": "stewardship_and_custody_records",
            "status": "future",
            "evidence": ["docs/institutional-federation-implementation-roadmap.md#IF-02"],
        },
        {
            "capability_id": "contribution_review_lifecycle",
            "status": "future",
            "evidence": ["docs/institutional-federation-implementation-roadmap.md#IF-02"],
        },
        {
            "capability_id": "prior_work_discovery",
            "status": "partial",
            "evidence": [
                "src/groundrecall/prior_work.py",
                "tests/test_prior_work.py",
                "docs/institutional-federation-implementation-roadmap.md#IF-04",
            ],
        },
        {
            "capability_id": "signed_federation_catalogs",
            "status": "future",
            "evidence": ["docs/institutional-federation-implementation-roadmap.md#IF-05"],
        },
        {
            "capability_id": "incremental_change_subscriptions",
            "status": "future",
            "evidence": ["docs/institutional-federation-implementation-roadmap.md#IF-06"],
        },
        {
            "capability_id": "multi_party_review_feedback",
            "status": "future",
            "evidence": ["docs/institutional-federation-implementation-roadmap.md#IF-07"],
        },
        {
            "capability_id": "custody_transfer_and_instance_retirement",
            "status": "future",
            "evidence": ["docs/institutional-federation-implementation-roadmap.md#IF-08"],
        },
        {
            "capability_id": "institutional_views_and_impact_routing",
            "status": "future",
            "evidence": ["docs/institutional-federation-implementation-roadmap.md#IF-09"],
        },
        {
            "capability_id": "license_aware_release_withdrawal",
            "status": "future",
            "evidence": ["docs/institutional-federation-implementation-roadmap.md#IF-10"],
        },
    ]
    if compact:
        return {
            "schema_version": INSTITUTIONAL_FEDERATION_SCHEMA_VERSION,
            "summary": {
                "implemented": sum(item["status"] == "implemented" for item in items),
                "partial": sum(item["status"] == "partial" for item in items),
                "future": sum(item["status"] == "future" for item in items),
            },
        }
    return {
        "schema_version": INSTITUTIONAL_FEDERATION_SCHEMA_VERSION,
        "roadmap_date": "2026-07-29",
        "policy_action_count": len(INSTITUTIONAL_POLICY_ACTIONS),
        "policy_actions": list(INSTITUTIONAL_POLICY_ACTIONS),
        "capabilities": items,
        "summary": {
            "implemented": sum(item["status"] == "implemented" for item in items),
            "partial": sum(item["status"] == "partial" for item in items),
            "future": sum(item["status"] == "future" for item in items),
        },
    }
