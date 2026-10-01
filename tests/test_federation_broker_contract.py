from __future__ import annotations

import pytest
from pydantic import ValidationError

from groundrecall.catalog import FederationCatalog, FederationCatalogEntry, FederationCatalogManifest
from groundrecall.change_feed import FederationChangeBundle, FederationChangeBundleManifest, FederationChangeEvent
from groundrecall.federation import FederationSignature
from groundrecall.federation_broker_contract import (
    BROKER_API_VERSION,
    BROKER_HTTP_OPERATIONS,
    AuthenticatedParticipant,
    BrokerAuthorizationError,
    BrokerEnrollment,
    BrokerEnrollmentRequest,
    BrokerSigningKey,
    CatalogDiscoveryRequest,
    SubscriptionCreateRequest,
    authorize_catalog_for_enrollment,
    authorize_change_bundle_for_enrollment,
    broker_contract_json_schema,
    ensure_subscription_within_enrollments,
    verify_producer_binding,
)


def _enrollment(
    *,
    enrollment_id: str,
    participant_id: str,
    producer_instance_id: str,
    scope_ids: list[str] | None = None,
    release_ceiling: str = "internal",
    key_status: str = "active",
    enrollment_status: str = "active",
) -> BrokerEnrollment:
    return BrokerEnrollment(
        enrollment_id=enrollment_id,
        participant_id=participant_id,
        producer_instance_id=producer_instance_id,
        signing_keys=[
            BrokerSigningKey(
                key_id="key-1",
                algorithm="ed25519",
                public_key_pem="test public key",
                status=key_status,
                created_at="2026-01-01T00:00:00Z",
                revoked_at="2026-02-01T00:00:00Z" if key_status == "revoked" else "",
                revocation_reason="compromised" if key_status == "revoked" else "",
            )
        ],
        realm_ids=["team:alpha"],
        scope_ids=scope_ids or ["scope-a"],
        release_ceiling=release_ceiling,
        allowed_restriction_markers=["source_protected"],
        allowed_compartments=["research"],
        status=enrollment_status,
        created_at="2026-01-01T00:00:00Z",
        approved_by="broker-admin",
        revoked_at="2026-02-01T00:00:00Z" if enrollment_status == "revoked" else "",
        revocation_reason="participant retired" if enrollment_status == "revoked" else "",
    )


def _subscription(**overrides: object) -> SubscriptionCreateRequest:
    values: dict[str, object] = {
        "subscription_id": "sub-a",
        "producer_instance_id": "producer-a",
        "realm_id": "team:alpha",
        "scope_ids": ["scope-a"],
        "release_ceiling": "internal",
        "allowed_restriction_markers": ["source_protected"],
        "allowed_compartments": ["research"],
        "purpose": "shared project knowledge",
    }
    values.update(overrides)
    return SubscriptionCreateRequest.model_validate(values)


def test_contract_publishes_versioned_http_routes_and_schemas() -> None:
    contract = broker_contract_json_schema()

    assert BROKER_API_VERSION == "v1"
    assert contract["api_version"] == "v1"
    assert {operation.operation_id for operation in BROKER_HTTP_OPERATIONS} >= {
        "request_enrollment",
        "approve_enrollment",
        "publish_catalog",
        "create_subscription",
        "submit_change_bundle",
        "pull_change_bundles",
        "acknowledge_change_bundle",
        "revoke_signing_key",
        "add_signing_key",
    }
    assert contract["schemas"]["BrokerEnrollmentRequest"]["additionalProperties"] is False
    assert all(operation.path.startswith("/api/v1/") for operation in BROKER_HTTP_OPERATIONS)
    key_addition = next(operation for operation in BROKER_HTTP_OPERATIONS if operation.operation_id == "add_signing_key")
    assert key_addition.authentication == "broker_admin"
    assert key_addition.path == "/api/v1/admin/enrollments/{enrollment_id}/signing-keys"


def test_client_cannot_assign_authenticated_or_producer_identity() -> None:
    payload = {
        "producer_instance_id": "instance-a",
        "signing_keys": [{"key_id": "key-1", "public_key_pem": "public"}],
        "requested_realm_ids": ["team:alpha"],
        "requested_scope_ids": ["scope-a"],
        "purpose": "shared project knowledge",
        "participant_id": "somebody-else",
    }
    with pytest.raises(ValidationError, match="participant_id"):
        BrokerEnrollmentRequest.model_validate(payload)

    with pytest.raises(ValidationError, match="receiver_instance_id"):
        CatalogDiscoveryRequest.model_validate({"receiver_instance_id": "spoofed"})


def test_subscription_must_fit_both_enrollment_bounds() -> None:
    request = _subscription()
    receiver = _enrollment(enrollment_id="receiver", participant_id="alice", producer_instance_id="receiver-a")
    producer = _enrollment(enrollment_id="producer", participant_id="bob", producer_instance_id="producer-a")

    ensure_subscription_within_enrollments(request, receiver=receiver, producer=producer)

    with pytest.raises(BrokerAuthorizationError, match="receiver enrollment"):
        ensure_subscription_within_enrollments(
            _subscription(scope_ids=["scope-a", "scope-b"]),
            receiver=receiver,
            producer=producer.model_copy(update={"scope_ids": ["scope-a", "scope-b"]}),
        )
    with pytest.raises(BrokerAuthorizationError, match="producer enrollment"):
        ensure_subscription_within_enrollments(
            _subscription(release_ceiling="confidential"),
            receiver=receiver.model_copy(update={"release_ceiling": "confidential"}),
            producer=producer,
        )
    with pytest.raises(BrokerAuthorizationError, match="realm"):
        ensure_subscription_within_enrollments(
            _subscription(realm_id="team:beta"),
            receiver=receiver,
            producer=producer,
        )


def test_authenticated_principal_must_own_an_active_signing_key_binding() -> None:
    participant = AuthenticatedParticipant(participant_id="alice")
    enrollment = _enrollment(enrollment_id="e1", participant_id="alice", producer_instance_id="instance-a")
    key = verify_producer_binding(
        authenticated_participant=participant,
        enrollment=enrollment,
        producer_instance_id="instance-a",
        key_id="key-1",
        algorithm="ed25519",
    )
    assert key.key_id == "key-1"

    with pytest.raises(BrokerAuthorizationError, match="does not own"):
        verify_producer_binding(
            authenticated_participant=AuthenticatedParticipant(participant_id="mallory"),
            enrollment=enrollment,
            producer_instance_id="instance-a",
            key_id="key-1",
            algorithm="ed25519",
        )
    with pytest.raises(BrokerAuthorizationError, match="producer identity"):
        verify_producer_binding(
            authenticated_participant=participant,
            enrollment=enrollment,
            producer_instance_id="forged-instance",
            key_id="key-1",
            algorithm="ed25519",
        )
    revoked = _enrollment(
        enrollment_id="e2",
        participant_id="alice",
        producer_instance_id="instance-a",
        key_status="revoked",
    )
    with pytest.raises(BrokerAuthorizationError, match="not active"):
        verify_producer_binding(
            authenticated_participant=participant,
            enrollment=revoked,
            producer_instance_id="instance-a",
            key_id="key-1",
            algorithm="ed25519",
        )


def test_catalog_and_change_bundle_cannot_exceed_enrolled_producer_scope() -> None:
    participant = AuthenticatedParticipant(participant_id="alice")
    enrollment = _enrollment(enrollment_id="e1", participant_id="alice", producer_instance_id="producer-a")
    signature = FederationSignature(algorithm="ed25519", key_id="key-1", value="signature")
    catalog = FederationCatalog(
        manifest=FederationCatalogManifest(
            catalog_id="catalog-a",
            created_at="2026-01-01T00:00:00Z",
            producer_instance_id="producer-a",
            target_release_level="internal",
            detail_level="aggregate",
            content_hash="hash",
            signature=signature,
        ),
        entries=[FederationCatalogEntry(entry_id="scope-a", scope_id="scope-a", release_levels=["public"])],
    )
    assert authorize_catalog_for_enrollment(
        catalog,
        authenticated_participant=participant,
        enrollment=enrollment,
    ).key_id == "key-1"

    bundle = FederationChangeBundle(
        manifest=FederationChangeBundleManifest(
            bundle_id="bundle-a",
            created_at="2026-01-01T00:00:00Z",
            producer_instance_id="producer-a",
            subscription_id="sub-a",
            event_count=1,
            content_hash="hash",
            signature=signature,
        ),
        events=[
            FederationChangeEvent(
                event_id="event-a",
                event_kind="upsert",
                record_kind="claim",
                record_id="claim-a",
                content_hash="record-hash",
                scope_id="scope-a",
                release_level="internal",
            )
        ],
    )
    assert authorize_change_bundle_for_enrollment(
        bundle,
        authenticated_participant=participant,
        enrollment=enrollment,
        subscription=_subscription(),
    ).key_id == "key-1"

    with pytest.raises(BrokerAuthorizationError, match="outside producer enrollment"):
        authorize_catalog_for_enrollment(
            catalog.model_copy(update={"entries": [FederationCatalogEntry(entry_id="other", scope_id="scope-b")]}),
            authenticated_participant=participant,
            enrollment=enrollment,
        )
    with pytest.raises(BrokerAuthorizationError, match="outside approved subscription"):
        authorize_change_bundle_for_enrollment(
            bundle.model_copy(
                update={"events": [bundle.events[0].model_copy(update={"scope_id": "scope-b"})]}
            ),
            authenticated_participant=participant,
            enrollment=enrollment,
            subscription=_subscription(),
        )
