# Search Responsiveness

GroundRecall can grow past the point where repeated full JSON and source-note scans are pleasant. The first responsiveness layer is a local SQLite FTS5 index over canonical records and source notes.

## Implemented Layer

The local index lives under the store:

```text
.groundrecall/store/.index/groundrecall-search.sqlite
```

It indexes:

- sources
- fragments
- artifacts
- observations
- claims
- concepts
- relations
- review candidates
- promotions
- sibling `source-notes/*.md` files

Build or rebuild it:

```bash
groundrecall index ~/.groundrecall/store --rebuild
```

Search through the normal query command:

```bash
groundrecall query ~/.groundrecall/store "reasoning scaffold" --kind search
groundrecall query ~/.groundrecall/store "prefix caching" --kind search --object-kind source_note
```

The index is intentionally local and dependency-light. It uses Python's standard `sqlite3` module with FTS5, so it does not require an embedding service or network access.

## Why FTS First

Semantic embeddings are useful, but they add model choice, vector storage, refresh policy, and possible GPU/CPU service overhead. FTS5 gives an immediate improvement for:

- exact project names
- file paths
- source-note titles
- claim text
- concept aliases
- operational terms

It also creates a stable document inventory that can later receive embedding vectors.

## Next Layer: Associative Search

Graph-aware expansion now runs for normal `--kind search` query bundles:

1. Run FTS over claims, concepts, and source notes.
2. For concept hits, expand to linked claims, source artifacts, relations, and review candidates.
3. For claim hits, expand to concepts, source observations, supporting fragments, linked claims, and review candidates.
4. For observation and artifact hits, expand across their source/support chain.
5. For source-note hits, surface promoted claims or observations that cite the same path when such canonical links exist.

This is more predictable than opaque semantic search and fits GroundRecall's existing promoted-object model.

The result payload includes an `associations` map keyed by the matched `doc_key`.
Direct index search can still omit expansion for maximum speed:

```bash
groundrecall index ~/.groundrecall/store "host profile" --kind concept
groundrecall index ~/.groundrecall/store "host profile" --kind concept --expand
```

## Later Layer: Embeddings

Embeddings should be added only after FTS and graph expansion have clear gaps. A good embedding layer should:

- run locally
- cache vectors per indexed document row
- store model name and vector dimensionality
- rebuild only changed rows
- combine vector similarity with FTS and graph signals
- never replace provenance checks

Embeddings are best treated as recall expansion, not authority.
