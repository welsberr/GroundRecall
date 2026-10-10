# GroundRecall Repository Consolidation Roadmap

Reviewed: 2026-10-10. Baseline: `9a0eadc` plus the working tree inspected on
that date. Status: review complete; implementation milestones below are planned.

Retain the workspace safeguards, preservation tools, backlog correction, and
small context-checkpoint workflow. Retain the application interface as a
development candidate, but fix authorization and retrieval contracts before
enabling it. Reach a clean checkout through reviewed commits and explicit
disposition of unfinished work. Completing every long-term roadmap is not a
prerequisite for repository cleanliness.

This document coordinates the [application integration roadmap](application-integration-roadmap.md)
with the working-tree plans `docs/unified-prior-work-retrieval-roadmap.md`,
`docs/session-context-and-cost-roadmap.md`, and
`docs/lede-brief-design-and-roadmap.md`. Those three files are uncommitted at
the review baseline; their contents are not yet released capabilities.

**Decisions about the features**

| Feature group | Decision and practical value |
| --- | --- |
| Workspace manifest, explicit notes/canonical/unified projections, non-creating reads | Keep. These reduce wrong-root writes and make retrieval authority inspectable. Harden validation and preserve the existing reconciliation gate. |
| Format checks, additive-field preservation, store locks, backup/update/rollback | Keep. These protect durable knowledge during upgrades. Shared writer locks coordinate updates; they do not provide general transaction isolation. |
| Workspace inventory and copy-first import reconciliation | Keep as operator tools. They make preservation and custody checks reproducible. They must not run automatically during installation or startup. |
| Completed-import suppression in review backlog | Keep as a focused correction. Terminal work should not reappear, while artifact hashes must still suppress duplicate note intake. |
| Transport-neutral application contract and CLI | Keep after correction. These permit ordinary software to use GroundRecall and provide a common contract for later adapters. |
| HTTP/HTML search, record links, Kagi shortcut | Keep as a later gated increment. Browser access is useful, but the current routes do not inherit MCP's full enforcement and cannot yet substantiate the documented browser-session workflow. |
| Lede-brief package metadata, coverage bookkeeping, checkpoint writing, deterministic advice | Keep a narrow initial feature. Distinguish available content, required content, and demonstrated delivery; validate inputs and recovery before claiming reliable session resumption. |
| Automated compaction, provider controls, billing integration, session leases, generalized concurrency | Defer implementation to the session roadmap. The current checkpoint code does not implement these capabilities. |
| Semantic retrieval, external corpus registration, richer feeds/capture/public search | Defer to their existing roadmaps. They are unnecessary for consolidating the current work. |
| AgentOS documentation and manifest | Keep reusable, accurate project guidance after review. Private run receipts stay private; extract a public-safe verification summary when needed. |
| Generated SQLite index and other runtime data | Preserve locally and exclude from Git and applicable build contexts. They are rebuildable runtime artifacts, not source fixtures. |

**Reassessment of the findings**

1. **Authorization is the first release blocker.** The scope problem is broader
   than a misleading label. `application_service.py` calls low-level search
   with a scope string that does not filter authorization. In `mcp_http.py`,
   the added routes authenticate a token but do not pass its principal to the
   application service. They bypass the MCP processing path that applies
   server policy, tool permissions, release bounds, and audit logging. They
   also bypass its concurrency/deadline wrapper. These are code findings, not
   evidence that a production disclosure occurred.
2. **Separate projection from permission.** `notes`, `canonical`, and `unified`
   describe content projections; `private` is a release classification.
   Neither is a substitute for a governed scope grant. Define these separately
   in the application contract. A request may narrow server-granted access,
   never enlarge it. Apply permission filtering before results, counts,
   pagination, snippets, associations, and direct record responses are emitted.
3. **Pagination needs an honest first increment.** A nonempty cursor currently
   repeats the first page. Reject cursors explicitly until implemented, publish
   that capability, and report truncation accurately. A limit alone does not
   imply an erroneous result; silently accepting an unsupported cursor does.
4. **Manifest validation needs structural checks.** A JSON list currently raises
   `AttributeError`. Reject non-object payloads, invalid field types, path
   escapes, and conflicting authority roles with a stable configuration error.
   Define legal nesting: the canonical index may live under `store/.index`;
   private logs must not overlap a searchable corpus. Do not simply forbid all
   nesting, which would reject the documented default layout.
5. **Redaction is defense in depth.** Common Unix prefixes are redacted, but
   synthetic `/root`, `/etc`, and Windows paths pass through. Adding prefixes
   alone cannot establish a confidentiality boundary. Use an explicit response
   schema, authorized display fields, and sanitization of nested associations,
   identifiers, and errors. Test both sensitive paths and legitimate URLs/text.
6. **Index behavior contradicts the read-only option.** A missing index is built
   even when `ApplicationReadService(auto_build=False)` is used, because the
   lower-level search function builds absent indexes. Resolve manifest-defined
   projections and move maintenance out of HTTP reads. Return an explicit
   unavailable/degraded result for missing, stale, or incompatible projections.
7. **Browser navigation needs integration tests.** The HTML form submits to
   `/?q=...`, but the outer handler only recognizes the exact `/` or paths
   starting with `/search` or `/records/`; the root query URL falls through.
   Bearer-header authentication alone does not provide a normal browser login
   session. Search also exposes source-note result links while the record
   reader has no source-note resolver. Define and test these paths end to end.
8. **The newer context work is a foundation, not complete recovery.** Supplied
   loaded-unit IDs and delivery status need validation and provenance. Preserve
   the distinction between recording delivery and proving comprehension.
   Checkpoints need workspace/version binding, source integrity checks, private
   destinations, and stale-state handling before automated resumption.
9. **Release packaging has changed since the earlier review.** The working tree
   replaces an Epistemap Git tag dependency with a version range, adds an optional
   lede-brief dependency, and changes the package version. Local editable
   installations do not prove that a fresh install can resolve those releases.
   Verify distribution sources before committing the release metadata as ready.

**Milestones and completion gates**

| ID | Deliverable | Depends on | Status |
| --- | --- | --- | --- |
| RC-0 | Preserve and classify all pending work | Review baseline | Planned |
| RC-1 | Land workspace and preservation foundations | RC-0 | Planned |
| RC-2 | Resolve or explicitly isolate reconciliation-gated retrieval work | RC-1 | Planned |
| RC-3 | Correct application service, authorization, and retrieval contract | RC-1; RC-2 for unified release | Planned |
| RC-4 | Validate browser access and optional shortcut | RC-3 | Planned |
| RC-5 | Validate narrow context/checkpoint feature | RC-1; dependency verification | Planned |
| RC-6 | Reproducible package, documentation, and container checks | Selected feature gates | Planned |
| RC-7 | Publish scoped commits and verify clean repository state | RC-0 through RC-6 disposition | Planned |

RC-5 can proceed independently of RC-3/RC-4. Features that cannot pass their
gate may remain on a documented topic branch; they must not remain as
unattributed dirty files or appear as released features.

**RC-0 — Preserve and classify**

- Record HEAD, branch/upstream, staged and unstaged diffs, untracked paths,
  and content hashes in a private receipt outside the repository. Preserve a
  recoverable copy before moving or splitting any changes. Coordinate with
  other active sessions before editing shared files.
- Assign every changed file or hunk to a feature group above. Mixed files such
  as `cli.py`, `pyproject.toml`, and `README.md` require selective staging.
- Add narrowly scoped ignore rules for the generated `.index/` tree and
  `.agentos/runs/`; preserve those local files. Review `.agentos/manifest.json`
  and role definitions separately as possible public source.
- Review both root and Dockerfile-specific ignore files. The existing broker
  Dockerfile has its own build-context allowlist; a new root `.dockerignore`
  should not be assumed to govern that build. Check wheel/sdist contents too.

Exit: each baseline path is accounted for as retained source, private runtime
data, or preserved deferred work. No blanket add, clean, reset, or discard.

**RC-1 — Commit the protective foundations**

- Correct manifest shape/type/role validation and check malformed format markers.
- Verify read/index operations do not create typed-record families; test wrong
  mutation targets and authority boundaries for imports and promotion.
- Retain unknown additive record fields, including nested confidence fields,
  without weakening validation of known required fields or future format versions.
- Exercise update locks across processes, backup verification, unchanged-record
  rollback, and failures both before and after manifest publication. A failure
  after publication must report actual store state and a recovery route.
- Test inventory and reconciliation on non-default manifest paths as well as the
  default layout. Inventory role classification currently contains default
  directory names and needs to follow the manifest where present. Require clear
  handling of absent destinations, changed sources, malformed plans/receipts,
  interrupted copies, and idempotent retries. Preserve source bundles.
- Commit the backlog correction with tests for terminal versus active imports
  and duplicate-note suppression.

Exit: focused tests and temporary-store preservation/restore rehearsals pass.
Shipping tools does not authorize a migration of the live memory store.

**RC-2 — Respect the authority-reconciliation gate**

The working-tree unified retrieval roadmap still leaves UPR-0 open. Recheck its
historical completion claims against preserved receipts and current store
evidence. Complete the ID/content accounting and review divergent typed records
before approving unified production retrieval. Keep notes and canonical records
distinguishable, and verify that private operational files never become corpus
content through overlapping paths or configuration mistakes.

If those data decisions cannot be completed in this consolidation, keep the
dependent implementation on a named, pushed development branch with its tests
and gate recorded. Protective code and audit fixtures can still land. Do not
declare UPR-0 closed merely to clean the checkout. Live data migration remains
a separately reviewed operation under the existing roadmap.

Exit: either evidenced UPR-0 completion or an explicit branch-level disposition
that preserves the gate and permits a clean active checkout.

**RC-3 — Make the application service safe and truthful**

- Until corrected, disable application routes by default or keep their addition
  off the release branch. Make the eventual enabling configuration explicit.
- Carry server-owned principal and policy context into a shared authorization
  layer. Define application permissions explicitly, map existing identity
  restrictions conservatively, and fail closed on unavailable required policy.
- Filter search and direct reads consistently, including related records. Test
  two principals with different grants, denied direct IDs, unavailable policy,
  release restrictions, forged scope requests, and rejected metadata overrides.
- Select the correct manifest projection and provide stable generation/freshness
  metadata. Make no-build reads genuinely non-writing, including derived files.
- Reject unsupported cursors now. Later pagination must bind opaque cursors to
  query/filter/projection/generation and authorization context, with stable order
  and explicit expiration. Authorization must remain enforced on each page.
- Add response allowlists, bounded field handling, safe error mapping, audit
  events, concurrency limits, and deadline tests to API and HTML requests.

Exit: real HTTP integration tests demonstrate permission parity and bounded
behavior; unauthorized results cannot leak through snippets, counts, or links.
Dispatcher-only tests are insufficient for this milestone.

**RC-4 — Finish the small human interface**

Parse URL paths consistently, repair root search submission, and resolve every
advertised result kind or clearly mark it non-navigable. Provide a documented
browser authentication mechanism, such as a configured authenticating proxy
or a reviewed session flow. Never put bearer credentials in shortcut URLs.

Exercise signed-in and signed-out navigation, search, record opening, logout or
expired identity, unavailable indexes, and restart behavior through the actual
server. Check escaping and visual/keyboard usability. Verify the optional
shortcut using encoded spaces, punctuation, and Unicode on the deployed address.
The direct browser page is sufficient for the first useful release; Kagi is
optional and may remain deferred with its documentation labeled accordingly.

Exit: a person can search and follow an authorized record link in an ordinary
browser; local-only and external-query behavior is stated accurately.

**RC-5 — Graduate the checkpoint feature narrowly**

Validate package schema/version, artifact integrity, unit IDs, required and
loaded coverage, and permitted status values. Reject traversal and stale source
bindings. Bind checkpoints to the declared workspace and private run location;
preserve constraints, decisions, pending work, and verification evidence across
write/read/resume. Invalid or stale bindings must prompt reconciliation rather
than silently direct writes to another project.

Add CLI execution tests and a synthetic interrupted-session recovery exercise,
not just parser and atomic-write tests. Validate nonnegative measurements and
units for advice, label estimates, and keep unknown data unknown. Preserve
unconfirmed delivery unless an adapter supplies evidence. Automated compaction,
provider control, and transaction coordination remain future work.

Exit: the same package and checkpoint reproduce the intended task constraints
in an isolated recovery exercise; docs describe only the tested increment.

**RC-6 — Verify a distributable combination**

- Choose resolvable dependency references and document the optional extra.
  Verify the Epistemap/lede-brief compatibility matrix from fresh installed
  artifacts without sibling source paths or editable-install assumptions.
  A Git tag or verified wheel source is an option if a package-index release
  is unavailable; do not publish packages merely to satisfy cleanup.
- Build and inspect wheel/sdist contents. Verify installed CLI entry points,
  the base installation, and optional-feature behavior. Build the broker image
  against the final metadata and rerun its synthetic two-participant pilot.
- Run the full GroundRecall suite in the documented environment. Add the
  cross-project compatibility fixtures needed by actual dependency changes.
  Record failures, environment limits, and skipped checks explicitly.
- Align README, AgentOS status, operator guidance, and all relevant roadmaps.
  Separate historical execution receipts, tested current capability, and future
  work. Replace broad completion language with milestone-specific evidence.

Exit: the selected release works from a fresh checkout; dependencies, build
artifacts, and documentation agree on what is available.

**RC-7 — Publish and demonstrate cleanliness**

Use independently reviewable commits in dependency order: runtime exclusions;
workspace/format preservation; inventory/reconciliation tools; backlog fix;
gated retrieval disposition; application service/HTTP/browser increments;
context increment; release metadata and consolidated documentation. Adjust
grouping where imports require two changes to land together. Each intermediate
release commit must still import and pass its relevant tests.

Review staged diffs explicitly. Put deferred public-safe code on named topic
branches with tested base revisions and open gates; preserve private material
outside Git. Verify each preservation copy or commit before removing only its
corresponding working-tree changes. A stash alone is not the durable final
disposition of unfinished work.

Push accepted commits to active remotes without force. `main` tracks
`github/main`; `origin` is also configured and must have its current role and
reachability checked. An unreachable remote is a reported synchronization gap,
not evidence of successful publication. Divergent histories need review before
integration. Version tags and package publication require their own release
decision and are not implicit in a clean working tree.

Exit checks:

- `git diff --check` passes; staged diff is empty.
- `git status --porcelain=v1 --untracked-files=all` is empty in the active
  checkout; ignored runtime files remain intact and are not tracked.
- The preservation inventory accounts for every original changed path/hunk,
  including deferred branches and private receipts.
- Fresh-checkout tests and packaging evidence identify the final commit.
- Required remote branch tips match the intended commits; any unavailable
  remote or deferred milestone is recorded accurately.

**Evidence and progress recording**

The 2026-10-10 inspection found 21 modified tracked files and 34 untracked files
before adding this roadmap. The focused test run passed **66 tests** across the
application, workspace, update, reconciliation, inventory, backlog, index,
context CLI, and lede-brief context modules. This is not a fresh full-suite,
browser, deployment, or cross-host validation.

Temporary synthetic-store probes reproduced arbitrary scope acceptance,
ignored nonempty cursors, missing-index creation with `auto_build=False`,
`AttributeError` for a list-valued workspace manifest, and the unredacted path
formats described above. HTTP authorization and routing findings come from
source inspection; adversarial transport tests belong to RC-3/RC-4.

A bounded GroundRecall prior-work query returned general workspace and earlier
dirty-checkout records, but no directly useful current implementation receipt.
The live checkout is the evidence for this assessment. Historical test totals
in private run receipts were not rerun or promoted to current guarantees.

When completing a milestone, update its status and record the date, commit,
tests/rehearsal, reviewer, remaining limitations, and next action. Keep private
paths and raw run output in private receipts; publish only the reviewed summary.
