# Knowledge Graph Roadmap

## Top Priority: Graph/Epistemap Capability Before Performance

The current preprint timing pass found that full-store graph search can be
slow and can return sparse neighborhoods for broad project queries. The first
priority is therefore not query-speed optimization. It is to make sure the
graph projection is semantically useful and sufficiently connected.

Immediate graph/Epistemap work should proceed in this order:

1. measure graph density, claim/concept coverage, relation status/type
   distributions, and root-neighborhood coverage;
2. add a store-level graph-enrichment/backfill path over existing claims,
   observations, concepts, and citations, so missing semantic edges can be
   proposed without ordinary source re-ingestion;
3. audit which import, review, contradiction, supersession, bibliography, and
   Epistemap adapter paths generate edges;
4. improve edge generation and review for the relations that matter to
   governed memory: claim-to-concept, observation-to-claim, claim-to-claim,
   concept-to-concept, source-to-claim, contradiction, supersession, citation,
   and provenance edges;
5. align GroundRecall graph bundles with Epistemap so confidence,
   contradiction, temporal validity, and provenance remain visible in graph
   operations;
6. optimize graph traversal only after graph coverage is adequate.

This priority follows the design rule that graph databases, caches, and
precomputed adjacency indexes are projections. They should accelerate a useful
graph, not conceal an under-generated one.

GroundRecall has a live provenance-first graph substrate, but not yet a full
AI knowledge graph extraction and reasoning layer. The current system stores
typed `Concept`, `Claim`, `Relation`, `Observation`, `Artifact`, and provenance
records; can query concept neighborhoods; can expand search results with
bounded graph associations; and emits import-time graph diagnostics for review.

Most of the original P0–P7 path now has an initial implementation. This
roadmap therefore serves as a focused capability and maintenance record beneath
the primary [memory lifecycle roadmap](memory-lifecycle-roadmap.md). New graph
work should be justified by review quality, governed retrieval, or measured
downstream benefit rather than graph size alone.

This document defines the implementation path from that substrate to full
knowledge graph capability.

## Current Live Capability

- Canonical typed store for concepts, claims, relations, observations,
  artifacts, sources, review candidates, promotions, and snapshots.
- Concept-neighborhood query through `groundrecall query`.
- Claim contradiction and supersession links.
- Provenance and grounding status for claims and observations.
- Import-time `graph_diagnostics.json`.
- Review queue graph triage signals such as `bridge_concept`,
  `isolated_concept`, and `small_component`.
- Search-index expansion with linked claims, concepts, observations, artifacts,
  relations, and review candidates.
- Store-level graph diagnostics through `groundrecall inspect --graph`.
- Graph discovery search through `groundrecall query STORE TEXT --kind
  graph-search`, which maps full-text hits to candidate root concepts and
  returns bounded graph bundles.

## Target Capability

Full GroundRecall knowledge graph capability means:

1. Source-grounded graph extraction that preserves chunk/artifact provenance.
2. Reviewable candidate entities, concepts, claims, and relations.
3. Deterministic concept/entity standardization before any optional LLM pass.
4. Explicit distinction between grounded, derived, and inferred edges.
5. Store-level graph inspection, traversal, and export.
6. Review workflows that make graph quality problems visible.
7. Interchange formats that downstream tools such as Didactopus can consume.

The design rule remains: extracted triples are candidates, not canonical truth,
until reviewed or promoted.

## Recommended Next Graph Work

- Implement `groundrecall graph augment/backfill` as the next coding priority.
  It should scan the existing store, generate candidate semantic
  `RelationRecord`s and review candidates, and avoid requiring source
  re-ingestion when claims, observations, and concept assignments are already
  present.
- Treat ordinary re-ingestion as a fallback for thin or defective extraction,
  not as the default path for missing edges.
- Separate three graph layers in diagnostics and query output:
  reviewed semantic relations, reviewable candidate semantic relations, and
  derived evidence projection edges.
- Extend the existing heuristic co-mention extractor into a reusable backfill
  component, then add higher-value deterministic passes for claim/concept
  phrasing, contradiction/supersession fields, citation/source anchors,
  definition/qualification cues, and temporal validity cues.
- Add temporal validity and `as_of` traversal after the canonical bitemporal
  model is implemented.
- Include exact record versions or hashes in exported graph bundles.
- Record why graph expansion selected a node for an assistant context package.
- Evaluate FTS-only, graph-expanded, and hybrid retrieval with the same model
  and corpus.
- Treat sparse root neighborhoods as graph-generation defects to investigate
  before treating them as performance problems.
- Add poisoning and scope-leakage fixtures for inferred edges and graph
  traversal.
- Keep graph databases and embedding indexes as rebuildable projections unless
  measured scale or latency demonstrates the need for a new canonical store.

### CiteGeist Bibliography Graph Interchange

Coordinate bibliography graph work with CiteGeist's
`docs/epistemap-knowledge-graph-roadmap.md` and Epistemap's confidence
overhaul.

- Preserve CiteGeist work, relation, provenance, and assessment IDs.
- Import metadata and abstracts as observations rather than promoted truth
  claims.
- Treat citation and topical relations as discovery context, not claim support.
- Import only reviewed source-anchor relations as support/challenge candidates.
- Keep GroundRecall claim promotion separate from CiteGeist bibliographic
  review.
- Retain correction, retraction, supersession, and historical availability
  events for `as_of` queries.

## Priority Path

### P0: Expose The Existing Graph Substrate

Status: implemented in this pass.

- Document the live graph substrate in `README.md`.
- Add store-level graph diagnostics to `groundrecall inspect --graph`.
- Keep output machine-readable JSON.

This step makes the current graph behavior visible without changing import or
promotion semantics.

### P1: Canonical Graph Query And Export

Status: bounded graph query bundle and guardrailed graph bundle export
implemented.

- Add a first-class graph query mode for bounded concept traversal:
  `groundrecall query STORE CONCEPT --kind graph`.
- Return nodes and edges with record kind, status, provenance, grounding, and
  evidence ids.
- Include relevant claims, supporting observations, and graph diagnostics.
- Add regression tests for traversal depth, status filtering, and provenance.
- Export public graph bundles through `groundrecall export --graph-concept`,
  with node/edge wrappers pruned by public export guardrails and diagnostics
  recomputed after filtering.

### P2: Candidate Graph Extraction

- Status: initial heuristic relation extraction implemented.
- Add an opt-in `groundrecall import --extract-graph` flag.
- Add deterministic chunk-backed extraction before any optional LLM extractor.
- Emit candidate concepts, claims, and relations with chunk provenance.

### P2A: Store-Level Graph Enrichment And Backfill

Status: initial implementation expanded. `graph-augment` now has a
`graph-backfill` CLI alias, dry-run-by-default output, idempotent candidate
writes, layer diagnostics, and an `observation-cooccurrence` strategy that
reuses import-time heuristic graph extraction over existing store observations.
`graph-maintenance` now runs one bounded resumable slice, records state, and
exits so periodic schedulers can keep graph maintenance load bounded.
Augmentation output now reports raw candidate counts, candidates below evidence
threshold, skipped duplicate relation counts, limit omissions, relation type
counts, and write counts. The `claim-links` strategy now emits directed
claim-to-claim contradiction and supersession relation candidates from explicit
stored claim fields. The opt-in `claim-contradiction-cues` strategy now emits
reviewable `claim_may_contradict_claim` candidates for same-concept claim pairs
with opposing negation cues and high normalized text overlap. Because semantic
pair scanning can be expensive on large stores, the strategy is opt-in,
signature-bucketed, and bounded by `--max-pair-checks`; it is not part of the
default periodic maintenance strategy list. The `claim-support-anchors`
strategy now emits `observation_supports_claim` candidates from existing claim
source-observation links and keeps that relation type in the support/provenance
diagnostic layer rather than the concept-semantic graph layer.

The current store already contains abundant governed memory structure in
claims, observations, concept assignments, contradiction fields, supersession
fields, source artifacts, citations, and review candidates. Missing graph
edges should therefore be addressed first by enrichment/backfill over existing
records, not by broad source re-ingestion.

Implementation requirements:

- Add a `groundrecall graph-augment` or `groundrecall graph-backfill` command
  that scans the canonical store and writes only draft/candidate relations plus
  review candidates by default. Initial implementation exists.
- Reuse import-time heuristic graph extraction logic where applicable, but make
  it callable against existing stored observations and concepts. Initial
  implementation exists for observation co-mentions.
- Generate relation candidates for:
  - concept co-mentions in observations;
  - explicit claim-to-claim contradiction and supersession fields; initial
    implementation exists through `--strategy claim-links`;
  - source/artifact/observation anchors for claim support; initial observation
    support implementation exists through `--strategy claim-support-anchors`;
  - conservative semantic contradiction cues; initial opt-in implementation
    exists through `--strategy claim-contradiction-cues` with normalized
    signature buckets and a pair-check budget;
  - source/artifact/observation anchors for claim support;
  - citation/source-anchor links;
  - definition, qualification, distinction, dependency, and temporal-validity
    cues where deterministic patterns are strong enough.
- Record extraction method, evidence ids, support kind, grounding status,
  rationale, and confidence/provenance metadata for every candidate relation.
- Deduplicate against existing reviewed, promoted, draft, and rejected
  relations before writing new candidates.
- Route generated candidates into the relation review workflow rather than
  silently promoting them.
- Add dry-run output with candidate counts by relation type, evidence coverage,
  skipped duplicate counts, and examples for review. Initial output includes
  raw candidate counts, candidate counts after filters/limits, relation type
  counts, skipped duplicate counts, below-threshold counts, limit omissions,
  evidence counts, relation examples, write summary, and layer diagnostics.
- Add diagnostics that report reviewed semantic edges, candidate semantic
  edges, projection edges, and unresolved sparse concepts separately. Initial
  augmentation output distinguishes reviewed semantic relations, candidate
  semantic relations, and query-time projection edges.
- Add a resumable maintenance runner for scheduled operation. Initial
  implementation exists as `groundrecall graph-maintenance`: it chooses one
  strategy per invocation, applies a candidate limit, records JSON state, and
  rotates to the next configured strategy after applied runs.

Acceptance tests:

- Existing stores can produce candidate semantic edges without re-ingesting
  source files. Covered for observation co-mentions.
- Re-running the backfill is idempotent. Covered for claim co-occurrence.
- Periodic maintenance can process a bounded slice and resume from persisted
  state. Covered for strategy rotation and CLI dispatch.
- Rejected/private records do not generate public exportable candidates.
- Public export guardrails exclude draft/private candidate edges and their
  evidence when appropriate.
- Diagnostics distinguish sparse reviewed semantics from available projection
  structure and candidate semantic structure.
- Support extractor modes: `none`, `heuristic`, and later `llm`.
- Keep inferred candidates in draft/triage state.
- Current heuristic mode emits draft `co_occurs_with` relation candidates from
  existing concept co-mentions in imported observations, with observation
  evidence ids and `support_kind=inferred`.

### P3: Entity And Concept Standardization

- Status: initial auditable concept standardization reporting implemented.
- Add deterministic alias normalization for obvious duplicates.
- Emit review candidates for ambiguous alias clusters.
- Preserve original surface forms and source locations.
- Avoid silent merges when evidence is weak.
- Current import output writes `concept_standardization.json`, records
  deterministic merge groups, reports ambiguous alias candidates without
  merging them, and surfaces `concept_deterministic_merge` /
  `concept_alias_candidate` codes in the review queue.

### P4: Relation Inference And Review

- Status: initial relation review lane and canonical-store batch review
  implemented.
- Add relation inference from explicit links, repeated co-occurrence,
  prerequisite cues, support/contradiction cues, and citation metadata.
- Mark relation provenance as `direct_source`, `derived_from_page`, or
  `inferred`.
- Extend review payloads with candidate relation cards and evidence previews.
- Current review sessions include `relation_reviews`; the review workspace
  exposes a relation lane with endpoint labels, provenance class, queue codes,
  evidence previews, and editable status/notes. Promotion respects explicit
  relation review rejection.
- Canonical-store relation review can now be scripted with
  `groundrecall relation-review STORE`, which lists reviewable relation
  candidates and applies JSON decision batches that update relation status,
  optional relation type, review candidate status/rationale, and promotion
  audit records.

### P5: Graph Diagnostics And Quality Controls

- Status: initial graph quality diagnostics implemented.
- Expand diagnostics beyond connected components and bridges:
  weak grounding, inferred-edge density, high-fanout noisy concepts,
  unsupported claims, contradiction clusters, and stale/superseded neighborhoods.
- Add `groundrecall export --include-graph-diagnostics`.
- Add quality thresholds usable by review and CI.
- Current graph diagnostics include `quality_summary`, `relation_quality`,
  `claim_quality`, `concept_quality`, and `quality_controls` sections.
  Import, inspect, query, review, and public graph export paths recompute these
  diagnostics with the available filtered claims and observations.
- Claim diagnostics now distinguish raw contradiction links from first-class
  contradiction cases, flag explicit contradiction links that lack a case, flag
  cases that reference missing claims, and prioritize open cases involving
  promoted claims for adjudication.
- Contradiction review now has a CLI workflow for syncing explicit links into
  cases, listing case batches, and recording adjudications while preserving the
  disagreement history.
- Canonical exports can now write filtered `graph_diagnostics.json` through
  `groundrecall export --include-graph-diagnostics`.
- Store inspection supports compact active graph diagnostics through
  `groundrecall inspect STORE --graph-summary`, keeping top-level store counts
  while returning summarized components, relation quality, claim quality,
  high-fanout concepts, and quality-control flags.

### P6: Downstream Interchange

- Status: initial JSON graph interchange export implemented.
- Add graph JSON export for Didactopus workbenches.
- Consider JSON-LD/RDF/GraphML only after the internal graph semantics are
  stable.
- Keep assistant-specific exports separate from canonical graph semantics.
- Canonical exports can now write `graph_interchange.json` through
  `groundrecall export --include-graph-interchange`; the bundle contains
  guardrailed nodes, edges, claims, observations, diagnostics, and consumer
  notes for downstream graph-aware workbenches.

### P7: Graph Discovery Search

- Status: initial graph-search bundle implemented.
- Add a mode that lets users start from ordinary topic text rather than a known
  concept id.
- Use the full-text index plus bounded graph association expansion to map
  matching concepts, claims, relations, artifacts, observations, and source
  notes onto candidate root concepts.
- Return root concept match sources and existing depth-limited graph bundles,
  preserving graph diagnostics and provenance semantics.
- Current query syntax is `groundrecall query STORE TEXT --kind graph-search`
  with `--graph-limit`, `--limit`, `--depth`, `--corpus`, and `--object-kind`
  controls.
- Graph search now gives direct concept/title hits a supplemental retrieval pass
  and ranks candidate roots by direct concept matches, query-token overlap, and
  direct-vs-associated match evidence before falling back to FTS score.
- Graph bundles now expose derived evidence projection nodes and edges for
  claim-about-concept, observation-supports-claim, claim-contradicts-claim, and
  claim-supersedes-claim links. These projection edges make abundant governed
  memory structure visible while preserving the distinction from reviewed
  semantic `RelationRecord` edges.

## Non-Goals For The First Pass

- Do not introduce a graph database before file-backed canonical objects and
  JSON exports prove insufficient.
- Do not auto-promote LLM-extracted triples.
- Do not make Didactopus depend on graph extraction for ordinary pack import.
- Do not weaken provenance requirements to maximize edge count.
