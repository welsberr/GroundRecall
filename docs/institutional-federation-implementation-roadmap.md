# Institutional Federation Implementation Roadmap

Date: 2026-07-29
Status: implementation plan
Primary repositories:

- `/home/netuser/bin/GroundRecall`
- `/home/netuser/bin/ClaimWright`

IF-00 status (2026-07-29): implemented in `ff32ae7` with a deterministic
capability report, CLI inspection flags, and a versioned 18-action policy
fixture. ClaimWright's matching fixture/checker slice is `94b26f3`.

IF-01 status (2026-07-29): scope/work records, additive snapshots, release
filtering, inspection counts, and CLI CRUD are implemented locally. Contribution
and stewardship records remain in IF-02.

IF-02 status (2026-07-29): decision, contribution, review-receipt,
stewardship, and custody-event records plus contribution transition validation
are implemented. Reviewer authority and separation-of-duty enforcement remain
in IF-03.

IF-04 status (2026-07-29): policy-aware prior-work search is implemented for
work, decision, and claim records, including negative/inconclusive outcomes,
exact versus lexical candidate labels, release filtering, inaccessible-result
counts, and CLI output. Semantic duplicate confirmation remains review-gated.

IF-05 status (2026-07-29): signed catalog build, verification, descriptive /
aggregate / opaque detail levels, receiver release/instance caps, quarantine,
policy preflight, and catalog query are implemented. Network transport and
protected-topic inference evaluation remain future work.

IF-12 status (2026-07-29): a deterministic conformance evidence report is
implemented in `src/groundrecall/institutional_conformance.py` and exposed
through `groundrecall inspect --institutional-conformance`. The report maps
paper/roadmap scenarios to current capability IDs, policy actions, policy
coverage routes, code/test/doc evidence, and explicit caveats. It is evidence
mapping, not production certification.

IF-13 status (2026-07-29): policy-gated institutional write helpers are
implemented in `src/groundrecall/institutional_write.py`. Coding agents now have
a Python API that blocks policy `deny` / `hard_gate` results before scope, work,
decision, contribution, contribution-review receipt, stewardship, or custody
event writes, and a separate helper that policy-gates contribution transitions
before persisting the updated contribution plus append-only review receipt.
Direct low-level store methods remain trusted primitives, not public authority
surfaces.

IF-14 status (2026-07-29): `record_custody_event` now accepts an optional
policy provider and blocks policy `deny` / `hard_gate` results before persisting
append-only custody events. Release-broadening protection remains in place, and
explicit role/authority validation remains a follow-up beyond policy-provider
preflight.

## Objective

Build a more capable GroundRecall federation layer that turns appropriately
released member knowledge into durable group and institutional capability.

The implementation must support:

- propagation of reviewed individual knowledge to group memory;
- discovery across team and project silos;
- avoidance of duplicated exploration and repeated failed approaches;
- preservation of knowledge beyond an individual's group tenancy;
- onboarding, succession, decision-rationale, dependency, incident-learning,
  stewardship, accountability, controlled reuse, and organizational-resilience
  workflows;
- local control over what received knowledge becomes authoritative;
- mechanical release, privacy, provenance, and policy boundaries.

This is a coding-model execution plan. Each work package is intended to produce
a bounded, independently testable commit or small commit series.

## Repository Authority

GroundRecall is authoritative for:

- canonical memory and federation record schemas;
- the policy-plugin request and decision contract;
- release-level and provenance-visibility semantics;
- exchange bundles, catalogs, subscriptions, quarantine, promotion, audit, and
  lifecycle enforcement;
- policy-enforcement coverage reporting.

ClaimWright is authoritative for:

- collaborative research and institutional-memory policy content;
- ClaimWright reason codes, obligations, reviewer roles, and checklists;
- policy fixtures that conform to GroundRecall's contract;
- human-readable explanations of the supplied policy stance.

ClaimWright must not redefine the GroundRecall plugin format. GroundRecall must
not import ClaimWright as a required runtime dependency. Compatibility is
through versioned files and the existing `claimwright.directory` provider.

## Implementation Invariants

Every work package must preserve these invariants:

1. Contribution, receipt, quarantine, local acceptance, and authority are
   distinct states.
2. Origin identity does not confer local authority.
3. Producer policy cannot broaden receiver authority.
4. Private records are not federated.
5. `Restricted` is not a synonym for `confidential`; restriction, purpose,
   compartment, originator-control, legal, HR, incident, source-protection,
   export-control, and privilege constraints remain separate from release
   level.
6. Restricted records are local-only by default and cannot federate as ordinary
   confidential records.
7. Derived records cannot receive a less restrictive release level without a
   recorded redaction or declassification decision.
8. Hidden provenance is disclosed as hidden or partial; it is not represented
   as fully inspectable evidence.
9. Contradictions, minority positions, negative results, and rejected
   contributions are not silently discarded.
10. Ordinary expiry, supersession, retraction, and tenancy change do not erase
   provenance.
11. Exceptional erasure remains separately authorized and leaves only minimal
   non-sensitive tombstone state.
12. Institutional ownership, stewardship, and custody are not inferred from
    contribution volume.
13. Catalogs and expertise views must not leak protected project membership,
    topics, source identities, or privileged activity.
14. Automations that promote, publish, transfer custody, revoke, retire an
    instance, or erase data are policy-gated, audited, and resumable where
    applicable.

## IF-RF: Restriction-Aware Federation Hardening

Status as of 2026-07-29: core implementation complete for metadata-based
restriction markers. GroundRecall no longer normalizes `restricted` to
`confidential`; restricted records fail closed for federation export by default;
imports, promotion plans, catalogs, role directories, trust keysets, and
incremental change feeds now carry or enforce restriction/compartment caps.
The federation, catalog, change-feed, role-directory, and trust-key CLIs expose
explicit allow/cap flags for restriction markers and compartments; omission of
those flags preserves the fail-closed default.
Future schema work may add first-class restriction fields beyond metadata.
Export and catalog policy-plugin preflight now receives the aggregate
restriction and compartment context observed in the local snapshot; import and
promotion already receive the corresponding bundle context.
All four federation operations also accept an explicit `purpose` value and
forward it to policy plugins, with matching CLI flags.

This package should precede additional high-risk federation feature expansion.
It corrects the current lossy behavior where `restricted` metadata normalizes to
`confidential` and replaces release-level-only authorization with
release-plus-restriction authorization.

Problem statement:

- `public`, `internal`, `confidential`, `privileged`, and `private` are release
  levels.
- `restricted` is not a release level. It is a constraint signal indicating
  that ordinary release-level policy is insufficient.
- `restricted` content may be confidential, privileged, private, or internal,
  but federation needs to know the restriction basis before deciding whether
  catalog discovery, bundle export, import, promotion, or derivative release is
  allowed.

Target data model:

```yaml
release_level: confidential
restrictions:
  - legal_privileged
  - hr
  - incident
  - source_protected
  - export_controlled
  - originator_controlled
  - project_compartment:alpha
federation_policy:
  federatable: false
  derivatives_allowed: policy_gated
  catalog_discovery: none
```

Coding-model implementation sequence:

1. **Normalize classification semantics.**
   - Update `src/groundrecall/federation.py` so `restricted` no longer maps to
     `confidential` in `RELEASE_VALUE_ALIASES`.
   - Keep `confidential`, `sensitive`, `nonpublic`, and `non_public` mapped to
     `confidential`.
   - Keep `legal_privileged` mapped to `privileged` only as a release-level
     compatibility alias, but also treat it as a restriction marker when it
     appears in metadata.
   - Add tests showing `normalize_release_level("restricted") is None`.

2. **Add restriction extraction helpers.**
   - Implement helpers in `src/groundrecall/federation.py`, or a small shared
     module if reuse is needed:
     - `restriction_markers_from_metadata(metadata) -> list[str]`
     - `record_restriction_markers(record) -> list[str]`
     - `restriction_block_reason(record, action, target_release_level) -> str | None`
   - Recognize metadata keys:
     - `restriction`
     - `restrictions`
     - `restricted`
     - `compartment`
     - `compartments`
     - `purpose_restrictions`
     - `originator_controlled`
     - `export_controlled`
     - `legal_hold`
     - `privilege`
   - Normalize marker names to lowercase snake_case, preserving
     `project_compartment:<id>` or equivalent scoped markers.

3. **Fail closed on restricted export.**
   - In `_record_block_reason`, block records with restriction markers by
     default before ordinary release-level export succeeds.
   - Use distinct reasons such as:
     - `restricted_not_federated`
     - `restricted_catalog_discovery_blocked`
     - `restricted_derivative_requires_policy`
   - Allow export only when metadata names an explicit reviewed policy such as
     `restriction_policy_id`, `declassification_policy_id`, or
     `redaction_policy_id`, and only for a derivative whose own release level is
     no less restrictive than allowed by that policy.
   - Preserve restriction markers in audit findings. Do not silently discard
     them from exported derivatives.

4. **Harden import validation.**
   - Extend `_bundle_policy_violations` to validate every federated record
     family, not only sources, fragments, artifacts, observations, claims,
     contradiction cases, concepts, and relations.
   - Include scopes, works, decisions, contributions, review receipts,
     federation feedback, stewardship, custody events, promotions, and
     adjudications where those appear in a bundle.
   - Reject bundles containing restricted markers unless accepted policy
     explicitly allows the marker, scope, producer instance, purpose, and
     target release level.
   - Treat producer signatures as origin authentication only; local receiver
     policy remains final authority.

5. **Harden catalogs and discovery.**
   - In `src/groundrecall/catalog.py`, prevent restricted scopes from appearing
     in descriptive, aggregate, or opaque catalogs by default.
   - Do not leak restricted scope membership, topic names, record counts, time
     coverage, or release-level presence unless a policy explicitly allows
     sanitized discovery metadata.
   - If sanitized discovery is later allowed, include `basis_visibility:
     redacted` and avoid exact counts where counts themselves could disclose
     membership or activity.

6. **Add policy-plugin context.**
   - Extend `PolicyRequest.metadata` for federation export/import/catalog
     operations to include:
     - `restriction_markers`
     - `compartment_ids`
     - `purpose`
     - `producer_instance_id`
     - `receiver_instance_id` when known
     - `derivative_policy_id`
   - Do not add new decision points unless the existing
     `federate_export`/`federate_import` plus action strings prove inadequate.

7. **Update trust and role controls.**
   - Add optional restriction/compartment constraints to federation grants,
     role definitions, trust-key metadata, subscriptions, and catalog imports.
   - Defaults must be empty/no restricted authority.
   - Receiver-side import of role directories and keysets must cap restrictions
     just as it caps release levels, actions, instances, scopes, and subjects.

8. **Document release and restriction policy.**
   - Update `docs/memory-lifecycle-roadmap.md`,
     `docs/policy-plugin-spec.md`, and `docs/preprint/threat-model.md`.
   - State that release level answers “how broadly may this be shared?” while
     restriction markers answer “what special purpose, compartment, or legal
     constraints survive any sharing?”
   - State that `restricted` must not be mapped to `confidential`.

Required tests:

- `test_restricted_is_not_confidential_alias`
- `test_restricted_record_is_not_federated_as_confidential`
- `test_restricted_derivative_requires_explicit_policy`
- `test_restricted_scope_absent_from_federation_catalog`
- `test_restricted_catalog_does_not_leak_counts_or_topics`
- `test_import_rejects_bundle_with_unaccepted_restriction_marker`
- `test_role_directory_caps_restriction_markers`
- `test_trust_key_caps_restriction_markers`
- `test_policy_plugin_receives_restriction_context`
- `test_all_bundle_record_families_are_release_and_restriction_checked`

Exit criteria:

- `restricted` metadata no longer normalizes to `confidential`;
- private and restricted records are local-only by default;
- confidential federation requires explicit scoped authority;
- privileged federation remains explicit and exceptional;
- restricted catalog discovery is denied by default;
- imports reject unaccepted restrictions even when signatures and release
  levels are otherwise valid;
- policy decisions and audit findings preserve restriction reasons;
- tests cover export, import, catalog, role directory, trust key, change-feed,
  and policy-plugin paths;
- operators can express the same restriction and compartment caps through the
  supported CLI entry points as through the Python API.

## Policy Mapping

Use the existing GroundRecall v1 decision points and distinguish institutional
operations through `PolicyRequest.action`. Do not expand the decision-point
enumeration until implementation evidence shows that action-specific rules
cannot be expressed safely.

| Operation | Decision point | Action |
| --- | --- | --- |
| Discover a scope catalog | `query` | `discover_federation_catalog` |
| Read protected catalog details | `read` | `read_federation_catalog_entry` |
| Propose member knowledge | `propose` | `propose_group_contribution` |
| Review a contribution | `review` | `review_group_contribution` |
| Accept into group memory | `promote` | `accept_group_contribution` |
| Publish catalog | `federate_export` | `publish_federation_catalog` |
| Import catalog | `federate_import` | `import_federation_catalog` |
| Create/update subscription | `act` | `manage_federation_subscription` |
| Export incremental changes | `federate_export` | `export_incremental_changes` |
| Import incremental changes | `federate_import` | `import_incremental_changes` |
| Record receiver feedback | `propose` | `record_federation_feedback` |
| Transfer group custody | `act` | `transfer_knowledge_custody` |
| Retire an instance | `act` | `retire_federation_instance` |
| Generate onboarding view | `query` | `generate_scope_orientation` |
| Generate expertise/steward view | `query` | `generate_stewardship_view` |
| Generate impact report | `query` | `generate_change_impact_report` |
| Generate release pack | `publish` | `publish_knowledge_release_pack` |
| Withdraw/revoke a release | `supersede` | `withdraw_knowledge_release` |

Namespaced request metadata may carry:

- `groundrecall.scope_kind`;
- `groundrecall.destination_scope_id`;
- `groundrecall.contribution_intent`;
- `groundrecall.review_risk`;
- `groundrecall.required_quorum`;
- `groundrecall.origin_instance_id`;
- `groundrecall.owner_scope_id`;
- `groundrecall.steward_role_ids`;
- `groundrecall.retention_class`;
- `groundrecall.custody_event_kind`;
- `groundrecall.catalog_detail_level`;
- `groundrecall.subscription_id`;
- `groundrecall.change_kinds`;
- `groundrecall.affected_scope_ids`;
- `groundrecall.license_ids`;
- `groundrecall.provenance_visibility`;
- `groundrecall.incident_compartment`;
- `groundrecall.exceptional_authority_id`.

Plugins must ignore unknown metadata and must never treat metadata as proof of
authority. Authority comes from the locally configured policy provider and
review records.

## Target Records And Derived Artifacts

Add records incrementally rather than in one schema-breaking change.

### Canonical records

1. `ScopeRecord`
   - `scope_id`;
   - `scope_kind`: `entity`, `group`, `project`, or `community`;
   - title and optional parent scope;
   - owner scope/principal references;
   - default release level;
   - retention class;
   - active/retired lifecycle;
   - metadata.
2. `WorkRecord`
   - `work_id`;
   - `work_kind`: `project`, `technique`, `experiment`, `prototype`,
     `incident`, or `lesson`;
   - scope, title, summary, status, outcome;
   - started/completed/review dates;
   - related claim, artifact, concept, source, and work IDs;
   - negative/inconclusive outcome support;
   - release and provenance metadata.
3. `DecisionRecord`
   - `decision_id`, scope, question, outcome, status;
   - alternatives considered and rejected;
   - constraints and rationale;
   - supporting/opposing record IDs;
   - decision maker/reviewer role references;
   - effective, review, supersession, and expiry dates.
4. `ContributionRecord`
   - contribution ID, origin, contributor, destination scope, intent;
   - contributed record IDs and immutable hashes;
   - proposed release/provenance visibility;
   - state: proposed, triaged, under review, accepted, partially accepted,
     rejected, deferred, withdrawn, or superseded;
   - assigned steward/reviewer roles;
   - policy decisions and review receipts.
5. `StewardshipRecord`
   - subject record/scope;
   - steward principal or role;
   - custody scope;
   - responsibility type;
   - effective/expiry dates;
   - status and succession target.
6. `CustodyEventRecord`
   - event ID and kind: assign, accept, transfer, decline, orphan, recover, or
     retire;
   - affected scope/record/instance IDs;
   - previous and new custodians;
   - authority, rationale, timestamp, and audit references.
7. `FederationFeedbackRecord`
   - producer and receiver IDs;
   - bundle, record, or contribution references;
   - receiver outcome: accepted, rejected, contradicted, superseded,
     inapplicable, or needs-review;
   - rationale, release level, and review status.

### Derived or local-control artifacts

- signed `FederationCatalog`;
- local `FederationSubscription`;
- incremental `FederationChangeBundle`;
- `PriorWorkReport`;
- `ScopeOrientationPack`;
- `ChangeImpactReport`;
- `GovernanceHealthReport`;
- public/internal `KnowledgeReleasePack`.

Derived artifacts must be reproducible from canonical state plus explicit local
policy/configuration. Subscriptions remain receiver-local and are not promoted
as shared knowledge merely because they exist.

## Work Packages

### IF-00: Baseline And Contract Fixtures

GroundRecall:

- record current schema, CLI, federation, policy-coverage, and test counts;
- add representative v1 policy-request/decision JSON fixtures for every action
  in the policy-mapping table;
- add a generated institutional-federation capability status report with
  `implemented`, `partial`, and `future` states.

ClaimWright:

- add matching expected-decision fixtures for its provider;
- extend the checker so malformed collaboration policy files or duplicate
  stable IDs fail validation.

Tests:

- fixture schema validation;
- unknown metadata ignored;
- no fixture grants authority through request metadata;
- old policy configs remain loadable.

Exit:

- both repositories agree on current v1 contract fixtures;
- no production capability is claimed from roadmap prose alone.

### IF-01: Scope And Work Records

GroundRecall:

- add `ScopeRecord` and `WorkRecord` Pydantic models;
- add deterministic store directories and CRUD/list methods;
- include records in snapshots, inspect output, public export filtering, query
  indexing, and federation filtering;
- add explicit release and parent-scope validation;
- add migration/load compatibility for snapshots without the new arrays;
- add CLI commands to create/list/show scopes and work records.

ClaimWright:

- add policy rules requiring scope, provenance, review state, and release level
  for durable shared work;
- add negative-result preservation obligations;
- add a `prior-work-reviewer` role card.

Tests:

- deterministic round trip;
- release inheritance never broadens access;
- private work excluded from federation;
- negative and inconclusive outcomes remain queryable;
- legacy snapshots load unchanged.

Exit:

- local stores can represent projects, techniques, experiments, incidents, and
  negative results without encoding them as untyped claim metadata.

### IF-02: Decision, Contribution, And Stewardship Records

GroundRecall:

- add `DecisionRecord`, `ContributionRecord`, `StewardshipRecord`, and
  `CustodyEventRecord`;
- add store, snapshot, export, federation, inspect, and query support;
- implement a contribution state machine with explicit valid transitions;
- keep contribution review receipts append-only;
- distinguish origin, contributor, owner scope, accepting reviewer, and
  steward;
- reject transitions that imply acceptance without review authority.

ClaimWright:

- add `policies/collaboration.yaml`;
- add stable rules for contribution attribution, reviewer independence,
  rationale preservation, minority/dissent preservation, and stewardship;
- add role cards for `group-contributor`, `group-reviewer`, `scope-steward`,
  and `records-custodian`;
- add contribution pre-action and post-action checks.

Tests:

- invalid state transitions fail;
- contributor cannot self-approve when separation-of-duty policy applies;
- rejection/deferment preserves submitted hashes and rationale;
- stewardship does not derive from activity counts;
- public contribution cannot expose private basis.

Exit:

- member knowledge can move through an inspectable proposal-to-group-memory
  workflow.

### IF-03: ClaimWright Institutional Policy Provider

GroundRecall:

- extend `ClaimWrightPolicyProvider` to load the new collaboration policy file;
- evaluate the action mappings above;
- emit structured reasons, obligations, required reviewers, release caps,
  redactions, confidence effects, and audit tags;
- add each new enforcement surface to `policy_coverage.py`;
- block deny/hard-gate outcomes before durable changes.

ClaimWright:

- define stable reason codes for:
  - missing destination scope;
  - unclassified contribution;
  - contributor-reviewer conflict;
  - insufficient review quorum;
  - missing steward;
  - protected catalog disclosure;
  - unauthorized custody transfer;
  - tenancy departure without handoff;
  - minority-position suppression;
  - negative-result loss;
  - incident-compartment leakage;
  - expertise-view personnel-surveillance risk;
  - missing attribution/license;
  - stale high-impact knowledge;
- define matching obligations and required reviewer roles;
- make rules configurable by scope risk rather than globally hard-coded.

Tests:

- one GroundRecall test per reason-code family;
- ClaimWright checker fixtures agree with GroundRecall provider results;
- composed policies apply the most restrictive result;
- ClaimWright findings remain policy findings, not federation grants.

Exit:

- collaborative/institutional operations are policy-covered without making
  ClaimWright a GroundRecall dependency.

### IF-04: Prior-Work And Duplicate-Effort Discovery

GroundRecall:

- implement `groundrecall prior-work STORE QUERY`;
- search work records, decisions, negative results, claims, sources, and graph
  neighbors;
- return exact-identity, content-hash, lexical, and graph-related candidates in
  separate evidence classes;
- include outcome, scope, release, provenance visibility, review state,
  currentness, and access-limited-result counts;
- never label semantic candidates as duplicates without review;
- expose a Python API and MCP tool.

ClaimWright:

- add a configurable pre-action obligation to run prior-work review before
  expensive or durable project initiation;
- permit override with rationale where search is unavailable or disproportionate;
- require negative/inconclusive results to be represented fairly.

Tests:

- known technique and negative result are found;
- inaccessible records are not leaked through titles or snippets;
- hidden result counts do not disclose protected scope identity;
- candidate similarity remains review-gated;
- stale/superseded results are labeled.

Exit:

- a coding agent can check whether materially related work already exists
  before beginning a substantial task.

### IF-05: Signed Federation Catalogs

GroundRecall:

- define a versioned catalog schema containing only policy-approved discovery
  metadata: producer, scopes, topic/concept summaries, record-kind counts, time
  coverage, release levels, provenance-visibility summary, update cursor, and
  signature;
- implement catalog build, sign, verify, quarantine, local-cap import, list,
  and query commands;
- reuse Ed25519 trust-registry lifecycle;
- make detail levels explicit: opaque, aggregate, descriptive;
- require policy evaluation for catalog publication, import, and protected
  entry reads.

ClaimWright:

- add least-disclosure and membership/topic-inference rules;
- require catalog review for confidential, privileged, incident, HR, legal, or
  source-protected scopes;
- forbid using catalog activity counts as personnel performance measures.

Tests:

- signature/hash tampering rejected;
- private scopes absent;
- protected topic names absent at aggregate/opaque levels;
- receiver caps narrow imported catalog visibility;
- catalog discovery cannot promote canonical knowledge.

Exit:

- an authorized member can discover that relevant knowledge exists without
  first knowing the holding host and without receiving the underlying records.

### IF-06: Subscriptions And Incremental Change Bundles

Status (2026-07-29): a file-based, signed and resumable first transport is
implemented in `src/groundrecall/change_feed.py`. Receiver-local subscriptions
filter by scope, record kind, change kind, release ceiling, and cursor; imports
are verified and quarantined idempotently, and acknowledgements advance only
after cursor continuity (and optional signature verification). Network
transport, canonical promotion, and bounded cron orchestration remain follow-up
work.

GroundRecall:

- define receiver-local subscriptions by producer, scope, topic, record kind,
  release ceiling, change kind, and cursor;
- generate deterministic incremental bundles for create, revise, supersede,
  contradiction, adjudication, expiry, retraction, revocation, and custody
  events;
- verify and quarantine incremental bundles before promotion;
- make cursors producer-specific and replay-safe;
- add bounded resumable polling/import commands suitable for cron;
- record acknowledgements without making them evidence of epistemic agreement.

ClaimWright:

- add subscription-purpose, least-scope, acknowledgement, high-impact routing,
  and notification-fatigue rules;
- require escalation only for configured risk classes;
- prevent silent auto-promotion from subscriptions.

Tests:

- replay is idempotent;
- missing cursor ranges are detected;
- out-of-order bundles remain quarantined or explicitly reconciled;
- revocation/supersession reaches subscribers as review state;
- denied imports do not advance cursors;
- crash/restart resumes safely.

Exit:

- groups can receive bounded changes without full-store replication or
  last-write-wins behavior.

### IF-07: Multi-Party Review And Federation Feedback

Status (2026-07-29): a first functional slice is implemented in
`src/groundrecall/institutional_review.py`. GroundRecall now stores generalized
review receipts and federation feedback records, evaluates reviewer quorum,
separation, duplicate reviewer identity, dissent, and content-hash invalidation,
exports signed feedback bundles, includes these records in snapshots and
federation filters, and exposes unresolved disagreement summaries. Automatic
promotion blocking from quorum results, direct feedback-bundle import, and
deeper query/impact integration remain follow-up work.

GroundRecall:

- add review receipts with reviewer principal/role, decision, rationale,
  timestamp, policy ID, and reviewed content hash;
- add quorum and separation-of-duty evaluation before high-risk promotion;
- add `FederationFeedbackRecord` and signed feedback bundles;
- preserve producer and receiver adjudications as distinct assertions;
- expose unresolved cross-instance disagreement in query and impact views.

ClaimWright:

- define risk-based quorum defaults;
- require an independent reviewer for high-risk public, privileged, incident,
  or institution-wide changes;
- add conflict-of-interest, dissent/minority-position, and appeal obligations;
- avoid universal quorum requirements for low-risk private exploration.

Tests:

- changed content invalidates old review receipts;
- duplicate reviewer identities do not satisfy quorum;
- producer cannot force receiver acceptance;
- dissent remains visible after majority acceptance;
- feedback respects release and provenance visibility.

Exit:

- collective review improves quality without flattening disagreement or
  confusing consensus with authority.

### IF-08: Custody, Tenancy Departure, And Instance Retirement

Status (2026-07-29): a dry-run planning slice is implemented in
`src/groundrecall/institutional_custody.py`. GroundRecall now reports subjects
without active stewardship, plans tenancy departures without deleting or
silently converting private personal records, plans instance retirement across
trust keys, subscriptions, catalogs, pending contributions, stewardship,
canonical counts, quarantine, and backups, and provides a guarded custody-event
helper that blocks release broadening. Destructive apply commands, full
role/authority policy preflight, and automated key/subscription shutdown remain
follow-up work.

GroundRecall:

- implement custody assign/accept/transfer/decline/orphan/recover events;
- add queries for records/scopes without an active steward;
- implement a dry-run tenancy-departure plan;
- implement a dry-run instance-retirement plan covering keys, subscriptions,
  catalogs, pending contributions, stewardship, canonical records, quarantine,
  backups, and replacement instances;
- add policy-gated apply commands only after dry-run tests are complete;
- preserve origin and audit history after custody changes;
- link exceptional erasure without conflating it with departure or retirement.

ClaimWright:

- add handoff completeness, least-necessary retention, legal hold,
  confidentiality survival, attribution, correction rights, and orphan
  escalation rules;
- require separate authority for custody transfer, release broadening,
  exceptional erasure, and key revocation;
- add a `tenancy-handoff-reviewer` role.

Tests:

- departure does not delete group-owned reviewed knowledge;
- private personal material is not silently converted to group ownership;
- orphan report is deterministic;
- custody transfer cannot broaden release level;
- retired keys and instances are blocked while history remains inspectable;
- erasure and retirement have distinct audit events.

Exit:

- knowledge continuity is explicit and tested when people or hosts leave.

### IF-09: Institutional Views And Impact Routing

Status (2026-07-29): a read-only first slice is implemented in
`src/groundrecall/institutional_views.py`. GroundRecall now generates scope
orientation packs, reverse dependency/change-impact reports, governance-health
reports, and explicit stewardship views with release-cap filtering, contradiction
and confidence state, incomplete-basis labels, and anti-ranking labels. Direct
policy-plugin preflight/post-render filtering, deeper graph dependency expansion,
and richer policy-drift detection remain follow-up work.

GroundRecall:

- generate scope orientation packs with vocabulary, reviewed decisions,
  current work, negative results, unresolved contradictions, stale items, and
  steward roles;
- generate reverse dependency/change-impact reports;
- generate governance-health reports for unowned scopes, stale high-impact
  records, unresolved conflicts, policy drift, incomplete provenance, and
  unacknowledged changes;
- generate expertise/stewardship views from explicit stewardship and reviewed
  provenance, not raw activity rankings;
- apply query/read policy before collecting and again before rendering output.

ClaimWright:

- add purpose limitation, minimization, fairness, correction, and
  anti-surveillance rules;
- require clear labels separating explicit stewardship, inferred familiarity,
  and unavailable evidence;
- prohibit performance ranking from GroundRecall contribution activity by
  default.

Tests:

- orientation packs exclude unauthorized scopes;
- impact reports preserve contradiction and confidence state;
- expertise views do not rank people by volume;
- redacted views do not leak restricted membership or topic names;
- currentness and incomplete basis remain visible.

Exit:

- onboarding, dependency review, and stewardship discovery become useful
  institutional products with privacy guardrails.

### IF-10: License-Aware Release Packs And Withdrawal

Status (2026-07-29): a deterministic release/withdrawal slice is implemented in
`src/groundrecall/institutional_release.py`. GroundRecall now records release
metadata fields on sources, artifacts, and claims; builds signed release packs
only from reviewed/promoted records with compatible licenses and attribution;
redacts protected provenance according to record redaction policy; records
superseding pack relationships; emits signed withdrawal notices distinct from
erasure; and blocks explicit withdrawn pack IDs from silent re-entry. Direct
ClaimWright publication-gate preflight and distributed withdrawal propagation
remain follow-up work.

GroundRecall:

- add license, attribution, source-release, redaction-policy, and derivative
  lineage fields;
- generate deterministic public/internal knowledge packs;
- record immutable manifests and policy/review receipts;
- implement signed withdrawal/supersession notices;
- prevent withdrawn packs from silently re-entering current context while
  preserving historical audit state.

ClaimWright:

- add license compatibility, attribution, consent/authority, public
  defensibility, provenance visibility, and withdrawal-review rules;
- require publication gatekeeper approval for public packs.

Tests:

- incompatible or missing required licenses hard-gate publication;
- identical inputs reproduce manifests;
- protected provenance remains redacted;
- withdrawal is distinct from erasure;
- superseding pack relationships are visible.

Exit:

- institutions can reuse and publish reviewed knowledge with defensible
  provenance and withdrawal semantics.

### IF-11: MCP And Adapter Coverage

Status (2026-07-29): a first MCP coverage slice is implemented in
`src/groundrecall/mcp.py`. GroundRecall now exposes MCP tools for prior-work
review, federation catalog discovery, subscription status, change-impact
reports, stewardship/orphan review, and no-write contribution proposal drafts.
Responses include policy decisions when caller-supplied policy config is used,
and proposal tools explicitly state that no canonical writes were performed.
Mandatory server-side policy configuration, post-render filtering, and mutation
tools that write durable records remain follow-up work.

GroundRecall:

- add MCP tools for prior-work query, catalog discovery, contribution proposal,
  subscription status, impact report, and stewardship/orphan review;
- keep mutation tools policy-gated and review-visible;
- include policy decisions and audit references in tool responses.

ClaimWright:

- extend its MCP roadmap with collaboration pre/post checks, contribution
  review, custody/handoff review, catalog-release review, and institutional-view
  privacy review;
- provide stable fixture responses.

Tests:

- MCP and CLI/API results agree;
- tool descriptions do not imply autonomous authority;
- denied mutations leave audit evidence and no protected writes;
- adapters exchange stable IDs rather than private evidence text where
  possible.

Exit:

- assistants can use the institutional workflows without bypassing policy or
  creating a second canonical schema.

### IF-12: Evaluation, Operations, And Paper Evidence

GroundRecall:

- add reproducible demonstrations for contribution, prior-work discovery,
  signed catalog discovery, incremental subscription, multi-party review,
  custody transfer, and release withdrawal;
- measure discovery precision/recall on a synthetic multi-scope fixture;
- measure review burden, false duplicate cues, routing volume, replay
  idempotence, and catalog leakage failures;
- document cron/systemd examples using the repository Python environment;
- update architecture, threat model, claim-evidence matrix, implemented feature
  summary, and preprint only after tests/demos exist.

ClaimWright:

- add policy conformance examples for low-risk team work, confidential project
  work, privileged incident work, member departure, and public release;
- validate that stricter policy is proportional to risk;
- report policy findings separately from permission grants.

Exit:

- each manuscript claim maps to code, tests, reproducible demonstration, or
  explicit future-work status;
- the implementation does not claim production IAM, DLP, legal compliance,
  distributed consensus, or empirically proven productivity gains.

## Cross-Repository Delivery Rules For A Coding Model

For each work package:

1. Inspect `git status`, current schemas, tests, and roadmaps in both canonical
   repositories under `/home/netuser/bin`.
2. Do not overwrite unrelated user changes.
3. Implement GroundRecall contract/schema changes before ClaimWright relies on
   them.
4. Add backward-compatible loaders before emitting new schema fields.
5. Put destructive functionality behind an explicit dry-run plan, policy gate,
   confirmation flag, exact targets, and audit record.
6. Add unit tests for models and policy plus end-to-end tests for CLI/API/MCP
   behavior.
7. Add failure-path tests before claiming a security or governance property.
8. Update policy coverage and documentation in the same work package.
9. Run targeted tests, then the full suite in every modified repository.
10. Commit each repository separately with the same work-package ID in the
    commit message.
11. Push only after tests pass and the worktree is clean.
12. Report commit IDs, tests, remaining limitations, and any intentionally
    deferred cross-repository dependency.

Do not implement multiple later packages merely because adjacent code is
convenient. Preserve reviewable commit boundaries and complete the acceptance
criteria of the active package first.

## Recommended Execution Order

```text
IF-00 contract fixtures
  ↓
IF-01 scopes/work ──→ IF-04 local prior-work discovery
  ↓                         ↓
IF-02 contribution/stewardship
  ↓
IF-03 institutional policy provider
  ↓
IF-05 signed catalogs
  ↓
IF-06 subscriptions/change bundles
  ↓
IF-07 multi-party review/feedback
  ↓
IF-08 custody/retirement
  ↓
IF-09 institutional views
  ↓
IF-10 release packs
  ↓
IF-11 adapters
  ↓
IF-12 evaluation and paper evidence
```

IF-04 may begin after IF-01, but its policy obligations should not be considered
complete until IF-03. IF-08 planning can begin earlier, but destructive apply
paths must wait for the policy and audit foundation.

## Definition Of Completion

The institutional-federation roadmap is complete when:

- member knowledge has a reviewable contribution path to group memory;
- prior work and negative results are discoverable without access leakage;
- signed catalogs support cross-silo discovery;
- bounded subscriptions propagate relevant lifecycle changes;
- multi-party review and receiver feedback preserve local authority and dissent;
- custody and stewardship survive member and host departure;
- onboarding, impact, and governance views are policy-filtered;
- controlled releases include provenance, license, review, and withdrawal state;
- every durable or disclosure-sensitive path is represented in policy coverage;
- ClaimWright supplies versioned collaborative policy content conforming to the
  GroundRecall-owned plugin contract;
- tests and demonstrations substantiate the implemented claims.
