import json

import pytest

from groundrecall.handoff import propose_handoff, update_handoff_status
from groundrecall.handoff_discovery import discover_handoffs


def _policy(path, decision="allow"):
    path.write_text(json.dumps({"schema_version": "groundrecall.policy_plugins.v1", "providers": [{"type": "static", "default_decision": decision}]}))


def test_discovery_filters_scope_and_never_claims(tmp_path):
    first = propose_handoff(str(tmp_path), project="alpha", objective="ship alpha", subject_id="alice", realm_id="team", host_id="host-a")
    propose_handoff(str(tmp_path), project="beta", objective="ship beta", subject_id="alice", realm_id="team", host_id="host-b")
    payload = discover_handoffs(str(tmp_path), subject_id="alice", realm_id="team", project="alpha", host_id="host-a")
    assert payload["visible_total"] == 1
    assert payload["handoffs"][0]["handoff_id"] == first.handoff.handoff_id
    assert payload["canonical_write"] is False
    assert payload["execution_performed"] is False
    assert first.handoff.status == "proposed"


def test_discovery_active_statuses_and_release_isolation(tmp_path):
    item = propose_handoff(str(tmp_path), project="demo", objective="private", subject_id="alice", realm_id="team", release_level="private").handoff
    public = propose_handoff(str(tmp_path), project="demo", objective="public", subject_id="alice", realm_id="team", release_level="public").handoff
    update_handoff_status(str(tmp_path), item.handoff_id, "accepted", subject_id="alice", realm_id="team")
    payload = discover_handoffs(str(tmp_path), subject_id="alice", realm_id="team", maximum_release_level="public")
    assert {row["handoff_id"] for row in payload["handoffs"]} == {public.handoff_id}
    assert discover_handoffs(str(tmp_path), subject_id="alice", realm_id="team", statuses=["executing"])["visible_total"] == 0


def test_discovery_applies_policy_and_bounds_output(tmp_path):
    policy = tmp_path / "policy.yaml"
    _policy(policy, "deny")
    propose_handoff(str(tmp_path), project="demo", objective="x" * 2000, subject_id="alice", realm_id="team", context_refs=["r"] * 40)
    payload = discover_handoffs(str(tmp_path), policy_config=str(policy), limit=1)
    assert payload["visible_total"] == 0
    assert payload["denied_count"] == 1
    assert payload["policy_decisions"][0]["decision"] == "deny"


def test_discovery_rejects_non_active_status(tmp_path):
    with pytest.raises(ValueError, match="unsupported active handoff status"):
        discover_handoffs(str(tmp_path), statuses=["completed"])
