---
title: "ClaimWright Review Action Priorities"
date: 2026-07-28
---

# ClaimWright Review Action Priorities

This note converts the ClaimWright review of the governed-memory preprint into
an implementation-priority list. The ordering favors work that improves
GroundRecall's practical governed-memory capability while also improving the
paper's evidence position.

## Priority Criteria

Items are ranked higher when they:

1. close a functional governance gap in GroundRecall;
2. convert a paper limitation into an evidence-backed implementation claim;
3. reduce public-facing overclaim risk;
4. can be demonstrated with tests or reproducible examples;
5. avoid premature production claims, benchmark claims, or broad security
   proofs.

## P0: Policy Coverage And Audit Completeness

Initial implementation status:

- `src/groundrecall/policy_coverage.py` defines a versioned
  `groundrecall.policy_coverage.v1` registry for policy-enforcement coverage.
- `groundrecall inspect STORE --policy-coverage` emits the full route matrix.
- `groundrecall inspect STORE --policy-coverage-summary` emits compact counts
  and open items.
- `inspect_store(..., include_policy_coverage=True)` exposes the same report
  through the Python API.
- Graph augmentation/backfill and graph maintenance `--apply` paths now accept
  optional policy-plugin configs and block deny/hard-gate decisions before
  candidate relation, review-candidate, or maintenance-state writes.
- Those graph write paths also accept `--audit-log` and write JSONL policy
  preflight audit events for both allowed-with-policy and blocked decisions.
- Direct CLI query now accepts optional policy-plugin configs and blocks
  deny/hard-gate decisions before store access; softer decisions are attached
  to query output.
- Import proposal generation now accepts optional policy-plugin configs and
  blocks deny/hard-gate decisions before import output directories or proposal
  files are written. Soft decisions are recorded in the import manifest, and
  `--audit-log` writes JSONL preflight audit events.
- Tests cover the report, Python API, and CLI dispatch.

ClaimWright review basis:

- policy-plugin enforcement covers selected surfaces, not all mutation paths;
- the paper must not imply production IAM or complete policy coverage;
- public-facing agent use depends on enforceable publication and action gates.

Functional value:

- makes the policy-plugin boundary operationally meaningful beyond a few
  selected routes;
- reduces risk that an assistant or adapter can mutate durable memory through
  an ungated path;
- provides a concrete foundation for MCP, federation, public export,
  adjudication, and exceptional-erasure workflows.

Paper value:

- supports a stronger claim that GroundRecall owns a bounded, testable policy
  interface for governed memory operations;
- narrows the current caveat from "selected surfaces only" toward a documented
  coverage matrix;
- supplies reproducible audit artifacts for the preprint appendices.

Recommended implementation sequence:

1. Add a policy-enforcement coverage matrix for every read/write/export/import
   route: MCP tools, CLI commands, Python APIs, federation, promotion,
   relation review, contradiction adjudication, graph backfill, review queue,
   and future erasure. Implemented baseline.
2. Add deny/hard-gate audit events for every gated write attempt, including
   blocked attempts before durable memory changes occur. Implemented for graph
   augmentation/backfill and graph maintenance when `--audit-log` is supplied.
3. Add regression tests proving that each covered write path fails closed when
   a policy plugin denies or hard-gates the operation. Implemented for graph
   augmentation/backfill and graph maintenance apply paths.
4. Expose coverage status in diagnostics, for example
   `groundrecall inspect --policy-coverage`, so paper claims can cite a
   generated artifact rather than prose.
5. Update the claim-evidence matrix only after the coverage artifact and tests
   exist.

Acceptance criteria:

- each durable mutation route is classified as covered, intentionally ungated,
  or future-only; implemented for all current non-future coverage routes;
- covered write routes have deny/hard-gate tests;
- denied write routes leave audit evidence without writing protected records;
- the preprint can cite the coverage artifact without claiming production IAM.

## P1: Contradiction Workflow Depth

Initial implementation status:

- `groundrecall contradictions candidates STORE` lists graph-inferred
  `claim_may_contradict_claim` relation candidates as a review batch with
  participating claim previews, evidence IDs, provenance, assessments, missing
  claim diagnostics, and available review actions.
- `groundrecall contradictions accept-candidate STORE RELATION_ID --reviewer
  ... --rationale ...` promotes an accepted cue into explicit bidirectional
  `contradicts_claim_ids` links and synchronizes a deterministic first-class
  contradiction case.
- Candidate acceptance records reviewer, rationale, review timestamp, and the
  accepted relation ID in case metadata while leaving the underlying claim text
  unchanged.
- Candidate acceptance accepts optional policy-plugin configs; deny/hard-gate
  decisions block before claim, relation, or contradiction-case writes.
- `groundrecall contradictions reject-candidate STORE RELATION_ID --reviewer
  ... --rationale ...` marks a false-positive contradiction cue rejected
  without creating claim links or a case.
- Candidate acceptance and rejection can write
  `groundrecall.contradiction_candidate_audit.v1` JSONL audit events for
  accepted, rejected, and policy-blocked decisions.
- Concept query bundles now expose `candidate_contradiction_cues`,
  `adjudicated_contradiction_cases`, and `conflict_summary` fields so explicit
  contradictions, heuristic cues, resolved/adjudicated cases, supersessions,
  and stale claims are distinguishable in one payload.
- Public query export guardrails prune non-exportable contradiction cases and
  contradiction-candidate cues, then recalculate conflict counts after pruning.
- Tests cover candidate listing, candidate-to-case promotion, CLI candidate
  dispatch, policy-gated blocking, explicit-link case generation, case
  persistence, diagnostics, adjudication, query surfacing, and public-export
  cue pruning.
- `examples/preprint/run_preprint_demos.py` now emits
  `contradiction_candidate_review.json`, showing cue listing, candidate
  acceptance, audit evidence, first-class case creation, adjudication, preserved
  claim text, and query conflict-summary output.

ClaimWright review basis:

- contradiction cases and adjudication are implemented;
- heuristic cue generation exists;
- robust automatic semantic contradiction detection and resolution are still
  future work.

Functional value:

- makes contradictions less dependent on manual links;
- improves review queues by turning candidate contradiction cues into
  inspectable cases;
- reduces the chance that graph search hides unresolved disagreement behind a
  single high-ranking result.

Paper value:

- converts the current caveat into a more precise claim: GroundRecall supports
  explicit cases, adjudication, diagnostics, and review-gated cue promotion;
- strengthens the manifesto point that durable memory should preserve
  disagreement and adjudication history.

Recommended implementation sequence:

1. Add a `contradictions candidates` or review-queue view that surfaces
   `claim_may_contradict_claim` relation candidates generated by graph
   backfill. Implemented baseline.
2. Add a review action that promotes an accepted contradiction candidate into
   explicit `contradicts_claim_ids` links and then materializes a first-class
   contradiction case. Implemented baseline with policy-plugin gating.
3. Add query output fields that distinguish:
   - explicit contradiction cases;
   - candidate contradiction cues;
   - adjudicated/resolved contradiction cases;
   - stale or superseded claims. Implemented baseline in concept query bundles.
4. Add tests for candidate-to-case promotion, rejection, audit metadata, and
   no silent rewriting of underlying claims. Implemented baseline for listing,
   acceptance, rejection, policy blocking, audit events, and no claim-text
   rewriting.
5. Add a reproducible preprint demonstration showing candidate cue → review →
   case → adjudication. Implemented baseline in
   `examples/preprint/out/contradiction_candidate_review.json`.

Acceptance criteria:

- candidate contradiction cues are visible in review output;
- accepting a cue creates explicit review state, not a hidden relation-only
  signal;
- adjudication state appears in query bundles;
- the paper still avoids claiming full semantic contradiction resolution.

## P2: Privacy, Revocation, And Exceptional-Erasure Lifecycle

Initial implementation status:

- `groundrecall erasure plan STORE --target ID --reason-class ... --authority
  ...` builds a read-only exceptional-erasure plan.
- `src/groundrecall/erasure.py` defines versioned
  `groundrecall.exceptional_erasure.v1` plan, target, and tombstone models.
- The planner records reason class, authority, timestamp, target IDs, affected
  canonical records, derived/rebuildable projections, and a minimal
  non-sensitive tombstone payload with content hashes, origin hashes, and
  affected counts.
- Dependency expansion is bidirectional: a protected record pulls in supporting
  upstream records and downstream relations, review candidates, contradiction
  cases, adjudications, and promotions that reference it.
- Derived-artifact reporting includes the local FTS index, snapshots, and
  optional export/quarantine directories.
- The planner is dry-run only and performs no deletion.
- Policy coverage now lists `cli.erasure.plan` as covered for dry-run planning;
  destructive execution and re-import blocking remain future work.

ClaimWright review basis:

- privacy-leakage and distributed-revocation coverage should deepen;
- exceptional erasure remains incomplete;
- release controls and federation quarantine are implemented but are not DLP or
  production IAM.

Functional value:

- gives GroundRecall a concrete answer for exposed secrets, legal/privacy
  deletion requests, and unsafe re-imports;
- complements non-destructive epistemic maintenance with a separate destructive
  security/privacy path;
- improves federation safety by making revocation and erasure visible without
  rewriting ordinary provenance history.

Paper value:

- clarifies the difference between ordinary forgetting, expiry, supersession,
  revocation, and exceptional erasure;
- supports a stronger governance/security appendix without claiming complete
  enterprise compliance.

Recommended implementation sequence:

1. Define an exceptional-erasure request and tombstone schema that records
   reason class, authority, timestamp, affected IDs, and non-sensitive
   re-import prevention metadata. Implemented baseline for dry-run plans.
2. Implement a dry-run erasure planner that reports affected canonical records,
   indexes, exports, graph candidates, snapshots, and federation quarantine
   objects. Implemented baseline.
3. Implement erasure execution for records and rebuildable local projections
   under an explicit policy-plugin gate.
4. Add re-import blocking for erased content hashes or origin IDs.
5. Add revocation event export/import tests for federation bundles without
   claiming complete distributed propagation.

Acceptance criteria:

- erasure is separately authorized from ordinary epistemic maintenance;
- protected content is absent from covered local storage after execution;
- a minimal tombstone prevents silent re-import;
- tests distinguish erasure from expiry, supersession, and retraction.

## P3: Reproducible Evaluation Fixtures

ClaimWright review basis:

- benchmark evaluation design remains open;
- current timing demonstrations are internal engineering indications, not
  external benchmarks;
- GroundRecall has not been run against LongMemEval, LoCoMo, MemoryAgentBench,
  or GraphRAG-Bench.

Functional value:

- prevents performance and graph-quality discussions from relying on one local
  store;
- provides regression fixtures for temporal updates, contradiction,
  authorization, abstention, and graph expansion;
- gives the project a stable way to compare search modes as graph density
  changes.

Paper value:

- supports stronger empirical claims without comparing against external memory
  products prematurely;
- makes the paper's engineering-evidence stance more reproducible.

Recommended implementation sequence:

1. Freeze a small governed-memory fixture with claims, sources, release levels,
   contradictions, supersessions, and graph candidates.
2. Add a runner that reports FTS-only, graph-expanded, and policy-filtered query
   outputs plus latency summaries.
3. Add quality checks for expected provenance, contradiction visibility,
   abstention, and access filtering.
4. Keep external benchmark adaptation as a later step after the local fixture is
   stable.
5. Record generated JSON outputs under `examples/preprint/out/` and cite them
   from the claim-evidence matrix.

Acceptance criteria:

- fixture generation is deterministic;
- outputs include both latency and governance-quality checks;
- results remain explicitly scoped as engineering demonstrations.

## P4: Bibliography Completeness Protocol

ClaimWright review basis:

- the bibliography is broader but not systematic;
- privacy-leakage and distributed-revocation literature should deepen before
  submission;
- final human publication approval remains open.

Functional value:

- lower direct product value than P0-P3, but improves source-review discipline;
- gives CiteGeist a concrete use case for topic coverage and source status.

Paper value:

- reduces related-work selectivity risk;
- supports a defensible "seeded review" or "bounded review protocol" statement.

Recommended implementation sequence:

1. Define search strings, inclusion/exclusion criteria, source tiers, and stop
   conditions for a bounded bibliography pass.
2. Use CiteGeist to track candidate sources, reviewed sources, rejected
   sources, and coverage gaps.
3. Add privacy leakage, persistent memory attacks, distributed revocation,
   provenance-aware governance, and policy-composition sources.
4. Update the bibliography notes and claim-evidence matrix with the protocol,
   not just new citations.

Acceptance criteria:

- the paper can state what was searched and why the bibliography is bounded;
- source gaps remain explicit;
- no unsupported systematic-review claim is made.

## Recommended Order

| Rank | Workstream | Why now |
| --- | --- | --- |
| 1 | Policy coverage and audit completeness | Highest functional governance value; directly reduces paper overclaim risk. |
| 2 | Contradiction workflow depth | Central governed-memory capability; improves graph, query, and paper claims. |
| 3 | Privacy, revocation, and exceptional erasure | Important governance/security gap; needs clear separation from ordinary forgetting. |
| 4 | Reproducible evaluation fixtures | Converts local claims into repeatable engineering evidence. |
| 5 | Bibliography completeness protocol | Needed before submission, but less functional than P0-P3. |

The next coding model should start with P0 unless there is an immediate paper
deadline requiring bibliography protocol work first. P0 creates the strongest
shared benefit: better software behavior, better auditability, and a more
defensible preprint claim boundary.
