from groundrecall.change_feed import FederationChangeEvent, FederationSubscription
from groundrecall.federation_realm import FederationDevice, FederationRealm, event_matches_realm, load_device, load_realm, save_device, save_realm


def test_personal_realm_matches_only_enrolled_instances() -> None:
    realm = FederationRealm(
        realm_id="principal:alice",
        audience="principal",
        principal_id="alice",
        trusted_instance_ids=["laptop"],
    )
    assert event_matches_realm(
        realm=realm,
        audience="principal",
        event_realm_id="principal:alice",
        event_scope_id="",
        event_origin_instance_id="laptop",
    )
    assert not event_matches_realm(
        realm=realm,
        audience="principal",
        event_realm_id="principal:alice",
        event_scope_id="",
        event_origin_instance_id="unknown-host",
    )


def test_project_realm_rejects_personal_and_other_project_events() -> None:
    realm = FederationRealm(realm_id="project:alpha", audience="project", scope_ids=["alpha"])
    assert not event_matches_realm(
        realm=realm,
        audience="principal",
        event_realm_id="principal:alice",
        event_scope_id="alpha",
    )
    assert not event_matches_realm(
        realm=realm,
        audience="project",
        event_realm_id="project:beta",
        event_scope_id="beta",
    )


def test_legacy_subscription_round_trips_without_realm_fields() -> None:
    subscription = FederationSubscription(
        subscription_id="legacy",
        producer_instance_id="host-a",
        purpose="compatibility",
    )
    restored = FederationSubscription.model_validate_json(subscription.model_dump_json())
    assert restored.realm_id == ""
    assert restored.audience == ""


def test_event_contract_exposes_origin_and_audience() -> None:
    event = FederationChangeEvent(
        event_id="e",
        event_kind="upsert",
        record_kind="claim",
        record_id="c",
        content_hash="h",
        realm_id="principal:alice",
        audience="principal",
        origin_instance_id="laptop",
    )
    assert event.realm_id == "principal:alice"
    assert event.origin_instance_id == "laptop"


def test_realm_and_device_records_round_trip(tmp_path) -> None:
    realm_path = tmp_path / "realms" / "alice.json"
    device_path = tmp_path / "devices" / "laptop.json"
    save_realm(realm_path, FederationRealm(realm_id="principal:alice", audience="principal", principal_id="alice"))
    save_device(device_path, FederationDevice(principal_id="alice", instance_id="laptop", key_id="key-1"))
    assert load_realm(realm_path).realm_id == "principal:alice"
    assert load_device(device_path).key_id == "key-1"
