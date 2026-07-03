# Didactopus Bridge

This documents the `GroundRecall` side of the bridge into a learner-facing
`Didactopus` pack.

## Purpose

Use this when:

- you already have a reviewed concept in a canonical `GroundRecall` store
- your source material also exists as a normalized `doclift` bundle
- you want `Didactopus` to generate a learner-facing pack that carries the
  reviewed concept context along with the ordinary pack artifacts

`GroundRecall` remains the canonical reviewed knowledge layer.
`Didactopus` remains the learner-facing pack and workbench layer.

## Minimal Export

Export a pack-ready query bundle directly from the `GroundRecall` store:

```bash
groundrecall export /path/to/groundrecall-store /tmp/groundrecall-export \
  --pack-ready-concept channel-capacity
```

That writes:

- `/tmp/groundrecall-export/groundrecall_query_bundle.json`
- `/tmp/groundrecall-export/epistemap_graph.json`
- `/tmp/groundrecall-export/bayesian_reliability.md`

It also records the paths in `export_manifest.json`.

## End-To-End Bridge

The shortest full bridge path is:

```bash
doclift convert-dir /path/to/legacy-course /tmp/doclift-bundle --asset-root /path/to/legacy-course

didactopus doclift-bundle-groundrecall \
  /path/to/groundrecall-store \
  channel-capacity \
  /tmp/doclift-bundle \
  /tmp/didactopus-pack \
  --course-title "Example Course"
```

That command:

1. exports `groundrecall_query_bundle.json` for the selected concept
2. passes that file into the `Didactopus` `doclift` bundle demo workflow
3. writes a generated pack that includes the GroundRecall bundle as a declared
   supporting artifact

## Outputs

On the `GroundRecall` side:

- canonical store remains unchanged
- export directory contains `groundrecall_query_bundle.json`
- export directory contains `epistemap_graph.json` and
  `bayesian_reliability.md` for reviewable graph assessment context

On the `Didactopus` side:

- generated pack contains `groundrecall_query_bundle.json`
- the pack summary records that the GroundRecall bundle was included
- learner-workbench flows can consume the review and graph context from that
  bundle

## Why This Boundary Matters

This keeps responsibilities clean:

- `doclift` normalizes document corpora
- `GroundRecall` owns canonical reviewed concept/query context
- `Didactopus` owns learner-facing packs, workbenches, and pedagogy workflows

The bridge exists so those systems can cooperate without collapsing into one
repository boundary or one data model.

## Related Documentation

- [quickstart.md](quickstart.md)
- [architecture.md](architecture.md)
- `Didactopus`: `docs/groundrecall-bridge.md`
