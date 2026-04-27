# AI Knowledge Graph Adoption Plan

This document translates the feature set of
[`robert-mcdermott/ai-knowledge-graph`](https://github.com/robert-mcdermott/ai-knowledge-graph)
into concrete implementation tickets for the current local repositories:

- `GroundRecall`
- `Didactopus`
- `doclift`

The goal is not to copy that repository's data model directly.

The useful import is:

- chunk-aware extraction
- entity standardization
- relation suggestion
- graph inspection and review affordances

The main thing to avoid is treating raw extracted SPO triples as canonical truth.

## Design Rules

1. Keep canonical storage typed and provenance-first.
2. Treat extracted triples as candidate claims/relations, not promoted facts.
3. Keep LLM extraction optional and reviewable.
4. Keep `doclift` deterministic by default.
5. Put graph extraction in `GroundRecall` first, then expose downstream affordances in `Didactopus`.

## Repo Roles

### GroundRecall

Primary fit for:

- candidate claim extraction
- concept alias normalization
- candidate relation inference
- graph diagnostics
- review queue generation

Key current modules:

- [src/groundrecall/ingest.py](/home/netuser/bin/GroundRecall/src/groundrecall/ingest.py)
- [src/groundrecall/models.py](/home/netuser/bin/GroundRecall/src/groundrecall/models.py)
- [src/groundrecall/source_adapters](/home/netuser/bin/GroundRecall/src/groundrecall/source_adapters)
- [src/groundrecall/groundrecall_source_adapters/doclift_bundle.py](/home/netuser/bin/GroundRecall/src/groundrecall/groundrecall_source_adapters/doclift_bundle.py)
- [src/groundrecall/review_export.py](/home/netuser/bin/GroundRecall/src/groundrecall/review_export.py)

### Didactopus

Primary fit for:

- graph workbench visualization
- concept merge/split suggestions
- graph-aware review overlays
- learner-facing graph inspection built on grounded artifacts

Key current modules:

- [src/didactopus/knowledge_graph.py](/home/netuser/bin/Didactopus/src/didactopus/knowledge_graph.py)
- [src/didactopus/graph_builder.py](/home/netuser/bin/Didactopus/src/didactopus/graph_builder.py)
- [src/didactopus/graph_retrieval.py](/home/netuser/bin/Didactopus/src/didactopus/graph_retrieval.py)
- [src/didactopus/learner_workbench.py](/home/netuser/bin/Didactopus/src/didactopus/learner_workbench.py)
- [src/didactopus/review_export.py](/home/netuser/bin/Didactopus/src/didactopus/review_export.py)
- [src/didactopus/main.py](/home/netuser/bin/Didactopus/src/didactopus/main.py)

### doclift

Primary fit for:

- deterministic chunk metadata
- optional extraction-friendly sidecars
- optional graph preview artifacts

Key current modules:

- [src/doclift/convert.py](/home/netuser/bin/doclift/src/doclift/convert.py)
- [src/doclift/schemas.py](/home/netuser/bin/doclift/src/doclift/schemas.py)
- [src/doclift/cli.py](/home/netuser/bin/doclift/src/doclift/cli.py)

## Phase 1: GroundRecall Candidate Graph Import

### Ticket GR-1: Add chunk-aware candidate extraction layer

Outcome:

- ingest text artifacts into stable chunks
- extract candidate observations/claims/concepts/relations per chunk
- write reviewable import artifacts

Suggested implementation:

- add `src/groundrecall/candidate_graph.py`
- add `src/groundrecall/extraction_chunks.py`

Responsibilities:

- split long text into bounded chunks with overlap
- assign stable `chunk_id`
- keep chunk-to-artifact provenance
- emit candidate records with `support_kind="derived_from_page"` or `support_kind="inferred"`

CLI:

- extend `groundrecall import` with:
  - `--extract-graph`
  - `--chunk-size`
  - `--chunk-overlap`
  - `--extractor none|heuristic|llm`

Acceptance criteria:

- import still works without graph extraction
- import artifacts include chunk-backed candidate claims and relations when enabled
- all extracted candidates preserve artifact and chunk provenance

### Ticket GR-2: Add deterministic entity/concept standardization

Outcome:

- alias clusters for near-duplicate concepts before review

Suggested implementation:

- add `src/groundrecall/entity_standardization.py`

Responsibilities:

- normalize punctuation/case
- trim stopwords conservatively
- group obvious aliases
- emit alias-cluster review candidates when confidence is not high enough for direct merge

Data shape:

- enrich `ConceptRecord.aliases`
- optionally emit a new review payload section such as `alias_clusters`

Acceptance criteria:

- obvious duplicates like minor punctuation/case variants collapse deterministically
- ambiguous clusters remain reviewable rather than auto-merged

### Ticket GR-3: Add inferred relation candidates

Outcome:

- lexical and structural hints become review queue items

Suggested implementation:

- add `src/groundrecall/relation_inference.py`

Inference types:

- lexical co-occurrence hints
- transitive prerequisite/support hints
- repeated same-source concept pair hints

Important restriction:

- inferred relations stay `draft` or `triaged`
- they are never silently promoted to canonical relations

Acceptance criteria:

- inferred relations appear in import artifacts with explicit provenance
- review queue distinguishes grounded vs inferred edges

### Ticket GR-4: Add graph diagnostics and inspector output

Outcome:

- maintainers can inspect graph shape before promotion

Suggested implementation:

- add `src/groundrecall/graph_diagnostics.py`
- extend [inspect.py](/home/netuser/bin/GroundRecall/src/groundrecall/inspect.py)

Diagnostics:

- disconnected components
- orphan concepts
- claims with no strong support
- bridge concepts
- dense noisy clusters

CLI:

- `groundrecall inspect ... --graph`
- `groundrecall export ... --include-graph-diagnostics`

Acceptance criteria:

- graph diagnostics appear in machine-readable JSON
- review operators can identify noisy imports quickly

### Ticket GR-5: Add review export support for candidate graph artifacts

Outcome:

- current review flows can consume extracted graph candidates

Suggested implementation:

- extend [review_export.py](/home/netuser/bin/GroundRecall/src/groundrecall/review_export.py)
- extend review app payloads under [review_app](/home/netuser/bin/GroundRecall/src/groundrecall/review_app)

UI payload features:

- candidate relation cards
- alias-cluster cards
- chunk evidence preview
- inferred/grounded badges

Acceptance criteria:

- review bundle includes graph-candidate triage data
- no assistant-specific assumptions leak into canonical records

## Phase 2: Didactopus Graph Review And Workbench Improvements

### Ticket DT-1: Add review-oriented graph overlays

Outcome:

- graph visualizations expose quality problems, not just structure

Suggested implementation:

- extend [knowledge_graph.py](/home/netuser/bin/Didactopus/src/didactopus/knowledge_graph.py)
- extend [graph_retrieval.py](/home/netuser/bin/Didactopus/src/didactopus/graph_retrieval.py)

Overlay ideas:

- edge grounding status
- concept confidence/review status
- weakly grounded concept markers
- disconnected concept islands

Acceptance criteria:

- exported graph JSON can distinguish grounded, heuristic, and inferred links
- downstream visual layers can highlight fragile concepts

### Ticket DT-2: Add concept consolidation suggestions

Outcome:

- reviewers get merge/split suggestions based on graph and text structure

Suggested implementation:

- extend [graph_builder.py](/home/netuser/bin/Didactopus/src/didactopus/graph_builder.py)
- extend [review_export.py](/home/netuser/bin/Didactopus/src/didactopus/review_export.py)

Input signals:

- title similarity
- shared source lessons
- overlapping prerequisite neighborhoods
- overlapping mastery signals

Acceptance criteria:

- review exports include merge suggestions
- suggested merges remain proposals, not automatic edits

### Ticket DT-3: Add learner-workbench graph inspection modes

Outcome:

- learner and reviewer can inspect why concepts exist and how they connect

Suggested implementation:

- extend [learner_workbench.py](/home/netuser/bin/Didactopus/src/didactopus/learner_workbench.py)
- extend backend route [api.py](/home/netuser/bin/Didactopus/src/didactopus/api.py)

Views:

- concept neighborhood
- source-fragment grounding trail
- alternate supporting lessons
- fragile or noisy concept warnings

Acceptance criteria:

- workbench can show source-grounded concept neighborhoods
- concept provenance is inspectable without raw JSON digging

### Ticket DT-4: Add graph diagnostics to `doclift-bundle` pack generation

Outcome:

- `doclift -> Didactopus` imports surface noisy graph structure early

Suggested implementation:

- extend [doclift_bundle_demo.py](/home/netuser/bin/Didactopus/src/didactopus/doclift_bundle_demo.py)
- extend [main.py](/home/netuser/bin/Didactopus/src/didactopus/main.py) `doclift-bundle`

Artifacts:

- `graph_diagnostics.json`
- `concept_merge_suggestions.json`

Acceptance criteria:

- importing a `doclift` bundle produces diagnostics alongside `knowledge_graph.json`
- review workflow can consume those diagnostics

## Phase 3: doclift Optional Extraction-Friendly Sidecars

### Ticket DL-1: Emit stable chunk metadata

Outcome:

- downstream systems can import `doclift` bundles without re-segmenting blindly

Suggested implementation:

- extend [schemas.py](/home/netuser/bin/doclift/src/doclift/schemas.py)
- extend [convert.py](/home/netuser/bin/doclift/src/doclift/convert.py)

Artifacts:

- `document.chunks.json`

Fields:

- `chunk_id`
- `line_start`
- `line_end`
- `section_labels`
- `text`

Acceptance criteria:

- bundle remains valid without downstream AI extraction
- chunk metadata is deterministic across repeat runs

### Ticket DL-2: Add optional graph-preview sidecars

Outcome:

- operators can inspect likely extracted structure at the bundle stage

Suggested implementation:

- add optional post-processing module such as `src/doclift/graph_preview.py`

Artifacts:

- `document.entities.json`
- `document.relations.json`
- optional `bundle_graph_preview.json`

CLI:

- extend `doclift convert`
- extend `doclift convert-dir`
- flags:
  - `--graph-preview`
  - `--graph-preview-mode heuristic|llm`

Important restriction:

- these are preview/debug artifacts only
- they are not the bundle's canonical semantics

Acceptance criteria:

- graph preview can be disabled entirely
- default conversion remains deterministic and lightweight

### Ticket DL-3: Add HTML inspection output for graph previews

Outcome:

- maintainers can inspect extracted structure before import

Suggested implementation:

- add `doclift preview-graph /path/to/bundle`

Acceptance criteria:

- preview HTML references chunk ids and source lines
- graph preview is visibly separate from conversion success reporting

## Cross-Repo Integration Tickets

### Ticket X-1: `doclift -> GroundRecall` candidate-graph import path

Outcome:

- `GroundRecall` can consume `doclift` chunk metadata directly

Modules:

- `doclift` emits `document.chunks.json`
- `GroundRecall` `doclift_bundle` adapter imports it

Acceptance criteria:

- `groundrecall import /path/to/doclift-bundle --extract-graph`
- uses `doclift` chunk ids instead of re-splitting markdown where available

### Ticket X-2: Shared graph diagnostics vocabulary

Outcome:

- the three repos use compatible terminology for quality signals

Suggested shared diagnostic keys:

- `orphan_concept`
- `weak_grounding`
- `inferred_relation`
- `alias_cluster`
- `disconnected_component`
- `bridge_concept`
- `high_fanout_noisy_concept`

Acceptance criteria:

- review and export layers can exchange diagnostics without brittle custom mapping

## Recommended Build Order

1. `GR-1`
2. `GR-2`
3. `GR-3`
4. `GR-4`
5. `X-1`
6. `DT-1`
7. `DT-2`
8. `DL-1`
9. `DL-2`
10. `DT-4`

## Non-Goals

- replacing GroundRecall canonical models with freeform triples
- forcing LLM extraction into `doclift` core conversion
- auto-promoting inferred relations
- making Didactopus depend on a graph preview layer to ingest ordinary packs

## Immediate Next Step

If only one milestone is funded first, build:

- `GR-1`
- `GR-2`
- `X-1`

That gives the highest leverage path:

- `doclift` stays deterministic
- `GroundRecall` gains useful graph-candidate import
- `Didactopus` can later consume cleaner grounded artifacts without architectural churn
