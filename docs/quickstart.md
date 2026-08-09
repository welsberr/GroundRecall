# Quickstart

`GroundRecall` is a local-first grounded knowledge substrate for `llmwiki++`-style workflows.

This quickstart assumes a fresh checkout of the standalone repository.

## Install

```bash
pip install -e .
groundrecall --help
```

You can also use the module entry point:

```bash
PYTHONPATH=src python -m groundrecall --help
```

## Import A Knowledge Source

Fast import from an `llmwiki`-style tree:

```bash
groundrecall import /path/to/llmwiki --mode quick
```

More conservative import with stronger grounding expectations:

```bash
groundrecall import /path/to/llmwiki --mode grounded
```

The importer writes normalized artifacts under `imports/<import-id>/`.

Import from a normalized `doclift` bundle:

```bash
groundrecall import /path/to/doclift-bundle --mode quick
```

This path is intended for legacy-document corpora that were first normalized by
`doclift`. If you want a learner-facing pack first, use Didactopus in between:

```bash
doclift convert-dir /path/to/legacy-course /tmp/doclift-bundle --asset-root /path/to/legacy-course
didactopus doclift-bundle /tmp/doclift-bundle /tmp/didactopus-pack --course-title "Example Course"
groundrecall import /tmp/doclift-bundle --mode quick
```

## Review And Promote

Inspect the import outputs:

```bash
groundrecall lint imports/<import-id>
```

For anything non-trivial, open the review bundle before promotion:

```bash
groundrecall review-server imports/<import-id>
```

Promote the imported review artifacts into a canonical store:

```bash
groundrecall promote imports/<import-id> store/
```

Promotion is gated by lint errors. Warnings are retained for review, but errors
must be repaired before promotion unless you explicitly choose to keep the
import as triage material:

```bash
groundrecall promote imports/<import-id> store/ --allow-lint-errors
```

## Query The Canonical Store

Query a concept:

```bash
groundrecall query store/ channel-capacity
```

Inspect the overall store:

```bash
groundrecall inspect store/
```

Review backlog status is a read-only view over source notes, import review
queues, and canonical review candidates. It does not promote or modify records:

```bash
groundrecall review-status .groundrecall
groundrecall review-status .groundrecall --format json --limit 20
```

The JSON contract uses stable hashed workspace/store identifiers and source-path
hashes; local absolute paths are not included. Use `--store`, `--imports-root`,
and `--source-notes-root` when a workspace uses non-default locations.

Reviewer acknowledgement, deferral, and assignment are recorded separately in
`.review/backlog-events.jsonl` as hash-chained operational events. They do not
change canonical review status or promote records:

```bash
groundrecall review-ack .groundrecall BACKLOG_ID --actor reviewer-id
groundrecall review-defer .groundrecall BACKLOG_ID --until 2030-01-01T00:00:00Z --actor reviewer-id
groundrecall review-assign .groundrecall BACKLOG_ID --to teammate-id --actor reviewer-id
```

Framework-neutral dashboard consumers can use the read-only
`groundrecall.review_dashboard.dashboard_digest` and
`dashboard_item_detail` functions. They provide bounded cursor pagination and
policy-filtered totals before pagination; responses contain local-origin
metadata only and do not include absolute paths or content previews.

RB6b supplies a framework-neutral `FixtureFederationReviewSource` for testing
broker tabs. It preserves broker/producer identity, content and version hashes,
release caps, trust/signature status, quarantine/revocation/supersession, and
freshness metadata. It is read-only and never imports or promotes remote data.

## Export

Export assistant-neutral artifacts:

```bash
groundrecall export store/ exports/groundrecall --concept channel-capacity
```

Export a pack-ready `groundrecall_query_bundle.json` for `Didactopus`:

```bash
groundrecall export store/ exports/groundrecall --pack-ready-concept channel-capacity
```

That pack-ready export also writes `epistemap_graph.json` and
`bayesian_reliability.md` when graph assessment context is available.

Export assistant-targeted bundles:

```bash
groundrecall assistant-export store/ codex exports/codex --concept channel-capacity
groundrecall assistant-export store/ claude_code exports/claude --concept channel-capacity
```

## Bridge To Didactopus

If you want a `Didactopus` learner pack that carries reviewed GroundRecall
concept context, the shortest bridge flow is:

```bash
doclift convert-dir /path/to/legacy-course /tmp/doclift-bundle --asset-root /path/to/legacy-course
didactopus doclift-bundle-groundrecall \
  store/ \
  channel-capacity \
  /tmp/doclift-bundle \
  /tmp/didactopus-pack \
  --course-title "Example Course"
```

That command:

- exports a pack-ready `groundrecall_query_bundle.json` from `GroundRecall`
- feeds it into the `Didactopus` `doclift` bundle flow
- writes a pack with the GroundRecall query bundle included as a declared
  supporting artifact

## Default Working Layout

A simple local layout is:

```text
.groundrecall/
  imports/
  store/
  exports/
  events/
```

The current alpha does not require this exact layout, but it is a sensible starting point.

## Initialize Assistant Memory

For site, app, service, or deployment work, initialize the assistant-neutral
GroundRecall protocol:

```bash
groundrecall protocol-init /opt/www \
  --host-id local-dev \
  --host-role development \
  --assistant codex \
  --assistant claude_code
```

This writes a host profile, GroundRecall workspace README, assistant bootstrap
files, and local/remote inbox directories. See
[assistant-protocol.md](assistant-protocol.md).

RB6c consumers can compose local `dashboard_digest` output with a
`FederationReviewSource` through `combined_dashboard_digest`. The combined
contract keeps local and broker origins, counts, cursors, and action paths
separate; broker outages leave the local page usable. Remote items are filtered
by release and policy before counts or pagination.

Reminder evaluation is deterministic and separate from canonical review state:

```bash
groundrecall review-remind .groundrecall --config reminder-policy.yaml --dry-run
groundrecall review-remind .groundrecall --config reminder-policy.yaml --deliver --adapter file
```

Dry runs do not write the ledger. Delivery writes a metadata-only digest and
appends `reminder_emitted` only after successful delivery; failures append a
`reminder_failed` event. Quiet hours, urgent bypass, unchanged-digest
suppression, and daily rate limits are policy-controlled.

MCP clients may call `review_backlog` and `review_backlog_item` for bounded,
policy-filtered metadata views, or `acknowledge_review_reminder`,
`defer_review_reminder`, and `assign_review_item` for interaction-ledger state.
These tools never accept evidence, promote records, adjudicate contradictions,
export, or federate content; writes are limited to operational ledger events.

Federated broker actions are a separate fixture/API contract. Acknowledge,
assign, and request-import operations carry correlation and idempotency keys,
verify trust/signature/freshness/release state, and return explicit broker-origin
results. Request-import creates only a quarantine proposal; it never promotes
into the canonical store.

RB6e provides `save_snapshot_cache`, `load_snapshot_cache`, and
`CachedFederationReviewSource` for bounded offline operation. Cache files are
atomically replaced, content-hashed, size-bounded, and explicitly marked
`fresh`, `stale`, `invalid`, or `missing`; stale cache data is never reported as
fresh and cache paths are excluded from dashboard payloads.

Backlog views also support policy-safe filters before counts and pagination:

```bash
groundrecall review-status .groundrecall --scope-id project-a --owner alice \
  --overdue --status triaged --triage-lane relation_review
```

Use `--due-before TIMESTAMP` for an explicit UTC/ISO deadline; malformed
timestamps are reported as diagnostics rather than silently broadening access.

Reminder interactions maintain a rebuildable `.review/backlog-reminder-state.json`
cache. It is content-hashed and atomically replaced; corruption falls back to
ledger replay, and resolved or missing backlog IDs are reconciled out. The
append-only interaction ledger remains the source of truth.

`stewardship_dashboard.stewardship_digest` provides a read-only team view of
pending contributions, feedback, orphaned scopes, and stewardship obligations.
It separates local/remote origin, applies release and policy filtering before
counts and cursors, and reports only aggregate health metadata.

Use the synthetic benchmark for local regression checks:

```bash
PYTHONPATH=src .venv/bin/python -m groundrecall review-benchmark --items 1000 --page-size 50 --repetitions 5
```

Its JSON report is metadata-only and explicitly warns that timings depend on
host/cache conditions; values are not publication claims or cross-system
comparisons.

For cron, use the repository's explicit virtual environment and an absolute
working directory rather than relying on interactive shell activation:

```cron
17 * * * * cd /path/to/GroundRecall && PYTHONPATH=src /path/to/GroundRecall/.venv/bin/python -m groundrecall graph-maintenance /path/to/workspace/store --profile support --limit 10 --apply
27 8 * * 1-5 cd /path/to/GroundRecall && PYTHONPATH=src /path/to/GroundRecall/.venv/bin/python -m groundrecall review-remind /path/to/workspace --config /path/to/reminder-policy.yaml --deliver --adapter file
```

## Next Reading

- [architecture.md](architecture.md)
- [assistant-protocol.md](assistant-protocol.md)
- [didactopus-bridge.md](didactopus-bridge.md)
- [llmwiki-import.md](llmwiki-import.md)
- [sync-roadmap.md](sync-roadmap.md)
