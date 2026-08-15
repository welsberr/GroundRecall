from __future__ import annotations

import json
import re
import pytest

from groundrecall.mcp_http import (
    DEFAULT_READ_ONLY_TOOLS,
    MCPHTTPApplication,
    MCPHTTPConfig,
    MCP_HTTP_PROTOCOL_VERSION,
    MCP_HTTP_SERVER_INFO,
    MCP_HTTP_MIN_RESPONSE_BYTES,
    _bounded_response_body,
    verify_audit_log,
)
from groundrecall.mcp_audit_verify import main as verify_audit_cli


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


def test_http_handoff_lifecycle_writes_are_opt_in(tmp_path) -> None:
    policy = tmp_path / "policy.yaml"
    policy.write_text("schema_version: groundrecall.policy_plugins.v1\nproviders: []\n", encoding="utf-8")
    default = MCPHTTPApplication(MCPHTTPConfig(policy_config=str(policy), subject_id="alice"))
    listed = json.loads(default.dispatch({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}))
    names = {tool["name"] for tool in listed["result"]["tools"]}
    assert "handoff_events" in names
    assert "handoff_update_status" not in names
    app = MCPHTTPApplication(MCPHTTPConfig(policy_config=str(policy), subject_id="alice", allowed_tools=frozenset({"handoff_update_status", "handoff_events"})))
    listed = json.loads(app.dispatch({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}))
    annotations = {tool["name"]: tool["annotations"]["readOnlyHint"] for tool in listed["result"]["tools"]}
    assert annotations == {"handoff_update_status": False, "handoff_events": True}


def test_http_mcp_initialize_and_ping_return_stable_transport_handshake(tmp_path) -> None:
    policy = tmp_path / "policy.yaml"
    policy.write_text("schema_version: groundrecall.policy_plugins.v1\nproviders: []\n", encoding="utf-8")
    app = MCPHTTPApplication(MCPHTTPConfig(policy_config=str(policy), subject_id="alice"))

    initialized = json.loads(app.dispatch({
        "jsonrpc": "2.0",
        "id": "init-1",
        "method": "initialize",
        "params": {
            "protocolVersion": "1999-01-01",
            "clientInfo": {"name": "test-client", "version": "1"},
            "policy_config": "/should-never-appear",
        },
    }))
    assert initialized["id"] == "init-1"
    assert initialized["result"]["protocolVersion"] == MCP_HTTP_PROTOCOL_VERSION
    assert initialized["result"]["serverInfo"] == MCP_HTTP_SERVER_INFO
    assert "/should-never-appear" not in json.dumps(initialized)
    assert initialized["result"]["capabilities"] == {"tools": {"listChanged": False}}

    ping = json.loads(app.dispatch({"jsonrpc": "2.0", "id": 2, "method": "ping"}))
    assert ping["result"] == {}
    assert ping["_meta"]["groundrecall"]["correlation_id"]


def test_http_mcp_rejects_unsupported_method_without_calling_tool_core(tmp_path) -> None:
    policy = tmp_path / "policy.yaml"
    policy.write_text("schema_version: groundrecall.policy_plugins.v1\nproviders: []\n", encoding="utf-8")
    app = MCPHTTPApplication(MCPHTTPConfig(policy_config=str(policy), subject_id="alice"))
    response = json.loads(app.dispatch({"jsonrpc": "2.0", "id": 3, "method": "resources/list"}))
    assert response["id"] == 3
    assert response["error"]["code"] == -32000
    assert "Unsupported method" in response["error"]["message"]


def test_http_application_requires_server_policy_and_rejects_unknown_tool(tmp_path) -> None:
    with pytest.raises(ValueError, match="server policy"):
        MCPHTTPApplication(MCPHTTPConfig(policy_config=""))
    with pytest.raises(ValueError, match="existing policy file"):
        MCPHTTPApplication(MCPHTTPConfig(policy_config=str(tmp_path / "missing.yaml")))
    policy = tmp_path / "policy.yaml"; policy.write_text("schema_version: groundrecall.policy_plugins.v1\nproviders: []\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unknown MCP tools"):
        MCPHTTPApplication(MCPHTTPConfig(policy_config=str(policy), allowed_tools=frozenset({"missing"})))


def test_http_readiness_is_bounded_and_checks_policy_store(tmp_path) -> None:
    policy = tmp_path / "policy.yaml"
    policy.write_text("schema_version: groundrecall.policy_plugins.v1\nproviders: []\n", encoding="utf-8")
    not_ready = MCPHTTPApplication(MCPHTTPConfig(policy_config=str(policy)))
    ready, payload = not_ready.readiness()
    assert ready is False
    assert payload == {"ok": False, "service": "groundrecall-mcp-http", "checks": {"policy": True, "store": False}, "reason": "store_not_configured"}
    store = tmp_path / "store"
    store.mkdir()
    app = MCPHTTPApplication(MCPHTTPConfig(policy_config=str(policy), store_dir=str(store)))
    ready, payload = app.readiness()
    assert ready is True
    assert payload == {"ok": True, "service": "groundrecall-mcp-http", "checks": {"policy": True, "store": True}, "reason": "ready"}
    assert str(tmp_path) not in json.dumps(payload)


def test_http_require_policy_fails_closed_without_path_leak(tmp_path) -> None:
    policy = tmp_path / "policy.yaml"
    policy.write_text("schema_version: groundrecall.policy_plugins.v1\nproviders: []\n", encoding="utf-8")
    store = tmp_path / "store"; store.mkdir()
    app = MCPHTTPApplication(MCPHTTPConfig(policy_config=str(policy), store_dir=str(store), subject_id="alice", require_policy=True))
    policy.unlink()
    ready, payload = app.readiness()
    assert ready is False and payload["checks"]["policy"] is False
    response = json.loads(app.dispatch({"jsonrpc": "2.0", "id": 8, "method": "tools/list"}))
    assert response["error"] == {"code": -32004, "message": "server policy unavailable"}
    assert str(tmp_path) not in json.dumps(response)


def test_http_require_policy_rejects_invalid_policy_after_startup(tmp_path) -> None:
    policy = tmp_path / "policy.yaml"
    policy.write_text("schema_version: groundrecall.policy_plugins.v1\nproviders: []\n", encoding="utf-8")
    app = MCPHTTPApplication(MCPHTTPConfig(policy_config=str(policy), subject_id="alice", require_policy=True))
    policy.write_text("not: [valid", encoding="utf-8")
    response = json.loads(app.dispatch({"jsonrpc": "2.0", "id": 9, "method": "ping"}))
    assert response["error"]["code"] == -32004


def test_http_store_dir_is_server_owned_when_configured(tmp_path, monkeypatch) -> None:
    policy = tmp_path / "policy.yaml"
    policy.write_text("schema_version: groundrecall.policy_plugins.v1\nproviders: []\n", encoding="utf-8")
    store = tmp_path / "store"; store.mkdir()
    app = MCPHTTPApplication(MCPHTTPConfig(policy_config=str(policy), store_dir=str(store), subject_id="alice"))
    captured = {}

    def fake_handle(request):
        captured.update(request["params"]["arguments"])
        return {"jsonrpc": "2.0", "id": request["id"], "result": {"ok": True}}

    monkeypatch.setattr("groundrecall.mcp_http.handle_request", fake_handle)
    app.dispatch({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "search_store", "arguments": {"store_dir": "/caller-controlled"}}})
    assert captured["store_dir"] == str(store)


def test_http_response_limit_returns_bounded_error_without_content_leak(tmp_path) -> None:
    policy = tmp_path / "policy.yaml"
    policy.write_text("schema_version: groundrecall.policy_plugins.v1\nproviders: []\n", encoding="utf-8")
    with pytest.raises(ValueError, match="max_response_bytes"):
        MCPHTTPApplication(MCPHTTPConfig(policy_config=str(policy), max_response_bytes=MCP_HTTP_MIN_RESPONSE_BYTES - 1))
    secret_body = b'{"result":{"secret":"must-not-leak"}}\n'
    bounded, exceeded = _bounded_response_body(secret_body, MCP_HTTP_MIN_RESPONSE_BYTES)
    assert exceeded is True
    assert bounded == b'{"error":"response_too_large"}\n'
    assert b"must-not-leak" not in bounded


def test_http_response_limit_preserves_small_responses(tmp_path) -> None:
    policy = tmp_path / "policy.yaml"
    policy.write_text("schema_version: groundrecall.policy_plugins.v1\nproviders: []\n", encoding="utf-8")
    app = MCPHTTPApplication(MCPHTTPConfig(policy_config=str(policy), max_response_bytes=128))
    response = app.dispatch({"jsonrpc": "2.0", "id": 1, "method": "ping"})
    bounded, exceeded = _bounded_response_body(response, app.config.max_response_bytes)
    assert exceeded is False
    assert bounded == response


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
    assert captured["realm_id"] == "project:alpha"


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


def test_http_audit_log_is_hash_chained_and_verifiable_across_restart(tmp_path) -> None:
    policy = tmp_path / "policy.yaml"
    policy.write_text("schema_version: groundrecall.policy_plugins.v1\nproviders: []\n", encoding="utf-8")
    audit = tmp_path / "mcp.jsonl"
    config = MCPHTTPConfig(policy_config=str(policy), subject_id="alice", audit_log_path=str(audit))
    MCPHTTPApplication(config).dispatch({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    MCPHTTPApplication(config).dispatch({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    summary = verify_audit_log(str(audit))
    assert summary["records"] == 2
    assert summary["chained_records"] == 2
    assert re.fullmatch(r"[0-9a-f]{64}", summary["last_hash"])
    rows = [json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["previous_hash"] == ""
    assert rows[1]["previous_hash"] == rows[0]["record_hash"]


def test_http_audit_verifier_detects_tampering_and_accepts_legacy_prefix(tmp_path) -> None:
    audit = tmp_path / "mcp.jsonl"
    audit.write_text('{"event_kind":"legacy"}\n', encoding="utf-8")
    policy = tmp_path / "policy.yaml"
    policy.write_text("schema_version: groundrecall.policy_plugins.v1\nproviders: []\n", encoding="utf-8")
    app = MCPHTTPApplication(MCPHTTPConfig(policy_config=str(policy), audit_log_path=str(audit)))
    app.dispatch({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert verify_audit_log(str(audit))["chained_records"] == 1
    rows = audit.read_text(encoding="utf-8").splitlines()
    tampered = json.loads(rows[-1]); tampered["decision"] = "denied"
    audit.write_text("\n".join(rows[:-1] + [json.dumps(tampered)]) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        verify_audit_log(str(audit))


def test_mcp_audit_verify_cli_reports_bounded_summary_without_record_contents(tmp_path, capsys) -> None:
    policy = tmp_path / "policy.yaml"
    policy.write_text("schema_version: groundrecall.policy_plugins.v1\nproviders: []\n", encoding="utf-8")
    audit = tmp_path / "mcp.jsonl"
    app = MCPHTTPApplication(MCPHTTPConfig(policy_config=str(policy), subject_id="alice", audit_log_path=str(audit)))
    app.dispatch({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert verify_audit_cli([str(audit)]) == 0
    output = capsys.readouterr().out
    assert "OK: records=1 chained_records=1" in output
    assert "alice" not in output
    assert verify_audit_cli(["--json", str(audit)]) == 0
    assert '"records":1' in capsys.readouterr().out


def test_mcp_audit_verify_cli_returns_nonzero_for_tampering(tmp_path, capsys) -> None:
    audit = tmp_path / "mcp.jsonl"
    audit.write_text('{"event_kind":"legacy"}\n', encoding="utf-8")
    assert verify_audit_cli([str(audit)]) == 0
    audit.write_text("not-json\n", encoding="utf-8")
    assert verify_audit_cli([str(audit)]) == 1
    assert "INVALID:" in capsys.readouterr().err
