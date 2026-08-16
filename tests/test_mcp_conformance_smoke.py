"""Offline MCP HTTP/stdio conformance smoke checks."""
import json

from groundrecall.mcp import handle_request
from groundrecall.mcp_http import MCPHTTPApplication, MCPHTTPConfig


def test_stdio_conformance_initialize_list_and_bounded_read(tmp_path):
    policy = tmp_path / "policy.yaml"
    policy.write_text("schema_version: groundrecall.policy_plugins.v1\nproviders: []\n", encoding="utf-8")
    store = tmp_path / "store"; store.mkdir()
    init = handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    listed = handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert init["result"]["serverInfo"]["name"] == "groundrecall-mcp"
    assert any(tool["name"] == "handoff_state" for tool in listed["result"]["tools"])
    read = handle_request({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "inspect_store", "arguments": {"store_dir": str(store), "policy_config": str(policy)}}})
    assert read["result"]


def test_http_conformance_readiness_policy_denial_and_timeout_mapping(tmp_path):
    policy = tmp_path / "policy.yaml"
    policy.write_text("schema_version: groundrecall.policy_plugins.v1\nproviders: []\n", encoding="utf-8")
    store = tmp_path / "store"; store.mkdir()
    app = MCPHTTPApplication(MCPHTTPConfig(policy_config=str(policy), store_dir=str(store), allowed_tools=frozenset({"inspect_store"})))
    ready, payload = app.readiness()
    assert ready and payload["checks"]["policy"] and payload["checks"]["store"]
    initialize = json.loads(app.dispatch({"jsonrpc": "2.0", "id": 1, "method": "initialize"}))
    assert initialize["result"]["serverInfo"]["name"] == "groundrecall-mcp-http"
    denied = json.loads(app.dispatch({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "handoff_state", "arguments": {}}}))
    assert denied["error"]["code"] == -32003
    listed = json.loads(app.dispatch({"jsonrpc": "2.0", "id": 3, "method": "tools/list"}))
    assert [tool["name"] for tool in listed["result"]["tools"]] == ["inspect_store"]
