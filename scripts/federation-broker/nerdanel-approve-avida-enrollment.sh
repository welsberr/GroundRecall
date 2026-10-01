#!/usr/bin/env bash
set -euo pipefail

# Approve exactly the Avida project realm/scope and internal release ceiling.
# Run on nerdanel with the reviewed GroundRecall checkout and operator token.

if [[ $(hostname -s) != nerdanel ]]; then
  echo "Run this script on nerdanel (current host: $(hostname -s))." >&2
  exit 2
fi
if [[ $# -ne 2 ]]; then
  echo "Usage: $0 PENDING_ENROLLMENT_ID /path/to/operator.token" >&2
  exit 2
fi
enrollment_id=$1
operator_token=$2
if [[ ! $enrollment_id =~ ^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,255}$ ]]; then
  echo "Invalid enrollment ID." >&2
  exit 2
fi
if [[ ! -f $operator_token ]]; then
  echo "Operator token file not found." >&2
  exit 1
fi
if [[ $(stat -c '%a' "$operator_token") != 600 ]]; then
  echo "Operator token must have mode 600." >&2
  exit 1
fi
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
approval_file=$(mktemp)
trap 'rm -f "$approval_file"' EXIT
cat >"$approval_file" <<'JSON'
{
  "schema_version": "groundrecall.federation_broker.enrollment_approval.v1",
  "realm_ids": ["avida-project"],
  "scope_ids": ["avida"],
  "release_ceiling": "internal",
  "allowed_restriction_markers": [],
  "allowed_compartments": []
}
JSON
chmod 600 "$approval_file"
PYTHONPATH="$repo_root/src${PYTHONPATH:+:$PYTHONPATH}" \
  /home/netuser/bin/mambaforge/bin/python -m groundrecall.federation_broker_client \
  enrollment-approve --url http://127.0.0.1:18765 \
  --token-file "$operator_token" --enrollment-id "$enrollment_id" \
  --approval "$approval_file"
