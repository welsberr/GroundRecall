# Assistant-Neutral GroundRecall Protocol

This document codifies a site-neutral pattern for using GroundRecall as durable
memory across assistants and hosts. It applies to Codex, Claude Code, and other
assistants that can read and write local files.

## Problem

Long-running site, app, and service work often crosses multiple sessions,
assistants, hosts, and operational modes. Plain chat history is not enough for
that. GroundRecall provides a local, reviewable memory store with provenance,
exports, and assistant-specific bundles.

## Principles

- Each host has its own GroundRecall workspace and canonical store.
- Local and remote hosts exchange source notes or exports, not shared mutable
  store internals.
- Operational facts should be scoped by host, project, service, and role when
  those details matter.
- Assistants should read memory before planning and update memory as durable
  work progresses.
- Secrets are never stored in GroundRecall.

## Initialize A Host Or Project

Use `protocol-init`:

```bash
groundrecall protocol-init /opt/www \
  --host-id local-dev \
  --host-role development \
  --hostname devbox \
  --assistant codex \
  --assistant claude_code
```

Supported host roles are `development`, `staging`, `production`, and `mixed`.
Use `--force` to overwrite existing bootstrap files.

Generated files include:

- `.groundrecall/README.md`
- `.groundrecall/source-notes/host-profile-<host-id>.md`
- `.groundrecall/local-inbox/`
- `.groundrecall/remote-inbox/`
- `ASSISTANT_PROJECT.md`
- `CODEX_PROJECT.md` when `--assistant codex` is used
- `CLAUDE.md` when `--assistant claude_code` is used

## Host Profile

The generated host profile records:

```yaml
host_id: local-dev
hostname: devbox
fqdn:
host_role: development
primary_root: /opt/www
groundrecall_root: /opt/www/.groundrecall
public_entrypoint:
last_verified: yyyy-mm-dd
```

Assistants should read this profile before changing services, deployment state,
data stores, routing, or recovery configuration.

## Operational Scopes

Use these scopes in source notes:

- `local-only`: applies only to this host.
- `remote-only`: applies only to a paired remote host.
- `shared`: applies to both hosts or project architecture independent of host.
- `deployment`: describes controlled transfer from one host to another.
- `recovery`: describes backup, restore, rollback, or disaster recovery.

Example note header:

```yaml
scope: deployment
host_id: remote-prod
project: example.net
service: wordpress
topic: REST routing under /wp
```

## Assistant Startup

At session start, assistants should:

1. Read `ASSISTANT_PROJECT.md`, `CODEX_PROJECT.md`, or `CLAUDE.md` if present.
2. Read `.groundrecall/README.md`.
3. Read `.groundrecall/source-notes/host-profile-*.md`.
4. Inspect canonical or assistant-specific exports.
5. Query relevant project/service memory before planning changes.
6. Check version-control status before edits.
7. Record durable findings as source notes.

Codex should prefer `.groundrecall/exports/codex/` when present. Claude Code
should prefer `.groundrecall/exports/claude_code/` when present. Other
assistants should use `.groundrecall/exports/canonical/`.

## Source Notes

Write durable findings to:

```text
.groundrecall/source-notes/<project-or-topic>-YYYYMMDD.md
```

A good source note includes host and role, project/service, changed files,
commands/tests run, deployment or restart actions, backup/recovery status if
data was touched, remaining risks, and next safe action.

Then import, promote, and export:

```bash
groundrecall import .groundrecall/source-notes/example-20260501.md \
  --out-root .groundrecall/imports \
  --mode quick

groundrecall promote .groundrecall/imports/<import-id> .groundrecall/store \
  --reviewer codex

groundrecall export .groundrecall/store .groundrecall/exports/canonical
groundrecall assistant-export .groundrecall/store codex .groundrecall/exports/codex
groundrecall assistant-export .groundrecall/store claude_code .groundrecall/exports/claude_code
```

## Local/Remote Sharing

Do not make local and remote hosts write directly into the same store.

Recommended pattern:

1. Local host writes, promotes, and exports local notes.
2. Remote host imports selected local notes or canonical export with provenance.
3. Remote host writes, promotes, and exports remote notes.
4. Local host imports selected remote notes or canonical export with provenance.

Suggested inboxes:

```text
.groundrecall/local-inbox/
.groundrecall/remote-inbox/
```

Transport can be git, rsync, scp, Forgejo, or another controlled file sync. Do
not sync secrets.

## Deployment Records

Each deployed project should eventually have a source note or promoted record
containing:

```yaml
project: example.net
repo: git@git.example:owner/example.net.git
local_path: /opt/www/dev/example.net
remote_path: /opt/www/dev/example.net
host_scope: shared
compose_files:
  - docker-compose.yml
  - docker-compose-public.yml
containers:
  - example_web
  - example_db
deploy_method: git pull + docker compose up -d
pre_deploy:
  - git status --short
  - backup command if data-bearing
health_checks:
  - https://example.net/
rollback:
  - git checkout previous-known-good
  - docker compose up -d
data_owner: remote-prod
```

## No-Secrets Rule

Allowed:

```text
The database password is in /opt/www/dev/example.net/.env.
The Forgejo config is mounted from /mnt/data/www/.../app.ini.
```

Not allowed:

```text
password=...
token=...
private key material
cookies
session IDs
database dumps containing credentials
```

If an assistant sees a secret, it should not copy it into GroundRecall, docs,
chat, or commits.
