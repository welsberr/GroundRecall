# Codex handoff discovery

`groundrecall-handoff-discover` is an explicit, read-only startup-wrapper
command for Codex (and other local execution clients). It lists bounded
summaries of active assistant handoffs that match the supplied project, host,
subject, realm, status, and release filters:

```sh
groundrecall-handoff-discover /var/lib/groundrecall \
  --policy-config /etc/groundrecall/server-policy.yaml \
  --subject-id alice --realm-id project-a --project GroundRecall \
  --host-id build-host --format json --limit 10
```

The command evaluates the server-owned policy provider for each candidate and
omits denied or hard-gated records. Output is capped at 100 records (and the
requested lower limit), with bounded objective, acceptance-criteria, and
context-reference fields. It reports `canonical_write: false` and
`execution_performed: false` so a wrapper can safely present the result to a
Codex session.

Discovery does not claim, accept, execute, or mutate a handoff. A separate
authorized lifecycle call must perform any status transition or progress/result
append. A missing policy configuration uses GroundRecall's default-allow
behavior for local development; production deployments should always provide a
server-owned policy file.
