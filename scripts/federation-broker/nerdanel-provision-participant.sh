#!/usr/bin/env bash
set -euo pipefail

# Create a non-admin participant bearer token in the broker auth map.
# Run from the GroundRecall checkout on nerdanel. Transfer the resulting token
# to its participant over SSH; this script never prints token contents.

if [[ $(hostname -s) != nerdanel ]]; then
  echo "Run this script on nerdanel (current host: $(hostname -s))." >&2
  exit 2
fi
if [[ $# -ne 1 ]]; then
  echo "Usage: $0 PARTICIPANT_ID" >&2
  exit 2
fi
participant_id=$1
if [[ ! $participant_id =~ ^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$ ]]; then
  echo "Participant ID may contain only letters, digits, dot, underscore, and hyphen." >&2
  exit 2
fi

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
secrets_dir=$repo_root/deploy/federation-broker/secrets
auth_file=$secrets_dir/auth.json
image=${BROKER_IMAGE:-groundrecall-federation-broker:local}
host_port=${BROKER_HOST_PORT:-18765}
token_file=$secrets_dir/${participant_id}.token

if [[ ! -f $auth_file ]]; then
  echo "Broker auth file not found at $auth_file; verify the active Compose deployment." >&2
  exit 1
fi
if [[ -e $token_file ]]; then
  echo "Refusing to overwrite existing token file: $token_file" >&2
  exit 1
fi
if ! docker image inspect "$image" >/dev/null 2>&1; then
  echo "Broker image $image is unavailable; build the documented Compose image first." >&2
  exit 1
fi

mkdir -p "$secrets_dir"
chmod 700 "$secrets_dir"
docker run --rm --user "$(id -u):$(id -g)" \
  -v "$secrets_dir:/out" \
  --entrypoint python "$image" \
  -m groundrecall.federation_broker_server provision-token \
  --auth-file /out/auth.json \
  --participant-id "$participant_id" \
  --token-file "/out/${participant_id}.token"

chmod 600 "$token_file"
BROKER_HOST_PORT=$host_port docker compose -f "$repo_root/deploy/federation-broker/compose.yaml" up -d --force-recreate federation-broker
echo "Provisioned non-admin participant '$participant_id'. Token file: $token_file"
echo "Transfer the file securely; do not display or paste its contents."
