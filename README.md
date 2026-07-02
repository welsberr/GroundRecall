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

GroundRecall's assistant protocol also defines an update policy for
long-running operational work. The policy asks assistants to record task
definition, plan/implementation details, and results as durable source notes.
The rationale is practical: project goals, task boundaries, planning tradeoffs,
and intermediate service states are often lost because memory updates happen
only at the end, or not at all.

## Current Features

- Import from llmwiki-style trees, plain notes, normalized `doclift` bundles,
  Didactopus packs, transcripts, PolyPaper projects, and specialized corpora.
- Normalize imports into artifacts, fragments, observations, claims, concepts,
  and relations.
- Maintain a provenance-first knowledge graph substrate over concepts, claims,
  relations, observations, artifacts, and source evidence.
- Lint and review import output before promotion.
- Promote reviewed records into a canonical GroundRecall store.
- Query by concept and export query bundles.
- Inspect graph shape and concept/relation diagnostics with
  `groundrecall inspect --graph`.
- Surface graph quality diagnostics for inferred-edge density, weak relation
  grounding, unsupported claims, high-fanout concepts, and conflict links.
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
groundrecall import /path/to/source --out-root .groundrecall/imports --mode quick --extract-graph heuristic
```

Imports also write review sidecars such as `concept_standardization.json` and
`graph_extraction_candidates.json` when applicable.

Lint the import:

```bash
groundrecall lint .groundrecall/imports/<import-id>
```

Review significant imports:

```bash
groundrecall review-server .groundrecall/imports/<import-id>
```

The review workbench includes concept, relation, and citation lanes when the
import contains corresponding candidates.

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
groundrecall inspect .groundrecall/store --graph
groundrecall query .groundrecall/store channel-capacity
groundrecall query .groundrecall/store channel-capacity --kind graph
groundrecall export .groundrecall/store exports/canonical --graph-concept channel-capacity
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

For substantial work, update GroundRecall at three points:

- Task definition: objective, scope, paths, targets, verification criteria, and
  constraints.
- Plan or implementation specification: chosen approach, touched files/services,
  checks, rollback notes, risks, and relevant rejected alternatives.
- Results: outcomes, evidence, commands/tests, artifact/log paths, unresolved
  risks, and next safe action.

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
- [docs/knowledge-graph-roadmap.md](docs/knowledge-graph-roadmap.md)
- [docs/llmwiki-import.md](docs/llmwiki-import.md)
- [docs/sync-roadmap.md](docs/sync-roadmap.md)
