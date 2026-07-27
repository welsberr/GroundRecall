from __future__ import annotations

from pathlib import Path

from groundrecall.mcp import handle_request


def test_mcp_lists_tools() -> None:
    response = handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    tools = response["result"]["tools"]
    names = {tool["name"] for tool in tools}
    assert {"inspect_store", "query_concept", "search_store", "export_snapshot", "evaluate_policy"} <= names
    search_schema = next(tool["inputSchema"] for tool in tools if tool["name"] == "search_store")
    assert "policy_config" in search_schema["properties"]
    assert "policy_request" in search_schema["properties"]


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
