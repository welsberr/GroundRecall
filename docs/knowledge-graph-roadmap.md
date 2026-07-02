# Knowledge Graph Roadmap

GroundRecall has a live provenance-first graph substrate, but not yet a full
AI knowledge graph extraction and reasoning layer. The current system stores
typed `Concept`, `Claim`, `Relation`, `Observation`, `Artifact`, and provenance
records; can query concept neighborhoods; can expand search results with
bounded graph associations; and emits import-time graph diagnostics for review.

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
- Support extractor modes: `none`, `heuristic`, and later `llm`.
- Keep inferred candidates in draft/triage state.
- Current heuristic mode emits draft `co_occurs_with` relation candidates from
  existing concept co-mentions in imported observations, with observation
  evidence ids and `support_kind=inferred`.

### P3: Entity And Concept Standardization

- Add deterministic alias normalization for obvious duplicates.
- Emit review candidates for ambiguous alias clusters.
- Preserve original surface forms and source locations.
- Avoid silent merges when evidence is weak.

### P4: Relation Inference And Review

- Add relation inference from explicit links, repeated co-occurrence,
  prerequisite cues, support/contradiction cues, and citation metadata.
- Mark relation provenance as `direct_source`, `derived_from_page`, or
  `inferred`.
- Extend review payloads with candidate relation cards and evidence previews.

### P5: Graph Diagnostics And Quality Controls

- Expand diagnostics beyond connected components and bridges:
  weak grounding, inferred-edge density, high-fanout noisy concepts,
  unsupported claims, contradiction clusters, and stale/superseded neighborhoods.
- Add `groundrecall export --include-graph-diagnostics`.
- Add quality thresholds usable by review and CI.

### P6: Downstream Interchange

- Add graph JSON export for Didactopus workbenches.
- Consider JSON-LD/RDF/GraphML only after the internal graph semantics are
  stable.
- Keep assistant-specific exports separate from canonical graph semantics.

## Non-Goals For The First Pass

- Do not introduce a graph database before file-backed canonical objects and
  JSON exports prove insufficient.
- Do not auto-promote LLM-extracted triples.
- Do not make Didactopus depend on graph extraction for ordinary pack import.
- Do not weaken provenance requirements to maximize edge count.
