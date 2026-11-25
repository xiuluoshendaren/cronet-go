#!/bin/sh
# Run from GoLand's MCP terminal; all compiler caches and logs stay in the repo.
set -eu
TASK_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$TASK_ROOT"
CRONET_TARGET=${1:-mac-arm64}
CRONET_LIB="$TASK_ROOT/dist/$CRONET_TARGET"
export GOCACHE="$TASK_ROOT/.build/go-cache"
export GOMODCACHE="$TASK_ROOT/.build/go-mod"
export GOTMPDIR="$TASK_ROOT/.build/go-tmp"
export TMPDIR="$TASK_ROOT/.build/tmp"
export CGO_ENABLED=1
export CGO_CFLAGS="-I$CRONET_LIB/include"
export CGO_LDFLAGS="-L$CRONET_LIB -lcronet -Wl,-rpath,$CRONET_LIB"
mkdir -p "$GOCACHE" "$GOMODCACHE" "$GOTMPDIR" "$TMPDIR" .build/logs .build/bin
CRONET_GO_ROOT=${CRONET_GO_ROOT:-"$TASK_ROOT/.build/toolchains/go"}
if [ -x "$CRONET_GO_ROOT/bin/go" ]; then
    export PATH="$CRONET_GO_ROOT/bin:$PATH"
fi
case "$CRONET_TARGET" in
    mac-*) CRONET_LIBRARY="$CRONET_LIB/libcronet.dylib" ;;
    linux-*) CRONET_LIBRARY="$CRONET_LIB/libcronet.so" ;;
    *) echo "Unsupported target: $CRONET_TARGET" >&2; exit 1 ;;
esac
if command -v sha256sum > /dev/null 2>&1; then
    CRONET_HASH=$(sha256sum "$CRONET_LIBRARY" | awk '{print $1}')
else
    CRONET_HASH=$(shasum -a 256 "$CRONET_LIBRARY" | awk '{print $1}')
fi
# Include the native library identity in the link action to invalidate Go's cache.
CRONET_RESULT=0
go test -race -count=1 -timeout=120s -v -ldflags="-buildid=$CRONET_HASH" -o ".build/bin/cronet-$CRONET_TARGET.test" . > ".build/logs/go-test-$CRONET_TARGET.log" 2>&1 || CRONET_RESULT=$?
cat ".build/logs/go-test-$CRONET_TARGET.log"
exit "$CRONET_RESULT"
