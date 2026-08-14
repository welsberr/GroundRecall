import json

import pytest

from groundrecall.handoff import (
    append_handoff_progress,
    get_handoff,
    list_handoff_events,
    list_handoffs,
    propose_handoff,
    propose_handoff_result,
    update_handoff_status,
)
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


def test_handoff_lifecycle_is_scoped_idempotent_and_append_only(tmp_path):
    item = propose_handoff(str(tmp_path), project="demo", objective="ship", subject_id="alice", realm_id="team-a").handoff
    accepted = update_handoff_status(str(tmp_path), item.handoff_id, "accepted", subject_id="alice", realm_id="team-a", expected_status="proposed", idempotency_key="accept-1")
    assert accepted.handoff.status == "accepted"
    again = update_handoff_status(str(tmp_path), item.handoff_id, "accepted", subject_id="alice", realm_id="team-a", idempotency_key="accept-1")
    assert again.handoff.status == "accepted"
    progress = append_handoff_progress(str(tmp_path), item.handoff_id, state="planning", observations=["scope checked"], next_action="execute", subject_id="alice", realm_id="team-a", idempotency_key="progress-1")
    assert progress.event_type == "progress"
    assert append_handoff_progress(str(tmp_path), item.handoff_id, state="changed", subject_id="alice", realm_id="team-a", idempotency_key="progress-1").event_id == progress.event_id
    result = propose_handoff_result(str(tmp_path), item.handoff_id, outcome="done", tests=["pytest"], subject_id="alice", realm_id="team-a", idempotency_key="result-1")
    assert result.event_type == "result"
    completed = update_handoff_status(str(tmp_path), item.handoff_id, "executing", subject_id="alice", realm_id="team-a")
    assert completed.handoff.status == "executing"
    assert len(list_handoff_events(tmp_path, item.handoff_id, subject_id="alice", realm_id="team-a")) == 4
    assert list_handoff_events(tmp_path, item.handoff_id, subject_id="bob", realm_id="team-a") == []
    with pytest.raises(ValueError, match="invalid handoff status transition"):
        update_handoff_status(str(tmp_path), item.handoff_id, "proposed", subject_id="alice", realm_id="team-a")


def test_mcp_exposes_handoff_lifecycle_without_canonical_writes(tmp_path):
    item = propose_handoff(str(tmp_path), project="demo", objective="ship", subject_id="alice", realm_id="r1").handoff
    def call(name, arguments):
        raw = handle_request({"jsonrpc": "2.0", "id": name, "method": "tools/call", "params": {"name": name, "arguments": {"store_dir": str(tmp_path), "handoff_id": item.handoff_id, "subject_id": "alice", "realm_id": "r1", **arguments}}})
        return json.loads(raw["result"]["content"][0]["text"])
    assert {"handoff_update_status", "progress_append", "result_propose", "handoff_events"}.issubset({tool["name"] for tool in list_tools()})
    assert call("handoff_update_status", {"status": "accepted"})["handoff"]["status"] == "accepted"
    assert call("progress_append", {"state": "executing", "observations": ["started"]})["canonical_write"] is False
    assert call("result_propose", {"outcome": "blocked", "unresolved": ["dependency"]})["canonical_write"] is False
    assert len(call("handoff_events", {})["events"]) == 3
