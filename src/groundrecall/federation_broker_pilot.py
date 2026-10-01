"""Reproducible, synthetic two-participant federation broker pilot.

Run with ``PYTHONPATH=src python -m groundrecall.federation_broker_pilot``.
The pilot binds an ephemeral HTTP server to loopback and creates all state in
an automatically deleted temporary directory. It never connects to a configured
or deployed broker.
"""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import threading
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .catalog import (
    FederationCatalog,
    FederationCatalogEntry,
    FederationCatalogManifest,
    _catalog_content_hash,
)
from .change_feed import (
    FederationChangeBundle,
    FederationChangeBundleManifest,
    FederationChangeEvent,
    FederationSubscription,
    _bundle_hash,
    import_incremental_change_bundle_to_quarantine,
)
from .federation import FederationPolicyError, FederationSignature, _signature_for_payload
from .federation_broker_client import BrokerClientError, BrokerHTTPClient, _persist_bundles
from .federation_broker_contract import (
    BROKER_ACKNOWLEDGEMENT_SCHEMA,
    BROKER_BUNDLE_PULL_REQUEST_SCHEMA,
    BROKER_BUNDLE_SUBMISSION_SCHEMA,
    BROKER_CATALOG_DISCOVERY_REQUEST_SCHEMA,
    BROKER_CATALOG_SUBMISSION_SCHEMA,
    BROKER_ENROLLMENT_APPROVAL_SCHEMA,
    BROKER_KEY_REVOCATION_SCHEMA,
    BROKER_SIGNING_KEY_ADD_SCHEMA,
    BrokerEnrollmentRequest,
    BundleAcknowledgementReceipt,
    BundleAcknowledgementRequest,
    CatalogDiscoveryRequest,
    CatalogDiscoveryResponse,
    CatalogSubmissionReceipt,
    CatalogSubmissionRequest,
    ChangeBundlePage,
    ChangeBundlePullRequest,
    ChangeBundleReceipt,
    ChangeBundleSubmissionRequest,
    EnrollmentApprovalRequest,
    EnrollmentReceipt,
    ProducerSigningKeyRequest,
    RevocationReceipt,
    SigningKeyAddRequest,
    SigningKeyReceipt,
    SigningKeyRevocationRequest,
    SubscriptionCreateRequest,
    SubscriptionReceipt,
)
from .federation_broker_server import make_server, provision_token


REALM_ID = "pilot:team-alpha"
SCOPE_ID = "pilot:shared-research"
RELEASE = "internal"


def _key_pair() -> tuple[Ed25519PrivateKey, str, str]:
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
    return private, private_pem, public_pem


def _signed_catalog(
    private_pem: str, *, producer_id: str, catalog_id: str, key_id: str
) -> FederationCatalog:
    entry = FederationCatalogEntry(
        entry_id=f"{catalog_id}:entry",
        scope_id=SCOPE_ID,
        title=f"Synthetic pilot notes from {producer_id}",
        topic_summaries=["synthetic two-participant broker exercise"],
        release_levels=[RELEASE],
    )
    manifest = FederationCatalogManifest(
        catalog_id=catalog_id,
        created_at="2026-09-19T12:00:00Z",
        producer_instance_id=producer_id,
        target_release_level=RELEASE,
        detail_level="aggregate",
        content_hash=_catalog_content_hash([entry]),
    )
    unsigned = FederationCatalog(manifest=manifest, entries=[entry])
    signature = _signature_for_payload(unsigned.model_dump(mode="json"), private_pem, algorithm="ed25519")
    return unsigned.model_copy(update={
        "manifest": manifest.model_copy(update={
            "signature": FederationSignature(algorithm="ed25519", key_id=key_id, value=signature)
        })
    })


def _signed_bundle(
    private_pem: str,
    *,
    producer_id: str,
    subscription_id: str,
    key_id: str,
    bundle_id: str,
    event_id: str,
    cursor_start: str = "",
    release: str = RELEASE,
    scope_id: str = SCOPE_ID,
) -> FederationChangeBundle:
    event = FederationChangeEvent(
        event_id=event_id,
        event_kind="upsert",
        record_kind="claim",
        record_id=f"synthetic:{event_id}",
        content_hash=f"synthetic-hash:{event_id}",
        scope_id=scope_id,
        release_level=release,
        realm_id=REALM_ID,
        audience="team",
        origin_instance_id=producer_id,
        occurred_at="2026-09-19T12:01:00Z",
        payload={"text": f"Synthetic-only proposal {event_id}; not promoted."},
    )
    manifest = FederationChangeBundleManifest(
        bundle_id=bundle_id,
        created_at="2026-09-19T12:01:00Z",
        producer_instance_id=producer_id,
        subscription_id=subscription_id,
        cursor_start=cursor_start,
        cursor_end=event_id,
        event_count=1,
        content_hash=_bundle_hash([event]),
    )
    unsigned = FederationChangeBundle(manifest=manifest, events=[event])
    signature = _signature_for_payload(unsigned.model_dump(mode="json"), private_pem, algorithm="ed25519")
    return unsigned.model_copy(update={
        "manifest": manifest.model_copy(update={
            "signature": FederationSignature(algorithm="ed25519", key_id=key_id, value=signature)
        })
    })


def _http_server(database: Path, auth_file: Path) -> tuple[Any, threading.Thread, str]:
    # make_server intentionally sets a private umask for service operation;
    # restore the pilot process umask immediately after its listener is built.
    prior_umask = os.umask(0o077)
    try:
        server = make_server(database, auth_file, host="127.0.0.1", port=0)
    finally:
        os.umask(prior_umask)
    thread = threading.Thread(target=server.serve_forever, name="synthetic-broker", daemon=True)
    thread.start()
    return server, thread, f"http://127.0.0.1:{server.server_port}"


def _stop_server(server: Any, thread: threading.Thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)
    if thread.is_alive():
        raise RuntimeError("synthetic broker HTTP thread did not stop")


def _client(url: str, token: str) -> BrokerHTTPClient:
    return BrokerHTTPClient(url, token=token, timeout=5)


def _enroll(
    participant: BrokerHTTPClient,
    administrator: BrokerHTTPClient,
    *,
    producer_id: str,
    key_id: str,
    public_pem: str,
) -> str:
    request = BrokerEnrollmentRequest(
        producer_instance_id=producer_id,
        display_name=f"Synthetic {producer_id}",
        signing_keys=[ProducerSigningKeyRequest(key_id=key_id, public_key_pem=public_pem)],
        requested_realm_ids=[REALM_ID],
        requested_scope_ids=[SCOPE_ID],
        requested_release_ceiling=RELEASE,
        purpose="Reproducible, synthetic two-participant pilot",
    )
    receipt = participant.request(
        "POST", "/api/v1/enrollment-requests", request, EnrollmentReceipt
    )
    approved = administrator.request(
        "POST",
        f"/api/v1/admin/enrollments/{receipt.enrollment_id}/approval",
        EnrollmentApprovalRequest(
            schema_version=BROKER_ENROLLMENT_APPROVAL_SCHEMA,
            realm_ids=[REALM_ID],
            scope_ids=[SCOPE_ID],
            release_ceiling=RELEASE,
        ),
        EnrollmentReceipt,
    )
    if approved.status != "active":
        raise AssertionError(f"synthetic enrollment was not activated: {approved.status}")
    return receipt.enrollment_id


def _publish_catalog(client: BrokerHTTPClient, catalog: FederationCatalog) -> CatalogSubmissionReceipt:
    return client.request(
        "POST",
        "/api/v1/catalogs",
        CatalogSubmissionRequest(
            schema_version=BROKER_CATALOG_SUBMISSION_SCHEMA, catalog=catalog
        ),
        CatalogSubmissionReceipt,
    )


def _create_subscription(
    receiver: BrokerHTTPClient,
    *,
    subscription_id: str,
    producer_id: str,
) -> SubscriptionReceipt:
    return receiver.request(
        "POST",
        "/api/v1/subscriptions",
        SubscriptionCreateRequest(
            subscription_id=subscription_id,
            producer_instance_id=producer_id,
            realm_id=REALM_ID,
            scope_ids=[SCOPE_ID],
            record_kinds=["claim"],
            release_ceiling=RELEASE,
            purpose="Synthetic pilot; receive into quarantine only",
        ),
        SubscriptionReceipt,
    )


def _submit_bundle(client: BrokerHTTPClient, bundle: FederationChangeBundle) -> ChangeBundleReceipt:
    return client.request(
        "POST",
        "/api/v1/change-bundles",
        ChangeBundleSubmissionRequest(
            schema_version=BROKER_BUNDLE_SUBMISSION_SCHEMA, bundle=bundle
        ),
        ChangeBundleReceipt,
    )


def _discover(client: BrokerHTTPClient, query: str) -> CatalogDiscoveryResponse:
    return client.request(
        "POST",
        "/api/v1/catalogs/discover",
        CatalogDiscoveryRequest(
            schema_version=BROKER_CATALOG_DISCOVERY_REQUEST_SCHEMA,
            query=query,
            realm_id=REALM_ID,
        ),
        CatalogDiscoveryResponse,
    )


def _receive_quarantine_ack(
    receiver: BrokerHTTPClient,
    *,
    subscription_id: str,
    producer_id: str,
    verification_key: str,
    key_id: str,
    handoff_dir: Path,
    verified_dir: Path,
    tamper_check: bool = False,
    after_cursor: str = "",
) -> str:
    page = receiver.request(
        "POST",
        "/api/v1/change-bundles/pull",
        ChangeBundlePullRequest(
            schema_version=BROKER_BUNDLE_PULL_REQUEST_SCHEMA,
            subscription_id=subscription_id,
            limit=10,
            after_cursor=after_cursor,
        ),
        ChangeBundlePage,
    )
    if len(page.bundles) != 1:
        raise AssertionError(f"expected one synthetic bundle for {subscription_id}, got {len(page.bundles)}")
    bundle = page.bundles[0]
    paths = _persist_bundles(page, str(handoff_dir))
    local_subscription = FederationSubscription(
        subscription_id=subscription_id,
        producer_instance_id=producer_id,
        scope_ids=[SCOPE_ID],
        record_kinds=["claim"],
        change_kinds=["upsert"],
        maximum_release_level=RELEASE,
        realm_id=REALM_ID,
        audience="team",
        trusted_instance_ids=[producer_id],
        auto_accept=False,
        purpose="Synthetic pilot: quarantine, review, then explicit acknowledgement",
    )
    imported = import_incremental_change_bundle_to_quarantine(
        paths[0],
        verified_dir,
        verification_key=verification_key,
        key_id=key_id,
        subscription=local_subscription,
    )
    if imported.decision != "quarantined" or imported.event_count != 1:
        raise AssertionError(f"local verification/quarantine failed: {imported.model_dump(mode='json')}")
    if imported.replayed:
        raise AssertionError("first local quarantine write was unexpectedly a replay")

    if tamper_check:
        tampered = bundle.model_copy(update={
            "events": [bundle.events[0].model_copy(update={
                "payload": {"text": "tampered after broker delivery"}
            })]
        })
        tampered_path = handoff_dir / "tampered-after-delivery.json"
        tampered_path.write_text(tampered.model_dump_json(indent=2) + "\n", encoding="utf-8")
        try:
            import_incremental_change_bundle_to_quarantine(
                tampered_path,
                verified_dir,
                verification_key=verification_key,
                key_id=key_id,
                subscription=local_subscription,
            )
        except FederationPolicyError:
            pass
        else:
            raise AssertionError("receiver-side tampering was not rejected by local verification")

    # Pulling again before the receiver acknowledges must remain possible; the
    # HTTP pull itself neither advances consumer state nor auto-acknowledges.
    replay_page = receiver.request(
        "POST",
        "/api/v1/change-bundles/pull",
        ChangeBundlePullRequest(
            schema_version=BROKER_BUNDLE_PULL_REQUEST_SCHEMA,
            subscription_id=subscription_id,
            limit=10,
            after_cursor=after_cursor,
        ),
        ChangeBundlePage,
    )
    if [item.manifest.bundle_id for item in replay_page.bundles] != [bundle.manifest.bundle_id]:
        raise AssertionError("unacknowledged bundle did not remain available for retry")
    replay_paths = _persist_bundles(replay_page, str(handoff_dir))
    replay_import = import_incremental_change_bundle_to_quarantine(
        replay_paths[0],
        verified_dir,
        verification_key=verification_key,
        key_id=key_id,
        subscription=local_subscription,
    )
    if replay_import.decision != "quarantined" or not replay_import.replayed:
        raise AssertionError("identical receiver quarantine replay was not idempotent")

    acknowledgement = receiver.request(
        "POST",
        "/api/v1/change-bundles/acknowledgements",
        BundleAcknowledgementRequest(
            schema_version=BROKER_ACKNOWLEDGEMENT_SCHEMA,
            bundle_id=bundle.manifest.bundle_id,
            cursor=bundle.manifest.cursor_end,
        ),
        BundleAcknowledgementReceipt,
    )
    if not acknowledgement.acknowledged:
        raise AssertionError("explicit receiver acknowledgement did not persist")
    duplicate_ack = receiver.request(
        "POST",
        "/api/v1/change-bundles/acknowledgements",
        BundleAcknowledgementRequest(
            schema_version=BROKER_ACKNOWLEDGEMENT_SCHEMA,
            bundle_id=bundle.manifest.bundle_id,
            cursor=bundle.manifest.cursor_end,
        ),
        BundleAcknowledgementReceipt,
    )
    if not duplicate_ack.duplicate:
        raise AssertionError("duplicate receiver acknowledgement was not idempotent")
    return page.next_cursor


def _expect_http_error(call: Any, status: int, description: str) -> None:
    try:
        call()
    except BrokerClientError as exc:
        if f"HTTP {status}" not in str(exc):
            raise AssertionError(f"{description} failed with unexpected error: {exc}") from exc
    else:
        raise AssertionError(f"broker accepted unauthorized {description}")


def _sqlite_backup(source_path: Path, backup_path: Path, restored_path: Path) -> None:
    source = sqlite3.connect(source_path)
    backup = sqlite3.connect(backup_path)
    try:
        source.backup(backup)
        backup.commit()
    finally:
        backup.close()
        source.close()
    source_backup = sqlite3.connect(backup_path)
    restored = sqlite3.connect(restored_path)
    try:
        source_backup.backup(restored)
        restored.commit()
    finally:
        restored.close()
        source_backup.close()


def run_synthetic_pilot(work_dir: str | Path) -> dict[str, Any]:
    """Run the full synthetic HTTP exchange in an isolated scratch directory."""
    root = Path(work_dir)
    root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()):
        raise ValueError("pilot work directory must be empty")
    broker_dir = root / "broker"
    broker_dir.mkdir(mode=0o700)
    database = broker_dir / "broker.sqlite3"
    auth_file = broker_dir / "auth.json"
    tokens = {
        "operator": provision_token(auth_file, "synthetic-operator", administrator=True),
        "alice": provision_token(auth_file, "synthetic-alice"),
        "bob": provision_token(auth_file, "synthetic-bob"),
    }
    alice_v1, alice_v1_pem, alice_v1_public = _key_pair()
    bob_v1, bob_v1_pem, bob_v1_public = _key_pair()
    alice_v2, alice_v2_pem, alice_v2_public = _key_pair()
    server, thread, url = _http_server(database, auth_file)
    try:
        operator = _client(url, tokens["operator"])
        alice = _client(url, tokens["alice"])
        bob = _client(url, tokens["bob"])

        # Exercise real bearer auth: an anonymous protected request must fail.
        unauthenticated = BrokerHTTPClient(url, timeout=5)
        _expect_http_error(
            lambda: unauthenticated.request(
                "POST",
                "/api/v1/catalogs/discover",
                CatalogDiscoveryRequest(query="synthetic"),
                CatalogDiscoveryResponse,
            ),
            401,
            "unauthenticated discovery",
        )
        alice_enrollment = _enroll(
            alice, operator, producer_id="producer-alice", key_id="alice-v1", public_pem=alice_v1_public
        )
        bob_enrollment = _enroll(
            bob, operator, producer_id="producer-bob", key_id="bob-v1", public_pem=bob_v1_public
        )

        alice_catalog = _signed_catalog(
            alice_v1_pem, producer_id="producer-alice", catalog_id="catalog-alice-v1", key_id="alice-v1"
        )
        bob_catalog = _signed_catalog(
            bob_v1_pem, producer_id="producer-bob", catalog_id="catalog-bob-v1", key_id="bob-v1"
        )
        if not _publish_catalog(alice, alice_catalog).accepted:
            raise AssertionError("Alice catalog was not published")
        if not _publish_catalog(bob, bob_catalog).accepted:
            raise AssertionError("Bob catalog was not published")
        if _publish_catalog(alice, alice_catalog).duplicate is not True:
            raise AssertionError("catalog replay was not idempotent")
        if not any(item.manifest.catalog_id == "catalog-bob-v1" for item in _discover(alice, "synthetic").catalogs):
            raise AssertionError("Alice could not discover Bob's approved catalog")
        if not any(item.manifest.catalog_id == "catalog-alice-v1" for item in _discover(bob, "synthetic").catalogs):
            raise AssertionError("Bob could not discover Alice's approved catalog")

        alice_to_bob = "pilot-alice-to-bob"
        bob_to_alice = "pilot-bob-to-alice"
        _create_subscription(bob, subscription_id=alice_to_bob, producer_id="producer-alice")
        _create_subscription(alice, subscription_id=bob_to_alice, producer_id="producer-bob")

        # The broker refuses events beyond either approved scope or release.
        out_of_scope = _signed_bundle(
            alice_v1_pem,
            producer_id="producer-alice",
            subscription_id=alice_to_bob,
            key_id="alice-v1",
            bundle_id="rejected-out-of-scope",
            event_id="rejected-scope-event",
            scope_id="pilot:unauthorized-scope",
        )
        out_of_release = _signed_bundle(
            alice_v1_pem,
            producer_id="producer-alice",
            subscription_id=alice_to_bob,
            key_id="alice-v1",
            bundle_id="rejected-out-of-release",
            event_id="rejected-release-event",
            release="confidential",
        )
        _expect_http_error(lambda: _submit_bundle(alice, out_of_scope), 403, "out-of-scope bundle")
        _expect_http_error(lambda: _submit_bundle(alice, out_of_release), 403, "over-release bundle")

        tampered_catalog = alice_catalog.model_copy(update={
            "entries": [alice_catalog.entries[0].model_copy(update={"title": "tampered catalog"})]
        })
        _expect_http_error(
            lambda: _publish_catalog(alice, tampered_catalog), 403, "catalog with invalid signature/content hash"
        )

        alice_bundle_1 = _signed_bundle(
            alice_v1_pem,
            producer_id="producer-alice",
            subscription_id=alice_to_bob,
            key_id="alice-v1",
            bundle_id="pilot-alice-bundle-1",
            event_id="alice-event-1",
        )
        bob_bundle_1 = _signed_bundle(
            bob_v1_pem,
            producer_id="producer-bob",
            subscription_id=bob_to_alice,
            key_id="bob-v1",
            bundle_id="pilot-bob-bundle-1",
            event_id="bob-event-1",
        )
        if not _submit_bundle(alice, alice_bundle_1).accepted:
            raise AssertionError("Alice-to-Bob bundle was not accepted")
        if not _submit_bundle(alice, alice_bundle_1).duplicate:
            raise AssertionError("Alice-to-Bob bundle replay was not idempotent")
        if not _submit_bundle(bob, bob_bundle_1).accepted:
            raise AssertionError("Bob-to-Alice bundle was not accepted")
        if not _submit_bundle(bob, bob_bundle_1).duplicate:
            raise AssertionError("Bob-to-Alice bundle replay was not idempotent")

        alice_receive_dir = root / "alice" / "quarantine"
        bob_receive_dir = root / "bob" / "quarantine"
        alice_verified = root / "alice" / "verified-quarantine"
        bob_verified = root / "bob" / "verified-quarantine"
        bob_first_cursor = _receive_quarantine_ack(
            bob,
            subscription_id=alice_to_bob,
            producer_id="producer-alice",
            verification_key=alice_v1_public,
            key_id="alice-v1",
            handoff_dir=bob_receive_dir,
            verified_dir=bob_verified,
            tamper_check=True,
        )
        _receive_quarantine_ack(
            alice,
            subscription_id=bob_to_alice,
            producer_id="producer-bob",
            verification_key=bob_v1_public,
            key_id="bob-v1",
            handoff_dir=alice_receive_dir,
            verified_dir=alice_verified,
        )
        # These synthetic receiver roots intentionally have no canonical store.
        if (root / "alice" / "groundrecall.sqlite3").exists() or (root / "bob" / "groundrecall.sqlite3").exists():
            raise AssertionError("synthetic handoff unexpectedly created a canonical receiver store")

        # Signing-key revocation and replacement are done over the admin/owner
        # HTTP paths; the old key stops authorizing new objects while the
        # replacement continues under the same producer identity.
        alice.request(
            "POST",
            f"/api/v1/enrollments/{alice_enrollment}/keys/alice-v1/revocation",
            SigningKeyRevocationRequest(
                schema_version=BROKER_KEY_REVOCATION_SCHEMA,
                reason="synthetic pilot key rotation",
            ),
            RevocationReceipt,
        )
        replacement_request = SigningKeyAddRequest(
            schema_version=BROKER_SIGNING_KEY_ADD_SCHEMA,
            key_id="alice-v2",
            public_key_pem=alice_v2_public,
        )
        replacement_path = f"/api/v1/admin/enrollments/{alice_enrollment}/signing-keys"
        if not operator.request("POST", replacement_path, replacement_request, SigningKeyReceipt).key_id == "alice-v2":
            raise AssertionError("replacement signing key was not enrolled")
        if not operator.request("POST", replacement_path, replacement_request, SigningKeyReceipt).duplicate:
            raise AssertionError("replacement key request replay was not idempotent")

        revoked_catalog = _signed_catalog(
            alice_v1_pem, producer_id="producer-alice", catalog_id="catalog-alice-revoked-key", key_id="alice-v1"
        )
        _expect_http_error(lambda: _publish_catalog(alice, revoked_catalog), 403, "submission signed by revoked key")
        replacement_catalog = _signed_catalog(
            alice_v2_pem, producer_id="producer-alice", catalog_id="catalog-alice-v2", key_id="alice-v2"
        )
        if not _publish_catalog(alice, replacement_catalog).accepted:
            raise AssertionError("replacement key could not publish for the same producer")

        revoked_bundle = _signed_bundle(
            alice_v1_pem,
            producer_id="producer-alice",
            subscription_id=alice_to_bob,
            key_id="alice-v1",
            bundle_id="rejected-revoked-key-bundle",
            event_id="alice-event-2",
            cursor_start="alice-event-1",
        )
        _expect_http_error(lambda: _submit_bundle(alice, revoked_bundle), 403, "bundle signed by revoked key")
        replacement_bundle = _signed_bundle(
            alice_v2_pem,
            producer_id="producer-alice",
            subscription_id=alice_to_bob,
            key_id="alice-v2",
            bundle_id="pilot-alice-bundle-2",
            event_id="alice-event-2",
            cursor_start="alice-event-1",
        )
        if not _submit_bundle(alice, replacement_bundle).accepted:
            raise AssertionError("replacement key could not submit a signed bundle")
        _receive_quarantine_ack(
            bob,
            subscription_id=alice_to_bob,
            producer_id="producer-alice",
            verification_key=alice_v2_public,
            key_id="alice-v2",
            handoff_dir=bob_receive_dir,
            verified_dir=bob_verified,
            after_cursor=bob_first_cursor,
        )
    finally:
        _stop_server(server, thread)

    # Restart against the same broker file: catalog, subscription, cursor,
    # acknowledgement, enrollment and replacement-key state must survive.
    server, thread, url = _http_server(database, auth_file)
    try:
        operator = _client(url, tokens["operator"])
        alice = _client(url, tokens["alice"])
        bob = _client(url, tokens["bob"])
        if not any(item.manifest.catalog_id == "catalog-alice-v2" for item in _discover(bob, "synthetic").catalogs):
            raise AssertionError("replacement catalog did not persist across broker restart")
        if not _submit_bundle(alice, replacement_bundle).duplicate:
            raise AssertionError("bundle replay after broker restart was not idempotent")
        persisted_page = bob.request(
            "POST",
            "/api/v1/change-bundles/pull",
            ChangeBundlePullRequest(subscription_id=alice_to_bob, limit=10),
            ChangeBundlePage,
        )
        if [item.manifest.bundle_id for item in persisted_page.bundles] != [
            "pilot-alice-bundle-1", "pilot-alice-bundle-2"
        ]:
            raise AssertionError("broker restart lost ordered subscription delivery state")
        # The initial bundle's duplicate ack remains idempotent after restart.
        persisted_ack = bob.request(
            "POST",
            "/api/v1/change-bundles/acknowledgements",
            BundleAcknowledgementRequest(
                schema_version=BROKER_ACKNOWLEDGEMENT_SCHEMA,
                bundle_id="pilot-alice-bundle-1",
                cursor="alice-event-1",
            ),
            BundleAcknowledgementReceipt,
        )
        if not persisted_ack.duplicate:
            raise AssertionError("acknowledgement state did not persist across broker restart")
    finally:
        _stop_server(server, thread)

    backup_dir = broker_dir / "backups"
    backup_dir.mkdir(mode=0o700)
    backup_path = backup_dir / "pilot-backup.sqlite3"
    restored_path = backup_dir / "pilot-restored.sqlite3"
    _sqlite_backup(database, backup_path, restored_path)

    # A second isolated HTTP service from the SQLite backup proves it is a
    # usable restore, not merely a file-copy smoke check. Auth stays local and
    # the pilot token file is reused only by this synthetic restore instance.
    restored_server, restored_thread, restored_url = _http_server(restored_path, auth_file)
    try:
        restored_bob = _client(restored_url, tokens["bob"])
        restored_alice = _client(restored_url, tokens["alice"])
        if not any(item.manifest.catalog_id == "catalog-alice-v2" for item in _discover(restored_bob, "synthetic").catalogs):
            raise AssertionError("SQLite restore did not recover the published catalog")
        restored_page = restored_bob.request(
            "POST",
            "/api/v1/change-bundles/pull",
            ChangeBundlePullRequest(subscription_id=alice_to_bob, limit=10),
            ChangeBundlePage,
        )
        if len(restored_page.bundles) != 2:
            raise AssertionError("SQLite restore did not recover both bundle deliveries")
        if not _submit_bundle(restored_alice, replacement_bundle).duplicate:
            raise AssertionError("SQLite restore did not recover replay/idempotence state")
    finally:
        _stop_server(restored_server, restored_thread)

    return {
        "result": "passed",
        "transport": "loopback HTTP through broker server, dispatcher, and HTTP client",
        "participants": ["synthetic-alice", "synthetic-bob"],
        "directions": ["producer-alice -> synthetic-bob", "producer-bob -> synthetic-alice"],
        "security_checks": [
            "unauthenticated request denied",
            "out-of-scope event denied",
            "over-release event denied",
            "signed catalog tampering denied",
            "receiver-side bundle tampering denied",
            "revoked signing key denied",
            "replacement signing key accepted",
        ],
        "replay_checks": ["catalog", "bundle submit", "quarantine", "acknowledgement"],
        "lifecycle_checks": ["no auto-ack or promotion", "service restart persistence", "SQLite backup and restore"],
        "quarantine_files": 3,
        "promoted": False,
        "live_compose_touched": False,
    }


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="groundrecall-broker-pilot-") as temporary:
        result = run_synthetic_pilot(temporary)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
