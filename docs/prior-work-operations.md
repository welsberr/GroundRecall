# Prior-Work Discovery and Task Memory Operations

Use this runbook when orienting to a project, resuming a task, recording its
results, or upgrading a GroundRecall installation or store.

## Search the Workspace First

For general prior-work discovery, search the workspace's unified index. It
combines typed records from the configured canonical store with durable source
notes while preserving their different authority levels:

```sh
groundrecall index /path/to/.groundrecall "project name or task aliases" \
  --scope unified --limit 10
```

Use the actual workspace path in place of `/path/to/.groundrecall`. Always pass
an explicit scope when indexing a manifested workspace. A unified result may
come from a source note, canonical record, or both; inspect its path and record
type before relying on it. Source notes provide working context and handoffs.
They are not silently promoted to reviewed canonical knowledge.

The canonical prior-work command is a useful, narrower follow-up when reviewed
typed records are specifically needed:

```sh
groundrecall prior-work /path/to/.groundrecall/store "project name or task" \
  --scope-id project-scope
```

This command searches the typed store. It does not replace workspace-level
unified discovery and may not return source notes. Do not treat a no-result
canonical search as evidence that no source note or other workspace context
exists. Include the search root and scope in operational summaries when the
choice affects the result.

The workspace scopes are:

| Scope | Includes | Use |
| --- | --- | --- |
| `notes` | Source notes | Recent orientation and handoff notes |
| `canonical` | Typed records in the configured store | Reviewed, provenance-bearing records |
| `unified` | Source notes and typed canonical records | Default project and task discovery |

The legacy `.index/groundrecall-search.sqlite` is an audit artifact during
reconciliation, not the default workspace search index.

## Record Task Plans and Results

For every substantial project, task lane, or resumed work thread, maintain a
source note under `source-notes/` with enough detail to resume without chat
history or filesystem guessing.

At initiation or resumption, record:

- Project/task name, user shorthand, and searchable aliases.
- Objective, scope, and material assumptions or constraints.
- Repository and primary paths, relevant hosts/services, and external systems.
- Current status, blockers, and the next safe action.
- A brief plan when the chosen steps or rejected alternatives affect resumption.
- Pointers to private resources, without copying secrets or sensitive values.

After material work, update the same note or create a clearly linked result
note. Record:

- Files or systems changed and decisions made.
- Commands and relevant actions performed.
- Verification performed and its outcome; distinguish checks not run from
  checks that failed.
- Current status, unresolved issues, and the next safe action.
- Searchable project/task aliases, important artifact paths, and any limits on
  how results should be interpreted.

Keep private paths and sensitive details in appropriately restricted locations.
The note may point to them without reproducing private data. Never put
credentials, tokens, keys, cookies, or session material in a note.

## Refresh Workspace Indexes

After changing a source note, rebuild the notes and unified projections:

```sh
groundrecall index /path/to/.groundrecall --scope notes --rebuild
groundrecall index /path/to/.groundrecall --scope unified --rebuild
```

After changing canonical typed records, rebuild the canonical and unified
projections:

```sh
groundrecall index /path/to/.groundrecall --scope canonical --rebuild
groundrecall index /path/to/.groundrecall --scope unified --rebuild
```

Then query the unified scope using the project shorthand and at least one
result-specific term. Confirm that the expected note or record appears with the
correct path and kind. Indexes are rebuildable projections; the source note and
typed records remain the authoritative materials.

## Software Installation and Store Updates Are Separate

Installing or upgrading the GroundRecall software package is performed by its
package or deployment workflow. The `groundrecall update` command does not
download or install software. It checks or provisions store-format
capabilities.

Start with a read-only store-format check:

```sh
groundrecall update /path/to/.groundrecall/store --check
```

For an actual store-format update, follow the command's backup, quiescence,
confirmation, and recovery requirements. Stop readers and writers, choose a
backup outside the store, and verify a rollback path before applying changes.
Do not pass the workspace root as a canonical store. For legacy partial stores,
review the layout before using `--allow-partial-store`; never use that override
on a workspace root.

After an application upgrade, separately check the software installation and
the store format, then rebuild the affected workspace indexes and run a
unified-search smoke query. A successful package upgrade does not establish
that a store-format update or index rebuild occurred.

## Installation and Upgrade Regression Checks

Run `python scripts/install_upgrade_smoke.py` from the checkout. It builds and
installs a synthetic older wheel and upgrades it to the current wheel in a
temporary environment under a path with spaces and Unicode. It checks every
console entry point, verifies unified source-note retrieval, and exercises
store-format check, apply, backup verification, and rollback using synthetic
records only.

The `Install and upgrade smoke checks` GitHub Actions workflow runs this on a
Windows runner, native Linux and macOS runners, and inside a clean Linux Docker
container. Docker cannot run a macOS kernel, so the native macOS job is the
platform check for macOS path behavior.

The workflow provisions runtime dependencies before installing the GroundRecall
wheel because `epistemap>=0.1.0a6` is not available from public PyPI. The smoke
test uses `--no-deps`; it verifies the GroundRecall wheel and upgrade behavior,
but does not verify clean dependency resolution. Publish or otherwise provide a
compatible Epistemap release before treating public, dependency-resolved
installation as verified.
