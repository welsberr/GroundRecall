from __future__ import annotations

from pathlib import Path
import json

from groundrecall.catalog import build_federation_catalog
from groundrecall.change_feed import FederationSubscription, save_subscription
from groundrecall.mcp import handle_request
from groundrecall.models import ClaimRecord, ConceptRecord, ScopeRecord, StewardshipRecord, WorkRecord
from groundrecall.prior_work import prior_work_search
from groundrecall.store import GroundRecallStore


KEY = "mcp signing secret"


def test_mcp_lists_tools() -> None:
    response = handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    tools = response["result"]["tools"]
    names = {tool["name"] for tool in tools}
    assert {
        "inspect_store",
        "query_concept",
        "search_store",
        "export_snapshot",
        "evaluate_policy",
        "prior_work_review",
        "catalog_discovery",
        "subscription_status",
        "impact_report",
        "stewardship_orphans",
        "propose_contribution",
        "epistemap_assessment",
    } <= names
    search_schema = next(tool["inputSchema"] for tool in tools if tool["name"] == "search_store")
    assert "policy_config" in search_schema["properties"]
    assert "policy_request" in search_schema["properties"]


def test_mcp_epistemap_assessment_is_policy_gated_and_read_only() -> None:
    graph = {"graph_id": "mcp-graph", "nodes": [{"id": "claim", "type": "claim", "title": "Claim"}], "edges": []}
    response = handle_request({"jsonrpc": "2.0", "id": 20, "method": "tools/call", "params": {"name": "epistemap_assessment", "arguments": {"graph_bundle": graph, "operation": "diagnostics"}}})
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["schema_version"] == "groundrecall.mcp.epistemap_assessment.v1"
    assert payload["payload"]["summary"]["node_count"] == 1


def test_mcp_initializes() -> None:
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05"},
        }
    )
    assert response["result"]["serverInfo"]["name"] == "groundrecall-mcp"
    assert "tools" in response["result"]["capabilities"]


def test_mcp_reports_unknown_tool() -> None:
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "missing", "arguments": {}},
        }
    )
    assert response["error"]["code"] == -32000
    assert "Unknown tool" in response["error"]["message"]


def test_mcp_evaluates_policy_plugin_config(tmp_path: Path) -> None:
    policy_root = tmp_path / "claimwright"
    (policy_root / "policies").mkdir(parents=True)
    (policy_root / "policies" / "enforcement.yaml").write_text(
        "\n".join(
            [
                "version: 0.1",
                "defaults:",
                "  public_release: hard_gate",
            ]
        ),
        encoding="utf-8",
    )
    (policy_root / "policies" / "claim_states.yaml").write_text(
        "\n".join(
            [
                "version: 0.1",
                "claim_states:",
                "  - id: private_only_speculation",
                "    public_allowed: false",
            ]
        ),
        encoding="utf-8",
    )
    config = tmp_path / "policy-plugins.yaml"
    config.write_text(
        "\n".join(
            [
                "policy_id: mcp.test.policy",
                "providers:",
                "  - type: claimwright.directory",
                f"    root_dir: {policy_root}",
            ]
        ),
        encoding="utf-8",
    )

    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "evaluate_policy",
                "arguments": {
                    "policy_config": str(config),
                    "request": {
                        "decision_point": "publish",
                        "public_facing": True,
                        "claim_state": "private_only_speculation",
                    },
                },
            },
        }
    )

    text = response["result"]["content"][0]["text"]
    assert '"decision": "hard_gate"' in text
    assert "claim_state_not_public_allowed:private_only_speculation" in text


def test_mcp_policy_hard_gate_blocks_operation_before_store_access(tmp_path: Path) -> None:
    config = tmp_path / "policy-plugins.yaml"
    config.write_text(
        "\n".join(
            [
                "policy_id: mcp.blocking.policy",
                "providers:",
                "  - type: static",
                "    policy_id: test.hard_gate",
                "    default_decision: hard_gate",
            ]
        ),
        encoding="utf-8",
    )

    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "search_store",
                "arguments": {
                    "store_dir": str(tmp_path / "missing-store"),
                    "query": "memory",
                    "policy_config": str(config),
                    "subject_id": "agent-1",
                },
            },
        }
    )

    text = response["result"]["content"][0]["text"]
    assert '"blocked_by_policy": true' in text
    assert '"decision": "hard_gate"' in text
    assert "test.hard_gate" in text


def _seed_institutional_store(store: GroundRecallStore) -> None:
    store.save_scope(ScopeRecord(scope_id="scope-a", scope_kind="project", title="Scope A", release_level="public", current_status="reviewed"))
    store.save_concept(ConceptRecord(concept_id="concept::alpha", title="Alpha", current_status="reviewed"))
    store.save_work(
        WorkRecord(
            work_id="work-a",
            work_kind="project",
            title="Alpha project",
            scope_id="scope-a",
            related_claim_ids=["claim-a"],
            release_level="public",
            current_status="reviewed",
        )
    )
    store.save_claim(
        ClaimRecord(
            claim_id="claim-a",
            claim_text="Alpha claim.",
            concept_ids=["concept::alpha"],
            metadata={"scope_id": "scope-a", "release_level": "public"},
            current_status="reviewed",
        )
    )
    store.save_stewardship(
        StewardshipRecord(
            stewardship_id="steward-a",
            subject_type="scope",
            subject_id="scope-a",
            scope_id="scope-a",
            steward_principal_id="alice",
            steward_role_id="scope-steward",
            release_level="public",
            status="active",
            current_status="reviewed",
        )
    )


def _mcp_payload(response: dict) -> dict:
    return json.loads(response["result"]["content"][0]["text"])


def test_mcp_prior_work_matches_local_api(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    _seed_institutional_store(store)
    local = prior_work_search(store.base_dir, "Alpha", scope_id="scope-a", maximum_release_level="public", limit=5)

    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {
                "name": "prior_work_review",
                "arguments": {
                    "store_dir": str(store.base_dir),
                    "query": "Alpha",
                    "scope_id": "scope-a",
                    "maximum_release_level": "public",
                    "limit": 5,
                },
            },
        }
    )

    payload = _mcp_payload(response)
    assert payload["candidate_count"] == local.candidate_count
    assert payload["candidates"][0]["candidate_id"] == local.candidates[0].candidate_id


def test_mcp_catalog_subscription_impact_and_stewardship_tools(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    _seed_institutional_store(store)
    catalog_path = tmp_path / "catalog.json"
    build_federation_catalog(
        store.base_dir,
        producer_instance_id="host-a",
        target_release_level="public",
        detail_level="descriptive",
        signing_key=KEY,
        key_id="k1",
        signature_algorithm="hmac-sha256",
        out_path=catalog_path,
    )
    subscription_path = tmp_path / "subscription.json"
    save_subscription(
        subscription_path,
        FederationSubscription(subscription_id="sub-a", producer_instance_id="host-a", scope_ids=["scope-a"], cursor="cursor-1", maximum_release_level="public"),
    )

    catalog = _mcp_payload(
        handle_request(
            {
                "jsonrpc": "2.0",
                "id": 7,
                "method": "tools/call",
                "params": {"name": "catalog_discovery", "arguments": {"catalog_path": str(catalog_path), "query": "Scope"}},
            }
        )
    )
    status = _mcp_payload(
        handle_request(
            {
                "jsonrpc": "2.0",
                "id": 8,
                "method": "tools/call",
                "params": {"name": "subscription_status", "arguments": {"subscription_path": str(subscription_path)}},
            }
        )
    )
    impact = _mcp_payload(
        handle_request(
            {
                "jsonrpc": "2.0",
                "id": 9,
                "method": "tools/call",
                "params": {"name": "impact_report", "arguments": {"store_dir": str(store.base_dir), "subject_type": "claim", "subject_record_id": "claim-a", "release_cap": "public"}},
            }
        )
    )
    stewardship = _mcp_payload(
        handle_request(
            {
                "jsonrpc": "2.0",
                "id": 10,
                "method": "tools/call",
                "params": {"name": "stewardship_orphans", "arguments": {"store_dir": str(store.base_dir), "release_cap": "public"}},
            }
        )
    )

    assert catalog["entry_count"] == 1
    assert status["subscription_id"] == "sub-a"
    assert impact["subject_id"] == "claim-a"
    assert stewardship["stewardship"]["entries"][0]["basis"] == "explicit_stewardship_record"
    assert "raw_activity_rankings_suppressed" in stewardship["stewardship"]["unavailable_evidence"]


def test_mcp_contribution_proposal_performs_no_writes(tmp_path: Path) -> None:
    store = GroundRecallStore(tmp_path / "store")
    _seed_institutional_store(store)

    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 11,
            "method": "tools/call",
            "params": {
                "name": "propose_contribution",
                "arguments": {
                    "contributor_id": "alice",
                    "destination_scope_id": "scope-a",
                    "contribution_intent": "Share reviewed result.",
                    "contributed_record_ids": ["claim-a"],
                    "proposed_release_level": "public",
                },
            },
        }
    )

    payload = _mcp_payload(response)
    assert payload["writes_performed"] is False
    assert payload["proposal"]["contributed_record_ids"] == ["claim-a"]
    assert store.list_contributions() == []
