# Session Context, Parallel Safety, and Context Cost Roadmap

Status: proposed implementation roadmap; no session or cost features are
implemented by this document. Reviewed 2026-10-04 against checkout `9a0eadc`
and its existing uncommitted changes.

GroundRecall should identify where each session works, coordinate shared
writes, and help users carry only the context needed for their next action.
Implement a portable core with optional Codex and Claude Code integrations.
The first release should provide reliable identity, conflict detection, usage
accounting, and advice. Automated compaction and budget enforcement follow
only where an integration can actually control the relevant operations.

## Corrections to the earlier proposal

1. **Identity is not enforcement.** A manifest can constrain writes made through
   GroundRecall. It cannot intercept arbitrary shell commands or editor writes.
   Separate Git worktrees and assistant tool integration are needed for those.
   Report enforcement coverage explicitly; never label a session fully protected
   merely because it registered a root.
2. **Separate identity from observations.** Keep stable session identity apart
   from changing working directories, branches, commits, model choices, usage,
   and operation receipts. Ordinary commits and movement within a declared
   project should not require repeated confirmation. Crossing a project or
   changing the worktree binding requires an explicit context update.
3. **A session declaration grants no authority.** Effective write scope is the
   intersection of the declared scope, existing GroundRecall policy, authenticated
   principal, and host permissions. A client cannot authorize itself by naming
   a directory or another session's ID.
4. **Locks alone do not prevent stale writes.** Lock the revision check and
   mutation together. A session that read revision A must not silently replace
   revision B. Multi-record changes also need recovery and consistent readers.
5. **Keep runtime state private and separate from knowledge.** Reuse the
   workspace's `private_runs` location. Session metadata and cost events are not
   automatically imported, indexed as knowledge, or federated. A non-secret
   correlation ID may appear in provenance; credentials must never do so.
6. **Treat context occupancy, processed tokens, and money separately.** A large
   cached prompt can be cheaper than a smaller uncached prompt. Subscription
   consumption is not an API invoice. Context reduction has its own costs and
   can discard information needed to finish the task correctly.
7. **Use capability detection.** An MCP connection does not inherently reveal
   an assistant's context size, billing, local working directory, or compaction
   controls. Unsupported measurements remain unknown.

## Existing foundations and gaps

The bounded GroundRecall prior-work query returned review-required candidates,
including previous context-limit failures. Those results provide orientation,
not an approved specification. The following observations come from live code.

| Existing component | Reuse and required change |
| --- | --- |
| [Workspace layout](../src/groundrecall/workspace.py) | Reuse resolved workspace roles and `private_runs`; add explicit project bindings and validate overlapping roles. Existing validation does not make every role disjoint. |
| [Store](../src/groundrecall/store.py) and [store lock](../src/groundrecall/store_lock.py) | Keep atomic file publication and updater coordination; add conditional writes, operation transactions, and a documented lock order. Regular POSIX saves currently take a shared lock. |
| [Imports](../src/groundrecall/ingest.py) | Replace second-resolution default IDs and reusable output directories with exclusive allocation and immutable completed runs. |
| [Protocol initialization](../src/groundrecall/protocol.py) | Canonicalize roots once and make shared bootstrap publication atomic and coordinated. |
| [Assistant exports](../src/groundrecall/assistant_export.py) | Isolate output runs and publish a completed manifest. The fixed snapshot label is an identity ambiguity; `build_snapshot` itself does not persist a snapshot. |
| [Handoffs](../src/groundrecall/handoff.py) | Reuse governed handoff semantics and recovery records; replace process-local coordination with inter-process coordination. |
| [Startup profiles](../src/groundrecall/startup_profile.py) and [assistant adapter interface](../src/groundrecall/groundrecall_assistants/base.py) | Reuse curated context and rendering. Add a separate runtime adapter contract; export support does not imply access to live usage or compaction. |
| [Capability updates](../src/groundrecall/updates.py) | Reuse compatibility planning, backups, and preservation checks. New runtime metadata should not require rewriting the canonical graph. |

## Portable session contract

Use a small set of versioned records rather than one continually rewritten
manifest. Proposed module boundaries are `session_context.py`, `session_registry.py`,
`write_coordinator.py`, `usage.py`, `costs.py`, `context_advice.py`, and
`runtime_adapters/`. These names and the commands below are proposed interfaces.

| Record | Required information |
| --- | --- |
| `SessionIdentity` | Random GroundRecall session ID, task ID, optional parent session ID, authenticated owner reference, host ID, assistant/runtime and version, opaque provider session reference, creation time. Provider references are identifiers, never authentication tokens. |
| `WorkspaceBinding` | Binding revision, workspace ID and resolved path, canonical store identity/path, named project roots, allowed operation kinds and write targets, optional Git common directory, worktree path, branch/detached state and observed HEAD. |
| `SessionObservation` | Current project/CWD, observed Git state, model/provider, process incarnation, heartbeat, lifecycle state, collection time and evidence source. |
| `OperationReceipt` | Operation ID, session/binding revision, target identities, expected and resulting revisions/hashes, outcome, verification evidence and recovery reference. Record intended and observed paths separately. |
| `UsageObservation` | Source event ID, session/request/model identity, timestamp, provider/runtime version, counter semantics, token categories, context occupancy/capacity, measurement quality and coverage. |
| `ContextCheckpoint` | Task objective, constraints, decisions, outstanding work, file/revision references, test results, evidence links, next action, and an explicit list of information omitted. |

Store mutable registry state in a local SQLite database under
`<private_runs>/sessions/`, with transactions and bounded lock waits. Place
immutable receipts and checkpoints in session/operation-specific directories.
Do not put this database inside the canonical typed-record store. Set private
permissions and configurable retention, preserving checkpoints referenced by
unfinished work. A workspace shared across machines is not a supported lock
domain: use independent local stores or a single service that owns mutations.

Use explicit `--session` binding first, then a launcher-provided session
reference. Never select the most recently active session. CLI jobs without a
long-lived session can create an ephemeral session with an explicit target.
Read-only queries remain usable without registration. A contradictory supplied
context must fail; it must not fall back to automatic discovery.

MCP and HTTP requests carry a session reference that the server checks against
the authenticated caller and workspace mapping. Client paths and server paths
are different namespaces: translate declared roots through trusted bindings,
never interpret a remote client CWD as a server write path. A shared server must
not keep a process-global current session. Container bindings likewise need a
host/storage identity, not just a container-visible path string.

Resuming the same assistant conversation retains the GroundRecall session ID
but creates a new process incarnation and revalidates its binding. Forks and
subagents get new IDs linked to their parent/task. Compaction creates a context
epoch within the existing session; it does not reset spend or release work.
Heartbeat expiry marks liveness uncertain. Recovery must not delete another
session's files, steal a live OS lock, or assume a reused PID is the same process.

## Write coordination and the enforcement boundary

Default to separate worktrees for simultaneous source-code changes. Provide an
explicit shared-worktree mode with declared file scopes and overlap warnings.
Do not automatically copy or reset an existing dirty checkout. Git worktrees
still share repository metadata and may share build directories or external
services; declare those resources separately when an operation touches them.

In a shared worktree, a Git diff is an observation of aggregate changes, not
proof that one session made them. Attribute writes using tool receipts where
available; otherwise mark authorship unknown. Record a starting dirty-state
baseline so pre-existing changes are not claimed as new session output.

Within GroundRecall, use one write coordinator for CLI, library, MCP, and HTTP
mutations. Validate record IDs and path components, reject traversal, check the
resolved parent at the moment of writing, and account for symlink changes.
Where available, use directory-relative file operations and no-follow checks;
`Path.resolve()` at startup alone does not prevent a check/write race.

For the first implementation, prefer a store-wide transaction lock over a
complex collection of per-record locks. Acquire locks in one documented order:
maintenance gate, store transaction lock, then additional resource locks in
stable order. Never upgrade a held shared lock to exclusive. The coordinator
passes its transaction handle to internal saves so nested calls do not deadlock.
Use finite timeouts with diagnostic owner/operation information.

Lock identity must survive aliases, container mounts, and updater directory
replacement. Use a stable coordinator resource outside replaceable generations;
do not allow old and new writers to lock different inodes for the same logical
store. Test the compatibility transition against the existing updater lock.

A mutation checks the expected record revision while holding its write lock,
journals the operation, and publishes files atomically. Existing records can use
a content digest as the initial revision without a bulk data rewrite. Require
create-if-absent for new records and an expected revision for replacements;
explicit reconciliation handles intentional overwrites. Retries use an
idempotency key bound to the request payload.

Multi-record operations require journaled recovery and readers that cannot
observe a half-applied graph. Snapshot/export readers take a consistent read
lock or read a completed generation. Start with simple serialization; introduce
per-record concurrency only after measurements justify it. Coordinate indexes
with a captured store generation; a rebuild must not replace a live SQLite
database underneath active readers without a supported close/swap protocol.

Imports, exports, and notes get exclusively created operation directories or
unique note filenames. Stage artifacts privately and expose them only after a
completion marker. Preserve explicit import IDs when valid and unused; reject
collisions, or verify an identical completed operation for idempotent retry.
Publish any `latest` pointer separately under a lock. Do not silently reinterpret
all existing caller-selected export paths as new directory layouts.

GroundRecall can guarantee these checks only for participating writers. Report
coverage as `groundrecall_only`, `assistant_tools_integrated`, or
`externally_isolated`, with known gaps. Hooks and declared file claims are
cooperative controls, not an operating-system sandbox. Before advertising safe
concurrency, update all participating entry points and stop incompatible old
writers using the existing maintenance procedure.

## Usage and cost accounting

Present four independent quantities: current context occupancy, cumulative
processed tokens, estimated or reported monetary cost, and plan/quota usage.
Show measurement time, coverage, and `reported`, `estimated`, or `unknown` for
each. Missing values never become zero. A reported client cost is not necessarily
an authoritative bill.

Normalize usage into mutually exclusive billing categories: uncached input,
cache-read input, cache-write input where separately charged, and output.
Retain provider detail for reasoning, media, tools, and service tier. Do not add
reasoning tokens again when already included in output. Adapters must state
whether a count is per request, cumulative, or a current-context observation;
field names alone are insufficient to establish that meaning.

Deduplicate on source/request/event identity. Convert cumulative snapshots to
deltas only within the same counter epoch. Handle resets, delayed corrections,
out-of-order events, and retries. Keep parent and child usage separate and roll
up unique requests to a task total; never add child usage twice when a provider's
parent total already includes it. Flag incomplete attribution instead of guessing.

For a simple token-priced request, the estimate is:

```text
request_cost = sum(tokens_in_billing_category * category_rate_per_million) / 1,000,000
             + separately_metered_tool_or_service_fees
```

Rate cards need provider, exact model, effective dates, currency, billing route,
service tier, cache rules, relevant context thresholds, source URL, and retrieval
time. Support configured contracted rates. Use decimal arithmetic and retain the
rate-card version with each estimate. Unknown models, stale rates, missing usage,
and unsupported pricing rules produce a partial estimate or range, with coverage.
Never silently apply today's rate to an old request. Published categories and
rates must be checked against [OpenAI pricing](https://developers.openai.com/api/docs/pricing)
and [Claude pricing](https://platform.claude.com/docs/en/about-claude/pricing)
when implementing or refreshing the catalog.

For subscription users, present provider quota measurements when available and
optionally a clearly labeled API-equivalent estimate. Do not call that estimate
money charged, subscription savings, or remaining quota. Claude Code explicitly
distinguishes its calculated session cost from subscription billing in its
[cost documentation](https://code.claude.com/docs/en/costs).

GroundRecall's own retrieval, summary generation, compaction, and adapter work
also count toward task costs when metered. Keep the initial advisor deterministic
so periodic advice does not require an extra model call.

## Deciding when and how to reduce context

The proposed [lede-brief design](lede-brief-design-and-roadmap.md) adds three
preservation choices: a selective brief, a complete single document, or a
collection complete against a reviewed conceptual inventory. Track what the
collection preserves separately from what the current session has loaded.
Completeness includes qualifications and relationships, and a hard token budget
must not silently turn a complete transformation into a selective one.

Prefer preventive measures: bound tool output, retrieve specific sections, rank
and deduplicate memory results, keep large logs as referenced artifacts, and
load detailed evidence only when needed. Extend startup/retrieval bundles with a
token budget and report what was excluded. A tokenizer for the actual model is
preferred; character-based estimates must be labeled and must not drive hard
limits. Hidden instructions and provider state may make full occupancy unknown.

Calculate usable headroom from the effective runtime limit minus observed
occupancy and the reserve for the next response, tools, and reasoning where
applicable. Do not confuse a model's advertised maximum with the configured
runtime limit. Forecast the next few turns using observed growth and the planned
next operation; show uncertainty when there is little history.

Offer reduction advice when projected headroom is insufficient, the runtime
reports pressure, irrelevant material dominates the task, or a cost comparison
supports it. Percentage thresholds may be configurable fallback hints, not a
universal rule such as “compact at 80%.” Add a cooldown and compare actual
occupancy after the action so the advisor does not recommend compaction in a loop.

Compare keeping the current context with reducing it over an explicit horizon:

```text
expected_savings = cost_of_continuing_without_reduction
                 - (checkpoint_and_compaction_cost
                    + context_reload_and_cache_rebuild_cost
                    + cost_of_continuing_with_reduced_context)
```

Include warm-cache and cold-cache scenarios and likely remaining turns. Prompt
caching depends on reusable prefixes; smaller context does not guarantee lower
next-request cost. See [OpenAI prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching).
Report a range and assumptions, not a promised saving. Context exhaustion can
justify compaction even when estimated monetary savings are negative.

Illustrative arithmetic only: if compaction and reload cost $0.06 and the
estimated saving is $0.01 per later turn, six turns reach break-even. Two turns
would not recover that cost. These are synthetic values, not provider prices.

Every recommendation includes its trigger, evidence freshness, proposed action,
estimated context change, estimated cost range, and information to preserve.
Choose among limiting future output, retrieving a smaller evidence bundle,
native compaction, or starting a fresh conversation with a checkpoint. Forking
may preserve the full history and must not be presented as guaranteed reduction.
Model switching is a separate quality/cost choice, not a default compaction action.

Before compaction or transfer, create an immutable checkpoint with the active
task, constraints, uncommitted work locations, unresolved questions, evidence,
and next action. Validate references and distinguish results actually verified
from pending checks. Resume by verifying the live workspace binding and relevant
file hashes. A summary is a navigation aid; authoritative files and evidence
remain available. Do not automatically promote a checkpoint into accepted
knowledge or transport local path permissions to another host.

Initial operation is advisory. Later, explicit session policy can allow native
compaction after a checkpoint. GroundRecall must not edit private transcript
databases or invent an undocumented control mechanism. A soft budget produces
advice. A hard budget is enforceable only when GroundRecall or an integrated
launcher controls dispatch: reserve estimated spend transactionally across
parallel requests, reconcile actual usage, and report possible in-flight
overshoot. An MCP server alone cannot stop unrelated assistant requests.

## Lede-brief integration with session management

Lede-brief supplies reusable context packages and recovery checkpoints. Session
management owns their association with a task, workspace binding, and context
epoch; the cost advisor compares preparation and loading strategies. Runtime
adapters observe or perform transitions only through supported interfaces.

GroundRecall consumes a shared lede-brief library backed by Epistemap's neutral
coverage and dependency operations. Document extraction, drafting, partitioning,
and semantic-review orchestration belong to that shared library. GroundRecall
owns the operational checkpoint profile, persistence/access policy, session
bindings, transition lifecycle and cost accounting. See the
[cross-project ownership contract](lede-brief-design-and-roadmap.md#cross-project-ownership-and-dependency-direction).
Didactopus and CiteGeist need not adopt GroundRecall to use portable lede-brief.

Distribution is package based: local development uses sibling editable installs;
released consumers use bounded `lede-brief` and Epistemap versions from a
configured package index or lockfile. GroundRecall exposes the integration as
the optional `ledebrief` extra so installations that only use the core memory
store do not acquire the transformation package.

Maintain three distinct coverage records, all referencing the same versioned
inventory and preservation profile:

| Coverage | Meaning | Required evidence |
| --- | --- | --- |
| Preserved | Units and relationships represented in a verified collection | Package version, source hashes, mappings and review receipts. |
| Required | Units and dependencies needed for the current task or next action | Task revision, selection rationale, mandatory operational state and dependency closure. |
| Loaded | Units and dependencies supplied to the current assistant context | Delivery receipt, session/context epoch, bundle hashes, time and observation method; unconfirmed if the runtime cannot establish delivery. |

Keep `collection_coverage` as the lede-brief manifest's name for preserved
coverage. Add `required_coverage` and retain `loaded_context_coverage` for the
other two. A delivery receipt establishes supplied content, not that a model
understands or will retain it indefinitely. After native compaction, reconcile
loaded coverage with available evidence; do not assume all previously delivered
units survived. Record unknown occupancy separately from unconfirmed delivery.

The preparation and transition lifecycle is:

1. **Observe:** capture current context pressure, usage/cost, caching evidence,
   pending operations, and adapter capabilities. Mark missing or stale signals.
2. **Select:** derive required coverage for the next action, including definitions,
   qualifications and task constraints. A changed objective creates a new
   selection revision; a fixed token budget cannot silently remove requirements.
3. **Prepare:** reuse a valid package or generate and verify one. Save an immutable
   operational checkpoint and attach exact source and workspace revisions.
4. **Compare:** assess keeping context, selective loading, complete-single loading,
   complete-set retrieval, and a checkpoint followed by compaction or transfer.
   Include preparation, verification, reload, cache rebuild and expected later
   retrieval costs. Recommend an action with assumptions and coverage gaps.
5. **Transition:** at a completed operation boundary, revalidate the checkpoint
   and perform an authorized supported transition, or provide portable manual
   instructions. Do not transition across an unresolved write transaction or
   discard pending tool results; checkpoint running jobs explicitly if they remain.
6. **Verify:** record delivery and runtime completion independently, verify the
   receiving session's binding and file revisions, reconcile required versus
   loaded coverage, and capture post-transition occupancy/cost when available.

Use a `ContextTransition` record with operation ID, source/target session and
context epoch, binding/task revision, package/checkpoint IDs, proposed action,
cost forecast, coverage status, and outcome. Suggested states are `prepared`,
`requested`, `runtime_completed`, `resume_verified`, `failed`, and `unconfirmed`.
Manual transitions can remain unconfirmed; an accepted compaction request is
not a successful resume. Idempotent retries must not duplicate compaction or
launch another receiving session. Preserve the checkpoint on failure and use
a newly validated context to recover; do not promise restoration of opaque
provider conversation state.

Operational checkpoints require the objective, current user constraints,
decisions and rationale, unresolved questions, workspace/worktree identity,
uncommitted work references and attribution limits, actual verification results,
pending jobs, and next action. Treat these as mandatory meaning units even when
the source-document brief is selective. A checkpoint records permissions as
context; the receiving session must obtain its effective authority from normal
policy and host checks, and reacquire any needed file claims. It cannot inherit
write authority or live leases by reading a document.

| Situation | Candidate action |
| --- | --- |
| Repetitive, large tool output | Selective brief with an omission report and a retained source artifact. |
| Dense source whose details all matter | Complete-single package, or a budget-conflict result if it cannot fit. |
| Large source covering several topics | Complete-set preservation with task-specific dependency-complete loading. |
| Long session approaching its effective limit | Operational checkpoint followed by supported compaction or a fresh-session transfer. |
| Source or task changed since preparation | Invalidate affected mappings/selections and refresh before reuse. |

Compare costs over both the current session and an explicitly estimated reuse
horizon. Charge preparation once in actual accounting; allocation across sessions
is a separate reporting view. Hypothetical reuse savings must not reduce recorded
spend. Record generation/verification, cache rebuild, repeated retrieval, and
failed attempts. Report peak-context reduction separately from total task cost.
When cost signals are unavailable, provide coverage/pressure advice with unknown
monetary benefit. Scope package reuse by access policy as well as content hashes;
parallel preparation uses exclusive operation paths and conditional publication.

## Assistant integration strategy

Official interfaces below were checked on 2026-10-04. Installed versions and
surfaces may differ. Implement adapters against versioned fixtures and probe
capabilities before offering an action. Do not assume a documented interface
is accessible from the user's currently running app.

| Surface | Observation path | Reduction path and limitation |
| --- | --- | --- |
| Portable CLI/library/MCP | Explicit identity, operation receipts, optional supplied usage events and model-aware estimates | Build checkpoint and advice; user or host integration performs reduction. No automatic visibility into the full conversation. |
| Codex app-server integration | Bind a known thread to its CWD/session; consume `thread/tokenUsage/updated` through a client that owns or is authorized for that connection | `thread/compact/start` is documented; wait for the compaction lifecycle to finish before recording success. Access is not implied by running GroundRecall as an MCP server. |
| Codex interactive client | Use supported status/context surfaces; unknown fields stay unknown | Offer the documented `/compact` action when available. Do not inject slash commands into an unrelated conversation or scrape arbitrary local sessions. |
| Claude Code integration | Consume a deliberately configured status-line input for context/cost and optional OpenTelemetry events for usage | Lifecycle hooks support checkpoint integration. Advise native compaction; add automatic control only when a supported runtime interface is verified. |
| Other assistants | Register capabilities for identity, usage, context measurement, checkpoint delivery, and compaction | The baseline works with supplied context and advice even if no runtime control exists. |

Codex's [app-server reference](https://learn.chatgpt.com/docs/app-server) documents
the usage notification and compaction lifecycle. The [CLI commands reference](https://learn.chatgpt.com/docs/developer-commands?surface=cli)
documents interactive compaction. The Responses API's [compaction interface](https://developers.openai.com/api/docs/guides/compaction)
is a separate integration: opaque compacted output must be passed forward as
documented, not treated as a portable human-readable checkpoint.

Claude Code's [status-line reference](https://code.claude.com/docs/en/statusline)
provides context and cost fields, with missing/null cases. Its [monitoring
reference](https://code.claude.com/docs/en/monitoring-usage) provides token and cost
metrics and labels costs approximate. Its [hooks reference](https://code.claude.com/docs/en/hooks)
provides lifecycle events such as SessionStart, PreCompact, and SessionEnd.
Preserve existing user hook/status-line configuration when installing an adapter;
provide a composable integration and removal path.

Collect only the configured session and necessary numeric/identity fields by
default. Do not enable prompt logging or send telemetry externally as a side
effect of cost monitoring. Imported text is evidence, never executable policy.
Apply access controls to team reports and keep private paths and detailed usage
out of federation bundles unless deliberately shared.

## Delivery sequence and completion criteria

All stages below are pending. This is a new implementation track; it does not
reclassify existing broker work as incomplete or authorize live deployment.

| Stage | Deliverable | Dependencies and completion gate |
| --- | --- | --- |
| SC-0: Contracts and coverage | Inventory every mutation entry point; specify session/usage schemas, authority rules, lock order, adapter capabilities and migration compatibility | First. Review maps each write to enforcement or an explicit gap; synthetic fixtures cover two sessions, two worktrees, a non-Git project and a remote client. |
| SC-1: Session registration | `session start/status/list/rebind/end`; private registry; context propagation in CLI/library/MCP/HTTP; resume/fork rules | SC-0. Two clients cannot inherit each other's context, spoof ownership, silently switch stores, or turn unknown CWD into the server's CWD. Authorized scope changes are recorded without prompting for ordinary commits. |
| SC-2: Coordinated writes | Conditional writes, operation journal, consistent snapshots, unique import/export/note outputs, shared-file and handoff coordination | SC-1. Separate processes racing on a stale record get a conflict; killed multi-record writes recover; disjoint runs remain separate; updater exclusion and nested locking are tested. |
| SC-3: Portable usage and costs | Normalized event ingestion, deduplication, context observations, rate-card catalog, per-session/task reports and soft budgets | SC-1; can develop alongside SC-2. Fixtures verify missing usage, cumulative resets, duplicate/reordered events, model changes, cache categories, parent/child overlap and subscription labeling. |
| SC-4: Codex and Claude Code adapters | Versioned adapters, explicit session binding, capability probes, optional local collection, documented setup/removal | SC-3. One supported version of each assistant passes recorded-fixture tests plus an opt-in smoke test; unavailable features return an explicit capability result. |
| SC-5: Context advice and recovery | Lede-brief packages, mandatory operational checkpoints, preserved/required/loaded coverage, dependency-aware loading, transition recommendations and cost forecasts | SC-2 and SC-3 plus applicable LB package stages. Manual cross-assistant resume preserves constraints and validates files; delivery can remain explicitly unconfirmed; comparisons include verification, compaction and retrieval costs. |
| SC-6: Opt-in automation and release | Supported transition dispatch and resume verification, shared budget reservations where enforceable, recovery/retention controls, update and rollback documentation | SC-4 and SC-5. Concurrent spending cannot bypass reservations; duplicate requests do not repeat transitions; disconnects and failed compactions preserve checkpoints and truthful status; preservation tests pass. |

Recommended first milestone: SC-0 through SC-3, delivering session safety and
honest usage reports without requiring either assistant to expose full runtime
control. SC-4 and SC-5 deliver the practical cross-assistant context advisor.
SC-6 is optional automation after those behaviors have been demonstrated.

The lede-brief LB-0 through LB-5 track extends SC-5 with explicit preservation
contracts, verified document transformations, and dependency-aware retrieval.
Its portable prototype can proceed independently; durable publication and cost
comparison use SC-2 and SC-3. Native compaction remains optional.

These SC dependencies apply to the GroundRecall consumer only. Epistemap
ELB-0/ELB-1/ELB-2 precede the corresponding shared-library contracts and graph
operations; ELB-3 and LB-5 establish cross-project compatibility. LB-4 now covers
three consumer adapters; I-2 below requires its GroundRecall adapter, not the
completion of unrelated educational or bibliography workflows. The overall
shared capability release still requires all three consumer fixture gates.

Deliver the integrated capability in three increments. These group existing
stages rather than introducing a second competing implementation sequence:

| Increment | Stage mapping | Acceptance gate |
| --- | --- | --- |
| I-1: Packages and checkpoints | SC-1/SC-2 and LB-0 through LB-3; initial SC-5 checkpoint support | Produce portable versioned packages and operational checkpoints; required constraints survive manual resume; stale/missing sources and impossible budgets are explicit failures. |
| I-2: Coverage-aware loading and advice | SC-3, remaining advisory SC-5, LB-4/LB-5; SC-4 supplies optional runtime observations | Compare required and loaded coverage, retrieve dependencies, and report preparation-inclusive costs. Demonstrate Codex/Claude Code manual consumption; no telemetry is reported as unknown, not zero. |
| I-3: Optional automated transitions | SC-4 and SC-6, using the verified I-1/I-2 artifacts | Supported adapters checkpoint at safe boundaries, execute once, verify resume and report incomplete coverage. Unsupported surfaces retain the manual path. |

Prototype packaging without live session writes may precede SC-2; integrated
publication may not. LB-4 uses the SC-5 coverage/loader contract co-developed in
I-2, not a separately completed SC-5 release, avoiding a circular dependency.

Proposed commands, for API review rather than immediate use:

```text
groundrecall session start --workspace <memory-root> --project <checkout> --assistant <name>
groundrecall session status --session <id>
groundrecall session rebind --session <id> --project <new-checkout>
groundrecall usage ingest --session <id> --events <normalized-events.jsonl>
groundrecall usage report --session <id>
groundrecall context advise --session <id>
groundrecall context checkpoint --session <id>
groundrecall session end --session <id>
```

Roll out context enforcement with an explicit compatibility mode and published
cutover. Automation that supplies a wrong session fails immediately; legacy
callers may initially receive an ephemeral context and coverage warning. Update
[the assistant protocol](assistant-protocol.md), [workspace guidance](workspace-layout.md),
and relevant CLI help when behavior ships. Preserve existing canonical records,
graph edges, provenance and unknown additive fields through `groundrecall update`.
Use additive runtime migrations and verified backups if persistent formats change;
an old writer must not silently bypass a newly required concurrency protocol.

Release verification uses real subprocesses and synchronization barriers, not
only threads or timing sleeps. Cover path aliases and symlink changes, dirty and
shared worktrees, crashes at journal/publication boundaries, stale leases,
unavailable telemetry, unknown models, and failed checkpoint delivery. Test the
filesystem/platform combinations actually supported and state limitations for
network filesystems.

Evaluate context advice on fixed tasks with the same acceptance criteria:
completion quality, lost constraints, repeated retrieval, processed tokens,
estimated cost including the advisor, latency and recovery success. Compare
against native assistant behavior as well as no GroundRecall advice. Do not
claim a successful optimization from token reduction alone.

For integrated release tests, include a complete collection with a partially
loaded context, a missing qualifier dependency, task/source changes during
preparation, concurrent publication, unreadable checkpoints, denied access to a
required document, duplicate transition delivery, unavailable telemetry, and
compaction that completes without verifiable retained coverage. Compare resumed
task outcomes against the same acceptance criteria before reduction, including
preserved user constraints, correct file targets and truthful verification state.
