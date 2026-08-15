# Running the GroundRecall MCP HTTP adapter with systemd

`deploy/systemd/groundrecall-mcp-http.service` is a deployment template for a
private, read-only MCP endpoint. It is deliberately loopback-only; a private
tunnel or approved reverse proxy must terminate remote access. The template is
not installed or enabled by the repository.

## One-time host setup

Create a dedicated service account and directories, install GroundRecall into
the path used by `ExecStart`, and place server-owned policy and identity files
with restrictive permissions:

```sh
sudo useradd --system --home-dir /var/lib/groundrecall --shell /usr/sbin/nologin groundrecall
sudo install -d -o groundrecall -g groundrecall -m 0750 /var/lib/groundrecall /var/log/groundrecall
sudo install -d -o root -g groundrecall -m 0750 /etc/groundrecall
sudo install -o root -g groundrecall -m 0640 mcp-policy.yaml /etc/groundrecall/mcp-policy.yaml
sudo install -o root -g groundrecall -m 0640 mcp-identities.json /etc/groundrecall/mcp-identities.json
```

Install the package and its dependencies into `/opt/groundrecall/.venv`, or
edit `ExecStart` in a local copy of the unit. Identity-file bearer tokens are
pilot credentials; never commit them. Rotate by replacing the identity file,
then restarting the unit. A future tunnel/OAuth integration should replace
this local credential mechanism.

## Install and verify (do not enable automatically)

```sh
sudo install -o root -g root -m 0644 deploy/systemd/groundrecall-mcp-http.service \
  /etc/systemd/system/groundrecall-mcp-http.service
sudo systemctl daemon-reload
sudo systemctl start groundrecall-mcp-http.service
curl --fail --silent http://127.0.0.1:8765/healthz
curl --fail --silent http://127.0.0.1:8765/readyz
sudo systemctl status groundrecall-mcp-http.service
```

`/healthz` is a bounded liveness response and does not inspect or disclose
store contents. `/readyz` reports only boolean policy/store checks and returns
HTTP 503 until the server-owned policy file and `--store-dir` are available;
it never returns their paths or data. Configure `--store-dir` in local unit
copies when using readiness probes.

The systemd template also enables `--require-policy`: if the policy file is
removed or becomes invalid after startup, MCP requests fail closed with a
bounded error and `/readyz` returns HTTP 503. Local-development invocations
may omit this flag for backward-compatible behavior.

`--max-concurrent-requests` bounds in-flight MCP dispatches. Requests arriving
after the limit receive a bounded HTTP 429/JSON-RPC `server busy` response;
the limit does not queue unbounded work or expose store details.

The template sets a 30-second execution wait with `--request-timeout-seconds`.
Timeouts return HTTP 504/JSON-RPC `request timed out`; Python work cannot be
safely killed, so the timed-out worker is allowed to finish while retaining
its concurrency slot. This prevents timeout storms from bypassing the limit.

Enable on boot only after validating the policy, identity mapping, and tunnel:

```sh
sudo systemctl enable groundrecall-mcp-http.service
```

The unit restarts failed processes with a bounded burst. `ProtectSystem`,
`NoNewPrivileges`, an empty capability set, private temporary storage, and
explicit writable paths limit the service account. Logs go to journald; access
audit records are written only when `--audit-log-path` is configured and must
be rotated/retained by the host operator. The repository includes a conservative
logrotate template at `deploy/logrotate/groundrecall-mcp-http`; install it only
after reviewing local retention requirements:

```sh
sudo install -o root -g root -m 0644 \
  deploy/logrotate/groundrecall-mcp-http \
  /etc/logrotate.d/groundrecall-mcp-http
sudo logrotate -d /etc/logrotate.d/groundrecall-mcp-http
```

The template rotates daily, keeps 14 archives, compresses older archives, and
rotates at 50 MiB. It uses rename-based rotation because the adapter opens the
JSONL path for each event; do not add `copytruncate` unless a locally modified
adapter keeps the file descriptor open. Align retention and deletion with
project data-governance requirements, and protect rotated files because they
contain principal, realm, tool, decision, and correlation metadata (never
request content or bearer tokens).

The template also contains an operator-controlled `postrotate` hook that calls
`groundrecall-mcp-audit-manifest` after a successful rotation. Before installing
the template, edit `manifest_bin` to the command path in the host's GroundRecall
environment (the checked-in `/opt/groundrecall/.venv/bin/...` value is only a
documented placeholder). The hook writes
`mcp-access.manifest.json` through the utility's atomic replace operation and
redirects command output so audit records are never printed. If the command is
missing or fails, logrotate continues and emits only a bounded warning through
`logger`; operators can regenerate the manifest after correcting the path.

Operators can verify the active chain without exposing record contents:

```sh
groundrecall-mcp-audit-verify /var/log/groundrecall/mcp-access.jsonl
groundrecall-mcp-audit-verify --json /var/log/groundrecall/mcp-access.jsonl
```

The command exits zero only when the file is readable and valid; malformed or
tampered records return a nonzero status. Both output modes contain only
aggregate counts and the final hash.

To preserve a metadata-only inventory across log rotation, generate a manifest
after rotation (from a trusted operator or timer) and verify it before export:

```sh
groundrecall-mcp-audit-manifest /var/log/groundrecall \
  --output /var/log/groundrecall/mcp-access.manifest.json
groundrecall-mcp-audit-manifest /var/log/groundrecall \
  --verify /var/log/groundrecall/mcp-access.manifest.json --json
```

The manifest contains file names, byte sizes, SHA-256 hashes, and generation
time only; it never embeds audit records or credentials. A missing, changed, or
unexpected matching audit file makes verification fail. Keep the manifest under
the same retention and access controls as the rotated logs, and do not place it
inside the `mcp-access.jsonl*` pattern.

For a bounded operator handoff, export a verified redacted projection without
modifying the source log:

```sh
groundrecall-mcp-audit-export /var/log/groundrecall/mcp-access.jsonl \
  /var/log/groundrecall/mcp-access.export.json --max-records 1000
```

The export preserves correlation and hash-chain metadata but omits request
content, reasons, credentials, and identities by default. `--include-identities`
is an explicit operator choice. The command never deletes or truncates source
logs; retain the export under the same access policy.
