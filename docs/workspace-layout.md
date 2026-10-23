# Workspace Layout and Authority

A GroundRecall workspace is a container for several differently governed
areas. It is not itself a canonical store.

## Manifest

Place `workspace.json` at the workspace root:

```json
{
  "schema_version": "groundrecall.workspace.v1",
  "workspace_id": "example-host-memory",
  "canonical_store": "store",
  "imports": "imports",
  "source_notes": "source-notes",
  "indexes": {
    "notes": ".index/groundrecall-notes.sqlite",
    "canonical": "store/.index/groundrecall-search.sqlite",
    "unified": ".index/groundrecall-unified.sqlite"
  },
  "private_runs": "logs"
}
```

All declared paths must remain inside the workspace. The canonical store,
imports, and source-note paths must differ from the workspace root, and each
index scope must have a distinct path.

## Authority Boundaries

- `store/` is the canonical typed-record store.
- `imports/` contains generated import bundles and supporting fragments.
- `source-notes/` contains durable working and orientation notes; they are not
  silently promoted knowledge.
- search indexes are rebuildable projections and carry no authority.
- `private_runs` is private operational state and is not a search corpus.

Manifest-aware import and promotion commands reject the workspace root as a
write target. Typed-store construction and saves also reject a manifested
workspace root. Standalone stores without a manifest retain the alpha
compatibility behavior.

## Explicit Search Scopes

Workspace index commands require a scope:

```bash
groundrecall index .groundrecall --scope notes --rebuild
groundrecall index .groundrecall --scope canonical --rebuild
groundrecall index .groundrecall --scope unified --rebuild
groundrecall index .groundrecall "query terms" --scope unified --limit 10
```

The scopes mean:

| Scope | Typed records | Source notes | Intended use |
| --- | --- | --- | --- |
| `notes` | No | Yes | Fast orientation and recently written notes |
| `canonical` | Yes | No | Reviewed typed-record retrieval |
| `unified` | Yes | Yes | Default prior-work discovery without flattening authority |

Index enumeration opens the canonical store in non-creating mode. A read or
index operation must not make an arbitrary directory look like a store.

## Mutation Targets

Use the declared paths rather than the workspace root:

```bash
groundrecall import /path/to/source --out-root .groundrecall/imports
groundrecall promote .groundrecall/imports/IMPORT_ID .groundrecall/store
```

The manifest is a safety boundary, not a migration tool. Adding it does not
move, merge, archive, or delete pre-existing records or bundles.

## Safe Capability Updates

Software installation and canonical-store updates are separate operations.
Install a new GroundRecall package or deploy a new container image using its
normal package/deployment workflow; do not place the canonical store in an
image layer that is replaced during deployment. The `groundrecall update`
command checks and provisions store-format capabilities. It does not download
or install software.

The default command is read-only and validates the typed record families:

```bash
groundrecall update .groundrecall/store --check
```

By default, the updater requires the complete canonical record-family layout;
this helps prevent accidentally treating a workspace root or arbitrary
directory as the store. A legacy standalone store missing family directories
must be checked manually before using `--allow-partial-store` on both the check
and apply commands. Never use that override on a workspace root.

To apply a planned store update, stop all GroundRecall readers and writers,
choose a new backup path outside the store, and explicitly confirm the
maintenance window:

```bash
groundrecall update .groundrecall/store \
  --apply \
  --backup /private/backups/groundrecall-store-before-update-20260920 \
  --confirm-stopped
```

The updater refuses to overwrite an existing backup. It verifies the backup,
validates records and confirms that existing typed records, graph relations,
indexes, and other files are byte-for-byte unchanged before and after
promotion. The current initial migration only adds a format manifest atomically;
it does not swap the directory or rewrite canonical record files. To roll it
back before any record changes have been made, stop consumers and use the
external backup path:

```bash
groundrecall update .groundrecall/store \
  --rollback-from /private/backups/groundrecall-store-before-update-20260920 \
  --confirm-stopped
```

Rollback refuses if the canonical record tree has changed since the update;
it removes only the marker and never restores or deletes record data. The
external backup remains the durable recovery copy. Protect backups as carefully
as the canonical store because they contain the same knowledge. Search indexes
are rebuildable projections and should be refreshed separately after a
migration that explicitly changes indexed records.

## Itemized Inventory and Restore Checks

Create a deterministic, content-addressed inventory outside the workspace:

```bash
groundrecall-workspace-inventory create \
  .groundrecall \
  /private/backup-metadata/workspace.jsonl \
  --summary /private/backup-metadata/workspace-summary.json
```

The JSONL is sorted by relative path and records entry type, mode, byte size,
SHA-256, classified role, typed-record family and stable ID, lifecycle status,
and import ID where applicable. It contains no file contents. Files that change
while being hashed cause the operation to fail, and outputs inside the scanned
workspace are rejected.

After copying or restoring a workspace, inventory the destination independently
and compare it with the source manifest:

```bash
groundrecall-workspace-inventory compare \
  /private/backup-metadata/workspace.jsonl \
  /private/restore-metadata/workspace.jsonl
```

An equal comparison proves path, metadata, size, and content-hash equality for
the inventoried filesystem entries. It does not replace schema validation,
SQLite integrity checks, reference checks, or an operational retrieval test.

For an audited copy-first normalization of direct workspace/store import
bundles, first create and inspect a plan tied to a verified backup receipt:

```bash
groundrecall-reconcile-imports plan \
  .groundrecall \
  /private/backup/metadata/receipt.json \
  /private/backup/metadata/import-plan.json
groundrecall-reconcile-imports apply \
  .groundrecall \
  /private/backup/metadata/import-plan.json \
  /private/backup/metadata/import-receipt.json
groundrecall-reconcile-imports verify \
  .groundrecall \
  /private/backup/metadata/import-plan.json
```

The apply operation preflights every source and destination before copying,
uses private staging and atomic destination renames, verifies both trees after
copy, and preserves all sources. Reapplication is idempotent when destinations
match and stops on any divergent source or destination.
