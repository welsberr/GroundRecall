# Federation broker client

`groundrecall-broker` is the HTTP client for the deployable federation broker.
It uses the versioned `/api/v1` contract and never opens the broker SQLite
database. It accepts the broker origin with `--url` or
`GROUNDRECALL_BROKER_URL`. Authenticated commands accept a protected bearer
token file with `--token-file` or `GROUNDRECALL_BROKER_TOKEN`; do not pass a
bearer token in an argument, URL, shell history, or chat. Token files must be
regular, owned by the current user, and mode `0600` or stricter. The client
disables proxy discovery and redirects so credentials cannot be forwarded to
another origin. HTTPS is required except for `localhost` and loopback IPs.

All request/response bodies are bounded at 4 MB. Error messages contain only
the HTTP status and a short broker error code, never the request or credential.

## Onboard a participant

Create private client credential directories before storing bearer tokens or
producer private keys:

```sh
install -d -m 700 ~/.config/groundrecall ~/.config/groundrecall/keys
```

Create an Ed25519 producer keypair locally. The command prints paths and the
key ID only; the private key is written atomically with mode `0600` under a
private parent directory, and the public PEM is mode `0644`.

```sh
groundrecall-broker keygen --key-id producer-2026 \
  --private-key-file ~/.config/groundrecall/keys/producer-2026-private.pem \
  --public-key-file ~/.config/groundrecall/keys/producer-2026-public.pem
```

Create an enrollment JSON file containing the stable GroundRecall producer
instance ID, only public signing keys, requested realm/scope/release bounds,
and a stated purpose. Private signing-key material stays local. The broker
administrator reviews and approves the request against its policy.

```sh
groundrecall-broker enrollment-request \
  --url https://broker.example.invalid \
  --token-file ~/.config/groundrecall/broker.token \
  --request enrollment-request.json

groundrecall-broker enrollment-approve \
  --url https://broker.example.invalid \
  --token-file ~/.config/groundrecall/operator.token \
  --enrollment-id <pending-enrollment-id> \
  --approval enrollment-bounds.json
```

`enrollment-bounds.json` uses the `EnrollmentApprovalRequest` fields in the
broker contract: `realm_ids`, `scope_ids`, `release_ceiling`,
`allowed_restriction_markers`, and `allowed_compartments`. The approval may be
no broader than the submitted request. `info` queries public API capabilities
and does not need a token.

## Exchange signed catalogs and bundles

Catalog and bundle files passed to the client are the existing signed
GroundRecall JSON objects. The broker verifies producer enrollment and
signature; it does not replace the producer signature.

```sh
groundrecall-broker catalog-publish --url "$GROUNDRECALL_BROKER_URL" \
  --token-file ~/.config/groundrecall/broker.token --file catalog.json
groundrecall-broker catalog-discover --url "$GROUNDRECALL_BROKER_URL" \
  --token-file ~/.config/groundrecall/broker.token --realm-id team-research \
  --scope-id project-alpha --query "federation" --limit 20
groundrecall-broker subscription-create --url "$GROUNDRECALL_BROKER_URL" \
  --token-file ~/.config/groundrecall/broker.token --request subscription.json
groundrecall-broker bundle-submit --url "$GROUNDRECALL_BROKER_URL" \
  --token-file ~/.config/groundrecall/broker.token --file change-bundle.json
```

Pull writes exact signed bundle files atomically into an owner-only (mode
`0700`) receiver-local directory. Names are derived from hashes, not remote
bundle IDs, and an existing file is never silently overwritten. For local
signature, subscription, and policy checks during the pull, provide the
receiver's existing change-feed subscription and producer public key:

```sh
groundrecall-broker bundle-pull --url "$GROUNDRECALL_BROKER_URL" \
  --token-file ~/.config/groundrecall/broker.token \
  --subscription-id diane-project-alpha \
  --quarantine-dir ~/.local/share/groundrecall/federation-broker-quarantine \
  --local-subscription ~/.config/groundrecall/subscriptions/diane-project-alpha.json \
  --verification-key-file producer-ed25519-public.pem --key-id producer-2026
```

`--local-subscription` and `--verification-key-file` are an optional pair. If
provided, the client also runs the existing incremental-change importer into a
private `verified/` subdirectory; rejected bundles remain in the raw local
handoff directory but are not imported. Without them, the files are an
unverified transport handoff and must be passed through the normal
`groundrecall` change-feed verification/quarantine workflow before use. Neither
mode promotes knowledge or auto-accepts a bundle.

The pull response returns an opaque `next_cursor`; persist it and pass it as
`--after-cursor` to fetch the next page. Pulling does not acknowledge delivery.
Only after a bundle has passed receiver-side signature, subscription, and
quarantine review should the operator acknowledge that exact bundle:

```sh
groundrecall-broker bundle-ack --url "$GROUNDRECALL_BROKER_URL" \
  --token-file ~/.config/groundrecall/broker.token \
  --bundle-file ~/.local/share/groundrecall/federation-broker-quarantine/<pulled-file>.json \
  --verified-locally
```

The required `--verified-locally` flag is an explicit operator confirmation;
the client does not infer verification from transport delivery. Acknowledgement
uses the pulled manifest's bundle ID and cursor end. Key rotation and revocation
are separate explicit operations: `key-add` requires a broker-admin token and
a public key file; `key-revoke` requires the owning participant token.

## Local credential-map revocation

`auth-revoke` is the one local administration command. It removes every
hash-only token row for an exact participant ID from the server auth file,
atomically; it never prints a hash or bearer secret. The hash-only map remains
readable by the container's unprivileged UID, while its containing directory
must remain private. The broker loads the map at startup, and the Compose
deployment bind-mounts the auth file, so recreate the container after
revocation with `docker compose ... up -d --force-recreate`. To replace a token, provision its replacement first and then remove
the old participant mapping; the command refuses to remove the final token so
the broker cannot become unstartable.

```sh
groundrecall-broker auth-revoke \
  --auth-file deploy/federation-broker/secrets/auth.json \
  --participant-id compose-smoke
```

For provisioning, `groundrecall-federation-broker provision-token` retains its
one-time stdout behavior for compatibility. Prefer `--token-file PATH` to
create a new owner-only mode-`0600` token file without printing the secret:

```sh
groundrecall-federation-broker provision-token \
  --auth-file deploy/federation-broker/secrets/auth.json \
  --participant-id diane-blackwood \
  --token-file ~/.config/groundrecall/diane-broker.token
```

The token-file parent directory must be owner-only. The command refuses to
overwrite an existing token file. Pass its path to the client with
`--token-file`; the broker auth map stores only the token digest.
