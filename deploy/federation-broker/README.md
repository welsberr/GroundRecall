# GroundRecall federation broker container

This Compose deployment is a private, single-host starting point. It publishes
the broker only on host loopback (`127.0.0.1:8765` by default), stores broker
state in its own named volume, runs as UID/GID 10001, drops Linux capabilities,
uses a read-only root filesystem, and does not mount either participant's
GroundRecall store. Do not change the host bind to `0.0.0.0` for convenience.
For remote access, put an authenticated private tunnel/VPN in front of this
loopback service (or deliberately configure a private interface after reviewing
the deployment security boundary). The API itself is HTTP, so do not expose it
to an untrusted network without a TLS/authenticated private transport.

## Prepare authentication

Run these commands from the GroundRecall checkout with Docker available. The
image build installs the project and its build-time Git dependency; the
provisioning command below runs from that image, so no host Python environment
is required. The token utility stores only a SHA-256 digest of each randomly
generated 256-bit bearer token. These examples write each bearer token once to
a mode-0600 file under the owner-only secrets directory without printing the
secret. Never paste a token into the compose file, shell history, or source
control.

```sh
mkdir -p deploy/federation-broker/secrets
chmod 700 deploy/federation-broker/secrets
mkdir -p deploy/federation-broker/backups
chmod 700 deploy/federation-broker/backups
docker compose -f deploy/federation-broker/compose.yaml build
docker run --rm --user "$(id -u):$(id -g)" \
  -v "$PWD/deploy/federation-broker/secrets:/out" \
  --entrypoint python groundrecall-federation-broker:local \
  -m groundrecall.federation_broker_server provision-token \
  --auth-file /out/auth.json \
  --participant-id broker-operator --admin \
  --token-file /out/broker-operator.token
docker run --rm --user "$(id -u):$(id -g)" \
  -v "$PWD/deploy/federation-broker/secrets:/out" \
  --entrypoint python groundrecall-federation-broker:local \
  -m groundrecall.federation_broker_server provision-token \
  --auth-file /out/auth.json \
  --participant-id diane-blackwood \
  --token-file /out/diane-blackwood.token
docker run --rm --user "$(id -u):$(id -g)" \
  -v "$PWD/deploy/federation-broker/secrets:/out" \
  --entrypoint python groundrecall-federation-broker:local \
  -m groundrecall.federation_broker_server provision-token \
  --auth-file /out/auth.json \
  --participant-id <your-stable-participant-id> \
  --token-file /out/your-participant.token
chmod 644 deploy/federation-broker/secrets/auth.json
```

The auth file contains token hashes and participant/role assignments, not
bearer tokens; the generated bearer secrets are stored only in the requested
mode-0600 token files. Its containing directory is mode 0700. The hash-only config is mode 0644 because
the container runs as UID 10001 and needs to read the bind-mounted file; it
contains no bearer token, and its restricted host directory prevents other
local users from reaching it. The runtime mounts it read-only. The 256-bit
random tokens make offline recovery from their SHA-256 hashes infeasible; do
not replace them with human-chosen tokens. Do not grant `--admin` to participant
tokens. To revoke a token, remove its `token_sha256` row from the auth file and
recreate the container with `docker compose ... up -d --force-recreate` so the
file bind mount and startup-loaded mappings refresh. The broker admin token is
used for enrollment approvals and administrator revocations, not participant
data exchange. An editable host install also works for provisioning
(`python -m pip install -e .`, then invoke the same module).

## Start and verify

```sh
export BROKER_HOST_PORT=18765
docker compose -f deploy/federation-broker/compose.yaml up -d --build
docker compose -f deploy/federation-broker/compose.yaml ps
curl -fsS "http://127.0.0.1:${BROKER_HOST_PORT}/healthz"
curl -fsS "http://127.0.0.1:${BROKER_HOST_PORT}/api/v1/broker"
```

`/healthz` confirms that the HTTP listener and SQLite database are responsive.
Broker capabilities are public; all participant and administrator operations
require the corresponding `Authorization: Bearer …` token. To change host port,
set `BROKER_HOST_PORT` in the environment used by Compose. Keep the `127.0.0.1`
prefix in the port mapping.

On the machine used for this pilot, another local application already owns
port 8765, so the example exports 18765. Keep that export active for subsequent
Compose commands in the same shell. On another host, set the variable to 8765
if it is available, or choose a free loopback port.

To follow logs without disclosing request URLs or authorization headers:

```sh
docker compose -f deploy/federation-broker/compose.yaml logs --tail=100 federation-broker
```

Back up the dedicated volume with the broker stopped or using a SQLite-aware
backup procedure. Never replace it with, or point it at, a participant's
GroundRecall database. Use `docker compose ... down` to stop the service; do
not use `down -v` unless intentionally deleting broker state.

## Podman

The image is OCI-compatible and avoids Docker-specific runtime APIs. The
Compose file uses standard Compose features (named volume, bind mount, local
port publishing, health check, read-only root, and Linux security options) and
is intended to work with a compatible `podman compose` provider. Podman is not
installed in the current development environment, so Podman execution remains
unverified. For Podman, keep the loopback host mapping and ensure the rootless
user can read the mounted auth file and write the named volume.

## Backup, restore, and upgrades

Back up the broker database before an upgrade. This uses SQLite's online backup
API while the broker is live, then copies the completed snapshot from the
container to a host backup directory:

```sh
export BROKER_HOST_PORT=18765
mkdir -p deploy/federation-broker/backups
chmod 700 deploy/federation-broker/backups
backup_path="deploy/federation-broker/backups/broker-$(date +%Y%m%d-%H%M%S).sqlite3"
docker compose -f deploy/federation-broker/compose.yaml exec -T federation-broker \
  python -c "import sqlite3; src=sqlite3.connect('/var/lib/groundrecall-broker/broker.sqlite3'); dst=sqlite3.connect('/var/lib/groundrecall-broker/backup.sqlite3'); src.backup(dst); dst.close(); src.close()"
docker compose -f deploy/federation-broker/compose.yaml cp \
  federation-broker:/var/lib/groundrecall-broker/backup.sqlite3 \
  "$backup_path"
chmod 600 "$backup_path"
docker compose -f deploy/federation-broker/compose.yaml exec -T federation-broker \
  python -c "from pathlib import Path; Path('/var/lib/groundrecall-broker/backup.sqlite3').unlink(missing_ok=True)"
```

Protect the host backup directory with restrictive permissions and store a
copy separately from this machine. For upgrade, keep the current image tag and
database backup, then rebuild and restart:

```sh
export BROKER_HOST_PORT=18765
docker image tag groundrecall-federation-broker:local groundrecall-federation-broker:rollback
docker compose -f deploy/federation-broker/compose.yaml build
docker compose -f deploy/federation-broker/compose.yaml up -d
docker compose -f deploy/federation-broker/compose.yaml ps
curl -fsS "http://127.0.0.1:${BROKER_HOST_PORT}/healthz"
```

If the new image fails its smoke check, point the compose service back at the
saved `:rollback` tag (edit `image:` and remove/comment `build:` for that
rollback run), restart, and investigate without discarding the database. Do
not downgrade a database after a schema-changing release unless compatibility
is confirmed. To restore, stop the service, stage a temporary copy of the
selected snapshot in the protected backups directory, and run a one-off
container against the named broker volume. Only the selected snapshot is
mounted into that helper:

```sh
export BROKER_HOST_PORT=18765
docker compose -f deploy/federation-broker/compose.yaml stop federation-broker
cp deploy/federation-broker/backups/SELECTED_BACKUP.sqlite3 deploy/federation-broker/backups/restore.sqlite3
chmod 644 deploy/federation-broker/backups/restore.sqlite3
docker run --rm --read-only --user 10001:10001 \
  --security-opt no-new-privileges:true --cap-drop ALL \
  -v groundrecall-federation-broker-data:/var/lib/groundrecall-broker \
  -v "$PWD/deploy/federation-broker/backups/restore.sqlite3:/run/restore.sqlite3:ro" \
  --entrypoint python groundrecall-federation-broker:local -c \
  "import sqlite3; src=sqlite3.connect('file:/run/restore.sqlite3?mode=ro', uri=True); dst=sqlite3.connect('/var/lib/groundrecall-broker/broker.sqlite3'); src.backup(dst); dst.close(); src.close()"
rm deploy/federation-broker/backups/restore.sqlite3
docker compose -f deploy/federation-broker/compose.yaml up -d federation-broker
curl -fsS "http://127.0.0.1:${BROKER_HOST_PORT}/healthz"
```

Replace `SELECTED_BACKUP.sqlite3` with the chosen snapshot filename. The
protected host directory is mode 0700; mode 0644 on the temporary restore copy
is needed because the helper runs as UID 10001, and it is removed immediately
after restore. Keep an untouched copy of the pre-restore database until verification passes. The
server sets umask 077 and keeps the SQLite database, WAL, and SHM files at
mode 0600 under its dedicated mode-0700 data directory.
