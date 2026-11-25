# Chromium's pinned Rust toolchain is published for Linux x86-64.
# This builder cross-compiles both x86-64 and arm64, including on Apple Silicon.
ARG CRONET_BUILDER_PLATFORM=linux/amd64
FROM --platform=$CRONET_BUILDER_PLATFORM ubuntu:24.04
ARG DEBIAN_FRONTEND=noninteractive
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    rm -f /etc/apt/apt.conf.d/docker-clean && \
    for attempt in 1 2 3 4 5; do \
    apt-get -o Acquire::Retries=6 update; \
    apt-get -o Acquire::Retries=6 install -y --no-install-recommends \
    ca-certificates curl git python3 python3-setuptools python3-six \
    pkg-config xz-utils bzip2 unzip build-essential file \
    libglib2.0-dev libnss3-dev libnspr4-dev zlib1g-dev && exit 0; \
    done; exit 1
ENV DEPOT_TOOLS_UPDATE=0 PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
ENTRYPOINT ["python3", "scripts/build_linux.py"]
