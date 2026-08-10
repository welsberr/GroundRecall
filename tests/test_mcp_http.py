from __future__ import annotations

import json
import pytest

from groundrecall.mcp_http import DEFAULT_READ_ONLY_TOOLS, MCPHTTPApplication, MCPHTTPConfig


def test_http_mcp_requires_server_policy_and_exposes_read_only_tools(tmp_path) -> None:
    policy = tmp_path / "policy.yaml"
    policy.write_text("schema_version: groundrecall.policy_plugins.v1\nproviders: []\n", encoding="utf-8")
    app = MCPHTTPApplication(MCPHTTPConfig(policy_config=str(policy), subject_id="alice", bearer_token="secret"))
    listed = json.loads(app.dispatch({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}))
    names = {tool["name"] for tool in listed["result"]["tools"]}
    assert names == set(DEFAULT_READ_ONLY_TOOLS)
    assert all(tool["annotations"]["readOnlyHint"] is True for tool in listed["result"]["tools"])
    blocked = json.loads(app.dispatch({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "export_snapshot", "arguments": {"store_dir": str(tmp_path), "out_dir": str(tmp_path / "out")}}}))
    assert blocked["error"]["code"] == -32003


def test_http_application_requires_server_policy_and_rejects_unknown_tool(tmp_path) -> None:
    with pytest.raises(ValueError, match="server policy"):
        MCPHTTPApplication(MCPHTTPConfig(policy_config=""))
    with pytest.raises(ValueError, match="existing policy file"):
        MCPHTTPApplication(MCPHTTPConfig(policy_config=str(tmp_path / "missing.yaml")))
    policy = tmp_path / "policy.yaml"; policy.write_text("schema_version: groundrecall.policy_plugins.v1\nproviders: []\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unknown MCP tools"):
        MCPHTTPApplication(MCPHTTPConfig(policy_config=str(policy), allowed_tools=frozenset({"missing"})))
