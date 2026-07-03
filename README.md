# GroundRecall

GroundRecall is a local-first, provenance-aware knowledge substrate for
human-reviewable and assistant-usable memory. It imports source material into a
canonical store, supports review and promotion, exports assistant-neutral
snapshots, and can generate assistant-specific bundles for tools such as Codex
and Claude Code.

GroundRecall is intended for work where durable context matters:

- site, app, and service administration across sessions
- local/remote deployment memory with host-role distinctions
- research notes and grounded claim tracking
- legacy document normalization through `doclift`
- learner-facing workflows through `Didactopus`
- assistant handoff between Codex, Claude Code, and other file-aware tools

## Current Features

- Import from llmwiki-style trees, plain notes, normalized `doclift` bundles,
  Didactopus packs, transcripts, PolyPaper projects, and specialized corpora.
- Normalize imports into artifacts, fragments, observations, claims, concepts,
  and relations.
- Lint and review import output before promotion.
- Promote reviewed records into a canonical GroundRecall store.
- Query by concept and export query bundles.
- Export assistant-neutral canonical snapshots.
- Export assistant-specific bundles:
  - Codex: `SKILL.md` plus `codex_bundle.json`
  - Claude Code: `CLAUDE.md` plus `claude_code_bundle.json`
- Export pack-ready query bundles for Didactopus.
- Initialize an assistant-neutral host/project memory protocol with
  `groundrecall protocol-init`.

## Installation

From a checkout:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
groundrecall --help
```

For development:

```bash
.venv/bin/python -m pytest
```

The package also supports module invocation when working directly from source:

```bash
PYTHONPATH=src python -m groundrecall --help
```

## Basic Workflow

Import a source:

```bash
groundrecall import /path/to/source --out-root .groundrecall/imports --mode quick
```

Lint the import:

```bash
groundrecall lint .groundrecall/imports/<import-id>
```

Review significant imports:

```bash
groundrecall review-server .groundrecall/imports/<import-id>
```

Promote the import into a canonical store:

```bash
groundrecall promote .groundrecall/imports/<import-id> .groundrecall/store --reviewer your-name
```

Promotion refuses imports with lint errors by default. Fix the source material,
adapter, or review data first. If you intentionally need to preserve a flawed
import for triage or recovery, use:

```bash
groundrecall promote .groundrecall/imports/<import-id> .groundrecall/store \
  --reviewer your-name \
  --allow-lint-errors
```

Warnings remain visible in the review queue but do not block promotion.

Inspect or query the store:

```bash
groundrecall inspect .groundrecall/store
groundrecall query .groundrecall/store channel-capacity
```

Export assistant-neutral data:

```bash
groundrecall export .groundrecall/store .groundrecall/exports/canonical
```

Export assistant-specific data:

```bash
groundrecall assistant-export .groundrecall/store codex .groundrecall/exports/codex
groundrecall assistant-export .groundrecall/store claude_code .groundrecall/exports/claude_code
```

Export explicit claim-evaluation results as Epistemap G rows, manifest, and
summary JSON/Markdown:

```bash
groundrecall claim-evaluation-export evaluations.json .groundrecall/exports/g \
  --claims-json claims.jsonl \
  --experiment-id temporal-claim-check \
  --corpus channel-capacity
```

These rows evaluate an explicit learner/model claim-checking run. They are not
derived from GroundRecall review confidence or used as source-truth scores.

## Assistant-Neutral Host Protocol

GroundRecall can initialize a reusable memory pattern for a project or host:

```bash
groundrecall protocol-init /opt/www \
  --host-id local-dev \
  --host-role development \
  --assistant codex \
  --assistant claude_code
```

This creates:

- `.groundrecall/README.md`
- `.groundrecall/source-notes/host-profile-<host-id>.md`
- `.groundrecall/local-inbox/`
- `.groundrecall/remote-inbox/`
- `ASSISTANT_PROJECT.md`
- assistant bootstrap files such as `CODEX_PROJECT.md` and `CLAUDE.md`

Use `--force` only when you intend to overwrite existing bootstrap files.

For a two-host local/remote setup, each host should maintain its own
GroundRecall store and exchange source notes or exports. Do not make both hosts
write directly into the same mutable store.

See [docs/assistant-protocol.md](docs/assistant-protocol.md).

## Suggested Workspace Layout

```text
.groundrecall/
  source-notes/
  imports/
  store/
  exports/
    canonical/
    codex/
    claude_code/
  local-inbox/
  remote-inbox/
```

`source-notes/` is where humans and assistants should leave durable Markdown
notes. Those notes can later be imported and promoted.

## Didactopus Bridge

GroundRecall can export a pack-ready `groundrecall_query_bundle.json` for a
reviewed concept:

```bash
groundrecall export /path/to/groundrecall-store /tmp/groundrecall-export \
  --pack-ready-concept channel-capacity
```

The matching Didactopus bridge flow is:

```bash
didactopus doclift-bundle-groundrecall \
  /path/to/groundrecall-store \
  channel-capacity \
  /tmp/doclift-bundle \
  /tmp/didactopus-pack \
  --course-title "Example Course"
```

See [docs/didactopus-bridge.md](docs/didactopus-bridge.md).

## Use Cases

GroundRecall is useful when the same project may be touched by different
assistants, at different times, or on different hosts:

- A local development host and a remote production host both need operational
  memory.
- Codex performs a code change locally, then Claude Code investigates a service
  failure remotely.
- A WordPress or Forgejo service needs routing, backup, deployment, and recovery
  notes that survive across sessions.
- A research corpus needs grounded claims, citations, source provenance, and
  review state.
- Legacy office documents need `doclift` normalization before becoming
  searchable assistant context.

## Safety Rules

- Store where secrets live, not secret values.
- Keep host-specific facts labeled by host and role.
- Treat production and mixed hosts as higher risk than development hosts.
- Prefer source-note/export replication between hosts over shared mutable stores.
- Commit code/config changes separately from generated GroundRecall exports
  unless the export is intentionally part of the deliverable.

## Documentation

- [docs/quickstart.md](docs/quickstart.md)
- [docs/assistant-protocol.md](docs/assistant-protocol.md)
- [docs/architecture.md](docs/architecture.md)
- [docs/didactopus-bridge.md](docs/didactopus-bridge.md)
- [docs/llmwiki-import.md](docs/llmwiki-import.md)
- [docs/sync-roadmap.md](docs/sync-roadmap.md)
