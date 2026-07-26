# GroundRecall Preprint Roadmap

Date: 2026-07-26

This roadmap begins the paper-preparation phase for GroundRecall. It freezes the current implementation scope for preprint purposes, identifies defensible claims, and defines the remaining documentation, evidence, and drafting work needed before writing the manuscript.

## Scope Freeze For The Preprint

The preprint should present GroundRecall as a working prototype and architecture for governed AI memory, not as a completed distributed platform.

### In Scope

The paper can describe and demonstrate:

- a local-first, provenance-preserving memory substrate;
- structured records for sources, artifacts, observations, claims, concepts, relations, contradiction cases, promotions, adjudications, and snapshots;
- confidence and temporal-validity metadata;
- first-class contradiction cases generated from explicit claim contradiction links;
- contradiction review batches and explicit contradiction-case adjudication;
- non-destructive memory lifecycle handling through expiry, supersession, retraction, applicability, and confidence review;
- release-level classification and no-access-broadening export controls;
- signed federation bundles;
- quarantine-before-promotion import;
- local policy-gated export/import/promotion;
- audit logs for federation decisions;
- HMAC and Ed25519 signature support;
- trust registries with expiry, revocation, and supersession metadata;
- signed Ed25519 public keysets;
- role directories, scoped grants, and policy compilation;
- signed role-directory publication/import with receiver-side caps.

### Out Of Scope

The paper should explicitly treat these as limitations or future work:

- network transport and polling;
- real-time synchronization;
- CRDT-based distributed editing;
- hosted review services;
- automatic semantic contradiction detection beyond explicit contradiction links;
- production IAM integration;
- public/internal release-pack publishing;
- production key recovery, HSM, or enterprise key-management workflows;
- empirical claims of improved safety, recall, or productivity beyond what the current tests and examples directly demonstrate.

## Core Paper Claim

GroundRecall demonstrates that long-lived AI memory can be structured as a review-gated, provenance-first control plane where current-context use is governed by evidence, confidence, temporal validity, release level, local authority, and auditability.

The central distinction should be:

- ordinary epistemic maintenance is usually non-destructive: expiry, supersession, retraction, temporal validity, confidence review, and retrieval-priority changes preserve evidence and decision history;
- exceptional erasure is a separately authorized privacy, legal, or security operation that removes protected content while preserving only minimal non-sensitive audit state.

This framing directly addresses the “forgetting” issue without weakening provenance.

## Candidate Title

GroundRecall: Review-Gated, Provenance-First Memory for Long-Lived AI Agents

## Proposed Abstract Claim Boundaries

The abstract should claim that GroundRecall:

- implements a local prototype for governed memory;
- preserves provenance across import, review, export, federation, and promotion;
- models confidence and temporal validity explicitly;
- surfaces contradiction cases as reviewable and adjudicable objects;
- enforces release-level controls during federation export;
- verifies signed exchanged knowledge artifacts before quarantine;
- requires local policy before promotion;
- supports signed public-key and role-directory distribution with receiver-side authority caps.

The abstract should not claim:

- production-grade distributed sync;
- autonomous safe memory writes;
- measured productivity improvement;
- complete regulatory compliance;
- complete deletion/erasure propagation.

## Paper Structure

### 1. Introduction

Purpose:

- explain why durable AI memory is useful and dangerous;
- motivate provenance-preserving memory instead of opaque summaries;
- introduce review-gated promotion and local authority as the control model.

Needed work:

- write a concise motivating example;
- define the target setting: long-lived agents, software/research workflows, multi-host collaboration.

### 2. Problem And Threat Model

Cover risks from:

- stale facts treated as current;
- ungrounded summaries replacing evidence;
- contradictions treated as invisible context noise rather than explicit review state;
- accidental private-to-public leakage;
- malicious or mistaken federation inputs;
- unauthorized promotion into durable memory;
- key compromise, stale trust, and policy drift;
- overbroad team roles.

Clarify non-goals:

- not a full IAM system;
- not a CRDT sync platform;
- not proof against host compromise.

Needed work:

- write the threat model as a table: threat, mitigation implemented, remaining limitation.

### 3. Data Model And Memory Lifecycle

Cover:

- source, artifact, observation, claim, concept, relation, contradiction case, promotion, adjudication, snapshot;
- provenance links;
- candidate/imported vs canonical memory;
- confidence and temporal metadata;
- expiry/supersession/retraction as ordinary lifecycle markers.
- contradiction cases as explicit, non-destructive review objects linking competing claims to adjudications.

Needed work:

- create one diagram: ingest → observation/claim/concept/relation → review/promotion → export/federation;
- add a compact schema table.

### 4. Confidence And Temporal Validity

Cover:

- confidence as structured assessment rather than a single scalar;
- applicability and basis visibility;
- current validity vs historical support;
- contradiction/adjudication as confidence-relevant review evidence rather than silent averaging;
- why non-destructive lifecycle markers are preferable to ordinary deletion.

Needed work:

- summarize implemented confidence fields and migration status;
- avoid implying full Bayesian updating unless implemented and tested.

### 5. Release-Level And Governance Controls

Cover:

- release lattice: public, internal, confidential, privileged, private;
- no-access-broadening export rule;
- redaction/declassification policy references;
- partial/hidden provenance visibility.

Needed work:

- provide a small example where public export excludes internal/private records;
- provide a small example where a redacted public derivative is allowed with policy metadata.

### 6. Federation Architecture

Cover:

- signed federation bundle;
- content hash and signature verification;
- quarantine import;
- dry-run promotion plan;
- apply promotion only after verification, release acceptance, policy, and conflict checks.

Needed work:

- create one diagram: producer → signed bundle → receiver verification → quarantine → local policy → promotion.
- include contradiction cases in the bundle contents and promotion discussion, noting that cases only promote when their referenced claims are also exportable.

### 7. Trust, Keys, And Role Distribution

Cover:

- HMAC local/shared-secret mode;
- Ed25519 public-key mode;
- trust registry lifecycle: created, expires, revoked, superseded;
- signed public keysets;
- role directories and scoped policy compilation;
- signed role-directory publications with receiver-side caps.

Needed work:

- create one table contrasting HMAC, Ed25519 bundle signatures, signed keysets, and signed role directories;
- include local-cap enforcement as a key design feature.

### 8. Implementation

Cover:

- Python package and CLI;
- file-backed deterministic JSON store;
- Pydantic models;
- `cryptography` Ed25519 support;
- CLI commands for export/import/promote/trust/roles;
- CLI commands for contradiction case sync/list/adjudication;
- test suite status.

Needed work:

- generate a current CLI command inventory;
- include current validation count from a fresh run before paper submission.

### 9. Demonstrations

Minimum demonstrations to prepare:

1. Release-lattice export:
   - seed public/internal/private records;
   - export public bundle;
   - show internal/private exclusion.
2. Signed bundle quarantine:
   - export signed internal bundle;
   - verify and import to quarantine;
   - show canonical store unchanged.
3. Policy-gated promotion:
   - compile role policy;
   - promote only with matching subject/scope.
4. Key lifecycle:
   - show expired or revoked key rejection.
5. Signed control-plane distribution:
   - publish/import public keyset;
   - publish/import role directory with local caps.
6. Contradiction adjudication:
   - create explicit contradiction links between claims;
   - sync them into contradiction cases;
   - list review batch with claim previews;
   - adjudicate a case while preserving both underlying claims.

Needed work:

- add reproducible scripts under `examples/preprint/` or `scripts/preprint/`;
- capture generated JSON snippets and expected outputs;
- decide which outputs become paper figures/tables.

### 10. Evaluation Plan

For the initial preprint, use engineering evidence rather than broad empirical claims.

Evidence already available:

- unit tests for release lattice, policy decisions, scoped grants, bundle verification, quarantine, promotion, trust registry lifecycle, Ed25519 signatures, signed keysets, signed role directories, contradiction case generation, contradiction diagnostics, federation of contradiction cases, and contradiction adjudication workflow;
- full test suite currently passing;
- deterministic JSON artifacts and content hashes.

Additional evidence to generate:

- reproducible demo outputs;
- small table mapping each claimed property to tests/examples;
- failure-mode table for tampering, unauthorized release level, missing scope, expired/revoked key, and unauthorized role publication.

Defer:

- large user studies;
- productivity metrics;
- broad benchmark comparisons;
- claims of superior safety without empirical data.

### 11. Limitations And Future Work

State plainly:

- no network transport yet;
- no real-time sync;
- no CRDT conflict-free editing;
- no hosted review service;
- no production IAM integration;
- no release-pack publishing yet;
- no automatic semantic contradiction detection yet;
- no complete exceptional-erasure propagation proof;
- current implementation is a prototype.

## Immediate Work Plan

### P0: Consolidate Paper Inputs

Deliverables:

- this preprint roadmap;
- implemented-features summary;
- one architecture note;
- one threat-model table at `docs/preprint/threat-model.md`;
- one claim-to-evidence matrix at `docs/preprint/claim-evidence-matrix.md`;
- one memory-layer seed bibliography at `docs/preprint/memory-layer-bibliography.md`;
- one CiteGeist-backed BibTeX seed/export pair under `docs/preprint/`.

Exit criteria:

- each paper claim has an implementation, test, demo, or is marked future work.

### P1: Architecture Note

Deliverable:

- `docs/preprint-architecture.md`

Contents:

- memory lifecycle;
- data model;
- confidence/temporal validity;
- federation workflow;
- trust/key/role control plane;
- limitations.

### P2: Threat Model And Governance Analysis

Deliverable:

- `docs/preprint/threat-model.md`

Contents:

- threat table;
- implemented mitigations;
- residual risks;
- deletion vs non-destructive forgetting distinction.

### P3: Reproducible Demonstrations

Deliverables:

- scripts or examples under `examples/preprint/`;
- generated example artifacts;
- README with exact commands.

Exit criteria:

- a clean checkout can reproduce the paper’s examples.

### P4: Claim-To-Evidence Matrix

Deliverable:

- `docs/preprint/claim-evidence-matrix.md`

Contents:

- claim;
- implementation artifact;
- test coverage;
- demonstration artifact;
- caveat/limitation.

### P4a: Memory-Layer Bibliography

Deliverables:

- `docs/preprint/memory-layer-bibliography.md`
- `docs/preprint/memory-layer-seed.bib`
- `docs/preprint/memory-layer-citegeist-export.bib`
- `docs/preprint/citegeist-memory-layer.sqlite3`

Contents:

- seeded bibliography for agent memory and memory-layer technology;
- annotation of how each source positions GroundRecall;
- source URLs used for verification;
- expansion targets for benchmarks, privacy/security, provenance, and governance literature.

### P5: Manuscript Draft

Deliverable:

- `docs/preprint-draft.md` or a paper source directory.

Exit criteria:

- all figures/tables referenced;
- limitations explicit;
- implementation claims align with committed code.

## Stop Rule For Feature Expansion

Further feature work should be deferred unless it blocks a specific paper claim. Network transport and release-pack publishing are useful next roadmap items, but they should not block the initial preprint. They belong in limitations/future work unless the paper’s scope changes.
