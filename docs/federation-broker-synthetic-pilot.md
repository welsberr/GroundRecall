# Synthetic federation broker pilot

Run the isolated two-participant pilot from the repository root:

```sh
PYTHONPATH=src python -m groundrecall.federation_broker_pilot
```

It starts a real broker HTTP server on an ephemeral loopback port, provisions
synthetic bearer identities, generates throwaway Ed25519 keys, and sends
synthetic catalogs and signed change bundles through the broker HTTP client.
The process creates its SQLite database, auth file, and participant quarantine
directories under a temporary directory that is removed when the run exits.
It never reads a broker URL from the environment and does not use or modify the
Compose service, its secrets, database volume, backups, or any participant
credentials. The testable entry point accepts an empty scratch directory:

```sh
PYTHONPATH=src pytest -q tests/test_federation_broker_pilot.py
```

The run covers both exchange directions, enrollment and catalog discovery,
authorization rejection for unapproved scope/release, signed-object tampering,
idempotent catalog/bundle/quarantine/ack replays, local verification into
quarantine with explicit later acknowledgement, key revocation and replacement,
broker restart persistence, and SQLite backup followed by a separate restored
HTTP service. It does not create a canonical receiver store, promote knowledge,
or acknowledge during pull. A successful summary reports `promoted: false` and
`live_compose_touched: false`.
