# Architecture

`GroundRecall` is the grounded knowledge substrate in a larger stack:

- `GroundRecall`: canonical knowledge ingestion, promotion, query, export, and future sync
- `Didactopus`: learner-facing workflows and educational tooling
- `GenieHive`: model and routing layer where runtime assistant/service resolution is needed

For governed model access, GroundRecall treats the GenieHive Foundation gateway
profile as an external endpoint and policy boundary. GroundRecall does not own
GenieHive credentials, request audit logs, provider routing, or budget state.
See [geniehive-foundation-gateway.md](geniehive-foundation-gateway.md).

## Core Design

The system is built around one canonical flow:

1. ingest weakly structured sources
2. normalize them into stable knowledge objects
3. lint and queue them for review
4. promote reviewed objects into a canonical store
5. query and export promoted state

## Core Objects

The canonical store is built from these object families:

- `Source`
- `Fragment`
- `Artifact`
- `Observation`
- `Claim`
- `Concept`
- `Relation`
- `ReviewCandidate`
- `PromotionRecord`
- `GroundRecallSnapshot`

These objects are assistant-neutral. Assistant-specific formatting belongs at the adapter layer.

## Package Surface

The main standalone package surface is:

- `groundrecall.ingest`
- `groundrecall.lint`
- `groundrecall.models`
- `groundrecall.store`
- `groundrecall.promotion`
- `groundrecall.query`
- `groundrecall.export`
- `groundrecall.assistant_export`
- `groundrecall.inspect`
- `groundrecall.source_adapters.*`
- `groundrecall.assistants.*`

There are also compatibility-style helper modules prefixed with `groundrecall_` inside the package. Those exist because the standalone repo was extracted from an earlier monorepo layout.

## Source Adapters

Adapters handle source-shape-specific discovery and mapping while the downstream pipeline stays generic.

Current adapter families include:

- `llmwiki`
- `markdown_notes`
- `transcript`
- `didactopus_pack`

## Assistant Boundary

Assistant integration is intentionally outside the core store and query semantics.

The rule is:

- core `GroundRecall` owns truth, provenance, lifecycle, and retrieval semantics
- assistant adapters own presentation, bundle shaping, and tool-specific exports

Current adapters include:

- `codex`
- `claude_code`

## Alpha Boundary

The current alpha is strong enough for:

- local import and promotion
- canonical query and export
- assistant-neutral bundles
- assistant-targeted bundle generation

It is not yet complete for:

- multi-node sync and merge
- re-import/update semantics
- richer review adjudication
- large-scale distributed corpus integration
