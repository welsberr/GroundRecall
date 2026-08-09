from groundrecall.change_feed import FederationSubscription, build_incremental_change_bundle, load_subscription, save_subscription
from groundrecall.models import SourceRecord
from groundrecall.personal_sync import sync_personal_change_bundle
from groundrecall.store import GroundRecallStore


def _subscription(path: str = "") -> FederationSubscription:
    return FederationSubscription(
        subscription_id="alice-sync",
        producer_instance_id="laptop",
        maximum_release_level="private",
        realm_id="principal:alice",
        audience="principal",
        principal_id="alice",
        trusted_instance_ids=["laptop"],
        auto_accept=True,
        purpose="personal device sync",
        metadata={"subscription_path": path} if path else {},
    )


def _source(store: GroundRecallStore, title: str) -> None:
    store.save_source(SourceRecord(source_id="s1", title=title, metadata={
        "realm_id": "principal:alice",
        "replication_audience": "principal",
        "origin_instance_id": "laptop",
        "origin_principal_id": "alice",
    }))


def test_personal_bundle_applies_and_replays_idempotently(tmp_path) -> None:
    producer = tmp_path / "producer"
    receiver = tmp_path / "receiver"
    bundle_path = tmp_path / "bundle.json"
    key = b"personal-sync-key"
    _source(GroundRecallStore(producer), "from laptop")
    subscription_path = tmp_path / "subscription.json"
    subscription = _subscription()
    save_subscription(subscription_path, subscription)
    bundle = build_incremental_change_bundle(producer, subscription, signing_key=key, key_id="k1", signature_algorithm="hmac-sha256", out_path=bundle_path)
    assert bundle.events
    first = sync_personal_change_bundle(bundle_path, receiver, tmp_path / "quarantine", verification_key=key, subscription=subscription, key_id="k1", subscription_path=subscription_path)
    assert first.decision == "applied"
    assert load_subscription(subscription_path).cursor == bundle.manifest.cursor_end
    assert GroundRecallStore(receiver).get_source("s1").title == "from laptop"
    second = sync_personal_change_bundle(bundle_path, receiver, tmp_path / "quarantine", verification_key=key, subscription=subscription, key_id="k1")
    assert second.decision == "applied"
    assert second.unchanged_event_ids


def test_personal_sync_preserves_existing_conflict(tmp_path) -> None:
    producer = tmp_path / "producer"
    receiver = tmp_path / "receiver"
    bundle_path = tmp_path / "bundle.json"
    key = b"personal-sync-key"
    _source(GroundRecallStore(producer), "from laptop")
    _source(GroundRecallStore(receiver), "edited on server")
    build_incremental_change_bundle(producer, _subscription(), signing_key=key, key_id="k1", signature_algorithm="hmac-sha256", out_path=bundle_path)
    result = sync_personal_change_bundle(bundle_path, receiver, tmp_path / "quarantine", verification_key=key, subscription=_subscription(), key_id="k1")
    assert result.decision == "partial"
    assert result.conflict_event_ids
    assert GroundRecallStore(receiver).get_source("s1").title == "edited on server"


def test_device_local_event_is_not_selected_for_personal_realm(tmp_path) -> None:
    producer = tmp_path / "producer"
    source = SourceRecord(source_id="local", title="host only", metadata={"replication_audience": "device_local", "realm_id": "device:laptop", "origin_instance_id": "laptop"})
    GroundRecallStore(producer).save_source(source)
    bundle = build_incremental_change_bundle(producer, _subscription(), signing_key=b"key", key_id="k1", signature_algorithm="hmac-sha256")
    assert bundle.events == []
