# Sync Roadmap

The current standalone alpha is local-first. Stable re-import and append-only
version events are now foundational memory-lifecycle work; distributed merge
remains a later-stage feature.

See [memory-lifecycle-roadmap.md](memory-lifecycle-roadmap.md) for the governing
priority order. Its R1 phase incorporates Phases 1 and 2 below, while its R5
phase incorporates the distributed and team portions of Phases 3 through 5.

## Goal

Support these use cases cleanly:

- one user across multiple machines
- teams with shared and individual knowledge
- parallel corpus transformation and consolidation
- federated project or entity knowledge across multiple GroundRecall instances
- public, internal, confidential, and privileged release boundaries

## Group-Valued Federation Goals

Federation is not only a way to move records between GroundRecall instances.
Its larger purpose is to turn appropriately released member knowledge into a
durable group capability without treating every member's local memory as
automatically authoritative or shareable.

The group-valued goods are:

1. **Member-to-group knowledge propagation.** Useful individual observations,
   sources, techniques, and decisions can become reviewed group knowledge.
2. **Silo reduction.** Teams, departments, projects, and geographically
   separated hosts can discover relevant work outside their immediate local
   context.
3. **Avoidance of duplicate exploration.** Members can find techniques,
   prototypes, searches, experiments, and projects that were already attempted,
   including negative or inconclusive results.
4. **Institutional continuity.** Knowledge can survive an individual's
   departure from a project, group, host, or entity while respecting provenance,
   release, retention, and revocation rules.
5. **Faster onboarding and succession.** New members can recover the current
   state, vocabulary, evidence, decision history, unresolved questions, and
   responsible stewards without reconstructing them from chat archives.
6. **Preservation of decision rationale.** The group retains why an approach
   was chosen, rejected, superseded, or deferred—not merely the latest
   conclusion.
7. **Shared situational awareness.** Relevant changes, contradictions,
   dependencies, risks, expiries, and supersessions can reach affected members
   and projects.
8. **Expertise and stewardship discovery.** Provenance and contribution
   history can help members find knowledgeable people or responsible roles
   without turning contribution metrics into simplistic performance scores.
9. **Cross-project dependency and impact discovery.** A change in one body of
   knowledge can identify claims, procedures, artifacts, and projects elsewhere
   that may need review.
10. **Collective quality improvement.** Independent evidence, review,
    contradiction detection, and adjudication can improve group knowledge while
    preserving minority positions and unresolved disagreement.
11. **Operational consistency with local discretion.** Shared reviewed
    procedures and policies can reduce accidental divergence, while local
    authority can reject or qualify knowledge that does not fit local conditions.
12. **Incident and failure learning.** Lessons, mitigations, and contributing
    conditions can be retained and reused without requiring unrestricted
    circulation of sensitive incident material.
13. **Accountability and defensible governance.** The entity can show the
    provenance, authority, review state, release decision, and change history
    behind consequential shared knowledge.
14. **Controlled reuse and publication.** Reviewed knowledge can be repackaged
    for other projects, partners, or the public with license, attribution,
    redaction, and provenance-visibility controls.
15. **Resilience against host, account, and organizational change.** Important
    knowledge need not disappear with one device, service tenancy, or team
    reorganization; custody and stewardship can be transferred explicitly.
16. **Recombination and innovation.** Discoverable knowledge from different
    specialties can reveal useful connections that are unlikely to appear
    within a single member's or project's memory.

These benefits are conditional. Federation can otherwise amplify stale,
incorrect, duplicated, confidential, or malicious material. The design must
therefore preserve the difference between contribution, receipt, local
acceptance, current applicability, and authority.

## Current GroundRecall Contribution And Gaps

GroundRecall already supplies a substantial exchange-control foundation, but it
does not yet supply the discovery, dissemination, stewardship, or continuity
services needed to realize all of the group benefits above.

| Group need | What GroundRecall provides now | Modification still needed |
| --- | --- | --- |
| Safe member-to-group propagation | Signed, content-hashed bundles; release filtering; quarantine-before-promotion; local policy gates | A contribution workflow with group destination, contribution intent, steward/reviewer assignment, and explicit accepted/rejected/deferred outcomes |
| Silo reduction and discovery | Typed claims, concepts, relations, provenance, snapshots, and portable bundles | A federated catalog of available scopes, topics, time coverage, record kinds, and release levels; authorized cross-instance query or catalog subscription; relevance routing |
| Duplicate-work avoidance | Search, source identity, stable record IDs, hashes, provenance, supersession, and graph relations | First-class project, technique, experiment, decision, and negative-result records; semantic/identity duplicate detection; a policy-checkable prior-work query at project or task initiation |
| Continuity past member tenancy | Origin identity, immutable bundle manifests, canonical promotion, audit history, and non-destructive lifecycle state | Group ownership/custody distinct from origin; steward roles; custody-transfer events; retention and legal-hold policy; orphan detection; tested restore and rehydration procedures |
| Onboarding and succession | Reviewed canonical snapshots and query bundles | Scope-specific orientation packs, vocabulary maps, decision timelines, unresolved-conflict lists, freshness indicators, and named role/steward handoffs |
| Decision-rationale preservation | Claims, observations, promotions, adjudications, contradiction cases, supersession, and provenance | First-class decision records with alternatives, constraints, evidence, outcome, review date, and links to projects and affected knowledge |
| Shared situational awareness | Temporal validity, contradiction cases, graph links, query conflict summaries, and audit events | Subscriptions/watch rules, incremental change feeds, affected-scope routing, acknowledgements, and escalation for high-impact changes |
| Expertise and stewardship discovery | Source/contribution provenance and role-directory primitives | Privacy-aware contributor/steward indexes, topic responsibility records, opt-out/redaction policy, and safeguards against using raw activity as personnel evaluation |
| Cross-project impact discovery | Concepts, relations, contradiction cues, graph expansion, and provenance links | Stable project/scope entities, dependency relation types, reverse-impact queries, change-impact events, and review queues for affected scopes |
| Collective quality improvement | Review-gated promotion, confidence metadata, contradiction cases, candidate review, and adjudication | Multi-reviewer decisions, review quorum/separation-of-duty policy, origin diversity indicators, calibrated trust transfer, and receiver feedback to the producer |
| Consistent operations with local discretion | Signed role directories with receiver-side caps; local policy remains authoritative | Versioned policy/procedure distribution, applicability conditions, local exception records, drift detection, and explicit reconciliation rather than silent convergence |
| Incident and failure learning | Release lattice, provenance visibility, redaction metadata, privileged policy paths, and audit logs | Incident/lesson record types, compartmented scopes, sanitized derivatives, need-to-know routing, retention controls, and post-incident review lifecycle |
| Accountability and governance | Signatures, trust registries, policy decisions, audit events, release levels, and content hashes | Append-only event-chain verification, durable review receipts, access-decision reporting, retention/erasure linkage, and governance health reports |
| Controlled reuse/publication | Public-release filtering, redaction/declassification metadata model, deterministic snapshots | License and attribution fields, release-pack generation, derivative lineage validation, reproducible builds, and publication withdrawal/revocation notices |
| Host/account/reorganization resilience | Portable file-backed store, deterministic JSON, signed bundles, key lifecycle, and trust metadata | Replication policy, custody quorum, encrypted backup/restore, key recovery and rotation drills, instance retirement, namespace transfer, and stale-replica reconciliation |
| Recombination and innovation | Cross-linked concepts, claims, relations, graph search, and federated snapshots | Authorized cross-scope graph discovery, provenance-preserving recommendation, novelty/related-work views, and review gates before inferred connections become durable group knowledge |

The central implementation gap is therefore not cryptographic exchange. It is
the governed social lifecycle around exchange:

```text
member knowledge
    ↓ contribution proposal
group review and release check
    ↓ accepted shared knowledge
catalog, subscriptions, and impact routing
    ↓ use, challenge, correction, or supersession
durable stewardship, retention, and custody transfer
```

## Planned Model

The intended model is:

- append-only event capture at the edge
- canonical promoted store as the durable reviewed state
- generated exports and assistant bundles as derived artifacts
- signed, policy-checked exchange bundles rather than direct database
  replication
- explicit release classification and access policy on every shareable object

Assistant-facing remote access is a separate adapter lane. The current
`groundrecall-mcp` process is a local stdio server. ChatGPT web requires a
remote MCP endpoint; private-LAN use therefore needs an authenticated HTTP
adapter and an approved private-network path such as Secure MCP Tunnel. The
implementation plan is maintained in
[chatgpt-mcp-integration-roadmap.md](chatgpt-mcp-integration-roadmap.md).

Cross-assistant interoperability follows the same boundary: GroundRecall is
the shared state substrate, while ChatGPT and Codex remain separate clients.
The handoff lane uses compact, proposal-only task/plan/progress/result records
with stable IDs and context references. Local MCP now supports constrained
status transitions and append-only progress/result events, while the bounded
HTTP adapter keeps lifecycle writes opt-in. It does not synchronize chat
transcripts or grant a reasoning client arbitrary host execution authority.

This avoids treating compiled wiki pages or generated bundles as merge primitives.
Federation is controlled publication of provenance-bearing knowledge objects,
not blind memory copying between hosts.

## Federation And Release-Level Policy

Multiple GroundRecall instances may exist across laptops, servers, lab
machines, project hosts, and organizational infrastructure. Federation must
support collaboration while preventing content from crossing trust boundaries
without explicit policy.

### Release Levels

Every shareable record, bundle, assessment, and provenance reference should
carry an explicit release classification:

| Level | Meaning | Default handling |
| --- | --- | --- |
| `private` | Local-only personal or host-local material | Never federated by default |
| `public` | Safe for unrestricted release | Exportable and publishable |
| `internal` | Shared within an entity, team, or project boundary | Federated only to authorized internal peers |
| `confidential` | Limited to named projects, groups, or principals | Requires explicit policy grant and audit trail |
| `privileged` | Legal, medical, security, HR, source-protected, or similarly restricted material | Never federated by default; requires a privileged policy path |

Records may also include `embargoed_until`, `redacted_public`, and
`redacted_internal` states for derived artifacts.

### Access And Derivation Rule

A derived artifact's release level must be at least as restrictive as its most
restrictive source unless a documented redaction or declassification policy
created the derivative.

Examples:

- a public summary derived from confidential notes remains confidential unless
  an explicit redaction policy emits a separate public artifact;
- a public claim may reference hidden confidential provenance, but the exposed
  provenance view must disclose that the basis is partial;
- a privileged record must not be summarized into a lower release level without
  a policy-approved privileged workflow.

### Metadata Required For Federated Objects

Federated records should carry:

- `owner_instance_id`;
- `origin_instance_id`;
- stable `record_id` and immutable version/content hash;
- `release_level`;
- `access_policy_id`;
- authorized principals, groups, projects, or entity scopes;
- `provenance_visibility`;
- `redaction_policy_id`, when a lower-release derivative exists;
- `supersedes_record_ids`;
- `revocation_status`;
- export manifest hash and signature.

Confidence assessments and provenance records inherit the parent object's
release level unless they are explicitly more restrictive. They must never
silently broaden access.

### Provenance Visibility

Provenance itself can leak sensitive source names, relationships, projects,
and privileged work product. Federation therefore needs independent provenance
visibility controls:

- full provenance visible to authorized peers;
- redacted provenance visible to lower release levels;
- opaque provenance counts or families where detailed source identity is
  restricted;
- explicit `assessment_basis_visibility` values such as `full`, `partial`,
  `redacted`, or `hidden`.

If evidence is hidden by access policy, downstream confidence should expose the
limitation rather than pretending the evidence is fully inspectable. A public
consumer might receive `hidden_basis_count`, hidden release-level summaries,
and a warning that the assessment rests on partially visible evidence.

### Federation Modes

GroundRecall should distinguish four federation modes:

1. **Personal device sync:** same user across hosts, strong instance identity,
   low collaboration complexity.
2. **Project federation:** project-scoped sharing with internal/confidential
   boundaries and review workflows.
3. **Entity federation:** organization-wide sharing with formal roles, policy
   distribution, audit logs, retention classes, and privileged-data handling.
4. **Public release federation:** redacted, signed, license-aware knowledge
   packs with reproducible checksums and immutable release manifests.

ChatGPT integration is a consumer/access surface across these modes, not a
fifth authority realm. Identity mapping and server-side policy must select the
underlying principal, project, or team realm before any remote result is
returned.

### Exchange Format

Start with signed append-only federation bundles, not distributed consensus or
direct store replication. A bundle should include:

- manifest and schema version;
- producing instance and signing key identity;
- record versions and content hashes;
- confidence assessments;
- provenance references or redacted provenance summaries;
- release/access metadata;
- redaction and declassification decisions;
- supersession, expiry, retraction, and revocation events;
- import-policy result and quarantine status.

Receivers import into quarantine first. Promotion into active memory requires
local policy acceptance and, for shared scopes, review authority.

## Likely Local Layout

```text
.groundrecall/
  events/
  imports/
  store/
  exports/
```

## Planned Phases

### Phase 1: Re-import And Update Semantics

- import the same source tree repeatedly without duplicating everything
- support import lineage and supersession
- track object continuity across imports

### Phase 2: Event Log Capture

- record machine-local observations and import events
- distinguish machine-local state from promoted shared state
- preserve provenance and timestamps explicitly
- preserve immutable object versions, content hashes, and derivation events
- support rollback and deterministic derived-index invalidation

### Phase 3: Merge And Consolidation

- merge append-only events from multiple machines
- consolidate draft claims and review candidates
- preserve contradiction and supersession history

### Phase 4: Shared And Private Scopes

- private notes and private candidate knowledge
- shared promoted knowledge
- controlled promotion from private to shared
- mechanically enforce principals, scope, sensitivity, and review authority
- keep per-agent draft memory separate from reviewed shared memory
- add release-level classification: `private`, `public`, `internal`,
  `confidential`, and `privileged`
- enforce the no-access-broadening derivation rule
- add provenance visibility controls and redacted derivative artifacts
- quarantine imported federated bundles until local policy review completes

### Phase 5: Team And Corpus Workflows

- parallel ingestion over large corpora
- coordinated claim review and adjudication
- export of consolidated assistant-neutral snapshots
- project and entity federation using signed exchange bundles
- team role and group-policy mapping for read, propose, review, promote,
  publish, redact, and revoke authorities
- release-pack generation for public and internal knowledge bundles
- audit logs for federation import, export, redaction, and revocation decisions
- contribution proposals with destination scope, intent, and assigned steward
- first-class project, technique, experiment, negative-result, and decision
  records for prior-work discovery
- multi-reviewer or quorum policy for high-impact promotion and adjudication
- scope catalogs, subscriptions, change feeds, and impact-review queues
- custody transfer, orphan detection, retention, and instance-retirement
  workflows

### Phase 6: Institutional Discovery And Continuity

- publish a signed, release-filtered catalog describing which scopes, topics,
  record kinds, and time ranges an instance can offer without leaking protected
  record contents
- support authorized catalog subscription and incremental bundle exchange
- route relevant changes, contradictions, expiries, and supersessions to
  affected scopes
- add prior-work queries over projects, techniques, experiments, decisions, and
  negative results
- add group custody, stewardship, succession, and orphaned-knowledge review
- add tested backup, restore, rehydration, instance retirement, and namespace
  transfer procedures
- add feedback records so receivers can report local acceptance, rejection,
  contradiction, or supersession without granting producers authority over the
  receiver's canonical store
- add governance health reports for stale knowledge, unowned scopes, unresolved
  conflicts, policy drift, incomplete provenance, and unacknowledged high-impact
  changes

Acceptance criteria:

- an authorized member can discover relevant work without first knowing which
  host or team holds it;
- a project-start query can surface materially similar prior work and negative
  results with provenance and review state;
- departure of a member or retirement of an instance produces an explicit
  custody/orphan review rather than silent knowledge loss;
- consumers can subscribe to bounded changes and see why a change was routed
  to them;
- producer and receiver decisions remain separate, attributable, and locally
  governed;
- catalog metadata, expertise discovery, and operational reports do not expose
  protected content or become unreviewed personnel-surveillance mechanisms.

## Priority Order For Group-Value Federation

The following sequence builds on the implemented signed-bundle foundation and
prioritizes benefits that do not require real-time distributed consensus:

1. **Define group objects and stewardship.** Add stable entity, group, project,
   technique, experiment, decision, and contribution-proposal records, plus
   owner, steward, retention, and custody-transfer fields.
2. **Make prior work findable.** Add a local prior-work query and duplicate/
   related-work candidate generation before attempting cross-host discovery.
3. **Add signed federation catalogs.** Exchange release-filtered descriptions of
   available knowledge scopes, not raw contents, and apply receiver-side policy
   caps.
4. **Add subscriptions and incremental change bundles.** Let authorized
   consumers request bounded updates and route supersession, contradiction,
   expiry, and revocation events.
5. **Expose governed assistant access.** Add the remote MCP adapter, mandatory
   server-side policy, identity-to-realm mapping, private-network tunnel,
   read-only ChatGPT pilot, and audit/freshness/error contracts. Keep ChatGPT
   access separate from canonical promotion.
6. **Deepen group review.** Support multi-reviewer/quorum rules, separation of
   contribution from approval, receiver feedback, and cross-instance
   adjudication records.
7. **Implement continuity operations.** Add orphan detection, custody transfer,
   instance retirement, restore/rehydration tests, and stale-replica
   reconciliation.
8. **Add institutional views.** Generate onboarding packs, decision timelines,
   unresolved-question lists, expertise/steward directories, dependency impact
   reports, and governance health reports with privacy guardrails.
9. **Complete controlled release.** Add license-aware public/internal packs,
   reproducible build manifests, and withdrawal/revocation notices.

This sequence deliberately treats network transport as replaceable
infrastructure. The durable protocol should first define identities, objects,
events, authority, review, and lifecycle semantics so it can operate over files,
MCP adapters, repositories, polling, or later network services.

The coding-model-ready cross-repository work packages, schemas, policy action
mapping, test requirements, and acceptance criteria are maintained in
[institutional-federation-implementation-roadmap.md](institutional-federation-implementation-roadmap.md).

## Federation Implementation Milestones

Initial implementation status, 2026-07-26: GroundRecall now has federation
policy primitives, signed bundle export, signature/content-hash verification,
and quarantine import helpers in `groundrecall.federation`, exposed through
`groundrecall federation export` and `groundrecall federation import`. This is
the F0-F3 foundation. The CLI also accepts an optional local policy file and
JSONL audit log so hosts can require explicit requester grants before export,
quarantine import, or promotion. Quarantined bundles can be listed, dry-run
planned, and promoted into a canonical store only when signature verification,
release-level acceptance, local policy, and conflict checks pass. Local trust
registries retain created/revoked/supersession metadata and can revoke keys so
old signatures are blocked without erasing audit history. Ed25519 signatures,
signed public keysets, local role-directory-to-policy compilation, and signed
role-directory publication/import are now available. It does not yet provide
network transport or public release-pack publishing.

Local policy files use the `groundrecall.local_federation_policy.v1` shape:

```json
{
  "policy_id": "example-project-federation-policy",
  "grants": [
    {
      "subject_id": "alice",
      "actions": ["export", "import", "promote"],
      "release_levels": ["public", "internal"],
      "instance_ids": ["host-a", "host-b"],
      "scopes": ["project-alpha"],
      "allow_privileged": false
    }
  ]
}
```

Role directory files use the `groundrecall.federation_role_directory.v1` shape
and compile into local policy files. This keeps runtime enforcement on the same
audited grant model while letting teams maintain reusable role definitions:

```json
{
  "directory_id": "project-alpha-roles",
  "roles": [
    {
      "role_id": "reviewer",
      "actions": ["import", "promote"],
      "release_levels": ["public", "internal"],
      "instance_ids": ["host-a"],
      "scopes": ["project-alpha"],
      "allow_privileged": false
    }
  ],
  "memberships": [
    {
      "subject_id": "alice",
      "role_ids": ["reviewer"]
    }
  ]
}
```

Compile the directory before using it as `--policy-file`:

```bash
groundrecall federation policy-from-roles ./roles.json ./policy.json \
  --policy-id project-alpha-compiled-policy

groundrecall federation import ./bundle.json ./quarantine \
  --trust-registry ./trust.json \
  --policy-file ./policy.json \
  --requester-id alice \
  --scope-id project-alpha \
  --accept-release-level internal
```

Compilation fails closed if a membership references an unknown role. At policy
evaluation time, grants with `scopes` require a matching `--scope-id`; unscoped
grants remain global for the permitted action, release level, and instance.

Reviewed role-directory distribution can be automated through signed
role-directory publications. A project or entity hub signs the directory with an
already pinned Ed25519 signing key:

```bash
groundrecall federation role-publish-directory ./roles.json ./roles-publication.json \
  --producer-instance-id host-a \
  --signing-key-file ./host-a-role-root-private.pem \
  --signer-key-id host-a-role-root
```

Receivers verify the signed publication and write a locally capped policy. Caps
are intersected with the published directory before compilation, so imported
policies cannot exceed the receiver's allowed subjects, roles, instances,
release levels, actions, or scopes:

```bash
groundrecall federation policy-import-roles ./roles-publication.json ./policy.json \
  --signer-key-file ./host-a-role-root-public.pem \
  --signer-key-id host-a-role-root \
  --policy-id receiver-role-policy \
  --allow-subject-id alice \
  --allow-instance-id host-a \
  --allow-release-level internal \
  --allow-action import \
  --allow-action promote \
  --allow-scope project-alpha
```

Audit events use `groundrecall.federation_audit.v1` JSONL records and capture
the requester, action, decision, release level, bundle ID, instance ID, policy
ID, reasons, and decision metadata.

Local trust registries use the
`groundrecall.local_federation_trust_registry.v1` shape. They map producer
instances and key IDs to locally trusted key material, allowed release levels,
and trusted actions. `hmac-sha256` entries contain local shared secrets;
`ed25519` entries contain public verification keys:

```json
{
  "registry_id": "example-project-trust-registry",
  "keys": [
    {
      "instance_id": "host-a",
      "key_id": "host-a-2026-07",
      "key_material": "store this outside public exports for HMAC; Ed25519 entries store public PEM keys",
      "algorithm": "hmac-sha256",
      "active": true,
      "created_at": "2026-07-26T00:00:00Z",
      "expires_at": "2026-10-24T00:00:00Z",
      "revoked_at": "",
      "revocation_reason": "",
      "superseded_by_key_id": "",
      "release_levels": ["public", "internal"],
      "trusted_actions": ["export", "import", "promote"]
    }
  ]
}
```

The CLI can manage this local file:

```bash
groundrecall federation trust-add ./trust.json \
  --instance-id host-a \
  --key-id host-a-2026-07 \
  --key-file ./host-a-federation.key \
  --algorithm hmac-sha256 \
  --release-level internal \
  --trusted-action import \
  --trusted-action promote \
  --expires-at 2026-10-24T00:00:00Z

groundrecall federation trust-list ./trust.json

groundrecall federation trust-revoke ./trust.json \
  --instance-id host-a \
  --key-id host-a-2026-07 \
  --reason rotation \
  --superseded-by-key-id host-a-2026-08

groundrecall federation trust-export-metadata ./trust.json ./trust-metadata.json
```

`--trust-registry` can then replace `--key-file` for export, import, and
promotion for HMAC workflows. For Ed25519 workflows, export uses
`--key-file ./private-signing-key.pem --signature-algorithm ed25519`, while
import and promotion can use a trust registry entry created from the producer's
public key:

```bash
groundrecall federation trust-add ./trust.json \
  --instance-id host-a \
  --key-id host-a-2026-07 \
  --key-file ./host-a-ed25519-public.pem \
  --algorithm ed25519 \
  --release-level internal \
  --trusted-action import \
  --trusted-action promote
```

Reviewed Ed25519 public-key distribution can be automated through signed
keysets. The producer publishes Ed25519 public keys from a local registry and
signs the publication with an already pinned Ed25519 signing key:

```bash
groundrecall federation trust-publish-keyset ./producer-trust.json ./host-a-keyset.json \
  --producer-instance-id host-a \
  --signing-key-file ./host-a-root-private.pem \
  --signer-key-id host-a-root
```

The receiver verifies the keyset with the pinned signer public key before
merging it into a local trust registry. Receiver-side caps are mandatory in the
workflow: imported entries are intersected with the receiver's allowed release
instance IDs, release levels, and actions, so a producer cannot grant itself or
another host broader local authority by publishing a wider keyset. If
`--allow-instance-id` is omitted, import defaults to the keyset producer
instance.

```bash
groundrecall federation trust-import-keyset ./host-a-keyset.json ./receiver-trust.json \
  --signer-key-file ./host-a-root-public.pem \
  --signer-key-id host-a-root \
  --allow-instance-id host-a \
  --allow-release-level internal \
  --allow-trusted-action import \
  --allow-trusted-action promote
```

HMAC registry files contain shared secrets and must be treated as secrets; they
are local trust roots, not public federation artifacts. Ed25519 registry entries
contain public keys, but the registry still records local trust decisions and
should be reviewed before use. Expired, inactive, or revoked keys are retained
for audit/history but are blocked from export, import, and promotion. A later
milestone should add organization-managed role directories and transport for
publishing and polling signed keysets.

For coordination between hosts, `trust-export-metadata` writes
`groundrecall.federation_trust_metadata.v1`, which omits `key_material` and
retains only instance/key IDs, algorithm, lifecycle fields, release levels, and
trusted actions. `--include-key-fingerprint` can add a `sha256:` fingerprint
for operator comparison, but should only be used with high-entropy keys because
fingerprints of weak shared secrets can aid guessing. This metadata file is
safe for inventory/review workflows. For Ed25519, use signed public keysets
when receivers need to ingest full public verification keys.

### F0: Instance Identity And Trust Roots

- Define stable `instance_id`, local user/entity IDs, project IDs, and signing
  keys.
- Record origin and owner instance on imported records.
- Support explicit trust relationships between instances rather than implicit
  trust from network reachability.
- Support Ed25519 bundle signatures so receivers can verify with producer
  public keys instead of shared HMAC secrets.

Acceptance criteria:

- every imported object identifies its origin instance and content hash;
- unsigned or unknown-origin bundles are rejected or quarantined;
- trust decisions are auditable.

### F1: Release-Level Schema And Policy Lattice

- Add release classification and access policy IDs to shareable records,
  assessments, provenance, and bundles.
- Implement the no-access-broadening derivation rule.
- Add embargo, redaction, and privileged-policy metadata.

Acceptance criteria:

- derived artifacts cannot be exported at a lower release level unless a
  redaction/declassification policy is recorded;
- tests cover public, internal, confidential, privileged, and private records;
- assessments and provenance cannot silently become less restrictive than their
  parent records.

### F2: Signed Federation Bundle Export

- Produce append-only exchange bundles with manifests, hashes, release levels,
  provenance visibility, confidence assessments, and signatures.
- Support public, internal, confidential, and privileged export profiles.
- Exclude local caches, secrets, private drafts, backups, and run logs.

Acceptance criteria:

- bundle verification detects tampering;
- export dry-runs show exactly which records are included, redacted, or blocked;
- exported confidence assessments preserve dimensions, method provenance,
  basis visibility, and ambiguity warnings.

### F3: Quarantine Import And Local Policy Review

- Import federation bundles into quarantine.
- Evaluate local policy before promotion.
- Preserve conflicts, contradictions, supersession, and hidden-provenance
  warnings as reviewable state.
- Current implementation adds first-class contradiction case records generated
  from explicit `contradicts_claim_ids` links. Cases preserve open/reviewed/
  resolved state, can point to adjudication records, are included in snapshots,
  and move through signed federation bundles under the same release-level policy
  checks as other canonical records.
- `groundrecall contradictions sync STORE` materializes missing cases from
  explicit claim links, `groundrecall contradictions list STORE --sync` returns
  a review batch with claim previews, and `groundrecall contradictions
  adjudicate STORE CASE_ID ...` records the adjudication without silently
  rewriting the underlying claims.

Acceptance criteria:

- imports do not overwrite canonical memory directly;
- unauthorized release levels remain quarantined or rejected;
- reviewers see source instance, release level, provenance visibility, and
  affected downstream records before promotion.
- contradiction cases are promoted only when all referenced claims are included
  and the case itself is exportable at the target release level.

### F4: Project And Entity Federation

- Add project/team/entity scopes and role mappings.
- Support signed role-directory/policy distribution from an entity or project
  hub, with receiver-side caps before local policy compilation.
- Add import/export audit logs and revocation handling.

Acceptance criteria:

- team members cannot read or promote outside granted scopes;
- revocation and supersession events propagate without deleting historical
  audit context;
- conflict handling remains review-gated rather than last-write-wins.

### F5: Public Knowledge-Pack Release

- Generate public or internal release packs with license metadata, redacted
  provenance, checksums, and immutable manifests.
- Record source release levels and redaction policies used to create public
  derivatives.
- Provide reproducible import validation.

Acceptance criteria:

- public packs contain no confidential, privileged, private, secret, backup,
  run-log, or local-only database material;
- public claims disclose whether supporting provenance is full, partial,
  redacted, or hidden;
- checksums and manifests reproduce across builds from the same store version.

## Non-Goals For The Current Alpha

The current repo does not yet provide:

- real-time networked sync
- conflict-free replicated data types
- hosted review services
- remote ChatGPT MCP access without an authenticated transport and mandatory
  server-side policy

The next useful integration milestone is CG-00 through CG-04 in
[chatgpt-mcp-integration-roadmap.md](chatgpt-mcp-integration-roadmap.md): a
read-only, policy-bound ChatGPT access path that does not weaken local-first
operation or shared-memory authority.
