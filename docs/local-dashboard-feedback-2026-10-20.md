# Local dashboard feedback and proposed sequence

Date: 2026-10-20
Status: implementation in progress; security, release-ceiling, graph discovery,
and read-only review inspection slices are implemented.

## Implementation status (2026-10-20)

Completed in the local dashboard implementation:

- Explicit method rejection uses guarded 405 responses with `Allow: GET`; only
  the capability-token bootstrap remains a POST route.
- `--maximum-release-level` is enforced during canonical reads, search,
  association expansion, graph and backlog projections, and before API payload
  serialization. Missing release metadata is treated as private and therefore
  hidden by lower ceilings; malformed explicit labels fail closed.
- Capped search responses use current canonical text, not stale index snippets;
  dependency cycles cannot cache provisional visibility. Capped aggregate views
  rescan release state and do not reveal skipped-file diagnostics or excluded
  backlog counts.
- Overview and graph labels identify the active ceiling; search, record and
  maintenance pages show it in-page. Empty search says no matches were returned
  in the current view.
- Graph exploration now has coordinated concept/relationship tables, lifecycle
  and edge filters, endpoint-first relationship views, neighborhood labels,
  direct endpoint selection, and URL/history state. Relation assessment
  dimensions display confidence and source reliability separately; missing
  assessments remain explicit.
- Maintenance filters apply before pagination. “Open review” resolves current
  backlog IDs to bounded read-only candidate metadata and associated records;
  imports are checked within configured roots, and stale or release-excluded IDs
  share an unavailable state. No review decision or promotion is made.
- Overview includes a dated dashboard change entry and three CLI command cards.
  Tests confirm each template maps to the installed top-level command and its
  argument parser; buttons copy templates and never execute them. Effects are
  stated per command: application search may create a missing derived index,
  while queue status and confidence readiness are read-only.
- The graph page can download its current bounded, release-filtered view as a
  self-contained static HTML presentation with capture time and filter/bound
  disclosure. The snapshot has no live refresh.

Targeted verification includes dashboard/application/store/search/backlog tests
and 8 loopback HTTP security tests run outside the socket-restricted sandbox.
Browser visual QA is still outstanding. Configurable saved views, broader
substrate telemetry, broader workspace snapshot export, and governed review/
promotion actions remain future work.

This document maps the proposed dashboard improvements to the current local
dashboard implementation and suggests an order that keeps security and truthful
measurement ahead of presentation features.

## Current baseline

The dashboard already binds to IPv4 loopback, uses a per-process access secret
exchanged for an HttpOnly/SameSite cookie, checks Host/Origin and Fetch Metadata,
and emits a Content-Security-Policy. The bootstrap is the sole intended POST
route; the dashboard data and application routes are read-only. Existing
overview widgets show canonical record/storage size, filesystem capacity, index
presence/size, skipped inventory files, and successful search latency measured
within this dashboard process. Assistant sessions, token use, and costs are
explicitly unknown without an adapter. Graph browsing has search, bounded
node-link and table views, lifecycle/edge filters, focus/history, and separate
relation assessment dimensions. Maintenance supports filtered pagination and a
read-only inspector for canonical, import and source-note items.

Confidence assessment and Bayesian reliability infrastructure exist elsewhere
in GroundRecall/Epistemap. The dashboard displays assessments attached to
visible relations, keeps confidence and source reliability separate, and does
not calculate scores or treat them as promotion authority.

## Recommendations

### 1. Close HTTP method and data-ceiling gaps first

Keep the dashboard loopback-only and retain the current capability-token
authentication and CSP. Add explicit handlers for unsupported methods so PUT,
PATCH, DELETE, OPTIONS, HEAD and arbitrary methods consistently return a small
405 response with an `Allow` header; preserve only the narrowly scoped POST
bootstrap. Test the method matrix with and without a valid cookie and verify
that no unsupported request reaches the application dispatcher. Confirm
loopback binding, Host/Origin rejection, cookie flags and CSP directives in
real HTTP tests.

Add an explicit maximum release level for dashboard reads. Apply it while
loading records and building search, graph, maintenance, overview and record
projections, then run a final response-payload check before serialization. The
payload check is defense in depth: reject or redact any record that exceeds the
configured ceiling. Treat absent release metadata as private and malformed
explicit metadata as ineligible. Aggregate counts, edge counts, labels and error messages must not
reveal the existence or identity of filtered records. Add tests with mixed
release levels for every route, including nested associations and malformed
metadata. A caller-supplied query or presentation preset must never raise the
server's configured ceiling.

### 2. Show confidence and reliability as different evidence

Add separate fields and visual treatments to a trust/evidence map:

- **Confidence** describes an assessment of a claim or proposition, with its
  method, basis records, scope, time, rationale and uncertainty.
- **Reliability** describes evidence about a source, method, or process, with
  the observations and prior/profile supporting that estimate.

Do not derive one from the other, collapse either into a single trust score, or
use either as promotion authority. Show the value together with its method and
coverage; display “not assessed” when it is absent. Where Epistemap emits both a
heuristic reliability summary and a Bayesian posterior, label them separately.

### 3. Improve graph exploration around tasks and context

Keep the graph as one coordinated view, not the only way to browse. Offer a
searchable node/edge table alongside the visualization, selectable filters for
node type, relation type, source and lifecycle state, and click-to-expand
neighborhoods with a visible node/edge budget. Preserve focus and filters in a
shareable local view configuration; support Back/Forward navigation. On
selection, provide a compact knowledge card with summary, provenance,
confidence, reliability, current review state and links to source/evidence.
Avoid force-layout motion that changes meaning, and use semantic/type-aware
grouping only when the layout basis is explained. Keep direction, rejected and
superseded states legible without color alone.

These patterns are grounded in graph-exploration work rather than a claim that
one layout is universally best. KGBrowser uses reusable domain-specific view
configurations to expose simple node-detail and expansion operations while
hiding irrelevant complexity. KGEV combines search and filters over labels,
edge types, evidence sources and relationship confidence, and pairs a graph view
with a sortable list/table. A graph-exploration study reports requests for
overview/detail and focus/context, zooming, property search and navigation
history. For GroundRecall, implement these as low-risk browsing features before
any graph mutation controls.

### 4. Make views and scopes configurable without weakening policy

Support saved view presets for the user's ordinary work: selected scope,
release ceiling, node/edge filters, default landing page, and visible widgets.
Store presets as local UI configuration, separate from canonical knowledge.
Every route must reapply authenticated server-side scope and release policy;
view configuration only narrows the visible set and cannot grant access.
Distinguish “no matching records” from “records excluded by scope” only where
that disclosure is allowed.

### 5. Build truthful health and “what's new” widgets

Keep existing storage and retrieval measurements, then add substrate health
where sources are available: index age/freshness checks, latest successful and
failed operation times, queue age, skipped/malformed record counts, and telemetry
coverage. Each metric should include its source, measured-at time, coverage and
unknown state. Do not call storage “healthy” merely because files can be
counted, or infer model spend from session length.

The “What's new” panel should use explicit release notes, dashboard changelog
entries, or dated operational events with provenance. Do not infer product
changes from file modification times. Make viewed/unviewed state local and
reversible, and keep sensitive event details behind the same scope checks.

### 6. Add safe “Ask” shortcuts

Provide curated command cards for frequent tasks such as search, inspect a
record, show a review queue, check index status, and open relevant help. Source
the catalog from command metadata that is tested against the installed CLI
parser/help output. Render commands as parameterized text for copy, not
interpolated shell strings. Show whether a command is read-only, writes local
operational state, or changes canonical knowledge; require the CLI's normal
confirmation and policy gates for the latter. The first increment should
prepare/copy commands and never execute arbitrary shell input.

### 7. Add static export and presentation mode last

Create an explicit snapshot export with a named scope and release ceiling,
visible provenance, generation time, and an export manifest. Validate the
ceiling both when selecting records and over the final serialized payload. Avoid
exporting access tokens, host paths, private session telemetry or records above
the selected cap. Presentation mode should consume that snapshot, offer a clean
read-only layout, and disclose when data was captured; it should not silently
refresh from the live store or mutate canonical knowledge. Test exports with
mixed release levels, linked records, missing metadata and adversarial strings.

## Suggested delivery order

1. Explicit HTTP method policy and route/auth regression tests.
2. Configurable release ceiling enforced during reads and at the response
   boundary, with mixed-level route tests.
3. Graph/search usability slice: table + node-link views, lifecycle/edge filters,
   bounded expansion, history, and knowledge cards. (Implemented; browser QA pending.)
4. Separate confidence/reliability display, preserving dimensions and method.
   (Implemented for assessments attached to visible relations.)
5. Read-only review queue pagination and item inspection. (Implemented; richer
   import/wiki handoff and governed decisions remain future work.)
6. Saved local view presets, with policy ceilings immutable to the browser.
7. Substrate health and release-note-based “What's new” widgets. (A dated local
   dashboard change entry is implemented; broader release notes and viewed state remain.)
8. Curated, parser-checked “Ask” command cards. (Three command templates implemented with per-command effect labels.)
9. Capped static export and snapshot-based presentation mode. (A bounded graph
   snapshot presentation is implemented; broader dashboard/store export remains.)

## Sources on graph exploration

- Nečaský and Stenchlák, [Interactive and iterative visual exploration of
  knowledge graphs based on shareable and reusable visual
  configurations](https://doi.org/10.1016/j.websem.2022.100713), *Journal of Web
  Semantics* (2022).
- [KGEV: Knowledge Graph Exploration and
  Visualization](https://pmc.ncbi.nlm.nih.gov/articles/PMC9161770/), including
  node/edge/source/confidence filters and linked graph/list views.
- [Dynamic graph exploration by interactively linked node-link diagrams and
  matrix visualizations](https://link.springer.com/article/10.1186/s42492-021-00088-8),
  reporting user requests for focus/context, overview/detail, search and history
  controls.
