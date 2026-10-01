#!/usr/bin/env bash
set -euo pipefail

# Install a loopback-only reverse SSH tunnel from alatar to nerdanel's broker.
# Run as the nerdanel account that owns the SSH alias `alatar`.

broker_url=${BROKER_LOCAL_URL:-http://127.0.0.1:18765}
remote_port=${BROKER_ALATAR_PORT:-18766}
unit_name=groundrecall-broker-tunnel-alatar.service
unit_dir=${XDG_CONFIG_HOME:-"$HOME/.config"}/systemd/user
unit_file=$unit_dir/$unit_name

if [[ $(hostname -s) != nerdanel ]]; then
  echo "Run this script on nerdanel (current host: $(hostname -s))." >&2
  exit 2
fi
if ! command -v systemctl >/dev/null || ! command -v ssh >/dev/null; then
  echo "systemctl and ssh are required." >&2
  exit 2
fi
if ! curl --fail --silent --show-error --max-time 3 "$broker_url/api/v1/broker" >/dev/null; then
  echo "Broker is not responding at $broker_url/api/v1/broker." >&2
  exit 1
fi
if ! ssh -o BatchMode=yes -o ConnectTimeout=5 alatar true; then
  echo "Cannot open the nerdanel-to-alatar SSH path yet; fix host reachability/SSH before installing the tunnel." >&2
  exit 1
fi
if [[ ! $remote_port =~ ^[0-9]+$ ]] || (( remote_port < 1024 || remote_port > 65535 )); then
  echo "BROKER_ALATAR_PORT must be an unused port from 1024 through 65535." >&2
  exit 2
fi

mkdir -p "$unit_dir"
chmod 700 "$unit_dir"
unit_contents=$(cat <<EOF
[Unit]
Description=SSH tunnel from alatar to the nerdanel GroundRecall broker
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -R 127.0.0.1:${remote_port}:127.0.0.1:18765 alatar
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
EOF
)

if [[ -e $unit_file ]]; then
  if [[ $(cat "$unit_file") != "$unit_contents" ]]; then
    echo "Refusing to replace existing $unit_file; review or back it up first." >&2
    exit 1
  fi
else
  tmp=$(mktemp "$unit_dir/.${unit_name}.XXXXXX")
  trap 'rm -f "$tmp"' EXIT
  printf '%s\n' "$unit_contents" >"$tmp"
  chmod 600 "$tmp"
  mv "$tmp" "$unit_file"
  trap - EXIT
fi

systemctl --user daemon-reload
systemctl --user enable --now "$unit_name"
systemctl --user --no-pager --full status "$unit_name"
echo "Tunnel listener on alatar: 127.0.0.1:${remote_port}; broker destination on nerdanel: 127.0.0.1:18765."
