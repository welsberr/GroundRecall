# Local dashboard and shared-broker interface roadmap

The first milestone is an authenticated, owner-local browsing dashboard. It uses
GroundRecall's existing application search/record service, review backlog, and
Epistemap graph adapter. It does not change canonical knowledge. No changes to
the Epistemap library are needed for this increment.

## Run locally

From the GroundRecall checkout, with its Python dependencies installed:

```bash
PYTHONPATH=src python3 -m groundrecall.local_dashboard \
  /home/netuser/.groundrecall/store \
  --workspace /home/netuser/.groundrecall \
  --port 18767
```

Open the access link printed by the command. Keep that link private. It exchanges
a per-process secret in the URL fragment for an HttpOnly, SameSite=Strict cookie,
then clears the fragment. Stop with Ctrl-C; restarting invalidates existing
access. The server binds only to `127.0.0.1`. There is no external hosting, remote
model request, automatic browser launch, or persistent credential file. Use
`--port 0` to choose an available port automatically.

To limit the records visible in the local dashboard, pass
`--maximum-release-level public|internal|confidential|privileged|private`.
The default is `private`. Records with missing release metadata are treated as
`private`, so they are hidden by every lower ceiling. Malformed explicit labels
fail closed. The ceiling is enforced in canonical reads and again at response
projection.

The operator chooses the store at startup; browser callers cannot select paths.
If supplied, the workspace manifest must agree with that store. Custom import
and source-note locations in the manifest are respected. Without `--workspace`,
the maintenance page explains that it cannot inventory those queues.

This interface gives the local owner access to the configured store. It is not a
multi-user policy boundary and must not be exposed through a public reverse proxy.
Host and Origin checks reject off-origin requests. All pages and APIs require
an authenticated session, apart from the minimal access-link bootstrap.

## Available now

| Page | Behavior and limits |
| --- | --- |
| Overview | At the full private ceiling, quickly counts JSON record files and their on-disk bytes from filesystem metadata; it does not parse or validate each record. Lower ceilings parse records and apply release/dependency checks before counting. Reports filesystem free/capacity and search-index presence/size. Capped views label suppressed inventory diagnostics as undisclosed. These are inventory measurements, not integrity verification. |
| Assistant activity | Explicit unavailable state for open sessions, agents, assistant availability, context, processed tokens and spending. No process scraping or inferred zero counts. |
| Retrieval | Index presence, size and file age (private ceiling only), plus median and maximum duration of successful searches through this dashboard process, retaining the latest 200 samples. File age is not an index freshness check; this does not measure MCP traffic or retrieval quality. |
| Knowledge graph | Concept title/alias/summary search; lifecycle, relation-state and relation-type filters; coordinated concept/relationship tables; node summaries and review state; directed edges; pan/zoom; selected-node neighborhood focus; URL-backed filters, table, selection and browser history; links to visible concept, relation and associated artifact records; download of a self-contained, static HTML snapshot of the current bounded view. Relationship filters prioritize their endpoints before the 60-node bound. Totals and diagnostics describe the configured ceiling. |
| Maintenance | Existing workspace backlog, filtered by the configured ceiling at both candidate and target. Priority, origin, status and lane filters apply before pagination; all matching items are reachable in pages of 100. “Open review” resolves the current `backlog_id` and shows a bounded read-only candidate metadata and related-record preview for canonical candidates, imports and source notes. Missing, stale and excluded IDs return the same unavailable response. No review decisions or promotions are performed. |
| Search and records | Existing application pages with dashboard navigation and the active release ceiling shown in-page. Capped search results are rechecked against current canonical text to prevent stale index snippets from crossing a reclassification. Missing search indexes produce an explicit unavailable page instead of intentionally initiating an index build. |
| What's new and Ask | A dated local dashboard change entry and three parser-checked CLI command templates for application search, review status and confidence readiness. Copy only; the dashboard does not execute commands. The search command may build a missing index, while the other two are read-only. |

Graph responses show at most 60 nodes and 300 edges, with explicit truncation.
Relationship filters start from matching edges and include their endpoints
before applying the node bound. Neighborhood focus searches all projected
concept edges, not just the currently visible subset. The layout is for
browsing: spatial position and edge counts do
not encode confidence or truth. Associated artifact pages are metadata records;
this milestone does not read arbitrary source paths or render a separate wiki.
Malformed/symlink graph files are skipped and counted only in the unrestricted
private view; capped views suppress that diagnostic. Historical relation states
remain visible and can be inspected through relation record pages.

Unrestricted private inventory, graph and backlog projections cache for 30
seconds. Capped views rescan canonical release state on each request so recent
reclassification does not remain visible through a stale aggregate. Refresh
requests the latest available projection. The first backlog request scans the
configured workspace and may take several seconds for a large queue. Page links
resolve IDs against a fresh release-safe backlog projection; opening an item
creates no review bundle and changes no source or canonical files. An item can
become unavailable if it changes after the queue snapshot. Incremental queue
refresh is subsequent work.

## Next milestone: evidence-rich review handoff

1. Strengthen source-specific import evidence previews and safe source/wiki
   navigation constrained to configured roots. Distinguish unavailable or deleted
   evidence from empty records.
2. Add a parser-checked, source-specific next-step handoff and operation preview
   before governed decision/promotion controls. Show exactly which records will change and preserve reviewer, provenance, rationale and receipts. Acknowledgement is not acceptance.
3. Add review decisions and promotion previews through the existing policy and
   review services. Show exactly which records will change and preserve reviewer,
   provenance, rationale and receipts. Acknowledgement is not acceptance.
4. Support proposed edge additions, replacements and removals with evidence and
   rationale. Preserve historical edges; show active versus superseded relations.
   Use revision checks, coordinated writes, idempotency and conflicts before
   exposing canonical mutation buttons.
5. Test concurrent edits, stale browser state, denied actions, recovery after
   interruption, and canonical evidence preservation. Keep all mutations behind
   authenticated, same-origin POST requests.

## Session telemetry and efficiency advice

Follow [session context and cost](session-context-and-cost-roadmap.md), particularly
SC-0 through SC-3, rather than treating this dashboard as a session registry.
Introduce a portable runtime-adapter contract and private session observations:

- Stable session/agent identity, ownership, heartbeat, lifecycle state and the
  time of the latest observation. Disconnected, stale, closed and active are
  distinct states; an absent heartbeat alone does not prove closure.
- Model identity, context capacity/occupancy, processed and cached tokens, usage
  provenance and measurement windows. Keep estimates separate from measured
  values, and subscription consumption separate from monetary API billing.
- Assistant capability discovery; unsupported measurements/actions stay unknown.
  Never derive billing from conversation length alone.
- Task-sensitive model advice and checkpoint/compaction/restart suggestions with
  their basis, uncertainty and recovery cost. Session actions require a verified
  host integration and preserved operational checkpoint.

The dashboard can consume these observations without changing graph knowledge
or silently exporting private telemetry to a broker.

## Shared knowledge broker app

Build a separate deployment using the same transport-neutral service contracts,
with authenticated principal and policy enforcement on every backend operation.
The local owner's unrestricted store view is not suitable as a team API.

| Interface | Intended responsibility |
| --- | --- |
| User | Personal activity, authorized knowledge search, contribution proposals, review assignments and provenance. |
| Team | Scoped graph/wiki browsing, contribution and review queues, stewardship, conflicts and authorized aggregate operational status. |
| Admin | Identity-provider integration, membership and role administration, policy, storage/index health, federation/subscription status and audit operations. |

Authentication, server-enforced roles and scopes, session expiry/revocation,
CSRF protections, audit receipts, and tests for cross-user/team isolation precede
shared deployment. Aggregate counts and graph neighborhoods need authorization
filtering too; hiding a navigation tab is insufficient. Reuse existing broker
policy and federation contracts rather than introducing a second authority model.

## Verification

`tests/test_local_dashboard.py` covers real loopback authentication, origin/Host
checks, denied mutation routes, record traversal, escaped content, unknown
telemetry, graph neighborhoods and bounds, malformed records, workspace mismatch,
and unchanged canonical files during browsing. Socket tests require execution
outside a sandbox that prohibits loopback sockets.

Browser visual and interaction QA remains required before calling this milestone
release-ready. The current development environment had no connected browser;
Python/HTTP tests and JavaScript syntax checks do not establish visual quality.

## Three-role QA review (2026-10-17)

A checker exercised routes, authentication and read-only behavior; a knowledge
worker inspected graph/search/queue behavior against the local store; a planner
mapped missing workflows to existing services. Fixture tests used temporary
stores. Live-store checks were read-only. No connected browser was available,
so pointer interactions, responsive layout and visual accessibility remain
unverified.

### Defects addressed

- The search form submitted to `/`, which the dashboard reserves for Overview.
  The form and search navigation now use `/search`; the regression follows the
  rendered form action rather than only testing a manually constructed URL.
- Removing an index between the dashboard's preflight and retrieval could cause
  an automatic rebuild. Application read-only mode now disables index building
  in the search layer and opens SQLite with `mode=ro`. Tests remove the index
  both before dispatch and immediately before SQLite opens it; both return an
  unavailable response and do not recreate the index.
- Cookies are now named per port so different local dashboard instances do not
  overwrite each other's authenticated sessions.
- Record associations now link to supported claim, observation, concept and
  other record pages. These links still lead to bounded record projections,
  not a complete wiki reader.
- Graph relationship details show state and incoming/outgoing direction.
  Rejected/superseded relationships have dashed lines. Graph query and focus are
  stored in the URL and reused on refresh. Historical relations remain included;
  a state filter is still needed.

### Remaining priorities from the knowledge-worker and planner reviews

The inspected store contained 662 concepts and 401 concept edges, including 52
rejected edges. Of the concepts, 587 had no concept edges; all 662 had the same
import placeholder description. These are data-quality findings, not graph
navigation failures. Enrichment needs its own governed review workflow; the UI
must not invent summaries or inferred relationships to conceal missing data.

The backlog contained 91,569 pending items. The first 100 were import candidates
and none had a detail link. This makes the current queue an inventory, not yet a
usable review workspace. Prioritize:

1. **Open review / inspect item:** resolve `backlog_id` against configured roots
   and show candidate text, evidence, findings, rationale and a specific next
   action. Source notes need inspect/import; imports need candidate review;
   canonical candidates need their existing evidence and review state. Viewing
   must create no bundles or other files. Missing evidence is an explicit state.
2. **Queue filters and pagination:** expose existing backlog priority, status
   and lane filters; make every result reachable and preserve position when
   returning from an item. Show snapshot time and cache age.
3. **Review handoff:** offer a bound, source-specific operation preview before
   governed decision/promotion controls. A useful launch button can open an
   inspector or prepare a handoff without accepting evidence. Acknowledgement
   and deferral are distinct later actions, not approval.
4. **Evidence/wiki reading and graph state filters:** add safe source previews,
   useful labels and counts, and an explicit historical-edge toggle. Improve
   concept summaries separately with provenance and review.

Do not launch the existing `review_server.py` unchanged from a queue button.
Its current HTTP routes lack dashboard authentication, allow wildcard CORS and
accept caller-selected promotion targets. Loading its review workspace may
create/update review bundles. Reuse and harden the underlying projection and
review services inside the dashboard's authenticated boundary instead.

### Telemetry implementation sequence

CLI and MCP hooks are an approachable first increment. The relevant integration
points are `cli.main`, `mcp.handle_request`, and `MCPHTTPApplication.dispatch`.
The HTTP MCP audit log already records event/correlation identifiers, principal,
tool and outcome; it does not establish assistant session identity or duration.

1. Add a shared private operational event sink and dispatch instrumentation for
   operation name, timestamp, duration, outcome, result count when available,
   transport, and opaque correlation identifiers. Cover failures and denied
   requests as well as successes. Avoid counting the same request twice as it
   passes through HTTP and common MCP dispatch. Do not record raw prompts,
   queries, tool arguments or credentials by default.
2. Persist bounded operational aggregates for dashboard activity, latency and
   error reports across CLI/MCP/dashboard processes. Respect configured private
   runtime roots and retention; metrics are not canonical knowledge. Failure of
   optional telemetry must not change tool outcomes or corrupt MCP stdout.
3. Add explicit session/agent registration, parent relationships, heartbeat and
   end events. Label coverage and stale observations. MCP connection count and
   recent tool calls are not counts of open assistant conversations.
4. Ingest model/context/token/cost observations from supported runtime/provider
   adapters. Preserve unknown measurements, cumulative-counter semantics,
   source event IDs, cache categories, context epochs and estimation provenance.
   Deduplicate retries and parent/child usage; do not equate paid API estimates
   with subscription quota consumption.

This allows GroundRecall activity telemetry to ship before model-specific usage
adapters. Model-selection and restart advice should only become personalized
once the required observations and checkpoint integration exist.

After the fixes, the checker independently passed 33 dashboard, application and
search regression tests, including real HTTP checks outside the socket-blocking
sandbox. The knowledge worker followed two claim links and two observation links
against the live store, all successfully. Remaining graph interaction limitations
include no Back-history between neighborhoods (`replaceState`), selection without
focus not persisting, and zoom recentering after pan. None has had browser visual
verification yet.
