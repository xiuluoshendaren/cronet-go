#!/bin/sh
# Invoke through GoLand MCP. Tests and both native libraries stay in the project.
set -eu
TASK_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$TASK_ROOT"
python3 scripts/prepare_go.py
mkdir -p .build/logs
CRONET_RESULT=0
docker run --rm --platform linux/amd64 \
    -v "$TASK_ROOT:$TASK_ROOT" -w "$TASK_ROOT" \
    -e HOME="$TASK_ROOT/.build/linux/home" \
    --entrypoint python3 cronet-go-builder:159 scripts/test_linux.py "$@" \
    > .build/logs/go-test-linux.log 2>&1 || CRONET_RESULT=$?
cat .build/logs/go-test-linux.log
exit "$CRONET_RESULT"
