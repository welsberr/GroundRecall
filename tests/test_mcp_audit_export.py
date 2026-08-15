import json

import pytest

from groundrecall.mcp_audit_export import export_audit, main
from groundrecall.mcp_http import MCPHTTPApplication, MCPHTTPConfig


def _audit(tmp_path):
    policy = tmp_path / "policy.yaml"
    policy.write_text("schema_version: groundrecall.policy_plugins.v1\nproviders: []\n", encoding="utf-8")
    audit = tmp_path / "mcp.jsonl"
    app = MCPHTTPApplication(MCPHTTPConfig(policy_config=str(policy), subject_id="alice", realm_id="team-a", audit_log_path=str(audit)))
    app.dispatch({"jsonrpc": "2.0", "id": 1, "method": "ping"})
    return audit


def test_export_is_verified_bounded_and_redacted(tmp_path):
    source = _audit(tmp_path)
    output = tmp_path / "out" / "export.json"
    summary = export_audit(source, output, max_records=10)
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert summary["records"] == 1
    assert payload["truncated"] is False
    row = payload["records"][0]
    assert row["record_hash"]
    assert "subject_id" not in row and "realm_id" not in row
    assert "reason" not in row and str(source) not in output.read_text(encoding="utf-8")
    assert source.exists()


def test_export_identity_opt_in_and_record_bound(tmp_path):
    source = _audit(tmp_path)
    output = tmp_path / "export.json"
    export_audit(source, output, include_identities=True, max_records=1)
    row = json.loads(output.read_text(encoding="utf-8"))["records"][0]
    assert row["subject_id"] == "alice" and row["realm_id"] == "team-a"
    with pytest.raises(ValueError, match="max_records"):
        export_audit(source, output, max_records=0)


def test_export_rejects_tampered_source_and_cli_does_not_delete(tmp_path):
    source = _audit(tmp_path)
    source.write_text(source.read_text(encoding="utf-8").replace('"decision": "allowed"', '"decision": "tampered"', 1), encoding="utf-8")
    output = tmp_path / "export.json"
    assert main([str(source), str(output)]) == 1
    assert not output.exists()
    assert source.exists()
