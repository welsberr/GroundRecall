# Application Integration Roadmap

Status: active implementation plan. Evidence checked 2026-09-04; broker track
made the current priority on 2026-09-19.

## Current Priority: Containerized Federation Broker

Implement FB-0 through FB-4 before resuming the lower-priority Kagi and general
application-integration sequence below. The first release is an authenticated
broker for signed catalog discovery and incremental bundle exchange between
independent GroundRecall instances, initially a two-participant pilot. Deliver
one non-root OCI image, a Docker Compose reference deployment, and documented
Podman compatibility using the same image. Keep canonical acceptance and
promotion receiver-local.

The detailed delivery sequence is in the
[`institutional-federation-implementation-roadmap.md`](institutional-federation-implementation-roadmap.md)
and the v1 exchange contract is in
[`federation-broker-v1-contract.md`](federation-broker-v1-contract.md). The
review backlog's future broker dashboard consumes the deployed broker after
the exchange service is established; see
[`review-backlog-roadmap.md`](review-backlog-roadmap.md).

Implementation status (2026-09-20): FB-0 through FB-4 are implemented in this
working tree. Broker contract/service/client tests pass, the Compose image has
been built and smoke-tested, and the synthetic two-participant HTTP pilot
covers both exchange directions, quarantine-before-ack, key rotation, service
restart, and SQLite restore. Run it with
`PYTHONPATH=src python -m groundrecall.federation_broker_pilot`; see
[`federation-broker-synthetic-pilot.md`](federation-broker-synthetic-pilot.md).
The local Compose broker is healthy at `127.0.0.1:18765`. Its ignored,
owner-only secret directory now contains an operator token and two participant
tokens; the disposable `compose-smoke` identity was revoked. These participants
are not enrolled and have no approved realm/scope grants yet. The broker remains
loopback-only; remote access and local producer-key enrollment are pending.
Port 8765 is occupied by unrelated software on this host. Podman is not
installed here, so only Docker Compose has been runtime-validated. Current apt
metadata offers Podman, but installing it requires privileged package changes;
the noninteractive setup has no sudo password, so Podman validation is blocked
pending host administrator approval.

### FB-0: Exchange contract and trust model

Define versioned capabilities, enrollment, catalog, subscription, change
bundle, acknowledgement, and revocation operations. Keep participant login
identity separate from producer signing identity. Require independent
enrollment approval with realm, scope, release, restriction, and key bounds.

### FB-1: Persistent exchange service

Implement authenticated, bounded catalog publication/discovery and signed
bundle submission, retrieval, and acknowledgement over persistent broker
storage. Enforce both producer and receiver grants, verify publisher signatures
and content hashes, make retries idempotent, and retain an auditable origin.
The broker transports signed material; each receiving GroundRecall instance
verifies and quarantines it for local review.

### FB-2: Container deployment

Build a non-root OCI image with persistent storage, externally mounted secrets,
health and readiness checks, bounded logs, backup/restore, upgrades, and
rollback instructions. Provide a Docker Compose reference and validate the same
image with Podman. Bind to loopback behind an approved private tunnel by
default; do not publish a personal corpus automatically.

### FB-3: GroundRecall clients and onboarding

Provide CLI enrollment, catalog publication/discovery, subscription creation,
bundle publish/pull/ack, key rotation, and local quarantine handoff. Include a
reproducible two-participant example with synthetic keys and data.

### FB-4: Two-participant pilot

Run an isolated broker instance, enroll two producers, and demonstrate signed
knowledge exchange in both directions. Verify that revoked keys, unauthorized
scope/release requests, tampering, duplicate delivery, service restart, and
restore behave safely. Diane's real signing key and network enrollment are
required only to onboard the live pilot, not to build or test the service.

### Cross-cutting: Safe capability updates

Do not couple software installation with mutation of canonical memory. Package
or container upgrades use their deployment mechanism; canonical stores remain
on durable storage outside replaceable image layers. Store/schema migrations
use `groundrecall update`: read-only compatibility planning by default, an
explicit apply after an operator-confirmed maintenance window, a verified
non-overwriting backup, record validation, and backup-verified rollback.
Reject future or malformed store-format markers and preserve unknown additive
record fields across read/write cycles. Keep indexes as rebuildable projections
and refresh them separately.

The first implementation adds a format marker without rewriting graph or
record data. Later capabilities that need data changes must register an
idempotent, versioned migration with graph-preservation/semantic checks,
failure-injection tests, and a tested rollback path before it is enabled. This
update lifecycle is a prerequisite for release packaging; it does not make
GroundRecall self-download or self-install software.

GroundRecall should expose durable knowledge through ordinary search, links,
structured APIs, capture forms, and change notifications. A person should be
able to use it from a browser, search engine, editor, or dashboard without
starting a conversation or invoking a language model.

The first release should let a user search GroundRecall in a browser, open a
record with its sources and review state, and return to that record through a
stable link. Kagi is the first search integration; a small command-line client
is the second consumer, proving that the interface serves conventional software.

## Existing foundation and dependencies

Inspection covered checkout `68ef574` plus its existing uncommitted changes.
These observations describe the working tree, not a released API guarantee.

| Observed foundation | Implementation implication |
| --- | --- |
| Canonical records, provenance, review/promotion, and snapshots in the [project overview](../README.md) | Reuse the knowledge lifecycle and stable identities. |
| Scoped lexical search in [search_index.py](../src/groundrecall/search_index.py) and concept/graph bundles in [query.py](../src/groundrecall/query.py) | Build a shared application service over existing retrieval. |
| HTTP MCP adapter with `/mcp`, `/healthz`, server-owned identities, policy checks, and bounded requests in [mcp_http.py](../src/groundrecall/mcp_http.py) | Reuse enforcement concepts; add a documented application API and human interface. |
| Low-level search returns filesystem paths, snippets, metadata, and index location; it can build a missing index during a request | Introduce an explicit response allowlist and move index maintenance out of interactive requests. |
| [Unified retrieval roadmap](unified-prior-work-retrieval-roadmap.md) records UPR-0 as open, with R0-A through R0-C complete | Reconcile authority before deploying a unified production search interface. |

GroundRecall's prior-work tool responded during this review. A bounded Kagi
query returned no candidates; this is a search result, not proof that no prior
integration exists. The user unit `groundrecall-mcp-http.service` reported
inactive. Other service names and hosts were not audited, so deployment
readiness remains unverified.

This plan complements the [memory lifecycle roadmap](memory-lifecycle-roadmap.md)
and [search responsiveness work](search-responsiveness.md). It does not replace
their authority, reconciliation, or retrieval-quality requirements. The existing
UPR-0 merge restriction remains in force for dependent retrieval work. Contract
design, fixtures, and interface mockups can be prepared while that gate is open.

## What Kagi integration means

There are several useful integration levels with different data flows.

| Integration | User outcome | Dependency and boundary |
| --- | --- | --- |
| Custom Bang | Enter `!gr query` and open GroundRecall's search page | Requires a browser-reachable GroundRecall UI and authenticated session. This is navigation, not embedded Kagi results. |
| Browser companion | Search local knowledge in a side panel while browsing Kagi or another site; explicitly save a page | Requires an extension and bounded permissions; private results stay in the extension-owned interface. |
| Optional web search | See GroundRecall records and Kagi web results in the GroundRecall UI | Requires Kagi API access, budget controls, and explicit external-query behavior. |
| Public Lens | Search a deliberately published GroundRecall collection through Kagi | Requires publicly reachable, indexed pages; publication is a separate workstream. |

Kagi documents custom search shortcuts in its [Bangs documentation](https://help.kagi.com/kagi/features/bangs.html).
Prototype a full-query redirect template against the running UI and test spaces,
Unicode, punctuation, and existing query parameters. Do not put credentials in
the template. The query entered into Kagi is visible to Kagi; users who need
local-only queries should use the GroundRecall page or a direct browser shortcut.

Kagi's [Search API documentation](https://help.kagi.com/kagi/api/search.html)
currently describes programmable search using `/api/v1/search` and account
personalization. Its full API reference could not be retrieved in this review.
Verify access, current limits, pricing, response schema, and caching permissions
during the adapter spike rather than treating them as settled dependencies.

Kagi [Lenses](https://help.kagi.com/kagi/features/lenses.html) constrain web searches
by sites and other parameters. The proposed public-collection integration is an
inference from those capabilities. A Lens does not establish a private database
connection or guarantee that published pages will be indexed. No native mechanism
for injecting private GroundRecall results into Kagi's own result ranking was
established by this review.

## Application contract

Use one shared service for retrieval, authorization, record resolution, and
capture. Browser UI, REST clients, CLI, and MCP should call that service. Avoid
copying policy and retrieval logic into each adapter.

The following routes are proposed, not implemented endpoints:

| Interface | Purpose |
| --- | --- |
| `GET /search?q=...` | Bookmarkable human search page; support form submission without putting private queries in URLs as well. |
| `GET /records/{id}` | Human record page, with source evidence and history. |
| `POST /api/v1/search` | Structured search with query, permitted scope, filters, limit, and opaque cursor. |
| `GET /api/v1/records/{id}` | Authorized record detail, version, provenance, and permitted relationships. |
| `GET /api/v1/capabilities` | Supported API/schema versions and enabled operations. |
| `POST /api/v1/captures` | Later: create a draft source submission with an idempotency key. |
| `GET /api/v1/changes?cursor=...` | Later: scoped change feed for refresh and invalidation. |

Define an application result schema with stable ID, kind, title, excerpt,
human URL, source references, source authority, review state, freshness,
supersession/contradiction cues, record version, and an explainable match reason.
Keep lexical relevance distinct from evidence confidence. Missing review or
freshness information must display as unknown rather than imply verification.

The response envelope should include schema version, request ID, next cursor,
index generation, effective scope, and explicit partial/degraded status. Define
bounded requests, invalid filters, expired cursors, unavailable indexes, and
revoked records. Return indistinguishable not-found responses for inaccessible
record identifiers. Specify deterministic ordering within a generation and
restart behavior when that generation changes.

Bind scope and release permissions to authenticated identity. Clients may
narrow their scope; they cannot supply a store path or elevate their identity.
Enforce authorization before constructing visible snippets, counts, facets,
relationships, or caches. Audit raw search and graph expansion paths rather
than assuming transport-level policy checks protect every derived field.

Use server-generated record URLs rather than exposing local file paths. Escape
source text and render it as content. Private browser responses should not be
stored in shared caches. Any retained client cache needs identity isolation,
expiry, and revocation handling.

## Delivery sequence

Effort ranges below are planning estimates for one experienced engineer with
review support. They exclude unresolved reconciliation, vendor access, and
deployment approvals. Release by acceptance gates rather than calendar dates.

### AI-0: Baseline and contract — 3–5 engineering days

Document five model-free workflows: find prior work, inspect evidence, reopen a
stable link, capture a source, and refresh a dependent application after a
correction. Build public/synthetic fixtures and a relevance baseline. Freeze an
initial OpenAPI contract and the record/result schemas above.

Map each field to its existing source and policy check. Identify which existing
query functions can be reused directly and which require authorization-aware
wrappers. Define one configured workspace authority; reconcile this with UPR-0.

Exit: reviewed contract, fixtures, dependency checklist, and a recorded answer
to whether UPR-0 is ready. Unfinished reconciliation is visible, not hidden by a
new interface.

### AI-1: Read service and browser search — 2–3 weeks

Implement the shared read service and the search, record, and capability routes.
Add a small same-origin interface with search, filters, excerpts, evidence
links, and clear review/freshness labels. Support keyboard navigation, accessible
labels, loading, empty, error, unavailable-source, and superseded-record states.

Start with existing lexical retrieval and exact IDs. Preserve the separate
authority of notes and reviewed records. Register any additional corpus
explicitly. Defer semantic ranking to the existing retrieval roadmap.

Build indexes in an explicit maintenance operation; use an atomic generation
switch. An unavailable index should produce an actionable error, and a permitted
older generation should be marked stale. Do not rebuild a corpus in a browser
request. Keep ordinary read credentials unable to promote knowledge.

Reuse the HTTP adapter's identity and request-limit design where suitable.
Define browser session authentication, CSRF protection for writes, strict
Host/Origin validation, and binding defaults; loopback alone is not a complete
authorization design. Existing MCP clients need regression coverage if shared
logic is extracted.

Exit: a person can find and inspect fixture records with all model endpoints
disabled. Permission tests cover search, direct IDs, expansions, counts, and
cache isolation. Restarting the service preserves record links. Production
rollout requires the applicable UPR-0 gate to be complete.

### AI-2: Kagi shortcut and independent client — 3–5 days

Document and test a Kagi Custom Bang pointing to the browser UI. Verify local,
remote-device, signed-out, expired-session, and service-unavailable behavior.
Explain that `localhost` on another device identifies that device; private
remote access needs an intentionally configured reachable address.

Ship a minimal CLI client that queries the HTTP contract, supports JSON output,
and opens record links. It must not read the canonical filesystem or implement
its own ranking. This verifies reuse beyond browsers and assistants before
investing in a larger SDK or extension.

Exit: both the shortcut and independent client work against the same service
without a model, MCP session, or Kagi API key. Publish an installation and
troubleshooting recipe. This completes the first useful release.

### AI-3: Explicit source capture and browser companion — 2–3 weeks

Add a capture form and then a browser companion for saving the current URL,
selected text, title, timestamp, and user note. Record the origin application,
source URL, available source version/hash, and selection context. Use duplicate
detection and idempotency keys to make retries safe.

Show the destination scope and saved content before submission. Capture creates
a draft/import candidate in the existing review lifecycle. A saved search result
or excerpt must retain its actual source type and must not become a verified
claim automatically. Return a durable capture receipt and review status link.

Use an extension-owned side panel for local results rather than placing private
record text in a third-party page's DOM. Request narrow permissions and use
explicit user actions for search and capture. If server-side URL fetching is
added, bound redirects, response size, content types, and reachable destinations.

Exit: saving twice creates one logical submission; failed/offline attempts are
visible and recoverable; capture remains separate from promotion. Test permission
revocation and ensure browsing history is not collected implicitly.

### AI-4: Optional web search provider — 1–2 weeks

Define a small provider contract for query, result URL/title/excerpt, provenance,
timeout, and error classification. Implement Kagi as the first provider after
verifying the current API contract and account access. Keep credentials on the
service side and configure budgets, rate limits, and bounded retries.

Offer explicit “Search the web” behavior. Show the exact outgoing query; any
expansion from private records requires an inspectable choice. Start with
separate local-knowledge and web-results groups. Avoid comparing provider scores
as though they were evidence confidence. Preserve source attribution when
deduplicating URLs or capturing a result.

Exit: denial, timeout, quota exhaustion, or provider removal leaves local search
working. A recorded network test shows that local-only search sends no queries
or record contents to the provider. Fixtures verify provider personalization
metadata is retained when supplied, without making unsupported API assumptions.

### AI-5: More applications and change propagation — 2–4 weeks

Pilot an editor lookup and a dashboard showing reviewed records, evidence, and
freshness. Select these consumers to exercise contextual retrieval and ongoing
refresh, rather than adding another conversational adapter. Provide concise
language examples before committing to maintained SDK packages.

Implement a cursor-based change feed for updates, supersession, withdrawal, and
deletion. Specify at-least-once delivery, stable event IDs, idempotent consumption,
retention limits, and resynchronization after cursor expiry. Recheck authorization
on each read. Use content-free invalidation when access is revoked; do not expose
new protected details through an old subscription. Add signed webhooks only if
a pilot needs push delivery.

Exit: two conventional applications consume the documented API and respond to
a corrected or withdrawn record without direct database access. A dropped or
duplicated event does not produce permanent stale state.

## Optional public discovery track

After the read interface is stable, support a separately generated public
collection from approved release snapshots. Give records stable public URLs,
source links, accessible HTML, sitemap entries, and explicit revision/withdrawal
behavior. A Kagi Lens can constrain search to that published site once indexed.

Keep publication separate from private service deployment. Release eligibility
must cover both a record and its displayed evidence. Test that private titles,
snippets, relationships, and source paths do not appear in the generated output.
External search caches may outlive withdrawal; publishing cannot promise recall
of all third-party copies. Deploying or publishing the collection is outside
this roadmap-writing task.

## Verification and release decisions

Use a versioned set of at least 30 representative queries, including exact names,
aliases, reviewed facts, notes, contradictions, superseded records, and queries
whose relevant records are inaccessible to the caller. Capture a baseline before
setting improvement claims. Suggested initial performance targets are p95 warm
local API search under 500 ms and first usable results under one second on a
declared pilot machine/corpus with five concurrent readers. These are targets,
not measurements of the current implementation; measure cold start separately.

Every milestone should verify its complete user workflow, provenance fidelity,
authorization boundaries, model-free operation, and recovery behavior. Use
contract tests across clients and a small set of browser checks. Keep relevance
benchmarks separate from transport tests so successful requests do not conceal
missing knowledge. Measure time to find a useful record and successful source
inspection in an opt-in pilot, without logging raw queries by default.

The delivery owner should coordinate the shared contract and adapters. The
existing retrieval owner should resolve authority/index dependencies, and a
reviewer should validate permissions, capture semantics, and usability. These
are responsibilities to assign, not assumptions that additional staff exist.

After FB-4, resume AI-0 through AI-5 in order. Add capture after real use shows
where knowledge enters the workflow; add Kagi API aggregation when external web
results are useful enough to justify its operational cost. Keep public
publishing and advanced notifications optional until a named consumer needs
them.

Completion means a user can search, inspect, cite, and later capture knowledge
from ordinary software, while every client sees the same authority, provenance,
and lifecycle rules. AI assistants remain consumers of that shared service.
