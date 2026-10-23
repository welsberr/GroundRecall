# Unified Prior-Work Retrieval Roadmap

Status: active; UPR-0 R0-A through R0-C complete. Later units remain
review-gated.

## Decision

GroundRecall should become the unified retrieval view for prior work, while
preserving separate authorities and trust levels underneath that view. Before
any retrieval architecture changes, the current fractured knowledge stores and
indexes must be reconciled. That reconciliation is a hard Phase 0 gate.

This roadmap is a focused execution plan under R0 and R4 of
[`memory-lifecycle-roadmap.md`](memory-lifecycle-roadmap.md), not a replacement
for the broader lifecycle roadmap.

## Confirmed Product Choices

- Primary outcome: improve GroundRecall's ability to retrieve relevant prior
  work.
- Primary failure: relevant prior work is present but not retrieved.
- View: one query surface over typed GroundRecall records, source notes, and
  explicitly registered repository documentation and commit summaries.
- Authority: the view is unified; the underlying stores are not flattened into
  one trust class.
- Ranking: query-intent-sensitive.
- Semantic retrieval: local embeddings only, with lexical and graph fallbacks.
- Output: a structured evidence bundle rather than an unstructured excerpt
  list.
- Resumption: automatic recall at deterministic task boundaries, supported by
  structured checkpoints and bounded private recovery segments.
- Evaluation: public/synthetic fixtures plus opt-in, host-local replay of real
  queries.
- Initial pilots: GroundRecall, Epistemap, Didactopus, and CiteGeist.

## Authority Map

| Material | Authority | Retrieval treatment |
| --- | --- | --- |
| Reviewed claims, concepts, relations, artifacts, and promotion records | GroundRecall typed canonical store | Highest GroundRecall lifecycle authority; expose version, status, provenance, and release level |
| Working notes, operational narrative, and orientation notes | GroundRecall source notes | Authoritative as notes, not silently promoted to reviewed knowledge |
| Registered repository documentation | The owning repository and recorded Git revision | Read-only external corpus; preserve repository/path/revision provenance |
| Registered commit summaries | The owning Git history | Historical orientation; never substitute for current documentation or canonical records |
| Search, graph, and embedding indexes | None; rebuildable projections | May rank and link material but never become a source of truth |
| Evidence bundles and retrieval receipts | None; derived request artifacts | Explain selection and make a run reproducible |
| Task checkpoints | Operational state | Resumption aid, not reviewed knowledge |
| Recovery segments | Private, expiring operational state | Secret-scanned, access-restricted, never indexed, promoted, synchronized, or exported |

There must be exactly one configured canonical GroundRecall store root. A
workspace root may contain source notes, imports, exports, and projections, but
it must not be accepted implicitly as a second canonical store.

## Current Fracture: Read-Only Observation

The following snapshot was observed on 2026-09-01. It is evidence for an audit,
not a declaration that either location is safe to discard:

- `/home/netuser/.groundrecall/.index/groundrecall-search.sqlite` contains 986
  indexed documents;
- `/home/netuser/.groundrecall/store/.index/groundrecall-search.sqlite` contains
  42,625 indexed documents;
- canonical-shaped directories exist both at the workspace root and below
  `store/`;
- root/store JSON counts include: artifacts 4/323, observations 171/13,172,
  claims 171/13,172, concepts 25/646, relations 0/401, review candidates
  196/14,219, promotions 4/279, and snapshots 8/255;
- `search_index.py` writes its index under the directory supplied as
  `store_dir`, constructs `GroundRecallStore(store_dir)`, and locates sibling
  source notes specially only when that directory is named `store`.

The workspace README describes the two indexes as serving different purposes:
workspace-level source-note discovery versus canonical-store search. Separate
projections are not themselves a defect. The ambiguity is that the same
store-shaped API accepts both roots, the workspace root also contains typed
record directories, and the resulting query scope is not explicit to the
caller. That ambiguity is a plausible direct contributor to missing prior work
and must be resolved before tuning ranking.

## Phase 0: Reconcile Stores and Projections

Phase 0 is complete only when every current record and projection is accounted
for and one unambiguous authority path is operational. Store reconciliation
must remain read-only until an explicit migration plan, backup, and rollback
procedure have been reviewed; protective code and tests may proceed without
moving data.

Implementation status, 2026-09-02: the R0-A protection layer is complete. A
versioned workspace manifest now separates store/import/note authority,
indexing uses non-creating reads, workspace search requires an explicit scope,
and wrong-root import, promotion, typed-store construction, and typed-record
writes are rejected. R0-B is also complete: an itemized full-workspace
inventory, quiescence-verified backup, checksum-identical isolated restore,
model/reference checks, and scoped-index rebuild rehearsal succeeded. R0-C
copied and verified all 79 misplaced bundles into the declared import registry
while preserving their original paths. UPR-0 remains open: typed-record
reconciliation and the conflict decisions below are still required.

### UPR-0.1 Inventory and classification

- Freeze a dated inventory of both store-shaped trees, source notes, import
  areas, snapshots, indexes, exports, and configuration references.
- Compare stable IDs, content hashes, schemas, lifecycle states, provenance,
  release levels, and modification history.
- Classify each item as identical duplicate, divergent same-ID record, unique
  canonical candidate, working/source material, legacy import shape,
  projection, backup, or unresolved.
- Record unknowns; do not resolve divergent records by newest timestamp alone.

### UPR-0.2 Authority and migration plan

- Select and configure one canonical store root.
- Produce a dry-run manifest for every proposed copy, merge, rename, archive,
  quarantine, index rebuild, and documentation change.
- Define conflict handling that preserves both variants and requires review.
- Take a verified backup or snapshot and test the rollback procedure before
  applying the migration.
- Require separate approval before material moves, merges, or archival. Do not
  delete either tree as part of initial reconciliation.

### UPR-0.3 Path and command hardening

- Replace ambiguous positional “store directory” usage with an explicit
  workspace configuration that resolves the canonical store, source-note root,
  and declared projection locations.
- Require explicit query scopes for canonical records, source notes, or the
  unified view. Do not let `GroundRecallStore(workspace_root)` silently treat a
  workspace as a second canonical store.
- Give every derived index a manifest containing canonical-store identity,
  source roots, schema/index version, record counts, content/dependency hashes,
  build time, and tool revision.
- Add regression tests for the wrong-root failure and for source-note discovery.
- Correct startup, operator, and assistant instructions to use one validated
  command path.

### UPR-0 exit gate

- one configured canonical store root and one documented workspace layout;
- all pre-reconciliation IDs and files appear in an accounting manifest;
- all divergent same-ID records are preserved and reviewed or quarantined;
- clean rebuilds create the declared, distinctly named projections from their
  configured inputs, and the unified query covers the expected combined view;
- counts, representative queries, release controls, and provenance pass
  verification;
- backup restoration has been exercised;
- obsolete paths are only marked or archived after verification, never silently
  removed;
- the baseline missing-prior-work query set is captured before ranking changes.

No work in UPR-1 or later may merge while this gate is open, except tests and
documentation that directly enable the audit.

## Phase 1: Corpus Contract and Baselines

### UPR-1.1 Registered corpus manifest

Define a versioned registry for each external corpus with repository identity,
local path, selected branch or revision, include/exclude rules, allowed document
types, authority owner, release level, refresh mode, and last indexed commit.
The initial repository scope is selected documentation and generated commit
summaries, not full source code.

Registration is explicit. Discovery of a nearby Git repository must not make
its content searchable automatically.

### UPR-1.2 Query and intent contract

Start with explicit, inspectable intent classes:

- current operational orientation;
- reviewed factual knowledge;
- historical decision or prior attempt;
- research/source discovery;
- relationship or neighborhood exploration;
- interrupted-task resumption.

Intent selection may be automatic, but the chosen intent, alternatives, and
ranking effects must appear in the retrieval receipt. Callers can override it.

### UPR-1.3 Baseline evaluation

- Build synthetic and public fixtures with known relevant, irrelevant,
  superseded, contradictory, inaccessible, and near-duplicate records.
- Capture an opt-in private set of real failed and successful GroundRecall
  queries locally.
- Measure lexical-only candidate recall, bundle recall, MRR, nDCG, stale-result
  rate, contradiction visibility, release-policy violations, latency, and token
  cost.
- Seal gold relevance judgments from the system under evaluation and include
  negative controls.

Exit: the registry, query contract, fixtures, evaluation runner, and baseline
report are versioned and reproducible.

## Phase 2: Unified Lexical View and Evidence Bundles

### UPR-2.1 Normalized retrieval documents

Compile typed records, notes, and registered repo documents into a common
retrieval-document envelope without changing their native authority. Include
stable source reference, corpus, kind, lifecycle/review state, release level,
timestamps, current/superseded status, aliases, dependency hash, and a display
title/body.

### UPR-2.2 Broad candidates, bounded selection

Retrieve a deliberately broad internal candidate set from lexical, exact-ID,
alias, and existing graph paths. Select a smaller output set under a declared
token budget. Record candidate-source ranks, fused score components, filters,
and selection or exclusion reasons.

### UPR-2.3 Structured evidence bundle

Return a versioned bundle with these groups:

1. `orientation`: current project state, constraints, and active decisions;
2. `reviewed_knowledge`: canonical reviewed records relevant to the query;
3. `history`: prior attempts, decisions, and superseded material clearly
   labeled;
4. `graph_context`: bounded related nodes and edges, with relationship meaning
   and provenance.

Every item carries authority, lifecycle state, provenance, release level,
version/revision, component scores, and a plain-language selection reason. The
bundle reports omitted-candidate counts, weak-evidence warnings, conflicts, and
abstention when it cannot support a useful answer.

Exit: the unified lexical view materially improves bundle recall over the Phase
1 baseline without release leakage or hidden authority flattening.

## Phase 3: Local Hybrid Retrieval

- Add a pluggable local embedding provider with model identity, model hash,
  dimensionality, chunking policy, normalization, and license recorded in the
  index manifest.
- Cache vectors by content and policy hash; invalidate deterministically.
- Fuse lexical, exact/alias, local-vector, and graph candidates with an
  explainable method such as reciprocal-rank fusion before testing learned or
  adaptive alternatives.
- Retain a fully functional lexical/graph path when the local embedding service
  is missing, slow, or incompatible.
- Compare benefit by intent class; do not retain semantic retrieval where its
  measured gain does not justify storage, latency, or maintenance cost.

Exit: candidate recall and bundle recall improve on held-out fixtures and
opt-in private replay, while local-only and fallback tests pass.

## Phase 4: Resumption Checkpoints and Recovery

### Structured checkpoint

At deterministic task boundaries, write a compact operational checkpoint with
task identity, objective, current phase, decisions, constraints, completed and
pending work, relevant source references, last verified repository revisions,
commands/tests run, blockers, and the next safe action. It references canonical
knowledge; it does not copy or promote it.

### Recovery segment

Where host hooks make interruption likely, maintain a bounded private segment
for otherwise-lost recent context. It must be secret-scanned, access-restricted,
size-limited, encrypted where the host supports it, and deleted by TTL or clean
completion. It must never enter search, embeddings, normal source-note import,
federation, or public export.

### Resume behavior

On resumption, retrieve the checkpoint first, validate repository/configuration
drift, then compile a resumption evidence bundle. If state is stale or missing,
say so and fall back to ordinary retrieval instead of inventing continuity.

Exit: interruption tests show that an assistant can state the objective,
decisions, completed work, current blocker, and next action without substantial
user re-orientation, and privacy/TTL tests show recovery data does not leak.

## Phase 5: Pilot Evaluation and Adoption

- Run the same retrieval contract across GroundRecall, Epistemap, Didactopus,
  and CiteGeist companion fixtures.
- Compare candidate recall with final bundle recall so a good internal hit that
  is dropped from context is visible as a selection failure.
- Archive immutable receipts containing code revision, corpus manifests,
  configuration, local embedding identity, prompts/query text, gold version,
  timing, and per-stage results.
- Review failures by intent and corpus before changing weights.
- Expand corpus registration only after the four pilots pass their acceptance
  gates.

## Repository Boundaries

- GroundRecall owns ingestion, authority/lifecycle policy, unified retrieval,
  bundle compilation, checkpoints, and private replay policy.
- Epistemap may provide neutral graph-context and assessment artifacts. It does
  not own ranking, promotion, or general memory authority.
- Didactopus is a learner-facing consumer. Retrieved prior work is context, not
  evidence that a learner has mastered anything.
- CiteGeist remains authoritative for bibliographic identity and review state.
  Citation topology is discovery context, not claim support or truth.

The bounded companion plans are:

- Epistemap:
  [`groundrecall-unified-retrieval-integration-plan.md`](../../Epistemap/docs/groundrecall-unified-retrieval-integration-plan.md)
- Didactopus:
  [`groundrecall-unified-retrieval-integration-plan.md`](../../Didactopus/docs/groundrecall-unified-retrieval-integration-plan.md)
- CiteGeist:
  [`groundrecall-unified-retrieval-integration-plan.md`](../../CiteGeist/docs/groundrecall-unified-retrieval-integration-plan.md)

## Risks and Stop Conditions

- Stop if reconciliation cannot account for every current record or rollback is
  untested.
- Stop if a unified view erases authority, review state, release level, or
  source revision.
- Stop if private replay or recovery material can enter ordinary indexes or
  exports.
- Stop if evaluation gold or expected answers contaminate retrieval inputs.
- Stop if local embeddings become a required service rather than an optional
  measured aid.
- Stop cross-repository abstraction if only GroundRecall needs the contract.

## Influences and Evidence Discipline

This plan adapts useful ideas from [GBrain](https://github.com/garrytan/gbrain):
canonical human-readable material with rebuildable projections, layered memory,
hybrid retrieval, evidence-oriented context compilation, checkpoints, and
real-query replay. It does not adopt GBrain's storage choices wholesale because
GroundRecall already has typed canonical records and stricter lifecycle,
provenance, and release policy.

Evaluation design also draws on
[gbrain-evals](https://github.com/garrytan/gbrain-evals), especially immutable
run artifacts and auditability. Headline results must not be treated as
authority: the repository's
[2026-08-31 audit](https://github.com/garrytan/gbrain-evals/blob/main/docs/audit/2026-08-31-eval-audit.md)
documents substantial corrections, including an erratum to a LongMemEval
claim. GroundRecall should therefore reproduce methods locally and preserve
receipts rather than importing performance claims.
