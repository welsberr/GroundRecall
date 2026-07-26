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

## Planned Model

The intended model is:

- append-only event capture at the edge
- canonical promoted store as the durable reviewed state
- generated exports and assistant bundles as derived artifacts
- signed, policy-checked exchange bundles rather than direct database
  replication
- explicit release classification and access policy on every shareable object

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

## Federation Implementation Milestones

Initial implementation status, 2026-07-26: GroundRecall now has federation
policy primitives, signed bundle export, signature/content-hash verification,
and quarantine import helpers in `groundrecall.federation`, exposed through
`groundrecall federation export` and `groundrecall federation import`. This is
the F0-F3 foundation. The CLI also accepts an optional local policy file and
JSONL audit log so hosts can require explicit requester grants before export,
quarantine import, or promotion. Quarantined bundles can be listed, dry-run
planned, and promoted into a canonical store only when signature verification,
release-level acceptance, local policy, and conflict checks pass. It does not
yet provide network transport, role directory integration, distributed policy
publication, or public release-pack publishing.

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

Audit events use `groundrecall.federation_audit.v1` JSONL records and capture
the requester, action, decision, release level, bundle ID, instance ID, policy
ID, reasons, and decision metadata.

### F0: Instance Identity And Trust Roots

- Define stable `instance_id`, local user/entity IDs, project IDs, and signing
  keys.
- Record origin and owner instance on imported records.
- Support explicit trust relationships between instances rather than implicit
  trust from network reachability.

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

Acceptance criteria:

- imports do not overwrite canonical memory directly;
- unauthorized release levels remain quarantined or rejected;
- reviewers see source instance, release level, provenance visibility, and
  affected downstream records before promotion.

### F4: Project And Entity Federation

- Add project/team/entity scopes and role mappings.
- Support policy distribution from an entity or project hub.
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

The next useful milestone is a practical local event-log, stable re-import,
temporal validity, and rollback model—not a full distributed platform in one
step.
