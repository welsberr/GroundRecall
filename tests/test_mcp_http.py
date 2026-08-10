from __future__ import annotations

import json
import re
import pytest

from groundrecall.mcp_http import DEFAULT_READ_ONLY_TOOLS, MCPHTTPApplication, MCPHTTPConfig


def test_http_mcp_requires_server_policy_and_exposes_read_only_tools(tmp_path) -> None:
    policy = tmp_path / "policy.yaml"
    policy.write_text("schema_version: groundrecall.policy_plugins.v1\nproviders: []\n", encoding="utf-8")
    app = MCPHTTPApplication(MCPHTTPConfig(policy_config=str(policy), subject_id="alice", bearer_token="secret"))
    with pytest.raises(PermissionError, match="invalid bearer"):
        app.dispatch({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, token="wrong")
    listed = json.loads(app.dispatch({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, token="secret"))
    names = {tool["name"] for tool in listed["result"]["tools"]}
    assert names == set(DEFAULT_READ_ONLY_TOOLS)
    assert all(tool["annotations"]["readOnlyHint"] is True for tool in listed["result"]["tools"])
    blocked = json.loads(app.dispatch({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "export_snapshot", "arguments": {"store_dir": str(tmp_path), "out_dir": str(tmp_path / "out")}}}, token="secret"))
    assert blocked["error"]["code"] == -32003


def test_http_application_requires_server_policy_and_rejects_unknown_tool(tmp_path) -> None:
    with pytest.raises(ValueError, match="server policy"):
        MCPHTTPApplication(MCPHTTPConfig(policy_config=""))
    with pytest.raises(ValueError, match="existing policy file"):
        MCPHTTPApplication(MCPHTTPConfig(policy_config=str(tmp_path / "missing.yaml")))
    policy = tmp_path / "policy.yaml"; policy.write_text("schema_version: groundrecall.policy_plugins.v1\nproviders: []\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unknown MCP tools"):
        MCPHTTPApplication(MCPHTTPConfig(policy_config=str(policy), allowed_tools=frozenset({"missing"})))


def test_http_identity_file_caps_subject_tools_and_release(tmp_path) -> None:
    policy = tmp_path / "policy.yaml"; policy.write_text("schema_version: groundrecall.policy_plugins.v1\nproviders: []\n", encoding="utf-8")
    identity = tmp_path / "identities.json"
    identity.write_text(json.dumps({"identities": [{"token": "alice-token", "subject_id": "alice", "realm_id": "project:alpha", "maximum_release_level": "internal", "allowed_tools": ["search_store"]}]}), encoding="utf-8")
    app = MCPHTTPApplication(MCPHTTPConfig(policy_config=str(policy), identity_file=str(identity)))
    listed = json.loads(app.dispatch({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, token="alice-token"))
    assert {tool["name"] for tool in listed["result"]["tools"]} == {"search_store"}
    with pytest.raises(PermissionError, match="unknown bearer"):
        app.dispatch({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, token="wrong")


def test_http_identity_file_cannot_enable_anonymous_mode(tmp_path) -> None:
    policy = tmp_path / "policy.yaml"
    policy.write_text("schema_version: groundrecall.policy_plugins.v1\nproviders: []\n", encoding="utf-8")
    identity = tmp_path / "identities.json"
    identity.write_text(json.dumps({"identities": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="at least one identity"):
        MCPHTTPApplication(MCPHTTPConfig(policy_config=str(policy), identity_file=str(identity)))


def test_http_responses_include_server_generated_correlation_ids(tmp_path) -> None:
    policy = tmp_path / "policy.yaml"
    policy.write_text("schema_version: groundrecall.policy_plugins.v1\nproviders: []\n", encoding="utf-8")
    app = MCPHTTPApplication(MCPHTTPConfig(policy_config=str(policy), subject_id="alice"))
    first = json.loads(app.dispatch({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}))
    second = json.loads(app.dispatch({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}))
    first_id = first["_meta"]["groundrecall"]["correlation_id"]
    second_id = second["_meta"]["groundrecall"]["correlation_id"]
    assert re.fullmatch(r"[0-9a-f]{32}", first_id)
    assert re.fullmatch(r"[0-9a-f]{32}", second_id)
    assert first_id != second_id


def test_http_injects_correlation_and_realm_metadata_into_policy_request(tmp_path, monkeypatch) -> None:
    policy = tmp_path / "policy.yaml"
    policy.write_text("schema_version: groundrecall.policy_plugins.v1\nproviders: []\n", encoding="utf-8")
    identity = tmp_path / "identities.json"
    identity.write_text(json.dumps({"identities": [{"token": "alice-token", "subject_id": "alice", "realm_id": "project:alpha", "allowed_tools": ["search_store"]}]}), encoding="utf-8")
    app = MCPHTTPApplication(MCPHTTPConfig(policy_config=str(policy), identity_file=str(identity)))
    captured = {}

    def fake_handle(request):
        captured.update(request["params"]["arguments"])
        return {"jsonrpc": "2.0", "id": request["id"], "result": {"ok": True}}

    monkeypatch.setattr("groundrecall.mcp_http.handle_request", fake_handle)
    body = app.dispatch({"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": "search_store", "arguments": {"policy_request": {"subject_id": "spoof"}}}}, token="alice-token")
    response = json.loads(body)
    correlation_id = response["_meta"]["groundrecall"]["correlation_id"]
    metadata = captured["policy_request"]["metadata"]
    assert metadata == {"groundrecall.correlation_id": correlation_id, "groundrecall.realm_id": "project:alpha"}
    assert captured["subject_id"] == "alice"


def test_http_optional_audit_log_records_safe_access_decisions(tmp_path) -> None:
    policy = tmp_path / "policy.yaml"
    policy.write_text("schema_version: groundrecall.policy_plugins.v1\nproviders: []\n", encoding="utf-8")
    audit = tmp_path / "audit" / "mcp.jsonl"
    app = MCPHTTPApplication(MCPHTTPConfig(policy_config=str(policy), subject_id="alice",
                                            bearer_token="secret", audit_log_path=str(audit)))
    listed = json.loads(app.dispatch({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, token="secret"))
    correlation_id = listed["_meta"]["groundrecall"]["correlation_id"]
    blocked = json.loads(app.dispatch({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                       "params": {"name": "export_snapshot", "arguments": {"prompt": "do not log"}}}, token="secret"))
    assert blocked["error"]["code"] == -32003
    rows = [json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2
    assert rows[0]["correlation_id"] == correlation_id
    assert rows[0]["subject_id"] == "alice"
    assert rows[0]["decision"] == "allowed"
    assert rows[1]["decision"] == "denied"
    assert rows[1]["reason"] == "tool_not_enabled"
    assert all("prompt" not in row and "secret" not in json.dumps(row) for row in rows)


def test_http_audit_is_opt_in(tmp_path) -> None:
    policy = tmp_path / "policy.yaml"
    policy.write_text("schema_version: groundrecall.policy_plugins.v1\nproviders: []\n", encoding="utf-8")
    app = MCPHTTPApplication(MCPHTTPConfig(policy_config=str(policy), subject_id="alice"))
    app.dispatch({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert not list(tmp_path.glob("**/*.jsonl"))
