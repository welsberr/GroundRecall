#!/usr/bin/env bash
set -euo pipefail

# Install GroundRecall's broker client into a private venv and verify the tunnel.
# The source directory must contain the reviewed broker-client implementation.

if [[ $(hostname -s) != alatar ]]; then
  echo "Run this script on alatar (current host: $(hostname -s))." >&2
  exit 2
fi
if [[ $# -ne 1 ]]; then
  echo "Usage: $0 /path/to/reviewed/GroundRecall/checkout" >&2
  exit 2
fi
source_dir=$(cd "$1" && pwd)
if [[ ! -f $source_dir/pyproject.toml || ! -f $source_dir/src/groundrecall/federation_broker_client.py ]]; then
  echo "Source checkout does not contain GroundRecall's federation broker client." >&2
  exit 1
fi
if ! grep -Eq 'groundrecall-broker[[:space:]]*=' "$source_dir/pyproject.toml"; then
  echo "Source checkout does not install the groundrecall-broker command." >&2
  exit 1
fi

python_bin=${PYTHON:-python3}
venv_dir=${GROUNDRECALL_VENV:-$HOME/.local/share/groundrecall-broker/venv}
broker_url=${GROUNDRECALL_BROKER_URL:-http://127.0.0.1:18766}
token_file=${GROUNDRECALL_BROKER_TOKEN_FILE:-$HOME/.config/groundrecall/broker.token}

command -v "$python_bin" >/dev/null || { echo "Python not found: $python_bin" >&2; exit 1; }
"$python_bin" -m venv "$venv_dir"
"$venv_dir/bin/python" -m pip install --upgrade pip
"$venv_dir/bin/python" -m pip install --editable "$source_dir"
if [[ ! -f $token_file ]]; then
  echo "Client installed, but participant token is missing at $token_file." >&2
  exit 1
fi
if [[ $(stat -c '%a' "$token_file") != 600 ]]; then
  echo "Token file must have mode 600: $token_file" >&2
  exit 1
fi
"$venv_dir/bin/groundrecall-broker" info --url "$broker_url"
echo "Client is installed and the broker endpoint responded. Use this URL for broker commands: $broker_url"
