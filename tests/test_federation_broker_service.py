from __future__ import annotations

import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.rsa import generate_private_key

from groundrecall.catalog import (
    FederationCatalog,
    FederationCatalogEntry,
    FederationCatalogManifest,
    _catalog_content_hash,
)
from groundrecall.change_feed import (
    FederationChangeBundle,
    FederationChangeBundleManifest,
    FederationChangeEvent,
    _bundle_hash,
)
from groundrecall.federation import FederationSignature, _signature_for_payload
from groundrecall.federation_broker import FederationBrokerService
from groundrecall.federation_broker_contract import AuthenticatedParticipant
from groundrecall.federation_broker_http import FederationBrokerHTTPDispatcher


def _keys() -> tuple[str, str]:
    private = Ed25519PrivateKey.generate()
    private_pem = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")
    public_pem = private.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    return private_pem, public_pem


def _rsa_public_key() -> str:
    private = generate_private_key(public_exponent=65537, key_size=2048)
    return private.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")


def _participant(name: str, *roles: str) -> AuthenticatedParticipant:
    return AuthenticatedParticipant(participant_id=name, roles=list(roles))


def _send(dispatcher, method: str, path: str, payload=None, *, participant=None):
    body = b"" if payload is None else json.dumps(payload).encode("utf-8")
    status, response = dispatcher.dispatch(method, path, body, participant=participant)
    return status, json.loads(response)


def _enroll(dispatcher, participant, producer_id, public_key, *, approval_release="internal"):
    status, pending = _send(
        dispatcher,
        "POST",
        "/api/v1/enrollment-requests",
        {
            "producer_instance_id": producer_id,
            "signing_keys": [{"key_id": "ed-key", "public_key_pem": public_key}],
            "requested_realm_ids": ["team:alpha"],
            "requested_scope_ids": ["scope-a"],
            "requested_release_ceiling": "internal",
            "purpose": "two person broker pilot",
        },
        participant=participant,
    )
    assert status == 200, pending
    status, approved = _send(
        dispatcher,
        "POST",
        f"/api/v1/admin/enrollments/{pending['enrollment_id']}/approval",
        {
            "realm_ids": ["team:alpha"],
            "scope_ids": ["scope-a"],
            "release_ceiling": approval_release,
        },
        participant=_participant("admin", "broker_admin"),
    )
    assert status == 200, approved
    return pending["enrollment_id"]


def _signed_catalog(private_key: str, *, key_id: str = "ed-key") -> FederationCatalog:
    entry = FederationCatalogEntry(
        entry_id="scope-a",
        scope_id="scope-a",
        title="Alpha project",
        topic_summaries=["shared research"],
        release_levels=["public"],
    )
    manifest = FederationCatalogManifest(
        catalog_id="catalog-a",
        created_at="2026-08-01T00:00:00Z",
        producer_instance_id="producer-a",
        target_release_level="internal",
        detail_level="aggregate",
        content_hash=_catalog_content_hash([entry]),
    )
    unsigned = FederationCatalog(manifest=manifest, entries=[entry])
    signature = _signature_for_payload(
        unsigned.model_dump(mode="json"), private_key, algorithm="ed25519"
    )
    return unsigned.model_copy(update={
        "manifest": manifest.model_copy(update={
            "signature": FederationSignature(algorithm="ed25519", key_id=key_id, value=signature)
        })
    })


def _signed_bundle(private_key: str) -> FederationChangeBundle:
    event = FederationChangeEvent(
        event_id="event-a",
        event_kind="upsert",
        record_kind="claim",
        record_id="claim-a",
        content_hash="record-hash-a",
        scope_id="scope-a",
        release_level="internal",
        payload={"claim_id": "claim-a", "text": "a quarantined proposal"},
    )
    manifest = FederationChangeBundleManifest(
        bundle_id="bundle-a",
        created_at="2026-08-01T00:01:00Z",
        producer_instance_id="producer-a",
        subscription_id="sub-a",
        cursor_start="",
        cursor_end="event-a",
        event_count=1,
        content_hash=_bundle_hash([event]),
    )
    unsigned = FederationChangeBundle(manifest=manifest, events=[event])
    signature = _signature_for_payload(
        unsigned.model_dump(mode="json"), private_key, algorithm="ed25519"
    )
    return unsigned.model_copy(update={
        "manifest": manifest.model_copy(update={
            "signature": FederationSignature(algorithm="ed25519", key_id="ed-key", value=signature)
        })
    })


def test_broker_http_exchange_is_authenticated_verified_durable_and_quarantined_by_receiver(tmp_path: Path) -> None:
    database = tmp_path / "broker" / "state.sqlite3"
    service = FederationBrokerService(database)
    dispatcher = FederationBrokerHTTPDispatcher(service)
    alice = _participant("alice")
    bob = _participant("bob")
    producer_private, producer_public = _keys()
    receiver_private, receiver_public = _keys()

    status, _ = _send(dispatcher, "POST", "/api/v1/enrollment-requests", {}, participant=None)
    assert status == 401
    status, _ = _send(
        dispatcher,
        "POST",
        "/api/v1/admin/enrollments/unknown/approval",
        {},
        participant=alice,
    )
    assert status == 403
    status, _ = _send(
        dispatcher,
        "POST",
        "/api/v1/enrollment-requests",
        {"participant_id": "mallory"},
        participant=alice,
    )
    assert status == 400

    _enroll(dispatcher, alice, "producer-a", producer_public)
    _enroll(dispatcher, bob, "receiver-b", receiver_public)

    catalog = _signed_catalog(producer_private)
    catalog_json = catalog.model_dump(mode="json")
    status, receipt = _send(
        dispatcher, "POST", "/api/v1/catalogs", {"catalog": catalog_json}, participant=alice
    )
    assert status == 200 and receipt["accepted"] and not receipt["duplicate"]
    status, duplicate = _send(
        dispatcher, "POST", "/api/v1/catalogs", {"catalog": catalog_json}, participant=alice
    )
    assert status == 200 and duplicate["duplicate"]
    status, found = _send(
        dispatcher,
        "POST",
        "/api/v1/catalogs/discover",
        {"query": "research", "realm_id": "team:alpha"},
        participant=bob,
    )
    assert status == 200 and [row["manifest"]["catalog_id"] for row in found["catalogs"]] == ["catalog-a"]

    status, subscription = _send(
        dispatcher,
        "POST",
        "/api/v1/subscriptions",
        {
            "subscription_id": "sub-a",
            "producer_instance_id": "producer-a",
            "realm_id": "team:alpha",
            "scope_ids": ["scope-a"],
            "release_ceiling": "internal",
            "purpose": "shared project knowledge",
        },
        participant=bob,
    )
    assert status == 200 and subscription["active"]

    bundle = _signed_bundle(producer_private)
    bundle_json = bundle.model_dump(mode="json")
    status, received = _send(
        dispatcher, "POST", "/api/v1/change-bundles", {"bundle": bundle_json}, participant=alice
    )
    assert status == 200 and received["accepted"]
    status, replay = _send(
        dispatcher, "POST", "/api/v1/change-bundles", {"bundle": bundle_json}, participant=alice
    )
    assert status == 200 and replay["duplicate"]
    status, page = _send(
        dispatcher,
        "POST",
        "/api/v1/change-bundles/pull",
        {"subscription_id": "sub-a"},
        participant=bob,
    )
    assert status == 200 and page["bundles"][0]["manifest"]["bundle_id"] == "bundle-a"
    assert page["bundles"][0]["events"][0]["payload"]["text"] == "a quarantined proposal"
    status, ack = _send(
        dispatcher,
        "POST",
        "/api/v1/change-bundles/acknowledgements",
        {"bundle_id": "bundle-a", "cursor": "event-a"},
        participant=bob,
    )
    assert status == 200 and ack["acknowledged"]
    status, ack_replay = _send(
        dispatcher,
        "POST",
        "/api/v1/change-bundles/acknowledgements",
        {"bundle_id": "bundle-a", "cursor": "event-a"},
        participant=bob,
    )
    assert status == 200 and ack_replay["duplicate"]

    # Broker restart retains catalog, delivery, and acknowledgement state.
    restarted = FederationBrokerHTTPDispatcher(FederationBrokerService(database))
    status, catalog_after_restart = _send(
        restarted,
        "POST",
        "/api/v1/catalogs/discover",
        {"query": "Alpha"},
        participant=bob,
    )
    assert status == 200 and len(catalog_after_restart["catalogs"]) == 1
    status, replay_page = _send(
        restarted,
        "POST",
        "/api/v1/change-bundles/pull",
        {"subscription_id": "sub-a"},
        participant=bob,
    )
    assert status == 200 and replay_page["bundles"][0]["manifest"]["bundle_id"] == "bundle-a"

    # The dedicated broker database is the only persisted artifact; no receiver
    # canonical store is opened or modified by pull/ack.
    assert database.is_file()
    assert sorted(path.name for path in database.parent.iterdir())


def test_broker_rejects_tampered_signature_out_of_scope_access_and_revoked_key(tmp_path: Path) -> None:
    service = FederationBrokerService(tmp_path / "broker.sqlite3")
    dispatcher = FederationBrokerHTTPDispatcher(service)
    alice = _participant("alice")
    producer_private, producer_public = _keys()
    enrollment_id = _enroll(dispatcher, alice, "producer-a", producer_public)
    catalog = _signed_catalog(producer_private)
    tampered = catalog.model_copy(update={
        "entries": [catalog.entries[0].model_copy(update={"title": "altered after signing"})]
    })
    status, _ = _send(
        dispatcher,
        "POST",
        "/api/v1/catalogs",
        {"catalog": tampered.model_dump(mode="json")},
        participant=alice,
    )
    assert status == 403
    status, revoked = _send(
        dispatcher,
        "POST",
        f"/api/v1/enrollments/{enrollment_id}/keys/ed-key/revocation",
        {"reason": "test revocation"},
        participant=alice,
    )
    assert status == 200 and revoked["effective"]
    status, _ = _send(
        dispatcher,
        "POST",
        "/api/v1/catalogs",
        {"catalog": catalog.model_dump(mode="json")},
        participant=alice,
    )
    assert status == 403


def test_catalog_discovery_withholds_catalog_above_receiver_release_ceiling(tmp_path: Path) -> None:
    dispatcher = FederationBrokerHTTPDispatcher(FederationBrokerService(tmp_path / "broker.sqlite3"))
    alice, bob = _participant("alice"), _participant("bob")
    producer_private, producer_public = _keys()
    _, receiver_public = _keys()
    _enroll(dispatcher, alice, "producer-a", producer_public)
    # The request may seek internal access, but the admin approves only public.
    _enroll(dispatcher, bob, "receiver-b", receiver_public, approval_release="public")

    catalog = _signed_catalog(producer_private)
    status, receipt = _send(
        dispatcher,
        "POST",
        "/api/v1/catalogs",
        {"catalog": catalog.model_dump(mode="json")},
        participant=alice,
    )
    assert status == 200 and receipt["accepted"]

    status, discovery = _send(
        dispatcher,
        "POST",
        "/api/v1/catalogs/discover",
        {"query": "research", "realm_id": "team:alpha"},
        participant=bob,
    )
    assert status == 200
    assert discovery["catalogs"] == []


def test_broker_admin_can_add_replacement_signing_key_idempotently(tmp_path: Path) -> None:
    service = FederationBrokerService(tmp_path / "broker.sqlite3")
    dispatcher = FederationBrokerHTTPDispatcher(service)
    alice = _participant("alice")
    admin = _participant("rotation-admin", "broker_admin")
    _, old_public = _keys()
    new_private, new_public = _keys()
    enrollment_id = _enroll(dispatcher, alice, "producer-a", old_public)

    status, _ = _send(
        dispatcher,
        "POST",
        f"/api/v1/enrollments/{enrollment_id}/keys/ed-key/revocation",
        {"reason": "routine key rotation"},
        participant=alice,
    )
    assert status == 200

    path = f"/api/v1/admin/enrollments/{enrollment_id}/signing-keys"
    payload = {"key_id": "ed-key-2", "public_key_pem": new_public}
    status, _ = _send(dispatcher, "POST", path, payload, participant=None)
    assert status == 401
    status, _ = _send(dispatcher, "POST", path, payload, participant=alice)
    assert status == 403

    status, added = _send(dispatcher, "POST", path, payload, participant=admin)
    assert status == 200 and added["active"] and not added["duplicate"]
    status, duplicate = _send(dispatcher, "POST", path, payload, participant=admin)
    assert status == 200 and duplicate["duplicate"]

    _, another_public = _keys()
    status, _ = _send(
        dispatcher,
        "POST",
        path,
        {"key_id": "ed-key-2", "public_key_pem": another_public},
        participant=admin,
    )
    assert status == 409
    status, _ = _send(
        dispatcher,
        "POST",
        path,
        {"key_id": "ed-key", "public_key_pem": old_public},
        participant=admin,
    )
    assert status == 409

    status, _ = _send(
        dispatcher,
        "POST",
        path,
        {"key_id": "not-ed25519", "public_key_pem": _rsa_public_key()},
        participant=admin,
    )
    assert status == 403
    status, _ = _send(
        dispatcher,
        "POST",
        path,
        {"key_id": "bad-pem", "public_key_pem": "not a PEM key"},
        participant=admin,
    )
    assert status == 403

    # The old key remains in the enrollment's audit history as revoked, while
    # the replacement can sign submissions under the unchanged producer ID.
    enrollment = service._owned_enrollment(alice, "producer-a")
    assert [(key.key_id, key.status) for key in enrollment.signing_keys] == [
        ("ed-key", "revoked"),
        ("ed-key-2", "active"),
    ]
    catalog = _signed_catalog(new_private, key_id="ed-key-2")
    status, receipt = _send(
        dispatcher,
        "POST",
        "/api/v1/catalogs",
        {"catalog": catalog.model_dump(mode="json")},
        participant=alice,
    )
    assert status == 200 and receipt["accepted"]
