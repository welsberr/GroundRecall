# GroundRecall

GroundRecall is a local-first, provenance-aware knowledge substrate for
human-reviewable and assistant-usable memory. It imports source material into a
canonical store, supports review and promotion, exports assistant-neutral
snapshots, and can generate assistant-specific bundles for tools such as Codex
and Claude Code.

It is a governed memory layer, not a chat transcript store or an autonomous
agent runtime. GroundRecall keeps durable state, provenance, release policy,
review status, federation custody, and audit history separate from the
ephemeral sessions that use it.

GroundRecall is intended for work where durable context matters:

- site, app, and service administration across sessions
- local/remote deployment memory with host-role distinctions
- research notes and grounded claim tracking
- legacy document normalization through `doclift`
- learner-facing workflows through `Didactopus`
- assistant handoff between Codex, Claude Code, and other file-aware tools

GroundRecall's assistant protocol also defines an update policy for
long-running operational work. The policy asks assistants to record task
definition, plan/implementation details, and results as durable source notes.
The rationale is practical: project goals, task boundaries, planning tradeoffs,
and intermediate service states are often lost because memory updates happen
only at the end, or not at all.

## Current Features

- Import from llmwiki-style trees, plain notes, normalized `doclift` bundles,
  Didactopus packs, transcripts, PolyPaper projects, and specialized corpora.
- Normalize imports into artifacts, fragments, observations, claims, concepts,
  and relations.
- Maintain a provenance-first knowledge graph substrate over concepts, claims,
  relations, observations, artifacts, and source evidence.
- Lint and review import output before promotion.
- Promote reviewed records into a canonical GroundRecall store.
- Query by concept and export query bundles.
- Discover graph neighborhoods from full-text search hits with
  `groundrecall query STORE "topic phrase" --kind graph-search`.
- Inspect graph shape and concept/relation diagnostics with
  `groundrecall inspect --graph`.
- Surface graph quality diagnostics for inferred-edge density, weak relation
  grounding, unsupported claims, high-fanout concepts, and conflict links.
- Export assistant-neutral canonical snapshots.
- Export assistant-specific bundles:
  - Codex: `SKILL.md` plus `codex_bundle.json`
  - Claude Code: `CLAUDE.md` plus `claude_code_bundle.json`
- Export pack-ready query bundles for Didactopus.
- Initialize an assistant-neutral host/project memory protocol with
  `groundrecall protocol-init`.
- Run policy-gated institutional federation workflows for scopes, work,
  decisions, contributions, review receipts, stewardship, custody, catalogs,
  subscriptions, signed change bundles, quarantine, release packs, and
  withdrawal notices.
- Serve a bounded local/private-network HTTP MCP adapter with MCP
  `initialize`/`ping`, read-only query tools, server-owned identity and realm
  caps, request/response limits, correlation IDs, and privacy-conscious audit
  logging.
- Create and query governed assistant handoff proposals for ChatGPT/Codex
  interoperability; handoffs are proposal records, not arbitrary host
  execution or direct canonical-memory writes.

## Installation

From a checkout:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
groundrecall --help
```

For development:

```bash
.venv/bin/python -m pytest
```

The package also supports module invocation when working directly from source:

```bash
PYTHONPATH=src python -m groundrecall --help
```

## Basic Workflow

Import a source:

```bash
groundrecall import /path/to/source --out-root .groundrecall/imports --mode quick
groundrecall import /path/to/source --out-root .groundrecall/imports --mode quick --extract-graph heuristic
```

Imports also write review sidecars such as `concept_standardization.json` and
`graph_extraction_candidates.json` when applicable.

Lint the import:

```bash
groundrecall lint .groundrecall/imports/<import-id>
```

Review significant imports:

```bash
groundrecall review-server .groundrecall/imports/<import-id>
```

The review workbench includes concept, relation, and citation lanes when the
import contains corresponding candidates.

Promote the import into a canonical store:

```bash
groundrecall promote .groundrecall/imports/<import-id> .groundrecall/store --reviewer your-name
```

Promotion refuses imports with lint errors by default. Fix the source material,
adapter, or review data first. If you intentionally need to preserve a flawed
import for triage or recovery, use:

```bash
groundrecall promote .groundrecall/imports/<import-id> .groundrecall/store \
  --reviewer your-name \
  --allow-lint-errors
```

Warnings remain visible in the review queue but do not block promotion.

Inspect or query the store:

```bash
groundrecall inspect .groundrecall/store
groundrecall inspect .groundrecall/store --graph
groundrecall inspect .groundrecall/store --graph-summary
groundrecall review-status .groundrecall --format json
groundrecall review-ack .groundrecall BACKLOG_ID --actor reviewer-id
groundrecall review-defer .groundrecall BACKLOG_ID --until 2030-01-01T00:00:00Z --actor reviewer-id --reason "need source check"
groundrecall review-assign .groundrecall BACKLOG_ID --to teammate-id --actor reviewer-id
groundrecall query .groundrecall/store channel-capacity
groundrecall query .groundrecall/store channel-capacity --kind graph
groundrecall query .groundrecall/store "reliable communication" --kind graph-search --graph-limit 3
groundrecall graph-augment .groundrecall/store --concept-prefix concept::evo-edu --min-evidence 2
groundrecall graph-backfill .groundrecall/store --strategy claim-links
groundrecall graph-backfill .groundrecall/store --strategy claim-support-anchors --limit 25
groundrecall graph-backfill .groundrecall/store --strategy observation-artifact-anchors --limit 25
groundrecall graph-backfill .groundrecall/store --strategy source-anchors --limit 25
groundrecall graph-backfill .groundrecall/store --strategy claim-semantic-cues --limit 25
groundrecall graph-backfill .groundrecall/store --strategy claim-cooccurrence --extractor-mode none
groundrecall graph-backfill .groundrecall/store --strategy claim-contradiction-cues --concept-prefix concept::evo-edu --max-pair-checks 5000
groundrecall graph-augment .groundrecall/store --concept-prefix concept::evo-edu-notebook --strategy claim-mentions
groundrecall graph-backfill .groundrecall/store --strategy observation-cooccurrence --min-evidence 2
groundrecall graph-augment .groundrecall/store --concept-prefix concept::evo-edu-notebook --strategy source-family
groundrecall graph-augment .groundrecall/store --concept-prefix concept::evo-edu-notebook --strategy source-family --apply
groundrecall graph-maintenance .groundrecall/store --limit 5 --apply
groundrecall graph-maintenance .groundrecall/store --profile support --limit 5 --apply
groundrecall relation-review .groundrecall/store --concept-prefix concept::evo-edu-notebook --support-kind inferred --limit 25
groundrecall relation-review .groundrecall/store --apply relation-decisions.json
groundrecall export .groundrecall/store exports/canonical --graph-concept channel-capacity
groundrecall export .groundrecall/store exports/canonical --include-graph-diagnostics
groundrecall export .groundrecall/store exports/canonical --include-graph-interchange
```

Concept query bundles include an Epistemap graph, temporal summary, heuristic
epistemic reliability summary, and Bayesian reliability block with posterior
support estimates plus prior-sensitivity checks. These estimates expose evidence
strength and fragility; they are not source-truth labels.

`graph-maintenance` runs one bounded graph backfill slice and records resumable
state under the store by default. It is intended for cron/systemd-style periodic
launches with a small `--limit`, not as a long-running daemon. Its default
`safe` profile avoids high-volume support-anchor strategies; use
`--profile support` explicitly to backfill claim/observation/artifact support
anchors and source/fragment/claim provenance anchors. Each profile uses a
separate default state file under
`.groundrecall/store/.maintenance/` unless `--state-path` is provided. Each run
also takes an atomic lock next to the state file so overlapping scheduler
invocations skip safely by default. Use `--fail-if-locked` when the scheduler
should report lock contention as an error, and tune `--stale-lock-seconds` if a
host needs faster or slower recovery after an interrupted maintenance process.
Use `--profile semantic` for opt-in claim links, contradiction cues, topic
mentions, and deterministic semantic cue backfill for definitions,
qualifications, distinctions, dependencies, and temporal scope.
Use `--extractor-mode none` on `graph-backfill` or `graph-maintenance` when a
scheduled run should exercise filtering/state behavior without generating
candidates; `heuristic` is the default implemented extractor mode.

Inspect the institutional-federation capability baseline with:

```bash
groundrecall inspect .groundrecall/store --institutional-federation
groundrecall inspect .groundrecall/store --institutional-federation-summary
```

The report distinguishes implemented exchange foundations from future
institutional workflows. The coding-model execution plan is in
[`docs/institutional-federation-implementation-roadmap.md`](docs/institutional-federation-implementation-roadmap.md).

Create a bounded federation subscription and exchange signed incremental
change bundles:

```bash
groundrecall changes subscription-create .groundrecall/store .groundrecall/subscriptions/team-alpha.json \
  --subscription-id team-alpha-public \
  --producer-id host-a \
  --scope-id project-alpha \
  --release-ceiling public
groundrecall changes export .groundrecall/store .groundrecall/subscriptions/team-alpha.json exports/team-alpha-change-bundle \
  --signing-key-file federation-signing.key \
  --key-id host-a-2026
groundrecall changes import .groundrecall/store .groundrecall/subscriptions/team-alpha.json exports/team-alpha-change-bundle \
  --key-file federation-signing.pub \
  --key-id host-a-2026 \
  --quarantine-dir .groundrecall/quarantine
groundrecall changes ack .groundrecall/subscriptions/team-alpha.json exports/team-alpha-change-bundle \
  --key-file federation-signing.pub \
  --key-id host-a-2026
```

Imports verify the bundle hash, signature, subscription, producer, and cursor,
then write quarantine records instead of promoting imported content directly.
Acknowledgement advances the receiver-local cursor only after the bundle is
accepted, so scheduled exchange can be retried without duplicating state.

Evaluate multi-party review status and export dissent-preserving feedback:

```bash
groundrecall review quorum .groundrecall/store \
  --subject-type claim \
  --subject-id claim-123 \
  --minimum-approvals 2 \
  --required-role-id scope-steward \
  --independent-from original-author
groundrecall review disagreements .groundrecall/store
groundrecall review feedback-bundle .groundrecall/store exports/feedback.json \
  --origin-instance-id receiver-a \
  --target-instance-id producer-a \
  --key-id receiver-a-2026 \
  --signing-key-file federation-signing.key
```

Review receipts are content-hash scoped. If the reviewed content changes, the
old receipt is reported as invalidated rather than silently reused.

Plan custody handoff, tenancy departure, and instance retirement without
destructive writes:

```bash
groundrecall custody orphans .groundrecall/store
groundrecall custody departure-plan .groundrecall/store \
  --departing-principal-id alice \
  --planned-at 2026-07-29T00:00:00Z
groundrecall custody retirement-plan .groundrecall/store \
  --instance-id host-a \
  --replacement-instance-id host-b \
  --registry-path .groundrecall/federation/trust-registry.json \
  --subscriptions-dir .groundrecall/subscriptions \
  --catalogs-dir .groundrecall/catalogs \
  --quarantine-dir .groundrecall/quarantine \
  --backups-dir .groundrecall/backups
```

These commands produce reviewable plans. They do not revoke keys, delete
records, promote private material to group ownership, or shut down instances.

Generate institutional views with release caps and explicit incomplete-basis
labels:

```bash
groundrecall views orientation .groundrecall/store --scope-id project-alpha --release-cap internal
groundrecall views impact .groundrecall/store --subject-type claim --subject-id claim-123 --release-cap internal
groundrecall views governance .groundrecall/store --release-cap internal --subscriptions-dir .groundrecall/subscriptions
groundrecall views stewardship .groundrecall/store --release-cap internal
```

Stewardship views are based on explicit stewardship records. They suppress raw
activity rankings and inferred familiarity by default.

Build release packs and withdrawal notices:

```bash
groundrecall release pack .groundrecall/store exports/release-pack \
  --target-release-level public \
  --allowed-license-id CC-BY-4.0 \
  --signing-key-file federation-signing.key \
  --key-id release-2026
groundrecall release withdraw exports/withdrawal.json \
  --pack-id release-pack-id \
  --superseded-by-pack-id replacement-pack-id \
  --signing-key-file federation-signing.key \
  --key-id release-2026
```

Release packs hard-gate missing or incompatible licenses, missing attribution,
and unreviewed records before writing a pack.

The MCP server exposes institutional read/report tools for assistant adapters:

- `prior_work_review`
- `catalog_discovery`
- `subscription_status`
- `impact_report`
- `stewardship_orphans`
- `propose_contribution`

The current `groundrecall-mcp` command is a local stdio server. ChatGPT web
requires a remote MCP endpoint, so LAN use needs the authenticated adapter and
private-network deployment described in
[chatgpt-mcp-integration-roadmap.md](docs/chatgpt-mcp-integration-roadmap.md).

The repository now includes a bounded HTTP pilot:

```bash
groundrecall-mcp-http --policy-config /path/to/server-policy.yaml \
  --subject-id alice --bearer-token "$GROUNDRECALL_MCP_TOKEN" \
  --max-response-bytes 1000000
```

Production-like deployments should add `--require-policy`; this makes MCP
requests fail closed if the server-owned policy file disappears or becomes
invalid. Without it, existing local-development behavior is preserved.

Set `--max-concurrent-requests` to bound in-flight MCP work (the default is
16). Saturated requests receive a bounded `429`/`server busy` response and do
not disclose store paths or content.

Use `--request-timeout-seconds` to bound how long the HTTP caller waits for a
dispatch. A timeout returns a bounded 504/`request timed out`; the worker is
not force-killed and retains its concurrency slot until it finishes.

Operators can create a bounded, redacted audit projection with
`groundrecall-mcp-audit-export`. It verifies the source chain, preserves safe
correlation/hash metadata, omits request content, credentials, reasons, and
identities by default, and never deletes the source log.

Codex-side acceptance is explicit and lease-bound through the opt-in
`handoff_accept` MCP method. It requires matching subject, host, project, and
realm plus an active lease and expected `proposed` status; it changes only the
operational handoff record and never executes host work or promotes canonical
memory.

Completed handoffs can receive an append-only governed review through
`handoff_review` (`accept`, `reject`, or `defer`). Reviews require reviewer
subject/project/realm scope, rationale or a result reference, and remain
operational proposals rather than canonical promotion.

After an accepted review, `handoff_promotion_request` can append a scoped
promotion request for downstream review/quarantine. It requires a completed
handoff, accepted review, rationale or result reference, and never mutates
canonical memory itself.

`handoff_promotion_confirm` records an explicit `confirm=true` after a matching
accepted-review promotion request. Its canonical effect is intentionally none:
actual promotion remains a separate governed operation.

`handoff_promotion_apply` consumes a confirmed request into a bounded,
auditable quarantine/action receipt. Its canonical effect is none; an existing
promotion API must separately approve and perform any canonical mutation.

The read-only `handoff_promotion_actions` MCP method lists bounded,
subject/project/realm/release-filtered metadata summaries of quarantined
actions. It omits rationale and protected content and does not mutate state.

An operator may consume a selected quarantined action with
`groundrecall-handoff-promotion-operator` using server-owned policy and
explicit confirmation. This records an operator receipt only; canonical effect
is `none` until a separate governed promotion API is invoked.

`handoff_review_appeal` appends a scoped appeal/correction request against an
existing review event. It requires rationale or an evidence reference and does
not alter handoff status or canonical memory.

`handoff_assignment_request` appends a policy-gated requester/assignee proposal
with project/realm scope and rationale or acceptance context. It is not an
assignment or execution authority.

`handoff_rejection_request` appends a policy-gated, project/realm-scoped
`reject` or `withdraw` request with a rationale or evidence reference. It is an
append-only request: it does not revoke, change handoff status, write canonical
memory, or execute host work; policy and idempotency remain enforced.

`handoff_rejection_resolve` appends a reviewer-scoped `uphold`, `dismiss`, or
`supersede` resolution for an existing request, requiring rationale/evidence
and policy authorization. It is also append-only and does not itself revoke,
change status, write canonical memory, or execute work.

`handoff_start` is the explicit lease-bound accepted-to-executing transition.
It requires an accepted assignment for the lease owner and performs no host
execution itself.

`handoff_block` provides a lease-bound accepted/executing-to-blocked
transition with a required reason or evidence reference; it performs no host
execution or canonical write.
`handoff_unblock` resolves a blocked handoff back to `accepted` with an active
lease, scoped owner, and resolution/evidence reference; it does not execute
work or write canonical memory.

`handoff_assignment_accept` appends assignee acceptance only when it references
an existing assignment request and supplies scoped context; it does not change
handoff status or grant execution authority.

Lease-bound Codex completion is exposed as `handoff_complete`. It requires an
active matching lease, expected `accepted` or `executing` status, and an
outcome or result reference; it only records the operational completion event.

Progress and result proposals are likewise lease-bound when submitted through
MCP: callers must provide the active lease ID, subject, host, project, realm,
and expected status. Legacy direct Python calls can remain unbound only when
explicitly using the compatibility API; the remote MCP surface fails closed.

For boot-time private deployment, use the reviewed systemd template and setup
notes in [`docs/mcp-http-systemd.md`](docs/mcp-http-systemd.md). The template
binds to loopback and is not installed or enabled automatically; a private
tunnel or approved reverse proxy must provide any remote access.

For multiple collaborators, replace the fixed token with a server-owned
identity file (JSON entries contain `token`, `subject_id`, optional `realm_id`,
`maximum_release_level`, and `allowed_tools`):

```bash
groundrecall-mcp-http --policy-config /path/to/server-policy.yaml \
  --identity-file /path/to/mcp-identities.json
```

It exposes read-only tools by default and is intended for a private tunnel or
local testing, not direct public exposure.

The planned cross-assistant lane treats GroundRecall as the shared durable
state substrate for ChatGPT and Codex. Handoffs will be compact,
proposal-only task/plan/progress/result records with stable IDs and references
to governed GroundRecall context; chat transcripts and arbitrary host
execution are not synchronized through the memory layer.

The handoff surface includes proposal/query methods (`handoff_propose`,
`handoff_get`, `handoff_list`, and `handoff_events`) plus policy-gated
operational methods (`handoff_update_status`, `progress_append`, and
`result_propose`). Status changes are constrained to the documented lifecycle,
use expected-state and idempotency checks, and append-only progress/result
events remain outside canonical memory. HTTP exposes the event query by
default; lifecycle write tools require an explicit server allow-list. Codex
claim/discovery automation remains planned work.

The adapter provides bounded `/healthz` and `/readyz` endpoints. `/healthz`
reports liveness without inspecting data. `/readyz` checks the server-owned
policy file and configured `--store-dir`, returning only boolean check results
and HTTP 503 when dependencies are unavailable; it never exposes paths or
store contents.

Handoff status and lease mutations are journaled per record and persisted with
atomic replacement plus fsync. Scoped reads recover an interrupted mutation
idempotently. A malformed recovery journal is intentionally retained for
operator inspection rather than silently discarded.

For fixed-token deployments, `--subject-id` and `--realm-id` are server-owned
identity controls; identity-file entries provide those controls per token.

The adapter bounds both request and response bodies. An oversized MCP result
returns the fixed `response_too_large` error without including any part of the
result; configure `--max-response-bytes` for the deployment's client and
latency budget.

`propose_contribution` returns a draft proposal only; it does not write to the
canonical store. All MCP tools accept optional `policy_config`,
`policy_request`, and `subject_id` arguments so callers can attach policy
findings or block before access.

Run a prior-work review before starting a substantial initiative:

```bash
groundrecall prior-work .groundrecall/store "graph backfill" --scope-id project-alpha
```

Export assistant-neutral data:

```bash
groundrecall export .groundrecall/store .groundrecall/exports/canonical
```

Export assistant-specific data:

```bash
groundrecall assistant-export .groundrecall/store codex .groundrecall/exports/codex
groundrecall assistant-export .groundrecall/store claude_code .groundrecall/exports/claude_code
```

For host startup memory, provide a curated startup profile. The profile adds
selected concept query bundles, repository pointers, standing premises, recent
source-note links, and startup reminders to `STARTUP.md` plus the assistant JSON
bundle:

```bash
groundrecall assistant-export .groundrecall/store codex .groundrecall/exports/codex \
  --startup-profile .groundrecall/startup-profile.yaml
```

Example profile:

```yaml
host:
  host_id: local-dev
canonical_export_dir: .groundrecall/exports/canonical
curated_concepts:
  - GroundRecall
  - Epistemap
  - knowledge graph grounding research premise
active_repos:
  - name: GroundRecall
    path: /home/netuser/bin/GroundRecall
    url: https://github.com/welsberr/GroundRecall
    branch: main
standing_premises:
  - Query GroundRecall before broad repo scans or planning changes.
startup_reminders:
  - Treat Bayesian reliability as assessment metadata, not promotion authority.
recent_note_count: 8
```

Export explicit claim-evaluation results as Epistemap G rows, manifest, and
summary JSON/Markdown:

```bash
groundrecall claim-evaluation-export evaluations.json .groundrecall/exports/g \
  --claims-json claims.jsonl \
  --experiment-id temporal-claim-check \
  --corpus channel-capacity
```

These rows evaluate an explicit learner/model claim-checking run. They are not
derived from GroundRecall review confidence or used as source-truth scores.

Confidence migration/readiness tooling is documented in
[`docs/confidence-migration.md`](docs/confidence-migration.md). Legacy scalar
`confidence_hint` fields remain readable, but typed Epistemap assessments are
generated only when producer method, version, policy, basis, and rationale
metadata are present.

## Assistant-Neutral Host Protocol

GroundRecall can initialize a reusable memory pattern for a project or host:

```bash
groundrecall protocol-init /opt/www \
  --host-id local-dev \
  --host-role development \
  --assistant codex \
  --assistant claude_code
```

This creates:

- `.groundrecall/README.md`
- `.groundrecall/source-notes/host-profile-<host-id>.md`
- `.groundrecall/local-inbox/`
- `.groundrecall/remote-inbox/`
- `ASSISTANT_PROJECT.md`
- assistant bootstrap files such as `CODEX_PROJECT.md` and `CLAUDE.md`

Use `--force` only when you intend to overwrite existing bootstrap files.

For a two-host local/remote setup, each host should maintain its own
GroundRecall store and exchange source notes or exports. Do not make both hosts
write directly into the same mutable store.

For substantial work, update GroundRecall at three points:

- Task definition: objective, scope, paths, targets, verification criteria, and
  constraints.
- Plan or implementation specification: chosen approach, touched files/services,
  checks, rollback notes, risks, and relevant rejected alternatives.
- Results: outcomes, evidence, commands/tests, artifact/log paths, unresolved
  risks, and next safe action.

See [docs/assistant-protocol.md](docs/assistant-protocol.md).

## Suggested Workspace Layout

```text
.groundrecall/
  source-notes/
  imports/
  store/
  exports/
    canonical/
    codex/
    claude_code/
  local-inbox/
  remote-inbox/
```

`source-notes/` is where humans and assistants should leave durable Markdown
notes. Those notes can later be imported and promoted.

## Didactopus Bridge

GroundRecall can export a pack-ready `groundrecall_query_bundle.json` for a
reviewed concept, plus Epistemap graph and Bayesian reliability sidecars:

```bash
groundrecall export /path/to/groundrecall-store /tmp/groundrecall-export \
  --pack-ready-concept channel-capacity
```

The matching Didactopus bridge flow is:

```bash
didactopus doclift-bundle-groundrecall \
  /path/to/groundrecall-store \
  channel-capacity \
  /tmp/doclift-bundle \
  /tmp/didactopus-pack \
  --course-title "Example Course"
```

See [docs/didactopus-bridge.md](docs/didactopus-bridge.md).

## Use Cases

GroundRecall is useful when the same project may be touched by different
assistants, at different times, or on different hosts:

- A local development host and a remote production host both need operational
  memory.
- Codex performs a code change locally, then Claude Code investigates a service
  failure remotely.
- A WordPress or Forgejo service needs routing, backup, deployment, and recovery
  notes that survive across sessions.
- A research corpus needs grounded claims, citations, source provenance, and
  review state.
- Legacy office documents need `doclift` normalization before becoming
  searchable assistant context.

## Safety Rules

- Store where secrets live, not secret values.
- Keep host-specific facts labeled by host and role.
- Treat production and mixed hosts as higher risk than development hosts.
- Prefer source-note/export replication between hosts over shared mutable stores.
- Commit code/config changes separately from generated GroundRecall exports
  unless the export is intentionally part of the deliverable.

## Documentation

- [docs/quickstart.md](docs/quickstart.md)
- [docs/assistant-protocol.md](docs/assistant-protocol.md)
- [docs/architecture.md](docs/architecture.md)
- [docs/didactopus-bridge.md](docs/didactopus-bridge.md)
- [docs/knowledge-graph-roadmap.md](docs/knowledge-graph-roadmap.md)
- [docs/review-backlog-roadmap.md](docs/review-backlog-roadmap.md)
- [docs/llmwiki-import.md](docs/llmwiki-import.md)
- [docs/sync-roadmap.md](docs/sync-roadmap.md)
