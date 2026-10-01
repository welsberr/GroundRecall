#!/usr/bin/env bash
set -euo pipefail

# Generate a host-local Ed25519 keypair and bounded Avida project enrollment.
# Run separately on nerdanel and alatar. The private signing key remains on
# that host; only enrollment-request.json and its public key go to the broker.

host=$(hostname -s)
if [[ $host != nerdanel && $host != alatar ]]; then
  echo "Run this script on nerdanel or alatar (current host: $host)." >&2
  exit 2
fi
if [[ $# -gt 1 ]]; then
  echo "Usage: $0 [OUTPUT_DIRECTORY]" >&2
  exit 2
fi

venv_dir=${GROUNDRECALL_VENV:-$HOME/.local/share/groundrecall-broker/venv}
out_dir=${1:-$HOME/.config/groundrecall/avida-federation}
producer_id=${AVIDA_PRODUCER_ID:-avida-$host}
realm_id=${AVIDA_REALM_ID:-avida-project}
scope_id=${AVIDA_SCOPE_ID:-avida}
key_id=${AVIDA_KEY_ID:-avida-$host-ed25519-2026}
if [[ $host == alatar ]]; then
  broker_url=${GROUNDRECALL_BROKER_URL:-http://127.0.0.1:18766}
  token_file=${GROUNDRECALL_BROKER_TOKEN_FILE:-$HOME/.config/groundrecall/broker.token}
  broker_cmd=("$venv_dir/bin/groundrecall-broker")
else
  broker_url=${GROUNDRECALL_BROKER_URL:-http://127.0.0.1:18765}
  repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
  token_file=${GROUNDRECALL_BROKER_TOKEN_FILE:-$repo_root/deploy/federation-broker/secrets/avida-nerdanel.token}
  broker_cmd=(env "PYTHONPATH=$repo_root/src${PYTHONPATH:+:$PYTHONPATH}" /home/netuser/bin/mambaforge/bin/python -m groundrecall.federation_broker_client)
fi
mkdir -p "$out_dir"
chmod 700 "$out_dir"
if [[ -e $out_dir/producer-private.pem || -e $out_dir/producer-public.pem || -e $out_dir/enrollment-request.json ]]; then
  echo "Refusing to overwrite existing key or enrollment files in $out_dir." >&2
  exit 1
fi

"${broker_cmd[@]}" keygen \
  --key-id "$key_id" \
  --private-key-file "$out_dir/producer-private.pem" \
  --public-key-file "$out_dir/producer-public.pem"
chmod 600 "$out_dir/producer-private.pem"
chmod 644 "$out_dir/producer-public.pem"
python3 - "$out_dir/producer-public.pem" "$out_dir/enrollment-request.json" "$producer_id" "$key_id" "$realm_id" "$scope_id" <<'PY'
import json
import pathlib
import sys

public_path, request_path, producer_id, key_id, realm_id, scope_id = sys.argv[1:]
pem = pathlib.Path(public_path).read_text(encoding="ascii")
request = {
    "schema_version": "groundrecall.federation_broker.enrollment_request.v1",
    "producer_instance_id": producer_id,
    "display_name": producer_id,
    "signing_keys": [{"key_id": key_id, "algorithm": "ed25519", "public_key_pem": pem}],
    "requested_realm_ids": [realm_id],
    "requested_scope_ids": [scope_id],
    "requested_release_ceiling": "internal",
    "purpose": "Share reviewed Avida project knowledge between enrolled GroundRecall hosts.",
}
pathlib.Path(request_path).write_text(json.dumps(request, indent=2) + "\n", encoding="utf-8")
pathlib.Path(request_path).chmod(0o600)
PY
echo "Created local keypair and bounded request under $out_dir. Keep producer-private.pem on $host."
echo "Submit with: ${broker_cmd[*]} enrollment-request --url $broker_url --token-file $token_file --request $out_dir/enrollment-request.json"
