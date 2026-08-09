# Review Backlog And Reminder Roadmap

## Purpose

### RB8 adversarial coverage

The implementation test matrix includes malformed and hash-tampered ledgers,
concurrent append serialization, invalid and context-mismatched cursors,
protected-release count/path/topic leakage, symlink and traversal fixtures,
corrupt or stale broker caches, policy-denied MCP writes, and clock/timezone
edge cases. These tests are isolated to temporary fixtures and do not claim
production performance or touch live stores.

GroundRecall deliberately separates evidence capture, proposal, review, and
canonical promotion. That separation is only workable if pending review remains
visible. A review-gated system without backlog visibility can accumulate
unreviewed imports, inferred graph edges, contradictions, stale records, and
federated contributions indefinitely.

This roadmap defines an implementation-ready review-backlog subsystem. It is
intended for execution by a coding model in small, tested changes.

The subsystem must:

1. aggregate pending work across a GroundRecall workspace and canonical store;
2. prioritize review without treating a heuristic score as authority;
3. remind users at a configurable cadence without creating notification
   fatigue;
4. preserve release controls, provenance, policy decisions, and auditability;
5. support individual, team, CLI, scheduled, and MCP-assisted workflows; and
6. never promote, adjudicate, publish, or federate content merely because a
   reminder was generated or acknowledged.

## Current State And Gap

GroundRecall already has several review-producing surfaces:

- imports emit `review_queue.json`;
- promotion writes canonical `ReviewCandidateRecord` objects;
- graph augmentation creates reviewable relation candidates;
- contradiction detection and adjudication maintain separate case state;
- institutional federation can leave contributions pending;
- graph maintenance records resumable per-profile state and audit output; and
- canonical inspection reports aggregate record counts.

These surfaces do not yet form one backlog. In particular, a normal workspace
may contain:

```text
.groundrecall/
  source-notes/
  imports/
  store/
```

Source notes awaiting import, import-local review queues, and canonical-store
review candidates are different stages of the same human-attention pipeline.
A store-only report would omit the earliest and potentially largest backlog.

There is also no first-class acknowledgement, deferral, assignment, reminder
policy, or notification-delivery contract.

## Design Invariants

- The backlog is a derived operational view, not an alternative canonical
  truth store.
- Discovery of pending work must be read-only.
- Acknowledgement means "the reminder was seen," not "the claim was accepted."
- Deferral and assignment do not change epistemic or canonical status.
- Review completion is derived from the authoritative source record whenever
  possible.
- Reminder output must default to metadata and counts; content snippets require
  separate read authorization.
- Release level, scope, ownership, and policy filtering apply before counts,
  identifiers, titles, snippets, or notification text are returned.
- A lower-release notification must not reveal the existence of a
  higher-release item through totals or category counts.
- Automated maintenance may propose review work but may not automatically
  approve it.
- Notification delivery is an adapter concern. GroundRecall owns the backlog
  and reminder-decision contract.
- Every state-changing backlog action is append-only audited.
- Backlog item identifiers must be stable and deterministically derived from
  the authoritative source identity and review reason.
- Repeated aggregation and reminder evaluation must be idempotent.

## Scope Of The Unified Backlog

The first complete aggregator should cover:

| Source | Pending condition | Expected action |
|---|---|---|
| Source notes | not represented by a completed or active import | import, dismiss with reason, or defer |
| Import directories | unresolved `review_queue.json` items or lint failures | review, repair, or reject |
| Canonical review candidates | draft, triaged, or needs-review state | accept, revise, reject, or defer |
| Inferred graph relations | unreviewed candidate semantic/provenance edges | relation review |
| Contradiction cases | open, triaged, or awaiting adjudication | inspect evidence and adjudicate |
| Lifecycle proposals | stale, expiry, supersession, consolidation, or retraction proposal | lifecycle review |
| Federation contributions | proposed, quarantined, triaged, or under review | accept, reject, return, or defer |
| Stewardship and custody | unassigned or overdue review obligations | assign or resolve |
| Policy obligations | `require_review` or unresolved soft-gate obligations | obtain required review |
| Maintenance diagnostics | sparse graph areas or failed/stalled maintenance requiring judgment | inspect or schedule corrective work |

Backups, completed imports, rejected candidates, expired reminders, and
historical audit records must not appear as active work unless explicitly
requested.

## Data Contracts

### `BacklogItem`

Add a versioned Pydantic model, initially in
`src/groundrecall/review_backlog.py`:

```text
schema_version
backlog_id
source_kind
source_id
source_path_hash
workspace_id
store_id
candidate_kind
candidate_id
reason_codes[]
required_actions[]
authoritative_status
triage_lane
priority_band
priority_factors[]
created_at
updated_at
age_seconds
due_at
scope_ids[]
owner_subject_ids[]
required_reviewer_roles[]
release_level
policy_obligations[]
content_available
acknowledgement_state
assignment_state
deferral_until
```

`source_path_hash` permits stable correlation without placing an absolute local
path in portable reports. Absolute paths may appear only in explicitly local
operator output and must never enter federation packs, publication artifacts,
or default notification payloads.

`priority_band` should be a bounded value such as `urgent`, `high`, `normal`,
or `low`. `priority_factors` must explain the classification. Do not expose a
single opaque score as though it were epistemic confidence.

### `BacklogDigest`

Add a versioned summary contract:

```text
schema_version
generated_at
workspace_id
subject_id
policy_context_hash
visible_total
new_since_last_digest
urgent_count
overdue_count
oldest_visible_age_seconds
counts_by_source_kind
counts_by_candidate_kind
counts_by_triage_lane
counts_by_priority_band
required_action_counts
maintenance_health
reminder_recommendation
items[]
redaction_summary
```

The default digest should include a bounded number of metadata-only items.
Callers must opt into content previews and pass the relevant read-policy gate.

### Backlog Interaction Ledger

Persist reminder interaction state outside canonical epistemic records:

```text
WORKSPACE/.review/backlog-events.jsonl
WORKSPACE/.review/backlog-reminder-state.json
```

Events should include:

```text
event_id
event_type
backlog_id
actor_subject_id
occurred_at
reason
until
assignment
policy_decision_ids[]
previous_event_hash
event_hash
```

Initial event types:

- `acknowledged`;
- `deferred`;
- `assigned`;
- `unassigned`;
- `reminder_emitted`;
- `reminder_suppressed`;
- `source_resolved`; and
- `source_disappeared`.

Acknowledgement, deferral, and assignment state should be reconstructed from
the ledger. The compact reminder-state file is a rebuildable cache.

## Workspace And Store Discovery

Implement explicit discovery rather than assuming that the command argument is
always a canonical store.

The CLI should accept a GroundRecall workspace root and optional overrides:

```bash
groundrecall review-status WORKSPACE \
  --store WORKSPACE/store \
  --imports-root WORKSPACE/imports \
  --source-notes-root WORKSPACE/source-notes
```

Discovery rules:

1. recognize a workspace by `source-notes/`, `imports/`, `store/`, or a
   workspace marker;
2. recognize a canonical store by its typed-record directories;
3. do not recursively interpret backup directories as active stores;
4. allow multiple explicitly named stores, but do not silently merge them;
5. report missing or ambiguous roots as diagnostics rather than silently
   returning an empty backlog; and
6. identify source notes already represented by imports through content hash
   and source provenance, not filename alone.

Add `groundrecall workspace-inspect` or extend `inspect` so users can see which
workspace, import roots, and stores were selected.

## Reminder Policy

Reminder evaluation should be deterministic and independently testable.

Suggested initial configuration:

```yaml
schema_version: groundrecall.review-reminders.v1
enabled: true
cadence: daily
quiet_hours:
  start: "21:00"
  end: "08:00"
timezone: America/New_York
digest:
  max_items: 20
  include_content_previews: false
thresholds:
  minimum_visible_items: 1
  urgent_immediate: true
  overdue_days: 7
  backlog_growth: 25
fatigue_control:
  unchanged_digest_suppression_hours: 72
  acknowledged_suppression_hours: 168
  maximum_reminders_per_day: 1
delivery:
  adapters:
    - type: file
      path: .review/latest-digest.json
```

The reminder evaluator should return one of:

- `emit`;
- `emit_urgent`;
- `suppress_empty`;
- `suppress_unchanged`;
- `suppress_quiet_hours`;
- `suppress_rate_limit`;
- `suppress_policy`; or
- `disabled`.

The result must include reason codes and the next eligible reminder time.

## Delivery Adapter Contract

Implement a small `ReminderDeliveryAdapter` protocol. Initial adapters:

1. `stdout`: text or JSON for interactive and cron use;
2. `file`: atomically replace a latest-digest file and optionally append a
   metadata-only history;
3. `desktop`: optional local `notify-send` adapter with no content previews by
   default; and
4. `webhook`: future work, disabled until authentication, release filtering,
   retry, and secret handling are specified.

Email, chat, and team dashboards should consume the same contract through
separate adapters or MCP clients. Do not put provider-specific credentials in
the canonical store.

Delivery must be two-phase:

1. compute and policy-check the exact payload;
2. deliver it and then append `reminder_emitted`, or append a failure event
   without falsely recording success.

`--dry-run` must evaluate and render without delivery or ledger writes.

## CLI Surface

Implement these commands incrementally:

```bash
# Read-only aggregation
groundrecall review-status WORKSPACE
groundrecall review-status WORKSPACE --format json
groundrecall review-status WORKSPACE --subject-id SUBJECT --policy-config FILE
groundrecall review-status WORKSPACE --only urgent --limit 20

# Reminder evaluation and optional delivery
groundrecall review-remind WORKSPACE --config reminder-policy.yaml --dry-run
groundrecall review-remind WORKSPACE --config reminder-policy.yaml --deliver

# Interaction state
groundrecall review-ack WORKSPACE BACKLOG_ID --actor SUBJECT
groundrecall review-defer WORKSPACE BACKLOG_ID --until TIMESTAMP --actor SUBJECT --reason TEXT
groundrecall review-assign WORKSPACE BACKLOG_ID --to SUBJECT --actor SUBJECT

# Diagnostics
groundrecall review-status WORKSPACE --health
```

All output should be JSON by contract, with a concise human rendering available
for terminal use. Exit codes should distinguish:

- success with no pending work;
- success with pending work;
- reminder recommended but not delivered;
- policy denial;
- invalid or ambiguous workspace; and
- delivery failure.

Do not use the number of pending items as an exit code.

## MCP Surface

Extend the versioned MCP adapter only after the core functions and CLI are
stable:

- `groundrecall.review_backlog`: read a policy-filtered, bounded digest;
- `groundrecall.review_backlog_item`: retrieve an authorized item and its
  provenance;
- `groundrecall.acknowledge_review_reminder`;
- `groundrecall.defer_review_reminder`; and
- `groundrecall.assign_review_item`.

MCP acknowledgement must not invoke promotion, relation acceptance,
contradiction adjudication, export, or federation. Tool descriptions and tests
must make this distinction explicit.

## Review Web Application And Federation-Broker View

The review experience should eventually be a web application, not only a CLI
or assistant surface. Its dashboard must combine two distinct work sources:

1. the local workspace and canonical-store backlog; and
2. the federation broker's policy-filtered catalog, quarantine, contribution,
   stewardship, and unresolved-review knowledge.

The broker view must not be treated as an extension of the local canonical
store. Broker records remain remote proposals or discovery metadata until they
are verified, imported to quarantine, and accepted through the local
promotion/review workflow. The dashboard is a coordinated review surface, not
an implicit federation or auto-promotion channel.

The intended read path is:

```text
local store/imports ─┐
                      ├─> policy-filtered backlog service ─> review dashboard
federation broker ───┘          │
                                ├─ local interaction ledger
                                └─ broker acknowledgement/assignment API
```

### Broker Adapter Contract

Add a versioned read-only `FederationReviewSource` adapter. It should consume
only signed, authenticated broker responses and normalize them into the same
metadata contract as `BacklogItem` without pretending that remote records are
local records.

Each remote item must retain:

- broker and producer instance identifiers;
- catalog or contribution identifier and content/version hash;
- source release level and receiver-allowed release level;
- trust-key and signature verification status;
- quarantine, revocation, supersession, and freshness status;
- remote scope and required reviewer roles;
- an explicit remote action URL or operation identifier, never a raw secret;
- the local policy decision and broker policy decision identifiers; and
- whether the item is discovery-only, reviewable, quarantined, or locally
  imported.

The adapter must support cursor-based incremental retrieval, bounded page
sizes, timeouts, retries without duplicate items, and an offline cached
snapshot with a visible last-successful-sync time. A broker outage must leave
the local backlog usable and must not silently present stale remote work as
current.

### Dashboard Views

The first dashboard should provide:

- **My review:** locally assigned or acknowledged work, with due and deferred
  states;
- **Local backlog:** source notes, imports, graph candidates, contradictions,
  lifecycle proposals, and local federation contributions;
- **Broker queue:** authorized remote contributions, quarantined bundles,
  unresolved broker disagreements, and stewardship obligations;
- **Cross-scope discovery:** broker catalog topics and prior-work references,
  clearly marked as discovery rather than accepted evidence;
- **Review detail:** source/provenance, policy decisions, release level,
  contradiction and supersession context, and the exact next authorized action;
  and
- **Health:** local aggregation time, broker sync freshness, signature/trust
  failures, quarantine counts, and delivery or API errors.

Counts, badges, search facets, and error messages must be computed after the
user's policy and release filtering. A user who cannot read a confidential
broker scope must not learn its existence from a hidden count, topic, assignee,
or “no results” distinction.

### Authority And Write Rules

- Dashboard acknowledgement, deferral, and assignment use the local or broker
  interaction ledger appropriate to the item origin.
- Accepting a broker contribution invokes the existing authenticated quarantine
  import and local promotion path; a dashboard button must not write directly
  to canonical records.
- Remote review decisions are advisory until verified as signed broker events
  and accepted under local policy.
- Broker-side assignment or acknowledgement must not be represented as local
  acceptance.
- Restricted, privileged, and otherwise non-federable content remains absent
  from dashboard responses unless both broker and local policy explicitly grant
  the operation.
- Every remote read, acknowledgement, assignment, import attempt, and policy
  denial is auditable with correlation IDs.

### Dashboard Implementation Phases

Extend the later roadmap phases as follows:

**RB6a — Local dashboard backend.** Expose a policy-filtered JSON API over the
existing `review-status` and interaction-ledger functions. Add pagination,
stable cursors, item-detail authorization, and CSRF/session protection. Keep
the web UI read-only until the API contracts are tested.

**RB6b — Broker read adapter.** Implement a mockable broker adapter over signed
catalog and contribution endpoints. Normalize remote metadata, verify trust and
release caps, cache snapshots, and expose freshness/error state. Add fixtures
for revoked keys, stale snapshots, quarantine, and restricted scopes.

**RB6c — Combined dashboard.** Add local/broker tabs, origin filters, unified
correlation links, cross-scope discovery, and separate local versus remote
actions. Ensure policy filtering occurs before aggregation and pagination.

**RB6d — Federated review actions.** Add explicit broker acknowledgement,
assignment, and contribution-import workflows. Require separate policy gates,
signed event verification, idempotency keys, and audit correlation for every
write.

**RB6e — Operational hardening.** Add authentication/session review, rate
limits, offline behavior, sync retry/backoff, audit export, browser security
headers, content-security policy, prompt-injection labeling for retrieved
content, and tests for cross-scope leakage.

Acceptance requires that:

- local review remains fully usable when the broker is unavailable;
- remote items cannot be mistaken for locally accepted knowledge;
- stale, revoked, quarantined, or superseded remote items are visibly marked;
- policy and release filtering is consistent in counts, lists, search, detail,
  and error paths;
- every dashboard write is attributable and reversible where applicable; and
- browser, API, and broker tests demonstrate no path, credential, or protected
  content leakage.

Assistant startup bundles may include a compact statement such as:

```text
GroundRecall review backlog: 14 visible items; 2 urgent; oldest 11 days.
```

This summary must be computed for the caller's subject and policy context.

## Policy And Release Enforcement

Define GroundRecall policy-plugin actions:

- `review_backlog.list`;
- `review_backlog.read_item`;
- `review_backlog.acknowledge`;
- `review_backlog.defer`;
- `review_backlog.assign`;
- `review_reminder.evaluate`; and
- `review_reminder.deliver`.

Apply policy before aggregation where necessary to prevent count leakage.
Conservative policy composition remains authoritative. Required reviewer roles
and obligations should be copied into backlog metadata without being treated as
satisfied.

Notifications must use the most restrictive release level among the item,
supporting records included in the payload, delivery adapter, and recipient
authorization. The first implementation should prohibit cross-instance
delivery of `restricted`, `confidential`, or `privileged` content and permit
only metadata that an explicit policy decision authorizes.

## Prioritization Rules

Implement explainable rules in this order:

1. explicit due date or policy deadline;
2. unresolved high-impact contradiction;
3. security, privacy, privilege, or release-policy concern;
4. blocked dependent work or federation contribution;
5. required reviewer availability or stewardship obligation;
6. age;
7. evidence completeness and estimated review effort; and
8. graph-connectivity benefit.

Graph density alone must not outrank safety or evidence quality. Confidence
values may inform review ordering, but low confidence must not automatically
mean low importance.

Allow policy plugins to raise priority, impose a deadline, require roles, or
suppress visibility. Do not allow a plugin to silently mark the underlying
review complete through the reminder interface.

## Implementation Phases

### RB0: Fixtures And Baseline

**Deliverables**

- Add workspace fixtures containing source notes, imports, a canonical store,
  graph candidates, contradictions, lifecycle proposals, and federation
  contributions.
- Add a fixture with backups and completed imports that must be ignored.
- Capture the current behavior of import-local and canonical review records.
- Document the backlog source/status mapping in tests.

**Tests**

- fixture inventory is deterministic;
- backup directories are excluded;
- source-note hashes connect notes to imports;
- existing review behavior is unchanged.

### RB1: Read-Only Unified Aggregator

**Deliverables**

- Add `review_backlog.py` with versioned `BacklogItem` and `BacklogDigest`
  models.
- Implement workspace discovery and source adapters.
- Add `review-status` CLI dispatch.
- Add stable backlog IDs and metadata-only JSON output.
- Add health diagnostics for missing, ambiguous, corrupt, or stale inputs.

**Acceptance criteria**

- one command reports pending work across source notes, imports, and the store;
- a workspace with pending source notes but an empty store does not report an
  empty backlog;
- repeated aggregation produces identical IDs and ordering;
- aggregation performs no writes;
- local absolute paths are excluded from portable/default JSON.

### RB2: Policy-Filtered Views And Explainable Priority

**Deliverables**

- Add subject, scope, release, and policy context to aggregation.
- Add bounded priority bands and reason factors.
- Add overdue, new-since, lane, kind, scope, and owner filters.
- Ensure counts are computed after visibility filtering.

**Acceptance criteria**

- unauthorized records do not affect totals;
- privileged supporting data does not leak through item titles or diagnostics;
- priority ordering is deterministic and explained;
- policy obligations remain visible but unsatisfied.

### RB3: Interaction Ledger

**Deliverables**

- Add append-only acknowledgement, deferral, and assignment events.
- Add hash chaining and a rebuildable state cache.
- Add `review-ack`, `review-defer`, and `review-assign`.
- Reconcile backlog events with authoritative source resolution.

**Acceptance criteria**

- acknowledgement never changes canonical review status;
- deferrals expire predictably;
- assignment is attributable and reversible;
- corrupt hash chains produce a visible health error;
- event writes are atomic and concurrency tested.

### RB4: Reminder Evaluation And Local Delivery

**Deliverables**

- Add the reminder-policy schema and parser.
- Add deterministic fatigue-control evaluation.
- Add `review-remind` with `--dry-run` and explicit `--deliver`.
- Implement stdout and atomic file adapters.
- Implement optional metadata-only desktop notifications.

**Acceptance criteria**

- unchanged digests are suppressed according to policy;
- urgent items override ordinary cadence but respect hard policy denial;
- quiet hours and timezone changes are tested;
- delivery failure is not recorded as successful delivery;
- notification text contains no content preview by default.

### RB5: Maintenance And Startup Integration

**Deliverables**

- Let graph maintenance return backlog deltas without delivering notifications.
- Add backlog-health fields to `inspect`.
- Include an authorized compact backlog summary in assistant startup/export
  bundles.
- Document cron and systemd-timer examples using the repository virtual
  environment explicitly.

**Acceptance criteria**

- maintenance candidate generation is visible on the next aggregation;
- maintenance remains usable without notification configuration;
- scheduled commands are bounded, lock-safe, and resumable;
- startup summaries cannot reveal higher-release counts.

### RB6: MCP And Review Workbench

**Deliverables**

- Add policy-gated MCP backlog read and interaction tools.
- Add backlog lanes and filters to the existing review workbench.
- Link backlog items to the authoritative review operation rather than
  duplicating it.

**Acceptance criteria**

- MCP reads are bounded and release filtered;
- MCP writes create backlog events only;
- prompt-injection content is marked untrusted;
- accepting an item still requires the existing promotion, relation-review, or
  adjudication API and its separate authority check.

### RB7: Federation And Team Stewardship

**Deliverables**

- Add local views of pending federation contributions and stewardship duties.
- Add assignment and reviewer-role views for teams.
- Define an aggregate-only, release-safe backlog status suitable for federation.
- Keep privileged and restricted review details local unless an explicit
  policy and recipient grant permit exchange.

**Acceptance criteria**

- remote teams cannot infer hidden backlog categories from totals;
- assignments survive ordinary member departure through scope stewardship;
- federation withdrawal or revocation removes subsequent visibility;
- notification delivery does not become an alternate content-federation path.

### RB8: Evaluation And Operational Hardening

## Implementation Status Audit (2026-07-30)

Implemented slices are RB1 (unified read-only aggregation), RB2 (policy and
release filtering), RB3 (hash-chained interaction ledger), RB4 (deterministic
local reminders), RB5 maintenance-health fields and cron guidance, RB6a-e
(framework-neutral local/broker dashboard contracts, fixture broker actions,
cache hardening, and MCP tools), RB7 stewardship digest, and RB8 synthetic
benchmark/adversarial regression coverage.

Remaining gaps are deliberate and should not be filled by guessing deployment
choices:

- RB0's broad fixture inventory (contradictions, lifecycle proposals, backups,
  and completed-import suppression) needs a dedicated fixture expansion.
- RB2 still lacks first-class scope/owner/overdue/new-since filters in the CLI;
  the current policy/release filtering is enforced before counts.
- RB3 has rebuildable state reconstruction but no compact reminder-state cache
  file or source-resolution reconciliation yet.
- RB5 does not yet add the backlog digest to `inspect` or assistant startup
  bundles; doing so requires choosing how startup subjects and policy config are
  discovered.
- Browser UI, authentication/session/CSRF protection, and production broker
  protocol/authentication remain deployment decisions; no framework or network
  listener is assumed here.

These gaps are documented rather than silently represented as complete. The
current test suite provides isolated coverage for path/release leakage,
tampered ledgers, cursor integrity, cache corruption/staleness, policy-denied
MCP writes, concurrent appends, and synthetic benchmark guardrails.

**Deliverables**

- Add synthetic large-backlog benchmarks.
- Measure aggregation latency, peak memory, incremental refresh cost, and
  reminder deduplication.
- Add corruption, clock-skew, daylight-saving, concurrent-run, symlink, path
  traversal, and poisoned-metadata tests.
- Add an operator runbook and migration notes.

**Initial targets**

- metadata-only aggregation of 10,000 backlog sources in under two seconds on a
  documented reference host;
- bounded memory use independent of source content size;
- no duplicate successful reminder for the same digest and delivery window;
- no absolute-path, release-level, or content leakage in portable fixtures;
- deterministic output for identical store, policy, subject, and time inputs.

Targets are engineering guardrails, not publication claims until measured.

## Suggested File Changes

The coding model should prefer these bounded additions:

```text
src/groundrecall/review_backlog.py
src/groundrecall/review_reminders.py
src/groundrecall/review_delivery.py
src/groundrecall/cli.py
src/groundrecall/mcp.py
src/groundrecall/inspect.py
src/groundrecall/policy_coverage.py
tests/test_review_backlog.py
tests/test_review_reminders.py
tests/test_review_backlog_mcp.py
docs/review-backlog-roadmap.md
docs/review-backlog-operations.md
README.md
```

Reuse `ReviewCandidateRecord`, existing contradiction/federation models, policy
composition, and graph-maintenance locking utilities where their contracts are
appropriate. Do not create a second canonical review-candidate schema merely
to simplify aggregation.

## Coding-Model Execution Rules

For each phase:

1. inspect current schemas and tests before changing contracts;
2. implement the smallest coherent vertical slice;
3. keep aggregation pure and testable apart from filesystem discovery;
4. add policy and release tests with the feature, not afterward;
5. run focused tests, then the complete GroundRecall suite;
6. update CLI help and documentation in the same commit;
7. record measured behavior and remaining limitations;
8. do not commit generated live-store data or host-specific paths; and
9. stop before adding provider-specific delivery integrations unless their
   credential and release model has been reviewed.

Recommended commit sequence:

1. `Add unified read-only review backlog aggregation`
2. `Add policy-filtered backlog priority views`
3. `Add audited backlog acknowledgement and deferral`
4. `Add reminder evaluation and local delivery adapters`
5. `Expose backlog health to maintenance and startup surfaces`
6. `Add policy-gated MCP review backlog tools`
7. `Add federation stewardship backlog views`
8. `Harden and benchmark review backlog operations`

## Definition Of Done

The review-backlog subsystem is complete for its first production-capable
release when:

- a newly initialized workspace includes reminder configuration guidance;
- source notes, imports, canonical review candidates, contradictions, graph
  candidates, lifecycle proposals, and federation work appear in one
  policy-filtered view;
- users can acknowledge, defer, and assign reminders without changing
  canonical truth status;
- cron or a systemd timer can safely emit bounded digests through an explicit
  Python environment;
- assistants can read a scoped backlog and record reminder interactions through
  MCP without acquiring promotion authority;
- notification fatigue controls and delivery audit are implemented;
- hidden content cannot be inferred from counts, paths, snippets, errors, or
  delivery metadata;
- all state-changing actions are attributable and auditable; and
- documentation clearly distinguishes reminder acknowledgement from review,
  acceptance, promotion, adjudication, publication, and federation.
