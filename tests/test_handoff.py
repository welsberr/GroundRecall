import json
import time

import pytest

from groundrecall.handoff import (
    accept_handoff,
    complete_handoff,
    append_handoff_progress,
    claim_handoff,
    get_handoff,
    list_handoff_events,
    list_handoffs,
    propose_handoff,
    propose_handoff_result,
    review_handoff_result,
    release_handoff,
    update_handoff_status,
)
from groundrecall.handoff import HandoffEvent, _transaction_path
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
    from groundrecall.handoff import claim_handoff
    item = propose_handoff(str(tmp_path), project="demo", objective="ship", subject_id="alice", realm_id="r1", host_id="host-a").handoff
    def call(name, arguments):
        raw = handle_request({"jsonrpc": "2.0", "id": name, "method": "tools/call", "params": {"name": name, "arguments": {"store_dir": str(tmp_path), "handoff_id": item.handoff_id, "subject_id": "alice", "realm_id": "r1", **arguments}}})
        return json.loads(raw["result"]["content"][0]["text"])
    assert {"handoff_update_status", "progress_append", "result_propose", "handoff_events"}.issubset({tool["name"] for tool in list_tools()})
    assert call("handoff_update_status", {"status": "accepted"})["handoff"]["status"] == "accepted"
    lease = claim_handoff(str(tmp_path), item.handoff_id, subject_id="alice", host_id="host-a", project="demo", expected_status="accepted", realm_id="r1")
    progress_args = {"state": "executing", "observations": ["started"], "lease_id": lease.lease_id, "host_id": "host-a", "project": "demo", "expected_status": "accepted"}
    assert call("progress_append", progress_args)["canonical_write"] is False
    result_args = {"outcome": "blocked", "unresolved": ["dependency"], "lease_id": lease.lease_id, "host_id": "host-a", "project": "demo", "expected_status": "accepted"}
    assert call("result_propose", result_args)["canonical_write"] is False
    assert len(call("handoff_events", {})["events"]) == 4


def test_handoff_recovers_interrupted_status_transaction(tmp_path):
    item = propose_handoff(str(tmp_path), project="demo", objective="recover", subject_id="alice", realm_id="r1").handoff
    recovered = item.model_copy(update={"status": "accepted", "updated_at": "2026-08-14T00:00:00+00:00"})
    event = HandoffEvent(event_id="event-recovery", event_type="status", handoff_id=item.handoff_id, task_id=item.task_id, subject_id=item.subject_id, realm_id=item.realm_id, status="accepted", created_at="2026-08-14T00:00:00+00:00")
    journal = _transaction_path(tmp_path, item.handoff_id)
    journal.write_text(json.dumps({"handoff": recovered.model_dump(mode="json"), "event": event.model_dump(mode="json")}), encoding="utf-8")
    restored = get_handoff(tmp_path, item.handoff_id, subject_id="alice", realm_id="r1")
    assert restored is not None and restored.status == "accepted"
    assert [e.event_id for e in list_handoff_events(tmp_path, item.handoff_id, subject_id="alice", realm_id="r1")] == ["event-recovery"]
    assert not journal.exists()


def test_handoff_recovery_does_not_duplicate_event_after_interrupted_cleanup(tmp_path):
    item = propose_handoff(str(tmp_path), project="demo", objective="recover", subject_id="alice", realm_id="r1").handoff
    recovered = item.model_copy(update={"status": "accepted"})
    event = HandoffEvent(event_id="event-existing", event_type="status", handoff_id=item.handoff_id, task_id=item.task_id, subject_id=item.subject_id, realm_id=item.realm_id, status="accepted", created_at="2026-08-14T00:00:00+00:00")
    events_path = tmp_path / "handoffs" / f"{item.handoff_id}.events.jsonl"
    events_path.write_text(event.model_dump_json() + "\n", encoding="utf-8")
    journal = _transaction_path(tmp_path, item.handoff_id)
    journal.write_text(json.dumps({"handoff": recovered.model_dump(mode="json"), "event": event.model_dump(mode="json")}), encoding="utf-8")
    assert get_handoff(tmp_path, item.handoff_id, subject_id="alice", realm_id="r1").status == "accepted"
    assert len(list_handoff_events(tmp_path, item.handoff_id, subject_id="alice", realm_id="r1")) == 1


def test_handoff_recovers_interrupted_lease_mutation(tmp_path):
    from datetime import datetime, timezone, timedelta
    from groundrecall.handoff import claim_handoff

    item = propose_handoff(str(tmp_path), project="demo", objective="lease", subject_id="alice", realm_id="r1", host_id="host-a").handoff
    expires = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    recovered = item.model_copy(update={"lease_id": "lease-recovery", "lease_subject_id": "alice", "lease_host_id": "host-a", "lease_expires_at": expires})
    event = HandoffEvent(event_id="event-lease-recovery", event_type="lease", handoff_id=item.handoff_id, task_id=item.task_id, subject_id=item.subject_id, realm_id=item.realm_id, lease_id="lease-recovery", lease_subject_id="alice", lease_host_id="host-a", lease_expires_at=expires, lease_action="claimed", created_at="2026-08-14T00:00:00+00:00")
    journal = _transaction_path(tmp_path, item.handoff_id)
    journal.write_text(json.dumps({"handoff": recovered.model_dump(mode="json"), "event": event.model_dump(mode="json")}), encoding="utf-8")
    restored = get_handoff(tmp_path, item.handoff_id, subject_id="alice", realm_id="r1")
    assert restored is not None and restored.lease_id == "lease-recovery"
    with pytest.raises(ValueError, match="active lease"):
        claim_handoff(str(tmp_path), item.handoff_id, subject_id="alice", host_id="host-a", project="demo", expected_status="proposed", realm_id="r1")


def test_handoff_acceptance_requires_active_scoped_lease_and_is_idempotent(tmp_path):
    from groundrecall.handoff import claim_handoff
    item = propose_handoff(str(tmp_path), project="demo", objective="accept", subject_id="alice", realm_id="r1", host_id="host-a").handoff
    with pytest.raises(PermissionError, match="active lease"):
        accept_handoff(str(tmp_path), item.handoff_id, subject_id="alice", host_id="host-a", project="demo", realm_id="r1")
    claimed = claim_handoff(str(tmp_path), item.handoff_id, subject_id="alice", host_id="host-a", project="demo", expected_status="proposed", realm_id="r1")
    accepted = accept_handoff(str(tmp_path), item.handoff_id, subject_id="alice", host_id="host-a", project="demo", realm_id="r1", idempotency_key="accept-1")
    assert accepted.handoff.status == "accepted"
    assert accepted.lease_id == claimed.lease_id
    again = accept_handoff(str(tmp_path), item.handoff_id, subject_id="alice", host_id="host-a", project="demo", realm_id="r1", idempotency_key="accept-1")
    assert again.handoff.status == "accepted"
    with pytest.raises(PermissionError, match="scope"):
        accept_handoff(str(tmp_path), item.handoff_id, subject_id="alice", host_id="other", project="demo", realm_id="r1")


def test_handoff_completion_requires_lease_scope_and_result(tmp_path):
    from groundrecall.handoff import claim_handoff
    item = propose_handoff(str(tmp_path), project="demo", objective="complete", subject_id="alice", realm_id="r1", host_id="host-a").handoff
    claim = claim_handoff(str(tmp_path), item.handoff_id, subject_id="alice", host_id="host-a", project="demo", expected_status="proposed", realm_id="r1")
    accepted = accept_handoff(str(tmp_path), item.handoff_id, subject_id="alice", host_id="host-a", project="demo", realm_id="r1")
    with pytest.raises(ValueError, match="outcome or result_ref"):
        complete_handoff(str(tmp_path), item.handoff_id, subject_id="alice", host_id="host-a", project="demo", realm_id="r1", expected_status="accepted")
    done = complete_handoff(str(tmp_path), item.handoff_id, subject_id="alice", host_id="host-a", project="demo", realm_id="r1", expected_status="accepted", outcome="tests passed", idempotency_key="done-1")
    assert done.handoff.status == "completed" and done.lease_id == claim.lease_id
    again = complete_handoff(str(tmp_path), item.handoff_id, subject_id="alice", host_id="host-a", project="demo", realm_id="r1", expected_status="accepted", outcome="tests passed", idempotency_key="done-1")
    assert again.handoff.status == "completed"


def test_handoff_result_review_is_scoped_idempotent_and_append_only(tmp_path):
    from groundrecall.handoff import claim_handoff
    item = propose_handoff(str(tmp_path), project="demo", objective="review", subject_id="alice", realm_id="r1", host_id="host-a").handoff
    claim = claim_handoff(str(tmp_path), item.handoff_id, subject_id="alice", host_id="host-a", project="demo", expected_status="proposed", realm_id="r1")
    accept_handoff(str(tmp_path), item.handoff_id, subject_id="alice", host_id="host-a", project="demo", realm_id="r1")
    complete_handoff(str(tmp_path), item.handoff_id, subject_id="alice", host_id="host-a", project="demo", realm_id="r1", expected_status="accepted", outcome="done")
    with pytest.raises(ValueError, match="rationale or result_ref"):
        review_handoff_result(str(tmp_path), item.handoff_id, reviewer_subject_id="reviewer", project="demo", decision="defer", realm_id="r1")
    event = review_handoff_result(str(tmp_path), item.handoff_id, reviewer_subject_id="reviewer", project="demo", decision="accept", rationale="verified", realm_id="r1", idempotency_key="review-1")
    assert event.review_decision == "accept" and event.event_type == "review"
    again = review_handoff_result(str(tmp_path), item.handoff_id, reviewer_subject_id="reviewer", project="demo", decision="accept", rationale="changed", realm_id="r1", idempotency_key="review-1")
    assert again.event_id == event.event_id
    with pytest.raises(PermissionError, match="project"):
        review_handoff_result(str(tmp_path), item.handoff_id, reviewer_subject_id="reviewer", project="other", decision="reject", rationale="no", realm_id="r1")


def test_handoff_claim_release_is_scoped_bounded_and_reclaims_expired_leases(tmp_path):
    item = propose_handoff(str(tmp_path), project="demo", objective="ship", subject_id="alice", realm_id="r1", host_id="codex-1").handoff
    with pytest.raises(ValueError, match="expected_status is required"):
        claim_handoff(tmp_path, item.handoff_id, subject_id="alice", host_id="codex-1", project="demo")
    claimed = claim_handoff(tmp_path, item.handoff_id, subject_id="alice", host_id="codex-1", project="demo", expected_status="proposed", lease_seconds=1, idempotency_key="claim-1")
    assert claimed.lease_id and claimed.handoff.lease_host_id == "codex-1"
    with pytest.raises(ValueError, match="active lease"):
        claim_handoff(tmp_path, item.handoff_id, subject_id="alice", host_id="codex-1", project="demo", expected_status="proposed", idempotency_key="claim-2")
    with pytest.raises(PermissionError, match="host"):
        release_handoff(tmp_path, item.handoff_id, subject_id="alice", host_id="other", project="demo", lease_id=claimed.lease_id)
    time.sleep(1.1)
    reclaimed = claim_handoff(tmp_path, item.handoff_id, subject_id="alice", host_id="codex-1", project="demo", expected_status="proposed", lease_seconds=30, idempotency_key="claim-3")
    assert reclaimed.lease_id != claimed.lease_id
    released = release_handoff(tmp_path, item.handoff_id, subject_id="alice", host_id="codex-1", project="demo", lease_id=reclaimed.lease_id, expected_status="proposed", idempotency_key="release-1")
    assert released.lease_released is True and released.handoff.lease_id == ""
    assert [event.lease_action for event in list_handoff_events(tmp_path, item.handoff_id, subject_id="alice", realm_id="r1") if event.event_type == "lease"] == ["claimed", "claimed", "released"]


def test_mcp_handoff_claim_and_release_require_scope_and_are_write_tools(tmp_path):
    item = propose_handoff(str(tmp_path), project="demo", objective="ship", subject_id="alice", realm_id="r1", host_id="codex-1").handoff
    names = {tool["name"] for tool in list_tools()}
    assert {"handoff_claim", "handoff_release"}.issubset(names)
    def call(name, arguments):
        raw = handle_request({"jsonrpc": "2.0", "id": name, "method": "tools/call", "params": {"name": name, "arguments": {"store_dir": str(tmp_path), "handoff_id": item.handoff_id, "subject_id": "alice", "realm_id": "r1", "host_id": "codex-1", "project": "demo", **arguments}}})
        return json.loads(raw["result"]["content"][0]["text"])
    claimed = call("handoff_claim", {"expected_status": "proposed", "lease_seconds": 30, "idempotency_key": "mcp-claim"})
    assert claimed["lease_id"]
    released = call("handoff_release", {"lease_id": claimed["lease_id"], "idempotency_key": "mcp-release"})
    assert released["lease_released"] is True
