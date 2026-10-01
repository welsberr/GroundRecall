"""Persistent SQLite service for GroundRecall signed federation exchange.

The broker stores enrollment, publication, delivery, and acknowledgement state
only. It never writes to a GroundRecall canonical store or accepts imported
records on behalf of a receiving participant.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import BaseModel

from .catalog import FederationCatalog, verify_federation_catalog
from .change_feed import FederationChangeBundle, verify_incremental_change_bundle
from .federation import FederationPolicyError, _canonical_json
from .federation_broker_contract import (
    AuthenticatedParticipant,
    BrokerAuthorizationError,
    BrokerCapabilities,
    BrokerEnrollment,
    BrokerEnrollmentRequest,
    BrokerSigningKey,
    BundleAcknowledgementReceipt,
    BundleAcknowledgementRequest,
    CatalogDiscoveryRequest,
    CatalogDiscoveryResponse,
    CatalogSubmissionReceipt,
    ChangeBundlePage,
    ChangeBundlePullRequest,
    ChangeBundleReceipt,
    EnrollmentApprovalRequest,
    EnrollmentReceipt,
    EnrollmentRevocationReceipt,
    EnrollmentRevocationRequest,
    RevocationReceipt,
    SigningKeyAddRequest,
    SigningKeyReceipt,
    SigningKeyRevocationRequest,
    SubscriptionCreateRequest,
    SubscriptionReceipt,
    authorize_catalog_for_enrollment,
    authorize_change_bundle_for_enrollment,
    catalog_within_release_ceiling,
    ensure_subscription_within_enrollments,
)


class BrokerConflictError(ValueError):
    """The requested operation conflicts with durable broker state."""


class BrokerNotFoundError(ValueError):
    """A participant-scoped broker resource does not exist."""


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _json(model: BaseModel | dict[str, Any]) -> str:
    if isinstance(model, BaseModel):
        return _canonical_json(model.model_dump(mode="json"))
    return _canonical_json(model)


class FederationBrokerService:
    """Authenticated broker operations backed by a dedicated SQLite file."""

    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS broker_meta (
                    name TEXT PRIMARY KEY, value BLOB NOT NULL
                );
                CREATE TABLE IF NOT EXISTS enrollment_requests (
                    enrollment_id TEXT PRIMARY KEY,
                    participant_id TEXT NOT NULL,
                    producer_instance_id TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('pending','active','revoked')),
                    UNIQUE(participant_id, producer_instance_id)
                );
                CREATE TABLE IF NOT EXISTS enrollments (
                    enrollment_id TEXT PRIMARY KEY,
                    participant_id TEXT NOT NULL,
                    producer_instance_id TEXT NOT NULL UNIQUE,
                    enrollment_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS catalogs (
                    catalog_id TEXT PRIMARY KEY,
                    producer_instance_id TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    object_digest TEXT NOT NULL,
                    catalog_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS subscriptions (
                    subscription_id TEXT PRIMARY KEY,
                    owner_participant_id TEXT NOT NULL,
                    receiver_enrollment_id TEXT NOT NULL,
                    producer_enrollment_id TEXT NOT NULL,
                    producer_instance_id TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    producer_cursor TEXT NOT NULL DEFAULT '',
                    consumer_cursor TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS bundles (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    bundle_id TEXT NOT NULL UNIQUE,
                    subscription_id TEXT NOT NULL,
                    producer_instance_id TEXT NOT NULL,
                    cursor_start TEXT NOT NULL,
                    cursor_end TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    object_digest TEXT NOT NULL,
                    bundle_json TEXT NOT NULL,
                    FOREIGN KEY(subscription_id) REFERENCES subscriptions(subscription_id)
                );
                CREATE TABLE IF NOT EXISTS bundle_deliveries (
                    subscription_id TEXT NOT NULL,
                    bundle_id TEXT NOT NULL,
                    delivered_at TEXT NOT NULL,
                    acknowledged_at TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY(subscription_id, bundle_id),
                    FOREIGN KEY(subscription_id) REFERENCES subscriptions(subscription_id),
                    FOREIGN KEY(bundle_id) REFERENCES bundles(bundle_id)
                );
                CREATE INDEX IF NOT EXISTS bundles_subscription_sequence
                    ON bundles(subscription_id, sequence);
                """
            )
            connection.execute(
                "INSERT OR IGNORE INTO broker_meta(name,value) VALUES('cursor_hmac_key',?)",
                (secrets.token_bytes(32),),
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=15, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=15000")
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            yield connection
        except BaseException:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _active_enrollment(row: sqlite3.Row | None) -> BrokerEnrollment:
        if row is None:
            raise BrokerNotFoundError("enrollment not found")
        enrollment = BrokerEnrollment.model_validate_json(row["enrollment_json"])
        if enrollment.status != "active":
            raise BrokerAuthorizationError("enrollment is not active")
        return enrollment

    def _owned_enrollment(self, participant: AuthenticatedParticipant, producer_instance_id: str) -> BrokerEnrollment:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM enrollments WHERE participant_id=? AND producer_instance_id=?",
                (participant.participant_id, producer_instance_id),
            ).fetchone()
        return self._active_enrollment(row)

    def _enrollment_for_producer(self, producer_instance_id: str) -> BrokerEnrollment:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM enrollments WHERE producer_instance_id=?", (producer_instance_id,)
            ).fetchone()
        return self._active_enrollment(row)

    def capabilities(self) -> BrokerCapabilities:
        return BrokerCapabilities(operations=[
            "enrollment_requests", "admin_enrollment_approval", "catalog_publish",
            "catalog_discovery", "subscriptions", "change_bundle_submit",
            "change_bundle_pull", "change_bundle_acknowledgement", "key_revocation",
            "admin_signing_key_addition", "enrollment_revocation",
        ])

    def request_enrollment(
        self, participant: AuthenticatedParticipant, request: BrokerEnrollmentRequest
    ) -> EnrollmentReceipt:
        for key in request.signing_keys:
            try:
                parsed = serialization.load_pem_public_key(key.public_key_pem.encode("ascii"))
            except (ValueError, UnicodeEncodeError) as exc:
                raise BrokerAuthorizationError("invalid Ed25519 public key") from exc
            if not isinstance(parsed, Ed25519PublicKey):
                raise BrokerAuthorizationError("broker enrollment requires Ed25519 public keys")
        enrollment_id = "enr_" + uuid.uuid4().hex
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            prior = connection.execute(
                "SELECT * FROM enrollment_requests WHERE participant_id=? AND producer_instance_id=?",
                (participant.participant_id, request.producer_instance_id),
            ).fetchone()
            if prior:
                if prior["request_json"] != _json(request):
                    raise BrokerConflictError("producer already has a different enrollment request")
                enrollment_id = prior["enrollment_id"]
                status = prior["status"]
            else:
                existing = connection.execute(
                    "SELECT 1 FROM enrollments WHERE producer_instance_id=?", (request.producer_instance_id,)
                ).fetchone()
                if existing:
                    raise BrokerConflictError("producer instance is already enrolled")
                connection.execute(
                    "INSERT INTO enrollment_requests VALUES(?,?,?,?,?)",
                    (enrollment_id, participant.participant_id, request.producer_instance_id, _json(request), "pending"),
                )
                status = "pending"
            connection.commit()
        return EnrollmentReceipt(
            enrollment_id=enrollment_id,
            status=status,
            producer_instance_id=request.producer_instance_id,
            release_ceiling=request.requested_release_ceiling,
            realm_ids=request.requested_realm_ids,
            scope_ids=request.requested_scope_ids,
        )

    def approve_enrollment(
        self,
        administrator: AuthenticatedParticipant,
        enrollment_id: str,
        approval: EnrollmentApprovalRequest,
    ) -> EnrollmentReceipt:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM enrollment_requests WHERE enrollment_id=?", (enrollment_id,)
            ).fetchone()
            if row is None:
                raise BrokerNotFoundError("enrollment request not found")
            requested = BrokerEnrollmentRequest.model_validate_json(row["request_json"])
            if row["status"] == "active":
                saved = self._active_enrollment(connection.execute(
                    "SELECT * FROM enrollments WHERE enrollment_id=?", (enrollment_id,)
                ).fetchone())
                connection.commit()
                return self._enrollment_receipt(saved)
            if row["status"] != "pending":
                raise BrokerConflictError("enrollment request is no longer pending")
            if not set(approval.realm_ids) <= set(requested.requested_realm_ids):
                raise BrokerAuthorizationError("approved realms exceed enrollment request")
            if not set(approval.scope_ids) <= set(requested.requested_scope_ids):
                raise BrokerAuthorizationError("approved scopes exceed enrollment request")
            # Release labels are ordered from least to most sensitive by the contract.
            from .federation_broker_contract import RELEASE_LEVELS
            if RELEASE_LEVELS.index(approval.release_ceiling) > RELEASE_LEVELS.index(requested.requested_release_ceiling):
                raise BrokerAuthorizationError("approved release exceeds enrollment request")
            created = _now()
            enrollment = BrokerEnrollment(
                enrollment_id=enrollment_id,
                participant_id=row["participant_id"],
                producer_instance_id=requested.producer_instance_id,
                signing_keys=[BrokerSigningKey(
                    key_id=key.key_id,
                    algorithm=key.algorithm,
                    public_key_pem=key.public_key_pem,
                    created_at=created,
                ) for key in requested.signing_keys],
                realm_ids=approval.realm_ids,
                scope_ids=approval.scope_ids,
                release_ceiling=approval.release_ceiling,
                allowed_restriction_markers=approval.allowed_restriction_markers,
                allowed_compartments=approval.allowed_compartments,
                created_at=created,
                approved_by=administrator.participant_id,
            )
            connection.execute(
                "INSERT INTO enrollments VALUES(?,?,?,?)",
                (enrollment_id, row["participant_id"], requested.producer_instance_id, enrollment.model_dump_json()),
            )
            connection.execute(
                "UPDATE enrollment_requests SET status='active' WHERE enrollment_id=?", (enrollment_id,)
            )
            connection.commit()
        return self._enrollment_receipt(enrollment)

    @staticmethod
    def _enrollment_receipt(enrollment: BrokerEnrollment) -> EnrollmentReceipt:
        return EnrollmentReceipt(
            enrollment_id=enrollment.enrollment_id,
            status=enrollment.status,
            producer_instance_id=enrollment.producer_instance_id,
            release_ceiling=enrollment.release_ceiling,
            realm_ids=enrollment.realm_ids,
            scope_ids=enrollment.scope_ids,
        )

    def publish_catalog(
        self, participant: AuthenticatedParticipant, catalog: FederationCatalog
    ) -> CatalogSubmissionReceipt:
        enrollment = self._owned_enrollment(participant, catalog.manifest.producer_instance_id)
        key = authorize_catalog_for_enrollment(catalog, authenticated_participant=participant, enrollment=enrollment)
        try:
            verify_federation_catalog(catalog, verification_key=key.public_key_pem, key_id=key.key_id)
        except FederationPolicyError as exc:
            raise BrokerAuthorizationError("catalog signature or content hash is invalid") from exc
        serialized = _json(catalog)
        digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            prior = connection.execute("SELECT * FROM catalogs WHERE catalog_id=?", (catalog.manifest.catalog_id,)).fetchone()
            if prior:
                if prior["producer_instance_id"] != enrollment.producer_instance_id or prior["object_digest"] != digest:
                    raise BrokerConflictError("catalog ID is already bound to different content")
                duplicate = True
            else:
                connection.execute(
                    "INSERT INTO catalogs VALUES(?,?,?,?,?)",
                    (catalog.manifest.catalog_id, enrollment.producer_instance_id, catalog.manifest.content_hash, digest, serialized),
                )
                duplicate = False
            connection.commit()
        return CatalogSubmissionReceipt(
            catalog_id=catalog.manifest.catalog_id,
            producer_instance_id=enrollment.producer_instance_id,
            content_hash=catalog.manifest.content_hash,
            accepted=True,
            duplicate=duplicate,
        )

    def discover_catalogs(
        self, participant: AuthenticatedParticipant, request: CatalogDiscoveryRequest
    ) -> CatalogDiscoveryResponse:
        with self._connection() as connection:
            own_rows = connection.execute(
                "SELECT * FROM enrollments WHERE participant_id=?", (participant.participant_id,)
            ).fetchall()
            catalog_rows = connection.execute("SELECT * FROM catalogs ORDER BY catalog_id").fetchall()
            producer_rows = {row["producer_instance_id"]: row for row in connection.execute("SELECT * FROM enrollments").fetchall()}
        own = [BrokerEnrollment.model_validate_json(row["enrollment_json"]) for row in own_rows]
        own = [item for item in own if item.status == "active"]
        entries: list[FederationCatalog] = []
        term = request.query.casefold().strip()
        for row in catalog_rows:
            producer_row = producer_rows.get(row["producer_instance_id"])
            if producer_row is None:
                continue
            producer = BrokerEnrollment.model_validate_json(producer_row["enrollment_json"])
            if producer.status != "active":
                continue
            producer_catalog = FederationCatalog.model_validate_json(row["catalog_json"])
            catalog_scopes = {entry.scope_id for entry in producer_catalog.entries}
            for receiver in own:
                shared_realms = set(receiver.realm_ids) & set(producer.realm_ids)
                if request.realm_id and request.realm_id not in shared_realms:
                    continue
                if not catalog_scopes <= set(receiver.scope_ids):
                    continue
                # Catalogs are delivered intact so publisher signatures remain
                # verifiable. Do not disclose even their summaries when any
                # declared release level exceeds this receiver's approved cap.
                if not catalog_within_release_ceiling(producer_catalog, receiver.release_ceiling):
                    continue
                if request.scope_ids and not (catalog_scopes & set(request.scope_ids)):
                    continue
                if term:
                    searchable = " ".join([
                        entry.title + " " + " ".join(entry.topic_summaries) + " " + entry.scope_id
                        for entry in producer_catalog.entries
                    ]).casefold()
                    if term not in searchable:
                        continue
                entries.append(producer_catalog)
                break
            if len(entries) >= request.limit:
                break
        return CatalogDiscoveryResponse(catalogs=entries)

    def create_subscription(
        self, participant: AuthenticatedParticipant, request: SubscriptionCreateRequest
    ) -> SubscriptionReceipt:
        producer = self._enrollment_for_producer(request.producer_instance_id)
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM enrollments WHERE participant_id=?", (participant.participant_id,)
            ).fetchall()
        candidates: list[BrokerEnrollment] = []
        for row in rows:
            receiver = BrokerEnrollment.model_validate_json(row["enrollment_json"])
            try:
                ensure_subscription_within_enrollments(request, receiver=receiver, producer=producer)
            except BrokerAuthorizationError:
                continue
            candidates.append(receiver)
        if not candidates:
            raise BrokerAuthorizationError("subscription is outside participant enrollment bounds")
        if len(candidates) > 1:
            raise BrokerConflictError("subscription matches multiple receiver enrollments")
        receiver = candidates[0]
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM subscriptions WHERE subscription_id=?", (request.subscription_id,)
            ).fetchone()
            if row:
                if row["owner_participant_id"] != participant.participant_id or row["request_json"] != _json(request):
                    raise BrokerConflictError("subscription ID is already bound to different content")
                connection.commit()
                return self._subscription_receipt(request)
            connection.execute(
                "INSERT INTO subscriptions(subscription_id,owner_participant_id,receiver_enrollment_id,producer_enrollment_id,producer_instance_id,request_json) VALUES(?,?,?,?,?,?)",
                (request.subscription_id, participant.participant_id, receiver.enrollment_id, producer.enrollment_id, producer.producer_instance_id, _json(request)),
            )
            connection.commit()
        return self._subscription_receipt(request)

    @staticmethod
    def _subscription_receipt(request: SubscriptionCreateRequest) -> SubscriptionReceipt:
        return SubscriptionReceipt(
            subscription_id=request.subscription_id,
            producer_instance_id=request.producer_instance_id,
            realm_id=request.realm_id,
            scope_ids=request.scope_ids,
            release_ceiling=request.release_ceiling,
            active=True,
        )

    def submit_bundle(
        self, participant: AuthenticatedParticipant, bundle: FederationChangeBundle
    ) -> ChangeBundleReceipt:
        manifest = bundle.manifest
        producer = self._owned_enrollment(participant, manifest.producer_instance_id)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            sub_row = connection.execute(
                "SELECT * FROM subscriptions WHERE subscription_id=?", (manifest.subscription_id,)
            ).fetchone()
            if sub_row is None:
                raise BrokerNotFoundError("subscription not found")
            subscription = SubscriptionCreateRequest.model_validate_json(sub_row["request_json"])
            producer_grant_row = connection.execute(
                "SELECT * FROM enrollments WHERE enrollment_id=?", (sub_row["producer_enrollment_id"],)
            ).fetchone()
            producer_grant = self._active_enrollment(producer_grant_row)
            receiver_row = connection.execute(
                "SELECT * FROM enrollments WHERE enrollment_id=?", (sub_row["receiver_enrollment_id"],)
            ).fetchone()
            receiver_grant = self._active_enrollment(receiver_row)
            # The submitting producer must still be the producer approved when the receiver subscribed.
            if producer.enrollment_id != producer_grant.enrollment_id:
                raise BrokerAuthorizationError("producer enrollment does not match subscription")
            ensure_subscription_within_enrollments(subscription, receiver=receiver_grant, producer=producer_grant)
            serialized = _json(bundle)
            digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
            prior = connection.execute("SELECT * FROM bundles WHERE bundle_id=?", (manifest.bundle_id,)).fetchone()
            if prior:
                if prior["subscription_id"] != manifest.subscription_id or prior["object_digest"] != digest:
                    raise BrokerConflictError("bundle ID is already bound to different content")
                connection.commit()
                return ChangeBundleReceipt(
                    bundle_id=manifest.bundle_id,
                    producer_instance_id=manifest.producer_instance_id,
                    subscription_id=manifest.subscription_id,
                    content_hash=manifest.content_hash,
                    accepted=True,
                    duplicate=True,
                )
            key = authorize_change_bundle_for_enrollment(
                bundle, authenticated_participant=participant, enrollment=producer, subscription=subscription
            )
            try:
                verify_incremental_change_bundle(bundle, verification_key=key.public_key_pem, key_id=key.key_id)
            except FederationPolicyError as exc:
                raise BrokerAuthorizationError("change bundle signature or content hash is invalid") from exc
            expected_cursor_end = bundle.events[-1].event_id if bundle.events else manifest.cursor_start
            if manifest.event_count != len(bundle.events) or manifest.cursor_end != expected_cursor_end:
                raise BrokerAuthorizationError("change bundle cursor or event count is invalid")
            if any(event.realm_id and event.realm_id != subscription.realm_id for event in bundle.events):
                raise BrokerAuthorizationError("change bundle event is outside approved realm")
            if manifest.cursor_start != sub_row["producer_cursor"]:
                raise BrokerConflictError("bundle cursor does not continue broker producer cursor")
            connection.execute(
                "INSERT INTO bundles(bundle_id,subscription_id,producer_instance_id,cursor_start,cursor_end,content_hash,object_digest,bundle_json) VALUES(?,?,?,?,?,?,?,?)",
                (manifest.bundle_id, manifest.subscription_id, manifest.producer_instance_id, manifest.cursor_start, manifest.cursor_end, manifest.content_hash, digest, serialized),
            )
            connection.execute(
                "UPDATE subscriptions SET producer_cursor=? WHERE subscription_id=?",
                (manifest.cursor_end, manifest.subscription_id),
            )
            connection.commit()
        return ChangeBundleReceipt(
            bundle_id=manifest.bundle_id,
            producer_instance_id=manifest.producer_instance_id,
            subscription_id=manifest.subscription_id,
            content_hash=manifest.content_hash,
            accepted=True,
        )

    def _cursor_key(self) -> bytes:
        with self._connection() as connection:
            row = connection.execute("SELECT value FROM broker_meta WHERE name='cursor_hmac_key'").fetchone()
        return bytes(row["value"])

    def _encode_cursor(self, subscription_id: str, sequence: int) -> str:
        payload = f"{subscription_id}\n{sequence}".encode("utf-8")
        signature = hmac.new(self._cursor_key(), payload, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(payload + b"\n" + signature.hex().encode("ascii")).decode("ascii").rstrip("=")

    def _decode_cursor(self, cursor: str, subscription_id: str) -> int:
        if not cursor:
            return 0
        try:
            raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
            payload, supplied_hex = raw.rsplit(b"\n", 1)
            supplied = bytes.fromhex(supplied_hex.decode("ascii"))
            expected = hmac.new(self._cursor_key(), payload, hashlib.sha256).digest()
            cursor_subscription, sequence_text = payload.decode("utf-8").split("\n", 1)
            sequence = int(sequence_text)
        except (ValueError, UnicodeDecodeError) as exc:
            raise BrokerAuthorizationError("invalid broker cursor") from exc
        if not hmac.compare_digest(supplied, expected) or cursor_subscription != subscription_id or sequence < 0:
            raise BrokerAuthorizationError("invalid broker cursor")
        return sequence

    def pull_bundles(
        self, participant: AuthenticatedParticipant, request: ChangeBundlePullRequest
    ) -> ChangeBundlePage:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            sub = connection.execute(
                "SELECT * FROM subscriptions WHERE subscription_id=? AND owner_participant_id=?",
                (request.subscription_id, participant.participant_id),
            ).fetchone()
            if sub is None:
                raise BrokerNotFoundError("subscription not found")
            self._active_enrollment(connection.execute(
                "SELECT * FROM enrollments WHERE enrollment_id=?", (sub["receiver_enrollment_id"],)
            ).fetchone())
            last_sequence = self._decode_cursor(request.after_cursor, request.subscription_id)
            rows = connection.execute(
                "SELECT * FROM bundles WHERE subscription_id=? AND sequence>? ORDER BY sequence LIMIT ?",
                (request.subscription_id, last_sequence, request.limit),
            ).fetchall()
            for row in rows:
                connection.execute(
                    "INSERT OR IGNORE INTO bundle_deliveries(subscription_id,bundle_id,delivered_at) VALUES(?,?,?)",
                    (request.subscription_id, row["bundle_id"], _now()),
                )
            connection.commit()
        models = [FederationChangeBundle.model_validate_json(row["bundle_json"]) for row in rows]
        next_cursor = self._encode_cursor(request.subscription_id, rows[-1]["sequence"]) if rows else request.after_cursor
        return ChangeBundlePage(subscription_id=request.subscription_id, bundles=models, next_cursor=next_cursor)

    def acknowledge_bundle(
        self, participant: AuthenticatedParticipant, request: BundleAcknowledgementRequest
    ) -> BundleAcknowledgementReceipt:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            bundle = connection.execute("SELECT * FROM bundles WHERE bundle_id=?", (request.bundle_id,)).fetchone()
            if bundle is None:
                raise BrokerNotFoundError("bundle not found")
            sub = connection.execute(
                "SELECT * FROM subscriptions WHERE subscription_id=? AND owner_participant_id=?",
                (bundle["subscription_id"], participant.participant_id),
            ).fetchone()
            if sub is None:
                raise BrokerNotFoundError("bundle not found")
            self._active_enrollment(connection.execute(
                "SELECT * FROM enrollments WHERE enrollment_id=?", (sub["receiver_enrollment_id"],)
            ).fetchone())
            if request.cursor != bundle["cursor_end"]:
                raise BrokerConflictError("acknowledgement cursor does not match bundle")
            delivery = connection.execute(
                "SELECT * FROM bundle_deliveries WHERE subscription_id=? AND bundle_id=?",
                (bundle["subscription_id"], request.bundle_id),
            ).fetchone()
            if delivery is None:
                raise BrokerAuthorizationError("bundle must be delivered before acknowledgement")
            if delivery["acknowledged_at"]:
                connection.commit()
                return BundleAcknowledgementReceipt(
                    bundle_id=request.bundle_id,
                    subscription_id=bundle["subscription_id"],
                    cursor=request.cursor,
                    duplicate=True,
                )
            if bundle["cursor_start"] != sub["consumer_cursor"]:
                raise BrokerConflictError("bundle acknowledgement is out of order")
            prior = connection.execute(
                "SELECT bundle_id FROM bundles WHERE subscription_id=? AND sequence<? ORDER BY sequence DESC LIMIT 1",
                (bundle["subscription_id"], bundle["sequence"]),
            ).fetchone()
            if prior:
                prior_delivery = connection.execute(
                    "SELECT acknowledged_at FROM bundle_deliveries WHERE subscription_id=? AND bundle_id=?",
                    (bundle["subscription_id"], prior["bundle_id"]),
                ).fetchone()
                if prior_delivery is None or not prior_delivery["acknowledged_at"]:
                    raise BrokerConflictError("bundle acknowledgements must follow delivery order")
            connection.execute(
                "UPDATE bundle_deliveries SET acknowledged_at=? WHERE subscription_id=? AND bundle_id=?",
                (_now(), bundle["subscription_id"], request.bundle_id),
            )
            connection.execute(
                "UPDATE subscriptions SET consumer_cursor=? WHERE subscription_id=?",
                (request.cursor, bundle["subscription_id"]),
            )
            connection.commit()
        return BundleAcknowledgementReceipt(
            bundle_id=request.bundle_id,
            subscription_id=bundle["subscription_id"],
            cursor=request.cursor,
        )

    def revoke_key(
        self,
        participant: AuthenticatedParticipant,
        enrollment_id: str,
        key_id: str,
        request: SigningKeyRevocationRequest,
    ) -> RevocationReceipt:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM enrollments WHERE enrollment_id=? AND participant_id=?",
                (enrollment_id, participant.participant_id),
            ).fetchone()
            enrollment = self._active_enrollment(row)
            keys = list(enrollment.signing_keys)
            target = next((index for index, key in enumerate(keys) if key.key_id == key_id), None)
            if target is None:
                raise BrokerNotFoundError("signing key not found")
            if keys[target].status == "revoked":
                connection.commit()
                key = keys[target]
                return RevocationReceipt(
                    enrollment_id=enrollment_id,
                    producer_instance_id=enrollment.producer_instance_id,
                    key_id=key_id,
                    revoked_at=key.revoked_at,
                )
            revoked_at = _now()
            keys[target] = keys[target].model_copy(update={
                "status": "revoked", "revoked_at": revoked_at, "revocation_reason": request.reason
            })
            updated = enrollment.model_copy(update={"signing_keys": keys})
            connection.execute("UPDATE enrollments SET enrollment_json=? WHERE enrollment_id=?", (updated.model_dump_json(), enrollment_id))
            connection.commit()
        return RevocationReceipt(
            enrollment_id=enrollment_id,
            producer_instance_id=enrollment.producer_instance_id,
            key_id=key_id,
            revoked_at=revoked_at,
        )

    def add_signing_key(
        self,
        administrator: AuthenticatedParticipant,
        enrollment_id: str,
        request: SigningKeyAddRequest,
    ) -> SigningKeyReceipt:
        """Add a replacement Ed25519 key without changing producer identity.

        Repeating the same request for an already-active key is idempotent.
        Revoked key IDs and already-enrolled public keys are never reactivated.
        """

        if "broker_admin" not in administrator.roles:
            raise BrokerAuthorizationError("admin role required")
        try:
            parsed = serialization.load_pem_public_key(request.public_key_pem.encode("ascii"))
        except (TypeError, ValueError, UnicodeEncodeError) as exc:
            raise BrokerAuthorizationError("invalid Ed25519 public key") from exc
        if not isinstance(parsed, Ed25519PublicKey):
            raise BrokerAuthorizationError("broker enrollment requires Ed25519 public keys")
        canonical_pem = parsed.public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("ascii")
        public_der = parsed.public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM enrollments WHERE enrollment_id=?", (enrollment_id,)
            ).fetchone()
            enrollment = self._active_enrollment(row)
            prior = next((key for key in enrollment.signing_keys if key.key_id == request.key_id), None)
            if prior is not None:
                try:
                    prior_public = serialization.load_pem_public_key(prior.public_key_pem.encode("ascii"))
                    prior_der = prior_public.public_bytes(
                        serialization.Encoding.DER,
                        serialization.PublicFormat.SubjectPublicKeyInfo,
                    )
                except (TypeError, ValueError, UnicodeEncodeError) as exc:
                    raise BrokerConflictError("stored signing key cannot be compared safely") from exc
                if prior_der != public_der or prior.status != "active":
                    raise BrokerConflictError("signing key ID is already used or revoked")
                connection.commit()
                return SigningKeyReceipt(
                    enrollment_id=enrollment_id,
                    producer_instance_id=enrollment.producer_instance_id,
                    key_id=request.key_id,
                    added_at=prior.created_at,
                    duplicate=True,
                )

            for existing in enrollment.signing_keys:
                try:
                    existing_public = serialization.load_pem_public_key(existing.public_key_pem.encode("ascii"))
                    existing_der = existing_public.public_bytes(
                        serialization.Encoding.DER,
                        serialization.PublicFormat.SubjectPublicKeyInfo,
                    )
                except (TypeError, ValueError, UnicodeEncodeError) as exc:
                    raise BrokerConflictError("stored signing key cannot be compared safely") from exc
                if existing_der == public_der:
                    raise BrokerConflictError("public signing key is already enrolled under another key ID")

            if len(enrollment.signing_keys) >= 10:
                raise BrokerConflictError("enrollment already has the maximum number of signing keys")
            added_at = _now()
            updated = enrollment.model_copy(update={
                "signing_keys": [
                    *enrollment.signing_keys,
                    BrokerSigningKey(
                        key_id=request.key_id,
                        algorithm="ed25519",
                        public_key_pem=canonical_pem,
                        created_at=added_at,
                    ),
                ]
            })
            connection.execute(
                "UPDATE enrollments SET enrollment_json=? WHERE enrollment_id=?",
                (updated.model_dump_json(), enrollment_id),
            )
            connection.commit()
        return SigningKeyReceipt(
            enrollment_id=enrollment_id,
            producer_instance_id=enrollment.producer_instance_id,
            key_id=request.key_id,
            added_at=added_at,
        )

    def revoke_enrollment(
        self,
        actor: AuthenticatedParticipant,
        enrollment_id: str,
        request: EnrollmentRevocationRequest,
        *,
        administrator: bool = False,
    ) -> EnrollmentRevocationReceipt:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM enrollments WHERE enrollment_id=?", (enrollment_id,)).fetchone()
            if row is None:
                raise BrokerNotFoundError("enrollment not found")
            if not administrator and row["participant_id"] != actor.participant_id:
                raise BrokerNotFoundError("enrollment not found")
            enrollment = BrokerEnrollment.model_validate_json(row["enrollment_json"])
            if enrollment.status == "revoked":
                connection.commit()
                return EnrollmentRevocationReceipt(
                    enrollment_id=enrollment_id,
                    producer_instance_id=enrollment.producer_instance_id,
                    revoked_at=enrollment.revoked_at,
                )
            revoked_at = _now()
            keys = [key.model_copy(update={
                "status": "revoked", "revoked_at": revoked_at, "revocation_reason": request.reason
            }) if key.status == "active" else key for key in enrollment.signing_keys]
            updated = enrollment.model_copy(update={
                "status": "revoked", "revoked_at": revoked_at,
                "revocation_reason": request.reason, "signing_keys": keys,
            })
            connection.execute("UPDATE enrollments SET enrollment_json=? WHERE enrollment_id=?", (updated.model_dump_json(), enrollment_id))
            connection.execute("UPDATE enrollment_requests SET status='revoked' WHERE enrollment_id=?", (enrollment_id,))
            connection.commit()
        return EnrollmentRevocationReceipt(
            enrollment_id=enrollment_id,
            producer_instance_id=enrollment.producer_instance_id,
            revoked_at=revoked_at,
        )


__all__ = ["BrokerConflictError", "BrokerNotFoundError", "FederationBrokerService"]
