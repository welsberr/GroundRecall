from __future__ import annotations

from groundrecall.broker_review_actions import FixtureBrokerReviewActions
from groundrecall.federation_review_source import RemoteReviewItem


def _item(**changes):
    payload = {"item_id": "r", "broker_id": "b", "producer_instance_id": "p", "content_hash": "h", "version_hash": "v", "release_level": "public", "signature_status": "valid", "trust_status": "trusted", "freshness_status": "fresh", "state": "reviewable"}
    payload.update(changes); return RemoteReviewItem(**payload)


def test_fixture_actions_are_explicit_and_idempotent() -> None:
    actions = FixtureBrokerReviewActions(); item = _item()
    first = actions.acknowledge(item, actor="alice", idempotency_key="k")
    replay = actions.acknowledge(item, actor="alice", idempotency_key="k")
    assert first.ok and first.origin == "broker" and first.canonical_write is False
    assert replay.replayed is True and replay.correlation_id == first.correlation_id
    imported = actions.request_import(item, actor="alice", idempotency_key="import-1")
    assert imported.ok and imported.quarantine_proposal and not imported.canonical_write


def test_fixture_actions_reject_trust_freshness_quarantine_and_release() -> None:
    actions = FixtureBrokerReviewActions()
    assert actions.acknowledge(_item(signature_status="invalid"), actor="a", idempotency_key="1").reason_codes == ["invalid_signature"]
    assert actions.acknowledge(_item(trust_status="revoked"), actor="a", idempotency_key="2").ok is False
    assert actions.acknowledge(_item(freshness_status="stale"), actor="a", idempotency_key="3").ok is False
    assert actions.acknowledge(_item(quarantine_status="quarantined"), actor="a", idempotency_key="4").ok is False
    assert actions.acknowledge(_item(release_level="private"), actor="a", idempotency_key="5", maximum_release_level="public").ok is False
