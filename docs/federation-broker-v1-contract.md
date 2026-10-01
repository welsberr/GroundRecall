# Federation Broker HTTP Contract, Version 1

This document defines the first transport contract for a deployable GroundRecall federation broker. The broker is a delivery and discovery service for existing signed federation catalogs and incremental change bundles. It does not own either participant's canonical store, and delivery never accepts or promotes knowledge on the receiver's behalf.

The Python request and response models, route declarations, authorization helpers, and generated JSON schemas live in `src/groundrecall/federation_broker_contract.py`. The broker API base path is `/api/v1`; every broker envelope carries a `groundrecall.federation_broker.*.v1` schema version.

## Identity and trust

Every authenticated HTTP request has a participant identity assigned by the deployment's authentication middleware. A request body cannot choose or override that identity. Enrollment requests name a GroundRecall producer instance and submit only public Ed25519 signing keys; private signing keys remain with the producer.

An approved enrollment binds the middleware participant to a producer instance, active signing keys, allowed realms, allowed scopes, a release ceiling, and any accepted restriction markers or compartments. Broker administrators approve requested enrollments. Catalog and bundle manifests must name the enrolled producer instance, and their signer key ID and algorithm must resolve to an active key in that participant's enrollment. The broker must also run the existing catalog or change-bundle signature and content-hash verifier with the resolved public key; the contract's identity helpers do not replace cryptographic verification.

The Ed25519-only broker profile avoids putting shared HMAC secrets in the broker. Existing GroundRecall files and APIs continue to support their existing signature algorithms; a producer must use Ed25519 for broker submission.

Subscriptions are receiver-owned. A requested subscription is authorized only when both the receiver and producer enrollments allow its realm, every requested scope, the release ceiling, restriction markers, and compartments. Effective scope and release bounds are their intersection. Request bodies omit receiver identity, cursor state, and `auto_accept`; the server derives the receiver from authentication, owns the cursor, and projects an approved request into the existing `FederationSubscription` model.

Signing-key revocation immediately prevents that key from authorizing new broker submissions. Enrollment revocation disables all keys and access for that producer binding. Previously accepted bundles retain their original signature and provenance; receiving clients still verify them and place imported content in local quarantine for review.

An administrator can add a replacement public Ed25519 key to an active enrollment without changing its producer instance ID. Existing keys remain in the enrollment history with their original status. Repeating an add with the same key ID and public key is idempotent; reusing a key ID with different material, reactivating a revoked key ID, or enrolling the same public key under another ID conflicts.

## HTTP operations

| Method and path | Authentication | Purpose |
| --- | --- | --- |
| `GET /api/v1/broker` | None | Discover API version, signature profile, and operations. |
| `POST /api/v1/enrollment-requests` | Participant | Request producer enrollment with public signing keys and requested bounds. |
| `POST /api/v1/admin/enrollments/{enrollment_id}/approval` | Broker administrator | Approve exact realms, scopes, release ceiling, and restrictions. |
| `POST /api/v1/admin/enrollments/{enrollment_id}/signing-keys` | Broker administrator | Add a validated public Ed25519 key to an active enrollment. The request carries `key_id`, `algorithm: "ed25519"`, and `public_key_pem`; the receipt reports `added_at` and whether the request was a duplicate. |
| `POST /api/v1/catalogs` | Participant | Publish a complete signed `FederationCatalog`. |
| `POST /api/v1/catalogs/discover` | Participant | Discover complete signed catalogs matching authorized discovery filters. |
| `POST /api/v1/subscriptions` | Participant | Create a bounded receiver subscription. |
| `POST /api/v1/change-bundles` | Participant | Submit a signed incremental `FederationChangeBundle`. |
| `POST /api/v1/change-bundles/pull` | Participant | Pull bounded bundles for one of the caller's subscriptions. |
| `POST /api/v1/change-bundles/acknowledgements` | Participant | Acknowledge a delivered bundle and its cursor. |
| `POST /api/v1/enrollments/{enrollment_id}/keys/{key_id}/revocation` | Participant | Revoke a signing key bound to the caller's enrollment. |
| `POST /api/v1/enrollments/{enrollment_id}/revocation` | Participant | Revoke the caller's entire producer enrollment. |
| `POST /api/v1/admin/enrollments/{enrollment_id}/revocation` | Broker administrator | Revoke any enrollment. |

Catalog responses preserve the publisher's complete signed catalog so its original signature remains verifiable. The broker returns it only when the complete catalog manifest and all declared entry release levels fit the receiver's approved release ceiling, in addition to realm and scope authorization; it must not trim entries and present the changed catalog as publisher-signed.

Publication receipts identify the signed object and content hash. Repeated submissions of the same object are idempotent and report `duplicate`; a conflicting object using an existing object ID is rejected. Pulls and acknowledgements are scoped to the authenticated participant and its approved subscription. Acknowledgements are idempotent and cannot advance a cursor beyond the acknowledged bundle.

## Compatibility and receiver behavior

The wire payloads reuse `FederationCatalog` from `catalog.py` and `FederationChangeBundle` from `change_feed.py`, preserving the existing signed manifests, producer instance IDs, subscription IDs, event origins, and content hashes. Approved subscription settings map to the existing `FederationSubscription`; the broker adds transport and account binding outside that file format.

Broker delivery is not an import decision. The receiver continues to verify signature, producer, subscription, cursor, scope, and release constraints, then writes the bundle to quarantine using the current import path. Only a separate local review or promotion workflow may alter canonical knowledge.

The contracts intentionally do not define a concrete authentication provider, database, server framework, container image, or public deployment address. Those belong to subsequent implementation steps; the server must honor the participant and administrator authentication classes declared by the route table.
