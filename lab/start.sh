#!/bin/sh
# Start the dedicated demo controller and loopback management agent.
set -eu
umask 077
runtime=/run/securefed-sdn
mkdir -p "$runtime"
test -s "$runtime/token" || openssl rand -hex 32 > "$runtime/token"
export SECUREFED_LAB_TOKEN
SECUREFED_LAB_TOKEN=$(cat "$runtime/token")
ovs-testcontroller -O OpenFlow13 ptcp:16653:127.0.0.1 --unixctl="$runtime/controller.sock" &
controller_pid=$!
trap 'kill "$controller_pid" 2>/dev/null || true' EXIT
/usr/bin/python3 "$(dirname "$0")/mininet_agent.py"
