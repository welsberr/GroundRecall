# GroundRecall Preprint Architecture Note

Date: 2026-07-26

This note describes the architecture that should anchor the GroundRecall preprint. It is intentionally paper-facing: it explains the design model and implemented prototype boundaries rather than documenting every API.

## Architectural Position

GroundRecall is a local-first, provenance-aware memory substrate for long-lived AI-assisted work. It is designed for settings where assistants need durable context, but where durable memory also creates governance risks: stale facts, ungrounded summaries, accidental disclosure, poisoned writes, and unauthorized sharing.

GroundRecall treats memory as a governed knowledge control plane rather than a passive transcript store or vector cache. The core architectural commitments are:

- memory records remain grounded in sources and observations;
- durable memory changes are review-gated;
- current-context use is distinct from historical preservation;
- confidence and applicability are explicit metadata;
- cross-host sharing is signed, release-level constrained, locally authorized, and quarantine-first;
- local policy remains authoritative even when keys or roles are imported from another host.

## System Boundary

GroundRecall currently implements a local Python package and CLI. The canonical store is file-backed and deterministic JSON-oriented.

Implemented:

- local store;
- import/promotion/query/export workflows;
- confidence and temporal-validity metadata handling;
- first-class contradiction cases generated from explicit claim contradiction links;
- contradiction case listing and adjudication workflow;
- federation bundle export/import/promote;
- release-level filtering;
- local policy and audit;
- HMAC and Ed25519 signatures;
- trust registry lifecycle management;
- signed public-key publication;
- role-directory compilation;
- signed role-directory publication/import.

Not implemented:

- network transport;
- real-time sync;
- CRDT distributed editing;
- hosted review service;
- automatic semantic contradiction detection beyond explicit contradiction links;
- production IAM integration;
- public/internal release-pack publication.

For the preprint, GroundRecall should be described as an inspectable prototype and architecture, not as a finished distributed memory platform.

## Data Model

GroundRecall stores durable knowledge as typed records rather than raw chat history.

| Record type | Architectural role |
| --- | --- |
| Source | Originating source material or source identity. |
| Artifact | Imported artifact, document, note, or extracted object. |
| Observation | Grounded extracted observation from an artifact/source. |
| Claim | Durable propositional memory linked to observations, concepts, and other claims. |
| Concept | Stable topic/entity/category node. |
| Relation | Typed relationship between concepts or knowledge objects. |
| Contradiction case | Reviewable conflict object linking contradictory claims to status, severity, rationale, and adjudication. |
| Promotion | Review decision moving candidate/imported material toward canonical memory. |
| Adjudication | Review/adjudication state for claims, observations, relations, and contradiction cases. |
| Snapshot | Deterministic export view of a store at a point in time. |

The model preserves record identity and linkage. This is important for both provenance and governance: a claim can remain historically present while its current applicability, confidence, or release status changes.

## Memory Lifecycle

GroundRecall separates memory lifecycle stages:

```text
source/artifact
    ↓
observation extraction
    ↓
claim/concept/relation candidates
    ↓
review and promotion
    ↓
canonical store
    ↓
query/export/federation
    ↓
contradiction case review/adjudication when explicit conflicts are present
```

The core lifecycle principle is that ordinary epistemic maintenance is non-destructive. When facts age, conflict, expire, or are superseded, GroundRecall should preserve history and lower current applicability or confidence rather than deleting evidence. Deletion is reserved for exceptional privacy, legal, or security erasure workflows.

## Provenance Model

GroundRecall keeps provenance close to the claims it supports.

Implemented behavior includes:

- observations carry support/grounding metadata;
- claims reference source observations and supporting fragments;
- claims can record contradictions and supersession relationships;
- explicit contradiction links can be materialized as first-class contradiction cases;
- contradiction cases preserve review status, severity, rationale, and adjudication linkage;
- export and federation preserve record IDs and content hashes;
- hidden or redacted basis can be represented explicitly through basis-visibility metadata.

This supports a paper claim that GroundRecall avoids replacing evidence with ungrounded summaries. It does not prove that all upstream extraction is correct; it preserves enough structure for later review and correction.

## Contradiction And Adjudication Workflow

GroundRecall now treats explicit contradictions as reviewable objects rather than only claim-level links.

Implemented behavior:

- `contradicts_claim_ids` links between claims can be synchronized into deterministic contradiction case records;
- case records store participating claim IDs, case kind, status, severity, open/resolved timestamps, rationale, metadata, and optional adjudication ID;
- query bundles surface contradiction cases alongside the older link-level contradiction view;
- graph diagnostics distinguish raw contradiction links from first-class cases;
- diagnostics flag contradiction links without cases, cases referencing missing claims, and open cases involving promoted claims;
- adjudications can target `contradiction_case` subjects;
- `groundrecall contradictions sync STORE` creates missing cases from explicit links;
- `groundrecall contradictions list STORE --sync` returns review batches with claim previews;
- `groundrecall contradictions candidates STORE` returns graph-inferred contradiction cues as a separate review batch before they are treated as explicit conflicts;
- `groundrecall contradictions accept-candidate STORE RELATION_ID ...` promotes an accepted `claim_may_contradict_claim` cue into explicit bidirectional contradiction links and synchronizes a first-class case;
- contradiction-candidate acceptance is policy-gated when a policy-plugin config is supplied, and hard-gate or deny decisions block before durable claim, relation, or case writes;
- concept query bundles expose candidate contradiction cues, adjudicated contradiction cases, and a compact conflict summary alongside explicit contradiction cases, supersessions, and temporal stale-claim signals;
- public query export guardrails prune contradiction cases and candidate cues whose claim endpoints are not exportable, then recalculate conflict counts;
- `groundrecall contradictions adjudicate STORE CASE_ID ...` records the decision and updates case status without rewriting the underlying claims.

This gives the paper a concrete mechanism for robust contradiction tracking: disagreement remains historically visible, and resolution is represented as additional review state rather than silent deletion or averaging. The current implementation can surface heuristic contradiction cues generated by graph maintenance, but those cues remain review-gated candidates. It does not claim robust automatic semantic contradiction detection or resolution.

## Confidence And Temporal Validity

GroundRecall treats confidence as structured metadata, not merely a single scalar.

Relevant architectural dimensions:

- evidential support;
- grounding status;
- basis visibility;
- ambiguity;
- temporal validity;
- expiry;
- supersession;
- retraction;
- current applicability.

The paper should emphasize that confidence in historical support and confidence in current applicability are different. A record may remain well-supported as a historical fact while being inapplicable to current planning because it expired, was superseded, or became contextually stale.

This is the basis for the paper’s treatment of “forgetting”: ordinary forgetting should usually mean controlled exclusion from current context, not destruction of provenance.

## Release-Level Lattice

Federation/export uses a release-level lattice:

```text
public < internal < confidential < privileged < private
```

Implemented rules:

- `private` is local-only and not federated;
- records cannot be exported to a less restrictive target without appropriate redaction/declassification metadata;
- public exports block internal, confidential, privileged, private, and unclassified records unless policy allows;
- hidden support can be represented as partial basis visibility;
- privileged federation requires explicit privileged allowance.

This provides a mechanical basis for the governance claim that GroundRecall can reduce accidental disclosure during memory sharing.

## Federation Bundle Architecture

A federation bundle is a signed, content-hashed snapshot for controlled exchange.

Producer side:

```text
canonical store
    ↓
snapshot
    ↓
release-level filter
    ↓
manifest + content hash
    ↓
signature
    ↓
federation bundle
```

Receiver side:

```text
bundle
    ↓
signature and hash verification
    ↓
release-level acceptance
    ↓
local policy check
    ↓
quarantine
    ↓
promotion plan
    ↓
review-gated promotion
```

Implemented verification checks include:

- signature;
- expected key ID;
- content hash;
- accepted release level;
- bundle policy violations.

Promotion is explicitly separate from import. This is important: receiving a valid signed bundle does not automatically make it canonical local memory.

## Quarantine And Promotion

Quarantine is the boundary between received knowledge and local durable memory.

Implemented properties:

- imports write to quarantine first;
- canonical store is not overwritten by import;
- quarantine bundles can be listed;
- promotion can be dry-run planned;
- promotion detects conflicts;
- promotion applies only non-conflicting records;
- policy failures produce rejected/planned outcomes rather than silent writes.
- contradiction cases are promoted only when the case itself and all referenced claims are exportable at the target release level.

This supports the paper’s review-gated memory claim.

## Local Policy And Audit

Federation actions are governed by local policy.

Policy grants can constrain:

- subject ID;
- action;
- release level;
- instance ID;
- scope ID;
- privileged access.

Supported federation actions are:

- export;
- import;
- promote.

Audit events capture:

- action;
- decision;
- subject;
- release level;
- bundle ID;
- instance ID;
- scope ID;
- policy ID;
- reasons;
- metadata.

The paper should emphasize that imported keys or role directories do not override local policy. Local authorization remains the final authority for federation actions.

## Trust Registry And Key Lifecycle

The trust registry is the local trust root for federation signing/verification workflows.

Supported algorithms:

- `hmac-sha256`;
- `ed25519`.

Trust entries record:

- instance ID;
- key ID;
- key material;
- algorithm;
- active status;
- creation time;
- expiry time;
- revocation time;
- revocation reason;
- superseding key ID;
- allowed release levels;
- trusted actions.

Expired, inactive, and revoked keys are retained but blocked from use. This follows the same non-destructive governance pattern: history remains inspectable, but current authority changes.

## Signed Public Keysets

Signed public keysets distribute Ed25519 public verification keys.

Producer:

- selects Ed25519 public keys from a local trust registry;
- creates a keyset with lifecycle metadata;
- signs the keyset with an Ed25519 signer key.

Receiver:

- verifies the keyset signature with a pinned signer public key;
- checks signer key ID;
- checks content hash and key count;
- imports keys only after applying local caps.

Receiver caps include:

- instance IDs;
- release levels;
- trusted actions.

By default, import accepts only keys for the keyset producer instance.

## Role Directory And Policy Compilation

Role directories provide reusable team/entity policy inputs.

Role definitions include:

- role ID;
- allowed actions;
- release levels;
- instance IDs;
- scopes;
- privileged allowance.

Memberships map subjects to roles. Role directories compile into ordinary `FederationLocalPolicy` grants. Compilation fails closed if a membership references an unknown role.

Scoped grants require a matching scope ID during policy evaluation. This makes scope an enforced authorization dimension rather than a descriptive tag.

## Signed Role-Directory Publication

Signed role-directory publication mirrors signed public-key distribution.

Producer:

- publishes a role directory;
- signs it with an Ed25519 signer key.

Receiver:

- verifies signature, signer key ID, role count, membership count, and content hash;
- applies local caps;
- compiles the capped directory into a local policy.

Receiver caps include:

- subjects;
- roles;
- instances;
- release levels;
- actions;
- scopes.

Wildcard instance grants are narrowed to receiver-approved instances during import.

This is the key governance pattern: a hub can publish proposed authority structure, but the receiver decides the maximum authority it will accept.

## Security And Governance Properties Demonstrated

The implementation demonstrates these properties:

- signed bundles detect tampering;
- content hashes detect snapshot mutation;
- private records are blocked from federation;
- release-level broadening is blocked unless redaction/declassification metadata is present;
- imports do not overwrite canonical memory;
- promotion is policy-gated and conflict-aware;
- contradiction cases preserve conflict/adjudication history as first-class review state;
- expired/revoked keys are blocked without deleting history;
- Ed25519 public-key verification avoids shared federation secrets for asymmetric workflows;
- signed keysets and role directories require pinned signer keys;
- imported keysets and role directories are locally capped.

These are architectural and engineering properties. They should not be overstated as empirical proof of improved safety or productivity.

## Evidence Currently Available

Current evidence comes from the implementation and test suite.

- Federation-focused tests cover release lattice, policy, scoped grants, signed bundles, quarantine, promotion, trust registry lifecycle, Ed25519 signatures, signed keysets, and signed role directories.
- Contradiction tests cover explicit-link case generation, case persistence in snapshots, graph diagnostic flags, query surfacing, federation inclusion/promotion, and CLI adjudication workflow.
- The full test suite passes.
- JSON artifacts are deterministic and content-hashed.
- CLI workflows are implemented for the major federation and role/trust operations.

For the preprint, these tests should be summarized in a claim-to-evidence matrix and supplemented with small reproducible demonstrations.

## Diagrams Needed For Manuscript

Recommended figures:

1. Memory lifecycle:
   - source/artifact → observation → claim/concept/relation → review/promotion → canonical store → query/export/federation.
2. Federation flow:
   - producer export/sign → receiver verify → quarantine → policy → promotion.
3. Control-plane flow:
   - signed keyset and signed role directory → receiver verification → local caps → trust registry/policy.
4. Contradiction/adjudication flow:
   - explicit contradiction links → contradiction case → review batch → adjudication → updated case status.
5. Forgetting/lifecycle distinction:
   - expiry/supersession/retraction/confidence review vs exceptional erasure.

## Limitations To State

Current limitations:

- no network transport or polling;
- no real-time distributed sync;
- no CRDT merge layer;
- no hosted review service;
- no automatic semantic contradiction detection;
- no production identity/IAM integration;
- no public/internal release-pack publishing;
- no complete exceptional-erasure propagation mechanism;
- no broad empirical evaluation yet.

## Preprint Use

This architecture note should be used to draft:

- the system overview section;
- the data model section;
- the governance model section;
- the federation/control-plane section;
- the limitations section.

It should be paired with:

- `docs/implemented-features-summary.md`;
- `docs/preprint-roadmap.md`;
- a forthcoming threat model;
- a forthcoming claim-to-evidence matrix;
- forthcoming reproducible demonstration scripts.
