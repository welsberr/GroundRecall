#!/usr/bin/env bash
set -euo pipefail

# Copy alatar's broker token to its owner-only config path over SSH.

if [[ $(hostname -s) != nerdanel ]]; then
  echo "Run this script on nerdanel (current host: $(hostname -s))." >&2
  exit 2
fi
if [[ $# -ne 1 ]]; then
  echo "Usage: $0 /path/to/alatar-participant.token" >&2
  exit 2
fi
source_token=$1
dest_path=.config/groundrecall/broker.token
if [[ ! -f $source_token ]]; then
  echo "Token file not found: $source_token" >&2
  exit 1
fi
mode=$(stat -c '%a' "$source_token")
if (( 10#$mode > 600 )); then
  echo "Token file permissions are too broad (mode $mode); set chmod 600 first." >&2
  exit 1
fi
ssh -o BatchMode=yes alatar 'umask 077; mkdir -p "$HOME/.config/groundrecall"; test ! -e "$HOME/.config/groundrecall/broker.token"'
scp -p -- "$source_token" "alatar:$dest_path"
ssh -o BatchMode=yes alatar 'chmod 600 "$HOME/.config/groundrecall/broker.token"'
echo "Transferred alatar participant token to ~/.config/groundrecall/broker.token without displaying it."
