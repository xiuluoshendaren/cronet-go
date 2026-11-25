#!/bin/sh
set -eu
TASK_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$TASK_ROOT"
mkdir -p .build/logs
# Native host Git avoids Docker Desktop's per-file mount overhead during checkout.
python3 scripts/build_linux.py --seed-only "$@" > .build/logs/linux-seed.log 2>&1
docker build --platform linux/amd64 \
    --build-arg HTTP_PROXY=http://host.docker.internal:8897 \
    --build-arg HTTPS_PROXY=http://host.docker.internal:8897 \
    -f native/Dockerfile -t cronet-go-builder:159 native > .build/logs/docker-image.log 2>&1
# Docker Desktop routes this hostname to the host's 127.0.0.1:8897 proxy.
docker run --rm --platform linux/amd64 \
    -v "$TASK_ROOT:$TASK_ROOT" -w "$TASK_ROOT" \
    -e HOME="$TASK_ROOT/.build/linux/home" \
    -e TMPDIR="$TASK_ROOT/.build/tmp" \
    cronet-go-builder:159 "$@" > .build/logs/linux-build.log 2>&1
