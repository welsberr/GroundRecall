# GroundRecall Implemented Features Summary

Date: 2026-07-26

This summary lists the implemented GroundRecall capabilities that are now in shape to support preprint drafting. It separates implemented prototype features from remaining roadmap work.

## Core Knowledge Substrate

GroundRecall provides a local, file-backed knowledge substrate for grounded assistant workflows.

- Structured records for sources, artifacts, observations, claims, concepts, relations, contradiction cases, promotions, adjudications, and snapshots.
- Local `GroundRecallStore` persistence with deterministic JSON records.
- Snapshot construction from a store for export, review, and federation workflows.
- Query/export surfaces for graph and provenance-oriented use.
- Source adapter framework for importing material from multiple upstream formats.

## Provenance-Preserving Memory Model

The implemented model keeps provenance attached to claims and observations rather than flattening memory into ungrounded summaries.

- Observations carry provenance metadata such as support kind and grounding status.
- Claims can reference source observations, supporting fragments, concepts, contradictions, and superseded claims.
- Explicit contradiction links can be materialized as first-class contradiction cases.
- Contradiction cases preserve status, severity, rationale, timestamps, metadata, and adjudication linkage.
- Export and federation workflows preserve record identities and content hashes.
- Promotion workflows distinguish candidate/imported material from canonical store state.

## Contradiction Case Review And Adjudication

GroundRecall now supports a first operational slice for robust contradiction tracking.

- `contradicts_claim_ids` links can be synchronized into deterministic contradiction case records.
- Query bundles surface contradiction cases alongside raw contradiction links.
- Graph diagnostics distinguish contradiction links from contradiction cases.
- Diagnostics flag:
  - explicit contradiction links without cases
  - contradiction cases referencing missing claims
  - open cases involving promoted claims
- Adjudications can target contradiction cases directly.
- `groundrecall contradictions sync STORE` materializes missing cases.
- `groundrecall contradictions list STORE --sync` returns review batches with claim previews and adjudication schema.
- `groundrecall contradictions adjudicate STORE CASE_ID ...` records review decisions while preserving the underlying conflicting claims.
- Semantic contradiction detection is not claimed; the current implementation operates on explicit contradiction links.

## Confidence And Temporal Validity Infrastructure

GroundRecall has implemented confidence-oriented metadata and migration support sufficient to discuss confidence as a structured assessment layer.

- Confidence records can represent multiple dimensions rather than only a single score.
- Confidence logic accounts for basis visibility, ambiguity, applicability, expiry, supersession, and retraction metadata.
- Temporal validity is represented through explicit validity/expiry/supersession fields rather than hard deletion.
- This supports the governance framing that “forgetting” can be modeled as expiry, supersession, and confidence reduction while preserving audit history.

## Release-Level Classification

Federation and export workflows implement an access/release lattice.

- Supported release levels:
  - `public`
  - `internal`
  - `confidential`
  - `privileged`
  - `private`
- `private` records are local-only and are not federated.
- The release lattice prevents access broadening during export.
- Public export blocks confidential/privileged/private material unless redaction/declassification metadata supports the derivative.
- Hidden supporting evidence can be represented as partial basis visibility rather than silently discarded.

## Federation Bundle Export And Verification

GroundRecall now supports signed federation bundles for controlled exchange between instances.

- `groundrecall federation export` writes signed federation bundles.
- Bundle manifests include producer instance, owner instance, target release level, source snapshot ID, record count, content hash, and signature.
- `groundrecall federation import` verifies bundles and places them into quarantine.
- Bundle verification checks:
  - signature
  - expected key ID
  - content hash
  - accepted release level
  - bundle policy violations
- HMAC signing remains available for local/shared-secret workflows.
- Ed25519 signing is implemented for public-key verification workflows.

## Quarantine And Promotion Workflow

Federated material does not enter canonical memory directly.

- Imported bundles are written to quarantine first.
- Quarantine summaries can be listed.
- Promotion can be planned as a dry run.
- Promotion can be applied only after signature verification, release-level acceptance, local policy checks, and conflict checks.
- Contradiction cases are included in federation bundles only when the case and all referenced claims are exportable at the target release level.
- Conflict handling remains review-gated rather than last-write-wins.
- Promotion avoids overwriting existing canonical records.

## Local Federation Policy And Audit

GroundRecall supports local authorization policy for federation actions.

- `FederationLocalPolicy` grants actions by:
  - subject ID
  - action
  - release level
  - instance ID
  - scope ID
  - privileged allowance
- Supported federation actions:
  - `export`
  - `import`
  - `promote`
- Scoped grants require matching `--scope-id`.
- Unscoped grants remain global for their permitted action, release level, and instance.
- CLI federation commands support `--policy-file`, `--requester-id`, `--scope-id`, and `--audit-log`.
- Audit events capture requester, action, decision, release level, bundle ID, instance ID, scope ID, policy ID, reasons, and metadata.

## Trust Registry

GroundRecall implements local trust registries for federation verification and signing workflows.

- `FederationTrustRegistry` maps instance IDs and key IDs to locally trusted key material.
- HMAC entries store shared secrets and must be treated as secret local trust roots.
- Ed25519 entries store public verification keys.
- Trust entries include:
  - algorithm
  - active status
  - creation timestamp
  - expiry timestamp
  - revocation timestamp
  - revocation reason
  - superseding key ID
  - allowed release levels
  - trusted actions
- Expired, inactive, or revoked keys are retained for audit/history but blocked from export, import, and promotion.
- CLI support includes:
  - `trust-add`
  - `trust-list`
  - `trust-revoke`

## Non-Secret Trust Metadata Export

GroundRecall can export trust metadata without leaking local key material.

- `trust-export-metadata` writes `groundrecall.federation_trust_metadata.v1`.
- Metadata exports omit `key_material`.
- Metadata includes instance/key IDs, algorithm, lifecycle fields, release levels, and trusted actions.
- Optional `sha256:` fingerprints are available for operator comparison.
- Fingerprints are explicitly treated as suitable only for high-entropy keys, because fingerprints of weak shared secrets can aid guessing.

## Ed25519 Federation Signatures

GroundRecall supports asymmetric bundle signatures.

- Bundle export can sign with an Ed25519 private key.
- Bundle import/promotion can verify with an Ed25519 public key from a trust registry.
- Trust registry lookup enforces algorithm consistency.
- HMAC remains the default for backward compatibility.
- The implementation uses the `cryptography` package.

## Signed Public Keysets

GroundRecall supports signed Ed25519 public-key publication.

- Producers can publish Ed25519 public keys from a local trust registry as a signed public keyset.
- Receivers verify keysets with a pinned Ed25519 signer public key.
- Keyset verification checks:
  - Ed25519 signature
  - signer key ID
  - content hash
  - key count
- Keyset import is locally capped before merging into a receiver trust registry.
- Receiver caps include:
  - instance IDs
  - release levels
  - trusted actions
- By default, keyset import only accepts keys for the keyset producer instance.

## Role Directories And Scoped Policy Compilation

GroundRecall implements role directories as reusable policy inputs.

- `FederationRoleDirectory` contains role definitions and memberships.
- Role definitions specify actions, release levels, instance IDs, scopes, and privileged allowance.
- Memberships map subject IDs to role IDs.
- `policy-from-roles` compiles role directories into ordinary local federation policy files.
- Compilation fails closed if a membership references an unknown role.
- Runtime enforcement still uses the audited `FederationLocalPolicy` grant model.

## Signed Role-Directory Publication

GroundRecall supports signed role-directory distribution.

- A project or entity hub can publish a signed role directory.
- Receivers verify the publication with a pinned Ed25519 signer public key.
- Verification checks:
  - Ed25519 signature
  - signer key ID
  - role count
  - membership count
  - content hash
- Import compiles a locally capped policy rather than trusting the published directory directly.
- Receiver caps include:
  - allowed subjects
  - allowed roles
  - allowed instances
  - allowed release levels
  - allowed actions
  - allowed scopes
- Wildcard instance grants are narrowed to receiver-approved instance IDs during import.

## CLI Surface

Implemented federation CLI commands include:

- `groundrecall federation export`
- `groundrecall federation import`
- `groundrecall federation list-quarantine`
- `groundrecall federation promote`
- `groundrecall federation policy-from-roles`
- `groundrecall federation role-publish-directory`
- `groundrecall federation policy-import-roles`
- `groundrecall federation trust-add`
- `groundrecall federation trust-list`
- `groundrecall federation trust-revoke`
- `groundrecall federation trust-export-metadata`
- `groundrecall federation trust-publish-keyset`
- `groundrecall federation trust-import-keyset`

Implemented contradiction CLI commands include:

- `groundrecall contradictions sync`
- `groundrecall contradictions list`
- `groundrecall contradictions adjudicate`

## Test And Validation Status

As of the latest implementation pass:

- Contradiction workflow test suite: `7 passed`
- Full test suite: `171 passed`
- Python compile check passes.
- `git diff --check` passes.
- Repository is clean and synced to `github/main`.

## Preprint-Ready Claims

The implementation now supports defensible preprint claims that GroundRecall demonstrates:

- a provenance-preserving local memory layer;
- explicit confidence/temporal-validity handling;
- explicit contradiction case tracking and adjudication without destructive claim rewriting;
- release-level-aware export and federation;
- signed exchange bundles;
- quarantine-before-promotion import;
- local policy-gated federation actions;
- auditable decisions;
- trust key lifecycle management;
- public-key federation verification with Ed25519;
- signed public-key distribution;
- signed role-directory distribution with receiver-side caps.

## Remaining Work To Treat As Limitations Or Future Work

The current implementation should not be described as a complete distributed platform.

Remaining roadmap items include:

- network transport and polling;
- hosted review services;
- automatic semantic contradiction detection;
- real-time synchronization;
- conflict-free replicated data types;
- public/internal release-pack publishing;
- stronger operator UX around review reports;
- broader integration with organization identity systems;
- production key management and recovery procedures.

For the preprint, these should be presented as limitations and future work, not as implemented capabilities.
