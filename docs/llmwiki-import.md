# llmwiki Import

`GroundRecall` treats `llmwiki` as one important source shape, not as the defining architecture.

An imported `llmwiki` tree is treated as:

- raw source material
- prior synthesized artifacts
- candidate claims and concepts
- provenance that needs to be normalized and reviewed

Compiled wiki pages are useful artifacts, but they are not automatically promoted as canonical truth.

## Import Modes

### `archive`

- preserve source material with minimal interpretation
- index and normalize without assuming promotion readiness
- useful for long-tail historical corpora

### `quick`

- fast bootstrap mode
- extracts candidate concepts, claims, and relations heuristically
- useful when getting an old corpus into GroundRecall quickly matters more than perfect grounding

### `grounded`

- stricter mode
- expects better provenance and cleaner support signals
- better fit for shared or promoted knowledge

## Import Flow

The normalized import flow is:

1. capture source files
2. discover and classify artifacts
3. segment content into observations
4. normalize claims, concepts, and relations
5. lint the import
6. emit a review queue and review bundle
7. promote reviewed artifacts into the canonical store

## Commands

```bash
groundrecall import /path/to/llmwiki --mode archive
groundrecall import /path/to/llmwiki --mode quick
groundrecall import /path/to/llmwiki --mode grounded

groundrecall lint imports/<import-id>
groundrecall promote imports/<import-id> store/
groundrecall export store/ exports/groundrecall --concept channel-capacity
```

## Current Heuristics

Today’s importer already supports:

- `raw/` and `wiki/` discovery
- markdown and log segmentation
- claim extraction with inline contradiction and supersession markers
- review queue generation
- review bundle export

Areas still planned:

- stronger re-import/update semantics
- more robust transcript and semi-structured document handling
- stronger large-corpus extraction and consolidation

## Recommended Promotion Rule

Treat imported wiki pages as derived artifacts.

That means:

- preserve them
- mine them for claims and concepts
- review what matters
- promote canonical claims and concepts into the store

This is the main difference between `GroundRecall` and a plain markdown wiki.
