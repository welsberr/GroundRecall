"""Versioned HTTP contracts for a GroundRecall federation broker.

The broker transports existing signed catalogs and incremental change bundles.
It does not decide whether a receiving GroundRecall instance accepts imported
knowledge: bundle delivery ends at the receiver's normal verification and
quarantine workflow.

Authentication identities are established by deployment middleware. They are
never supplied in request bodies. Producer identities and signing keys are
separately enrolled and checked against the signed object's manifest.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .catalog import FederationCatalog
from .change_feed import FederationChangeBundle
from .federation import FederationSignatureAlgorithm, ReleaseLevel


BROKER_API_VERSION = "v1"
BROKER_SCHEMA_VERSION = "groundrecall.federation_broker.v1"
BROKER_CAPABILITIES_SCHEMA = "groundrecall.federation_broker.capabilities.v1"
BROKER_ENROLLMENT_REQUEST_SCHEMA = "groundrecall.federation_broker.enrollment_request.v1"
BROKER_ENROLLMENT_SCHEMA = "groundrecall.federation_broker.enrollment.v1"
BROKER_ENROLLMENT_APPROVAL_SCHEMA = "groundrecall.federation_broker.enrollment_approval.v1"
BROKER_ENROLLMENT_RECEIPT_SCHEMA = "groundrecall.federation_broker.enrollment_receipt.v1"
BROKER_CATALOG_SUBMISSION_SCHEMA = "groundrecall.federation_broker.catalog_submission.v1"
BROKER_CATALOG_RECEIPT_SCHEMA = "groundrecall.federation_broker.catalog_receipt.v1"
BROKER_CATALOG_DISCOVERY_REQUEST_SCHEMA = "groundrecall.federation_broker.catalog_discovery_request.v1"
BROKER_CATALOG_DISCOVERY_SCHEMA = "groundrecall.federation_broker.catalog_discovery.v1"
BROKER_SUBSCRIPTION_REQUEST_SCHEMA = "groundrecall.federation_broker.subscription_request.v1"
BROKER_SUBSCRIPTION_RECEIPT_SCHEMA = "groundrecall.federation_broker.subscription_receipt.v1"
BROKER_BUNDLE_SUBMISSION_SCHEMA = "groundrecall.federation_broker.bundle_submission.v1"
BROKER_BUNDLE_RECEIPT_SCHEMA = "groundrecall.federation_broker.bundle_receipt.v1"
BROKER_BUNDLE_PULL_REQUEST_SCHEMA = "groundrecall.federation_broker.bundle_pull_request.v1"
BROKER_BUNDLE_PAGE_SCHEMA = "groundrecall.federation_broker.bundle_page.v1"
BROKER_ACKNOWLEDGEMENT_SCHEMA = "groundrecall.federation_broker.acknowledgement.v1"
BROKER_KEY_REVOCATION_SCHEMA = "groundrecall.federation_broker.key_revocation.v1"
BROKER_SIGNING_KEY_ADD_SCHEMA = "groundrecall.federation_broker.signing_key_add.v1"
BROKER_SIGNING_KEY_RECEIPT_SCHEMA = "groundrecall.federation_broker.signing_key_receipt.v1"
BROKER_REVOCATION_RECEIPT_SCHEMA = "groundrecall.federation_broker.revocation_receipt.v1"
BROKER_ENROLLMENT_REVOCATION_SCHEMA = "groundrecall.federation_broker.enrollment_revocation.v1"

RELEASE_LEVELS: tuple[ReleaseLevel, ...] = (
    "public",
    "internal",
    "confidential",
    "privileged",
    "private",
)
_RELEASE_RANK = {level: rank for rank, level in enumerate(RELEASE_LEVELS)}


class BrokerContractModel(BaseModel):
    """Strict base for broker-owned JSON request and response envelopes."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AuthenticatedParticipant(BrokerContractModel):
    """Server-side auth context; never deserialize this from request JSON."""

    participant_id: str = Field(min_length=1, max_length=256)
    roles: list[str] = Field(default_factory=list, max_length=20)


class ProducerSigningKeyRequest(BrokerContractModel):
    """Public signing material requested for enrollment; private keys stay local."""

    key_id: str = Field(min_length=1, max_length=128)
    algorithm: Literal["ed25519"] = "ed25519"
    public_key_pem: str = Field(min_length=1, max_length=8192)


class BrokerEnrollmentRequest(BrokerContractModel):
    schema_version: Literal[BROKER_ENROLLMENT_REQUEST_SCHEMA] = BROKER_ENROLLMENT_REQUEST_SCHEMA
    producer_instance_id: str = Field(min_length=1, max_length=256)
    display_name: str = Field(default="", max_length=256)
    signing_keys: list[ProducerSigningKeyRequest] = Field(min_length=1, max_length=10)
    requested_realm_ids: list[str] = Field(min_length=1, max_length=50)
    requested_scope_ids: list[str] = Field(min_length=1, max_length=200)
    requested_release_ceiling: ReleaseLevel = "public"
    purpose: str = Field(min_length=1, max_length=1024)

    @model_validator(mode="after")
    def unique_ids(self) -> "BrokerEnrollmentRequest":
        _require_unique(self.requested_realm_ids, "requested_realm_ids")
        _require_unique(self.requested_scope_ids, "requested_scope_ids")
        _require_unique([key.key_id for key in self.signing_keys], "signing key IDs")
        return self


class BrokerSigningKey(BrokerContractModel):
    key_id: str = Field(min_length=1, max_length=128)
    algorithm: Literal["ed25519"] = "ed25519"
    public_key_pem: str = Field(min_length=1, max_length=8192)
    status: Literal["active", "revoked"] = "active"
    created_at: str = Field(min_length=1, max_length=64)
    revoked_at: str = Field(default="", max_length=64)
    revocation_reason: str = Field(default="", max_length=1024)

    @model_validator(mode="after")
    def revocation_state_is_consistent(self) -> "BrokerSigningKey":
        if self.status == "revoked" and not self.revoked_at:
            raise ValueError("revoked signing keys require revoked_at")
        if self.status == "active" and (self.revoked_at or self.revocation_reason):
            raise ValueError("active signing keys cannot carry revocation fields")
        return self


class BrokerEnrollment(BrokerContractModel):
    """Approved binding from an authenticated participant to producer keys."""

    schema_version: Literal[BROKER_ENROLLMENT_SCHEMA] = BROKER_ENROLLMENT_SCHEMA
    enrollment_id: str = Field(min_length=1, max_length=256)
    # Set from AuthenticatedParticipant by broker code; never copied from a body.
    participant_id: str = Field(min_length=1, max_length=256)
    producer_instance_id: str = Field(min_length=1, max_length=256)
    signing_keys: list[BrokerSigningKey] = Field(min_length=1, max_length=10)
    realm_ids: list[str] = Field(min_length=1, max_length=50)
    scope_ids: list[str] = Field(min_length=1, max_length=200)
    release_ceiling: ReleaseLevel = "public"
    allowed_restriction_markers: list[str] = Field(default_factory=list, max_length=100)
    allowed_compartments: list[str] = Field(default_factory=list, max_length=100)
    status: Literal["active", "revoked"] = "active"
    created_at: str = Field(min_length=1, max_length=64)
    approved_by: str = Field(min_length=1, max_length=256)
    revoked_at: str = Field(default="", max_length=64)
    revocation_reason: str = Field(default="", max_length=1024)

    @model_validator(mode="after")
    def enrollment_is_consistent(self) -> "BrokerEnrollment":
        _require_unique(self.realm_ids, "realm_ids")
        _require_unique(self.scope_ids, "scope_ids")
        _require_unique([key.key_id for key in self.signing_keys], "signing key IDs")
        if self.status == "revoked" and not self.revoked_at:
            raise ValueError("revoked enrollments require revoked_at")
        if self.status == "active" and (self.revoked_at or self.revocation_reason):
            raise ValueError("active enrollments cannot carry revocation fields")
        return self


class EnrollmentApprovalRequest(BrokerContractModel):
    schema_version: Literal[BROKER_ENROLLMENT_APPROVAL_SCHEMA] = BROKER_ENROLLMENT_APPROVAL_SCHEMA
    realm_ids: list[str] = Field(min_length=1, max_length=50)
    scope_ids: list[str] = Field(min_length=1, max_length=200)
    release_ceiling: ReleaseLevel = "public"
    allowed_restriction_markers: list[str] = Field(default_factory=list, max_length=100)
    allowed_compartments: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def unique_ids(self) -> "EnrollmentApprovalRequest":
        _require_unique(self.realm_ids, "realm_ids")
        _require_unique(self.scope_ids, "scope_ids")
        return self


class EnrollmentReceipt(BrokerContractModel):
    schema_version: Literal[BROKER_ENROLLMENT_RECEIPT_SCHEMA] = BROKER_ENROLLMENT_RECEIPT_SCHEMA
    enrollment_id: str = Field(min_length=1, max_length=256)
    status: Literal["pending", "active", "revoked"]
    producer_instance_id: str = Field(min_length=1, max_length=256)
    release_ceiling: ReleaseLevel = "public"
    realm_ids: list[str] = Field(default_factory=list, max_length=50)
    scope_ids: list[str] = Field(default_factory=list, max_length=200)


class BrokerCapabilities(BrokerContractModel):
    schema_version: Literal[BROKER_CAPABILITIES_SCHEMA] = BROKER_CAPABILITIES_SCHEMA
    api_version: Literal[BROKER_API_VERSION] = BROKER_API_VERSION
    service: Literal["groundrecall-federation-broker"] = "groundrecall-federation-broker"
    signing_algorithms: list[Literal["ed25519"]] = Field(default_factory=lambda: ["ed25519"], max_length=1)
    operations: list[str] = Field(default_factory=list, max_length=20)


class CatalogSubmissionRequest(BrokerContractModel):
    schema_version: Literal[BROKER_CATALOG_SUBMISSION_SCHEMA] = BROKER_CATALOG_SUBMISSION_SCHEMA
    catalog: FederationCatalog


class CatalogSubmissionReceipt(BrokerContractModel):
    schema_version: Literal[BROKER_CATALOG_RECEIPT_SCHEMA] = BROKER_CATALOG_RECEIPT_SCHEMA
    catalog_id: str = Field(min_length=1, max_length=256)
    producer_instance_id: str = Field(min_length=1, max_length=256)
    content_hash: str = Field(min_length=1, max_length=128)
    accepted: bool
    duplicate: bool = False


class CatalogDiscoveryRequest(BrokerContractModel):
    schema_version: Literal[BROKER_CATALOG_DISCOVERY_REQUEST_SCHEMA] = BROKER_CATALOG_DISCOVERY_REQUEST_SCHEMA
    query: str = Field(default="", max_length=512)
    realm_id: str = Field(default="", max_length=256)
    scope_ids: list[str] = Field(default_factory=list, max_length=200)
    limit: int = Field(default=20, ge=1, le=100)


class CatalogDiscoveryResponse(BrokerContractModel):
    """Complete, publisher-signed catalogs; contents are never re-signed by broker."""

    schema_version: Literal[BROKER_CATALOG_DISCOVERY_SCHEMA] = BROKER_CATALOG_DISCOVERY_SCHEMA
    catalogs: list[FederationCatalog] = Field(default_factory=list, max_length=100)
    next_cursor: str = Field(default="", max_length=2048)


class SubscriptionCreateRequest(BrokerContractModel):
    """Safe input projected into the existing receiver-local subscription type."""

    schema_version: Literal[BROKER_SUBSCRIPTION_REQUEST_SCHEMA] = BROKER_SUBSCRIPTION_REQUEST_SCHEMA
    subscription_id: str = Field(min_length=1, max_length=256)
    producer_instance_id: str = Field(min_length=1, max_length=256)
    realm_id: str = Field(min_length=1, max_length=256)
    scope_ids: list[str] = Field(min_length=1, max_length=200)
    record_kinds: list[str] = Field(default_factory=list, max_length=50)
    change_kinds: list[Literal["upsert", "state"]] = Field(default_factory=lambda: ["upsert", "state"], max_length=2)
    release_ceiling: ReleaseLevel = "public"
    allowed_restriction_markers: list[str] = Field(default_factory=list, max_length=100)
    allowed_compartments: list[str] = Field(default_factory=list, max_length=100)
    purpose: str = Field(min_length=1, max_length=1024)

    @model_validator(mode="after")
    def unique_filter_values(self) -> "SubscriptionCreateRequest":
        _require_unique(self.scope_ids, "scope_ids")
        _require_unique(self.record_kinds, "record_kinds")
        _require_unique(self.change_kinds, "change_kinds")
        return self


class SubscriptionReceipt(BrokerContractModel):
    schema_version: Literal[BROKER_SUBSCRIPTION_RECEIPT_SCHEMA] = BROKER_SUBSCRIPTION_RECEIPT_SCHEMA
    subscription_id: str = Field(min_length=1, max_length=256)
    producer_instance_id: str = Field(min_length=1, max_length=256)
    realm_id: str = Field(min_length=1, max_length=256)
    scope_ids: list[str] = Field(min_length=1, max_length=200)
    release_ceiling: ReleaseLevel = "public"
    active: bool = True
    cursor: str = Field(default="", max_length=2048)


class ChangeBundleSubmissionRequest(BrokerContractModel):
    schema_version: Literal[BROKER_BUNDLE_SUBMISSION_SCHEMA] = BROKER_BUNDLE_SUBMISSION_SCHEMA
    bundle: FederationChangeBundle


class ChangeBundleReceipt(BrokerContractModel):
    schema_version: Literal[BROKER_BUNDLE_RECEIPT_SCHEMA] = BROKER_BUNDLE_RECEIPT_SCHEMA
    bundle_id: str = Field(min_length=1, max_length=512)
    producer_instance_id: str = Field(min_length=1, max_length=256)
    subscription_id: str = Field(min_length=1, max_length=256)
    content_hash: str = Field(min_length=1, max_length=128)
    accepted: bool
    duplicate: bool = False


class ChangeBundlePullRequest(BrokerContractModel):
    schema_version: Literal[BROKER_BUNDLE_PULL_REQUEST_SCHEMA] = BROKER_BUNDLE_PULL_REQUEST_SCHEMA
    subscription_id: str = Field(min_length=1, max_length=256)
    limit: int = Field(default=20, ge=1, le=100)
    after_cursor: str = Field(default="", max_length=2048)


class ChangeBundlePage(BrokerContractModel):
    schema_version: Literal[BROKER_BUNDLE_PAGE_SCHEMA] = BROKER_BUNDLE_PAGE_SCHEMA
    subscription_id: str = Field(min_length=1, max_length=256)
    bundles: list[FederationChangeBundle] = Field(default_factory=list, max_length=100)
    next_cursor: str = Field(default="", max_length=2048)


class BundleAcknowledgementRequest(BrokerContractModel):
    schema_version: Literal[BROKER_ACKNOWLEDGEMENT_SCHEMA] = BROKER_ACKNOWLEDGEMENT_SCHEMA
    bundle_id: str = Field(min_length=1, max_length=512)
    cursor: str = Field(default="", max_length=2048)


class BundleAcknowledgementReceipt(BrokerContractModel):
    schema_version: Literal[BROKER_ACKNOWLEDGEMENT_SCHEMA] = BROKER_ACKNOWLEDGEMENT_SCHEMA
    bundle_id: str = Field(min_length=1, max_length=512)
    subscription_id: str = Field(min_length=1, max_length=256)
    cursor: str = Field(default="", max_length=2048)
    acknowledged: bool = True
    duplicate: bool = False


class SigningKeyRevocationRequest(BrokerContractModel):
    schema_version: Literal[BROKER_KEY_REVOCATION_SCHEMA] = BROKER_KEY_REVOCATION_SCHEMA
    reason: str = Field(min_length=1, max_length=1024)


class SigningKeyAddRequest(BrokerContractModel):
    """Broker-admin-authorized addition of a public replacement signing key."""

    schema_version: Literal[BROKER_SIGNING_KEY_ADD_SCHEMA] = BROKER_SIGNING_KEY_ADD_SCHEMA
    key_id: str = Field(min_length=1, max_length=128)
    algorithm: Literal["ed25519"] = "ed25519"
    public_key_pem: str = Field(min_length=1, max_length=8192)


class SigningKeyReceipt(BrokerContractModel):
    schema_version: Literal[BROKER_SIGNING_KEY_RECEIPT_SCHEMA] = BROKER_SIGNING_KEY_RECEIPT_SCHEMA
    enrollment_id: str = Field(min_length=1, max_length=256)
    producer_instance_id: str = Field(min_length=1, max_length=256)
    key_id: str = Field(min_length=1, max_length=128)
    added_at: str = Field(min_length=1, max_length=64)
    active: bool = True
    duplicate: bool = False


class RevocationReceipt(BrokerContractModel):
    schema_version: Literal[BROKER_REVOCATION_RECEIPT_SCHEMA] = BROKER_REVOCATION_RECEIPT_SCHEMA
    enrollment_id: str = Field(min_length=1, max_length=256)
    producer_instance_id: str = Field(min_length=1, max_length=256)
    key_id: str = Field(min_length=1, max_length=128)
    revoked_at: str = Field(min_length=1, max_length=64)
    effective: bool = True


class EnrollmentRevocationRequest(BrokerContractModel):
    schema_version: Literal[BROKER_ENROLLMENT_REVOCATION_SCHEMA] = BROKER_ENROLLMENT_REVOCATION_SCHEMA
    reason: str = Field(min_length=1, max_length=1024)


class EnrollmentRevocationReceipt(BrokerContractModel):
    schema_version: Literal[BROKER_ENROLLMENT_REVOCATION_SCHEMA] = BROKER_ENROLLMENT_REVOCATION_SCHEMA
    enrollment_id: str = Field(min_length=1, max_length=256)
    producer_instance_id: str = Field(min_length=1, max_length=256)
    revoked_at: str = Field(min_length=1, max_length=64)
    effective: bool = True


@dataclass(frozen=True)
class BrokerHttpOperation:
    """An HTTP route declaration suitable for future server/OpenAPI adapters."""

    operation_id: str
    method: Literal["GET", "POST"]
    path: str
    request_model: type[BaseModel] | None
    response_model: type[BaseModel]
    authentication: Literal["none", "participant", "broker_admin"]


BROKER_HTTP_OPERATIONS: tuple[BrokerHttpOperation, ...] = (
    BrokerHttpOperation("capabilities", "GET", "/api/v1/broker", None, BrokerCapabilities, "none"),
    BrokerHttpOperation("request_enrollment", "POST", "/api/v1/enrollment-requests", BrokerEnrollmentRequest, EnrollmentReceipt, "participant"),
    BrokerHttpOperation("approve_enrollment", "POST", "/api/v1/admin/enrollments/{enrollment_id}/approval", EnrollmentApprovalRequest, EnrollmentReceipt, "broker_admin"),
    BrokerHttpOperation("publish_catalog", "POST", "/api/v1/catalogs", CatalogSubmissionRequest, CatalogSubmissionReceipt, "participant"),
    BrokerHttpOperation("discover_catalogs", "POST", "/api/v1/catalogs/discover", CatalogDiscoveryRequest, CatalogDiscoveryResponse, "participant"),
    BrokerHttpOperation("create_subscription", "POST", "/api/v1/subscriptions", SubscriptionCreateRequest, SubscriptionReceipt, "participant"),
    BrokerHttpOperation("submit_change_bundle", "POST", "/api/v1/change-bundles", ChangeBundleSubmissionRequest, ChangeBundleReceipt, "participant"),
    BrokerHttpOperation("pull_change_bundles", "POST", "/api/v1/change-bundles/pull", ChangeBundlePullRequest, ChangeBundlePage, "participant"),
    BrokerHttpOperation("acknowledge_change_bundle", "POST", "/api/v1/change-bundles/acknowledgements", BundleAcknowledgementRequest, BundleAcknowledgementReceipt, "participant"),
    BrokerHttpOperation("revoke_signing_key", "POST", "/api/v1/enrollments/{enrollment_id}/keys/{key_id}/revocation", SigningKeyRevocationRequest, RevocationReceipt, "participant"),
    BrokerHttpOperation("add_signing_key", "POST", "/api/v1/admin/enrollments/{enrollment_id}/signing-keys", SigningKeyAddRequest, SigningKeyReceipt, "broker_admin"),
    BrokerHttpOperation("revoke_enrollment", "POST", "/api/v1/enrollments/{enrollment_id}/revocation", EnrollmentRevocationRequest, EnrollmentRevocationReceipt, "participant"),
    BrokerHttpOperation("admin_revoke_enrollment", "POST", "/api/v1/admin/enrollments/{enrollment_id}/revocation", EnrollmentRevocationRequest, EnrollmentRevocationReceipt, "broker_admin"),
)


class BrokerAuthorizationError(ValueError):
    """Raised when a requested exchange exceeds an approved enrollment."""


def ensure_subscription_within_enrollments(
    subscription: SubscriptionCreateRequest,
    *,
    receiver: BrokerEnrollment,
    producer: BrokerEnrollment,
) -> None:
    """Fail closed unless both participants authorize the complete subscription.

    A receiver's grant limits what it may receive; the producer's grant limits
    what it may publish. Their intersection is the effective subscription.
    """

    if receiver.status != "active" or producer.status != "active":
        raise BrokerAuthorizationError("both participant enrollments must be active")
    if subscription.producer_instance_id != producer.producer_instance_id:
        raise BrokerAuthorizationError("subscription producer does not match producer enrollment")
    if subscription.realm_id not in receiver.realm_ids or subscription.realm_id not in producer.realm_ids:
        raise BrokerAuthorizationError("subscription realm is not authorized by both enrollments")
    for enrollment, role in ((receiver, "receiver"), (producer, "producer")):
        if not set(subscription.scope_ids) <= set(enrollment.scope_ids):
            raise BrokerAuthorizationError(f"subscription scope exceeds {role} enrollment")
        if _RELEASE_RANK[subscription.release_ceiling] > _RELEASE_RANK[enrollment.release_ceiling]:
            raise BrokerAuthorizationError(f"subscription release ceiling exceeds {role} enrollment")
        if not set(subscription.allowed_restriction_markers) <= set(enrollment.allowed_restriction_markers):
            raise BrokerAuthorizationError(f"subscription restriction markers exceed {role} enrollment")
        if not set(subscription.allowed_compartments) <= set(enrollment.allowed_compartments):
            raise BrokerAuthorizationError(f"subscription compartments exceed {role} enrollment")


def verify_producer_binding(
    *,
    authenticated_participant: AuthenticatedParticipant,
    enrollment: BrokerEnrollment,
    producer_instance_id: str,
    key_id: str,
    algorithm: FederationSignatureAlgorithm,
) -> BrokerSigningKey:
    """Resolve a manifest signer only through an active participant enrollment."""

    if enrollment.participant_id != authenticated_participant.participant_id:
        raise BrokerAuthorizationError("authenticated participant does not own producer enrollment")
    if enrollment.status != "active":
        raise BrokerAuthorizationError("producer enrollment is not active")
    if enrollment.producer_instance_id != producer_instance_id:
        raise BrokerAuthorizationError("signed producer identity does not match enrollment")
    key = next((candidate for candidate in enrollment.signing_keys if candidate.key_id == key_id), None)
    if key is None or key.status != "active":
        raise BrokerAuthorizationError("producer signing key is not active in enrollment")
    if key.algorithm != algorithm:
        raise BrokerAuthorizationError("signature algorithm does not match enrolled signing key")
    return key


def authorize_catalog_for_enrollment(
    catalog: FederationCatalog,
    *,
    authenticated_participant: AuthenticatedParticipant,
    enrollment: BrokerEnrollment,
) -> BrokerSigningKey:
    """Check the signed catalog identity and its declared scope/release bounds."""

    if enrollment.participant_id != authenticated_participant.participant_id:
        raise BrokerAuthorizationError("authenticated participant does not own producer enrollment")
    if enrollment.status != "active":
        raise BrokerAuthorizationError("producer enrollment is not active")
    key = catalog.manifest.signature
    if key is None:
        raise BrokerAuthorizationError("catalog must carry a producer signature")
    enrolled_key = verify_producer_binding(
        authenticated_participant=authenticated_participant,
        enrollment=enrollment,
        producer_instance_id=catalog.manifest.producer_instance_id,
        key_id=key.key_id,
        algorithm=key.algorithm,
    )
    if _RELEASE_RANK.get(catalog.manifest.target_release_level, len(_RELEASE_RANK)) > _RELEASE_RANK[enrollment.release_ceiling]:
        raise BrokerAuthorizationError("catalog release level exceeds producer enrollment")
    allowed_scopes = set(enrollment.scope_ids)
    for entry in catalog.entries:
        if entry.scope_id not in allowed_scopes:
            raise BrokerAuthorizationError("catalog contains a scope outside producer enrollment")
        if any(_RELEASE_RANK.get(level, len(_RELEASE_RANK)) > _RELEASE_RANK[enrollment.release_ceiling] for level in entry.release_levels):
            raise BrokerAuthorizationError("catalog entry exceeds producer enrollment release ceiling")
    return enrolled_key


def catalog_within_release_ceiling(catalog: FederationCatalog, release_ceiling: ReleaseLevel) -> bool:
    """Whether a complete signed catalog may be disclosed at this release.

    Catalogs are returned intact so the publisher signature remains verifiable;
    if any declared level exceeds the receiver's bound, the whole catalog is
    withheld rather than partially redacted.
    """

    ceiling_rank = _RELEASE_RANK.get(release_ceiling)
    if ceiling_rank is None:
        return False
    target_rank = _RELEASE_RANK.get(catalog.manifest.target_release_level)
    if target_rank is None or target_rank > ceiling_rank:
        return False
    return all(
        (rank := _RELEASE_RANK.get(level)) is not None and rank <= ceiling_rank
        for entry in catalog.entries
        for level in entry.release_levels
    )


def authorize_change_bundle_for_enrollment(
    bundle: FederationChangeBundle,
    *,
    authenticated_participant: AuthenticatedParticipant,
    enrollment: BrokerEnrollment,
    subscription: SubscriptionCreateRequest,
) -> BrokerSigningKey:
    """Check producer binding and ensure each event fits grant and subscription."""

    if bundle.manifest.subscription_id != subscription.subscription_id:
        raise BrokerAuthorizationError("bundle subscription does not match approved subscription")
    if bundle.manifest.producer_instance_id != subscription.producer_instance_id:
        raise BrokerAuthorizationError("bundle producer does not match approved subscription")
    signature = bundle.manifest.signature
    if signature is None:
        raise BrokerAuthorizationError("change bundle must carry a producer signature")
    key = verify_producer_binding(
        authenticated_participant=authenticated_participant,
        enrollment=enrollment,
        producer_instance_id=bundle.manifest.producer_instance_id,
        key_id=signature.key_id,
        algorithm=signature.algorithm,
    )
    allowed_scopes = set(subscription.scope_ids) & set(enrollment.scope_ids)
    maximum_release = min(
        (subscription.release_ceiling, enrollment.release_ceiling),
        key=_RELEASE_RANK.__getitem__,
    )
    allowed_markers = set(subscription.allowed_restriction_markers) & set(enrollment.allowed_restriction_markers)
    allowed_compartments = set(subscription.allowed_compartments) & set(enrollment.allowed_compartments)
    for event in bundle.events:
        if event.scope_id not in allowed_scopes:
            raise BrokerAuthorizationError("bundle event is outside approved subscription scope")
        if subscription.record_kinds and event.record_kind not in subscription.record_kinds:
            raise BrokerAuthorizationError("bundle event kind is outside approved subscription")
        if event.event_kind not in subscription.change_kinds:
            raise BrokerAuthorizationError("bundle change kind is outside approved subscription")
        if _RELEASE_RANK.get(event.release_level, len(_RELEASE_RANK)) > _RELEASE_RANK[maximum_release]:
            raise BrokerAuthorizationError("bundle event exceeds approved release ceiling")
        if not set(event.restriction_markers) <= allowed_markers:
            raise BrokerAuthorizationError("bundle event has unapproved restriction markers")
        if not set(event.compartments) <= allowed_compartments:
            raise BrokerAuthorizationError("bundle event has unapproved compartments")
    return key


def broker_contract_json_schema() -> dict[str, Any]:
    """Return versioned schemas and route metadata for client generation."""

    model_types: tuple[type[BaseModel], ...] = (
        BrokerEnrollmentRequest,
        BrokerSigningKey,
        BrokerEnrollment,
        EnrollmentApprovalRequest,
        EnrollmentReceipt,
        BrokerCapabilities,
        CatalogSubmissionRequest,
        CatalogSubmissionReceipt,
        CatalogDiscoveryRequest,
        CatalogDiscoveryResponse,
        SubscriptionCreateRequest,
        SubscriptionReceipt,
        ChangeBundleSubmissionRequest,
        ChangeBundleReceipt,
        ChangeBundlePullRequest,
        ChangeBundlePage,
        BundleAcknowledgementRequest,
        BundleAcknowledgementReceipt,
        SigningKeyRevocationRequest,
        SigningKeyAddRequest,
        SigningKeyReceipt,
        RevocationReceipt,
        EnrollmentRevocationRequest,
        EnrollmentRevocationReceipt,
    )
    return {
        "schema_version": BROKER_SCHEMA_VERSION,
        "api_version": BROKER_API_VERSION,
        "schemas": {model.__name__: model.model_json_schema() for model in model_types},
        "operations": [
            {
                "operation_id": operation.operation_id,
                "method": operation.method,
                "path": operation.path,
                "request": operation.request_model.__name__ if operation.request_model else None,
                "response": operation.response_model.__name__,
                "authentication": operation.authentication,
            }
            for operation in BROKER_HTTP_OPERATIONS
        ],
    }


def _require_unique(values: list[str], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")
