import json

from groundrecall.handoff import get_handoff, list_handoffs, propose_handoff
from groundrecall.mcp import handle_request, list_tools


def test_handoff_proposal_is_scoped_idempotent_and_noncanonical(tmp_path):
    first = propose_handoff(str(tmp_path), project="demo", objective="run tests", subject_id="alice", realm_id="team-a", idempotency_key="k1", context_refs=["concept::x"])
    again = propose_handoff(str(tmp_path), project="demo", objective="changed", subject_id="alice", realm_id="team-a", idempotency_key="k1")
    assert first.handoff.handoff_id == again.handoff.handoff_id
    assert first.handoff.status == "proposed"
    assert get_handoff(tmp_path, first.handoff.handoff_id, subject_id="bob") is None
    assert len(list_handoffs(tmp_path, subject_id="alice", realm_id="team-a")) == 1
    assert len(list(tmp_path.joinpath("handoffs").glob("*.json"))) == 1


def test_mcp_exposes_handoff_tools_and_filters_subject(tmp_path):
    assert {"handoff_propose", "handoff_get", "handoff_list"}.issubset({tool["name"] for tool in list_tools()})
    raw = handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "handoff_propose", "arguments": {"store_dir": str(tmp_path), "project": "demo", "objective": "ship", "subject_id": "alice", "realm_id": "r1", "idempotency_key": "abc"}}})
    payload = json.loads(raw["result"]["content"][0]["text"])
    handoff_id = payload["handoff"]["handoff_id"]
    hidden = handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "handoff_get", "arguments": {"store_dir": str(tmp_path), "handoff_id": handoff_id, "subject_id": "bob", "realm_id": "r1"}}})
    assert json.loads(hidden["result"]["content"][0]["text"])["ok"] is False
