from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable


VALID_HOST_ROLES = {"development", "production", "staging", "mixed"}
DEFAULT_ASSISTANTS = ("codex", "claude_code")


@dataclass
class ProtocolInitResult:
    root: Path
    written: list[Path]
    skipped: list[Path]

    def as_dict(self) -> dict[str, object]:
        return {
            "root": str(self.root),
            "written": [str(path) for path in self.written],
            "skipped": [str(path) for path in self.skipped],
        }


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_.-]+", "-", text.strip()).strip("-")
    return slug or "host"


def write_if_allowed(path: Path, text: str, *, force: bool, written: list[Path], skipped: list[Path]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        skipped.append(path)
        return
    path.write_text(text, encoding="utf-8")
    written.append(path)


def host_profile_note(
    *,
    host_id: str,
    host_role: str,
    primary_root: str,
    groundrecall_root: str,
    hostname: str = "",
    fqdn: str = "",
    public_entrypoint: str = "",
) -> str:
    return f"""# GroundRecall Host Profile - {host_id}

```yaml
host_id: {host_id}
hostname: {hostname}
fqdn: {fqdn}
host_role: {host_role}
primary_root: {primary_root}
groundrecall_root: {groundrecall_root}
public_entrypoint: {public_entrypoint}
last_verified: {date.today().isoformat()}
```

Purpose:
- Identify the operational role of this host for assistants using GroundRecall.
- Prevent assistants from assuming that a development, staging, production, or
  mixed host has the same safety rules as another host.

Assistant startup rule:
- Read this host profile before changing services, deployment state, data
  stores, routing, or recovery configuration.
- Treat host-specific facts as scoped to `{host_id}` unless a note explicitly
  says `scope: shared`.

No-secrets rule:
- This profile may name where secrets are stored, but it must not contain secret
  values, tokens, private keys, cookies, database passwords, or API keys.
"""


def workspace_readme(*, primary_root: str, groundrecall_root: str) -> str:
    return f"""# GroundRecall Workspace

This directory is the host or project GroundRecall workspace.

Primary root: `{primary_root}`

GroundRecall root: `{groundrecall_root}`

## Layout

- `source-notes/`: durable Markdown notes written by humans or assistants.
- `imports/`: normalized import artifacts.
- `store/`: promoted canonical GroundRecall store.
- `exports/canonical/`: assistant-neutral exports.
- `exports/codex/`: Codex-targeted exports when generated.
- `exports/claude_code/`: Claude Code-targeted exports when generated.
- `local-inbox/`: notes or exports imported from a local/development peer.
- `remote-inbox/`: notes or exports imported from a remote/staging/production
  peer.

## Assistant Startup

Assistants should:

1. Read `ASSISTANT_PROJECT.md`, `CODEX_PROJECT.md`, or `CLAUDE.md` if present.
2. Read this file and `source-notes/host-profile-*.md`.
3. Identify this host role before changing services or deployment state.
4. Query or inspect GroundRecall for the project/service in scope before broad
   filesystem searches, repo scans, service restarts, deployment actions, or
   planning changes.
5. If an assistant-specific export is empty or lacks enough context to orient
   the task, read relevant `source-notes/` and `exports/canonical/` entries,
   then write or update a concise project summary source note so future startup
   has sufficient context.
6. Write source notes for task definition, plan/implementation details, and
   results as work progresses; promote/export them and rebuild the FTS5 index
   after significant work.

## Update Policy

Record substantial work at three points so project goals, task boundaries,
planning tradeoffs, and intermediate operational states are not lost:

- Task definition: objective, scope, paths, targets, verification criteria, and
  constraints.
- Plan or implementation specification: chosen approach, touched files/services,
  checks, rollback notes, risks, and relevant rejected alternatives.
- Results: outcomes, evidence, commands/tests, artifact/log paths, unresolved
  risks, and next safe action.

## No-Secrets Rule

GroundRecall may store where secrets live, but not secret values. Do not store
passwords, tokens, private keys, cookies, database dumps with secrets, or
session material.
"""


def assistant_project_stub(*, primary_root: str, groundrecall_root: str) -> str:
    return f"""# Assistant Project Bootstrap

Primary durable memory is GroundRecall.

- primary root: `{primary_root}`
- GroundRecall workspace: `{groundrecall_root}`
- canonical export: `{groundrecall_root}/exports/canonical`
- source notes: `{groundrecall_root}/source-notes`

On startup:

1. Identify this host and host role from `{groundrecall_root}/source-notes/host-profile-*.md`.
2. Inspect relevant GroundRecall context before planning site, app, service,
   deployment, or recovery work.
3. Fall back to source notes and canonical exports when the assistant-specific
   export is empty or insufficient.
4. Check version-control status before edits.
5. Update GroundRecall source notes for task definition, plan/implementation
   details, and results as durable work progresses.
6. Promote/export source notes and rebuild the FTS5 index after significant
   work.
7. Do not store secrets in GroundRecall, chat, docs, or commits.

Use assistant-specific exports when available; otherwise use the canonical
GroundRecall export.
"""


def codex_stub(*, primary_root: str, groundrecall_root: str) -> str:
    return f"""# CODEX_PROJECT

Primary durable memory is GroundRecall.

- primary root: `{primary_root}`
- GroundRecall workspace: `{groundrecall_root}`
- canonical export: `{groundrecall_root}/exports/canonical`
- Codex export: `{groundrecall_root}/exports/codex`

On startup, identify this host role, read GroundRecall before broad filesystem
searches, repo scans, service restarts, deployment actions, or planning changes,
and query or inspect project/service memory. If the Codex export is empty or
insufficient, fall back to source notes and canonical exports. For substantial
work, update GroundRecall source notes for task definition,
plan/implementation details, and results; then promote/export notes and rebuild
the FTS5 index. Do not store secrets in GroundRecall, chat, docs, or commits.
"""


def claude_stub(*, primary_root: str, groundrecall_root: str) -> str:
    return f"""# CLAUDE

Primary durable memory is GroundRecall.

- primary root: `{primary_root}`
- GroundRecall workspace: `{groundrecall_root}`
- canonical export: `{groundrecall_root}/exports/canonical`
- Claude Code export: `{groundrecall_root}/exports/claude_code`

On startup, identify this host role, read relevant GroundRecall context, and
check project/service memory before planning changes. For substantial work,
update source notes for task definition, plan/implementation details, and
results; then promote/export notes and rebuild the FTS5 index. Do not store
secrets in memory, chat, docs, or commits.
"""


def normalize_assistants(assistants: Iterable[str] | None) -> list[str]:
    values = list(assistants or DEFAULT_ASSISTANTS)
    normalized: list[str] = []
    for value in values:
        name = value.strip().lower().replace("-", "_")
        if name and name not in normalized:
            normalized.append(name)
    return normalized


def initialize_protocol(
    root: str | Path,
    *,
    host_id: str,
    host_role: str,
    primary_root: str | None = None,
    groundrecall_root: str | None = None,
    hostname: str = "",
    fqdn: str = "",
    public_entrypoint: str = "",
    assistants: Iterable[str] | None = None,
    force: bool = False,
) -> ProtocolInitResult:
    if host_role not in VALID_HOST_ROLES:
        raise ValueError(f"host_role must be one of: {', '.join(sorted(VALID_HOST_ROLES))}")

    root_path = Path(root)
    primary_root_value = primary_root or str(root_path)
    groundrecall_value = groundrecall_root or str(root_path / ".groundrecall")
    groundrecall_path = Path(groundrecall_value)
    if not groundrecall_path.is_absolute():
        groundrecall_path = root_path / groundrecall_path
        groundrecall_value = str(groundrecall_path)

    written: list[Path] = []
    skipped: list[Path] = []
    for rel in ("source-notes", "imports", "store", "exports/canonical", "local-inbox", "remote-inbox"):
        (groundrecall_path / rel).mkdir(parents=True, exist_ok=True)

    write_if_allowed(
        groundrecall_path / "README.md",
        workspace_readme(primary_root=primary_root_value, groundrecall_root=groundrecall_value),
        force=force,
        written=written,
        skipped=skipped,
    )
    write_if_allowed(
        groundrecall_path / "source-notes" / f"host-profile-{slugify(host_id)}.md",
        host_profile_note(
            host_id=host_id,
            host_role=host_role,
            primary_root=primary_root_value,
            groundrecall_root=groundrecall_value,
            hostname=hostname,
            fqdn=fqdn,
            public_entrypoint=public_entrypoint,
        ),
        force=force,
        written=written,
        skipped=skipped,
    )
    write_if_allowed(
        root_path / "ASSISTANT_PROJECT.md",
        assistant_project_stub(primary_root=primary_root_value, groundrecall_root=groundrecall_value),
        force=force,
        written=written,
        skipped=skipped,
    )

    assistant_names = normalize_assistants(assistants)
    if "codex" in assistant_names:
        write_if_allowed(
            root_path / "CODEX_PROJECT.md",
            codex_stub(primary_root=primary_root_value, groundrecall_root=groundrecall_value),
            force=force,
            written=written,
            skipped=skipped,
        )
    if "claude_code" in assistant_names:
        write_if_allowed(
            root_path / "CLAUDE.md",
            claude_stub(primary_root=primary_root_value, groundrecall_root=groundrecall_value),
            force=force,
            written=written,
            skipped=skipped,
        )

    return ProtocolInitResult(root=root_path, written=written, skipped=skipped)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Initialize assistant-neutral GroundRecall protocol files.")
    parser.add_argument("root", help="Project or host root where bootstrap files should be written.")
    parser.add_argument("--host-id", required=True, help="Stable host identifier, for example local-dev or remote-prod.")
    parser.add_argument("--host-role", required=True, choices=sorted(VALID_HOST_ROLES))
    parser.add_argument("--primary-root", help="Operational root recorded in generated notes. Defaults to root.")
    parser.add_argument("--groundrecall-root", help="GroundRecall workspace path. Defaults to ROOT/.groundrecall.")
    parser.add_argument("--hostname", default="")
    parser.add_argument("--fqdn", default="")
    parser.add_argument("--public-entrypoint", default="")
    parser.add_argument("--assistant", action="append", default=[], help="Assistant bootstrap to write: codex, claude_code. Repeatable.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing bootstrap/profile files.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    result = initialize_protocol(
        args.root,
        host_id=args.host_id,
        host_role=args.host_role,
        primary_root=args.primary_root,
        groundrecall_root=args.groundrecall_root,
        hostname=args.hostname,
        fqdn=args.fqdn,
        public_entrypoint=args.public_entrypoint,
        assistants=args.assistant or DEFAULT_ASSISTANTS,
        force=args.force,
    )
    print(json.dumps(result.as_dict(), indent=2))


if __name__ == "__main__":
    main()
