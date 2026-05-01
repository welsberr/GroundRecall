# Quickstart

`GroundRecall` is a local-first grounded knowledge substrate for `llmwiki++`-style workflows.

This quickstart assumes a fresh checkout of the standalone repository.

## Install

```bash
pip install -e .
groundrecall --help
```

You can also use the module entry point:

```bash
PYTHONPATH=src python -m groundrecall --help
```

## Import A Knowledge Source

Fast import from an `llmwiki`-style tree:

```bash
groundrecall import /path/to/llmwiki --mode quick
```

More conservative import with stronger grounding expectations:

```bash
groundrecall import /path/to/llmwiki --mode grounded
```

The importer writes normalized artifacts under `imports/<import-id>/`.

Import from a normalized `doclift` bundle:

```bash
groundrecall import /path/to/doclift-bundle --mode quick
```

This path is intended for legacy-document corpora that were first normalized by
`doclift`. If you want a learner-facing pack first, use Didactopus in between:

```bash
doclift convert-dir /path/to/legacy-course /tmp/doclift-bundle --asset-root /path/to/legacy-course
didactopus doclift-bundle /tmp/doclift-bundle /tmp/didactopus-pack --course-title "Example Course"
groundrecall import /tmp/doclift-bundle --mode quick
```

## Review And Promote

Inspect the import outputs:

```bash
groundrecall lint imports/<import-id>
```

Promote the imported review artifacts into a canonical store:

```bash
groundrecall promote imports/<import-id> store/
```

## Query The Canonical Store

Query a concept:

```bash
groundrecall query store/ channel-capacity
```

Inspect the overall store:

```bash
groundrecall inspect store/
```

## Export

Export assistant-neutral artifacts:

```bash
groundrecall export store/ exports/groundrecall --concept channel-capacity
```

Export a pack-ready `groundrecall_query_bundle.json` for `Didactopus`:

```bash
groundrecall export store/ exports/groundrecall --pack-ready-concept channel-capacity
```

Export assistant-targeted bundles:

```bash
groundrecall assistant-export store/ codex exports/codex --concept channel-capacity
groundrecall assistant-export store/ claude_code exports/claude --concept channel-capacity
```

## Bridge To Didactopus

If you want a `Didactopus` learner pack that carries reviewed GroundRecall
concept context, the shortest bridge flow is:

```bash
doclift convert-dir /path/to/legacy-course /tmp/doclift-bundle --asset-root /path/to/legacy-course
didactopus doclift-bundle-groundrecall \
  store/ \
  channel-capacity \
  /tmp/doclift-bundle \
  /tmp/didactopus-pack \
  --course-title "Example Course"
```

That command:

- exports a pack-ready `groundrecall_query_bundle.json` from `GroundRecall`
- feeds it into the `Didactopus` `doclift` bundle flow
- writes a pack with the GroundRecall query bundle included as a declared
  supporting artifact

## Default Working Layout

A simple local layout is:

```text
.groundrecall/
  imports/
  store/
  exports/
  events/
```

The current alpha does not require this exact layout, but it is a sensible starting point.

## Initialize Assistant Memory

For site, app, service, or deployment work, initialize the assistant-neutral
GroundRecall protocol:

```bash
groundrecall protocol-init /opt/www \
  --host-id local-dev \
  --host-role development \
  --assistant codex \
  --assistant claude_code
```

This writes a host profile, GroundRecall workspace README, assistant bootstrap
files, and local/remote inbox directories. See
[assistant-protocol.md](assistant-protocol.md).

## Next Reading

- [architecture.md](architecture.md)
- [assistant-protocol.md](assistant-protocol.md)
- [didactopus-bridge.md](didactopus-bridge.md)
- [llmwiki-import.md](llmwiki-import.md)
- [sync-roadmap.md](sync-roadmap.md)
