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
sudo systemctl status groundrecall-mcp-http.service
```

Enable on boot only after validating the policy, identity mapping, and tunnel:

```sh
sudo systemctl enable groundrecall-mcp-http.service
```

The unit restarts failed processes with a bounded burst. `ProtectSystem`,
`NoNewPrivileges`, an empty capability set, private temporary storage, and
explicit writable paths limit the service account. Logs go to journald; access
audit records are written only when `--audit-log-path` is configured and must
be rotated/retained by the host operator.
