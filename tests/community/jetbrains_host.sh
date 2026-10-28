#!/bin/sh
set -eu
# Do not start native host tests on a network-enabled interface.
for interface in /sys/class/net/*; do
  [ "${interface##*/}" = lo ] || { echo 'Native IDE tests require Docker --network none'; exit 1; }
done
cd /workspace/integrations/upstream/jetbrains
exec ./gradlew --offline --no-daemon :client:test test --stacktrace
