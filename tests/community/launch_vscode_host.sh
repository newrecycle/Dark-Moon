#!/bin/sh
# Run only inside docker --network none. Explicit display startup prevents the
# opaque xvfb-run wrapper from hanging before the Node watchdog starts.
set -eu
echo "vscode-native: container entry started"
test -d /tmp || exit 1
Xvfb :98 -screen 0 1440x900x24 -nolisten tcp > /dev/null 2>&1 &
xvfb_pid=$!
cleanup() {
  kill "$xvfb_pid" 2>/dev/null || true
  wait "$xvfb_pid" 2>/dev/null || true
}
trap cleanup EXIT HUP INT TERM
i=0
while [ "$i" -lt 100 ]; do
  if ! kill -0 "$xvfb_pid" 2>/dev/null; then
    echo "vscode-native: display process exited early"
    exit 1
  fi
  if [ -S /tmp/.X11-unix/X98 ]; then
    break
  fi
  i=$((i + 1))
  sleep 0.1
done
if [ ! -S /tmp/.X11-unix/X98 ]; then
  echo "vscode-native: display startup deadline reached"
  exit 1
fi
echo "vscode-native: display ready"
export DISPLAY=:98
node tests/community/vscode_host.cjs
