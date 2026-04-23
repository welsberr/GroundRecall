# Sync Roadmap

The current standalone alpha is local-first. Sync and merge are planned next-stage features.

## Goal

Support these use cases cleanly:

- one user across multiple machines
- teams with shared and individual knowledge
- parallel corpus transformation and consolidation

## Planned Model

The intended model is:

- append-only event capture at the edge
- canonical promoted store as the durable reviewed state
- generated exports and assistant bundles as derived artifacts

This avoids treating compiled wiki pages or generated bundles as merge primitives.

## Likely Local Layout

```text
.groundrecall/
  events/
  imports/
  store/
  exports/
```

## Planned Phases

### Phase 1: Re-import And Update Semantics

- import the same source tree repeatedly without duplicating everything
- support import lineage and supersession
- track object continuity across imports

### Phase 2: Event Log Capture

- record machine-local observations and import events
- distinguish machine-local state from promoted shared state
- preserve provenance and timestamps explicitly

### Phase 3: Merge And Consolidation

- merge append-only events from multiple machines
- consolidate draft claims and review candidates
- preserve contradiction and supersession history

### Phase 4: Shared And Private Scopes

- private notes and private candidate knowledge
- shared promoted knowledge
- controlled promotion from private to shared

### Phase 5: Team And Corpus Workflows

- parallel ingestion over large corpora
- coordinated claim review and adjudication
- export of consolidated assistant-neutral snapshots

## Non-Goals For The Current Alpha

The current repo does not yet provide:

- real-time networked sync
- conflict-free replicated data types
- hosted review services

The next useful milestone is a practical local event-log and re-import model, not a full distributed platform in one step.
