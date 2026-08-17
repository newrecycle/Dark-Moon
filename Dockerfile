# ============================================================
# STAGE 1 — BUILDER
# ============================================================
FROM golang:1.26-bookworm AS builder

ENV DEBIAN_FRONTEND=noninteractive \
    GOTOOLCHAIN=local \
    GO111MODULE=on \
    GOWORK=off \
    GOPROXY=https://proxy.golang.org,direct \
    GOSUMDB=sum.golang.org \
    OUT=/out

WORKDIR /build

# ------------------------------------------------------------
# Build dependencies
# ------------------------------------------------------------
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl git unzip ca-certificates pkg-config \
    autoconf automake libtool make file \
    libssl-dev zlib1g-dev libnghttp2-dev libidn2-0-dev libpsl-dev \
    libkrb5-dev libssh2-1-dev \
    libreadline-dev libyaml-dev libffi-dev libbz2-dev libsqlite3-dev \
    liblzma-dev libgdbm-dev libnss3-dev libncurses-dev uuid-dev \
 && rm -rf /var/lib/apt/lists/*

# ------------------------------------------------------------
# libcurl custom
# ------------------------------------------------------------
RUN set -eux; \
    CURL_VER="8.15.0"; \
    CURL_SHA256="6cd0a8a5b126ddfda61c94dc2c3fc53481ba7a35461cf7c5ab66aa9d6775b609"; \
    curl -fsSL https://curl.se/download/curl-${CURL_VER}.tar.xz -o curl.tar.xz; \
    echo "${CURL_SHA256}  curl.tar.xz" | sha256sum -c -; \
    tar -xf curl.tar.xz; cd curl-${CURL_VER}; \
    ./configure --prefix=${OUT}/curl \
        --with-openssl \
        --with-nghttp2 \
        --enable-http --enable-ftp --enable-file --enable-tls-srp \
        --disable-static; \
    make -j$(nproc); make install; \
    ${OUT}/curl/bin/curl --version

ENV PKG_CONFIG_PATH=${OUT}/curl/lib/pkgconfig

# ------------------------------------------------------------
# Go tools
# ------------------------------------------------------------
COPY setup.sh .
RUN --mount=type=cache,target=/go/pkg/mod \
    --mount=type=cache,target=/root/.cache/go-build \
    chmod +x setup.sh \
 && sed -i -E 's/(apt( |-)?get install -y[^#\n]*)\s+(golang(-go|-doc|-src)?)/\1/g' setup.sh \
 && bash -x setup.sh

# ------------------------------------------------------------
# Nuclei templates
# ------------------------------------------------------------
RUN install -d ${OUT}/nuclei-templates \
 && git clone --depth 1 \
      https://github.com/projectdiscovery/nuclei-templates.git ${OUT}/nuclei-templates

# ------------------------------------------------------------
# Ruby 
# ------------------------------------------------------------
ARG RUBY_PREFIX=/opt/darkmoon/ruby
ARG RUBY_VERSION=3.3.5
ENV RUBY_BUILD_CACHE_PATH=/tmp/ruby-cache
RUN install -d ${RUBY_BUILD_CACHE_PATH} \
 && curl -fsSL https://cache.ruby-lang.org/pub/ruby/3.3/ruby-${RUBY_VERSION}.tar.gz \
      -o ${RUBY_BUILD_CACHE_PATH}/ruby-${RUBY_VERSION}.tar.gz \
 && echo "3781a3504222c2f26cb4b9eb9c1a12dbf4944d366ce24a9ff8cf99ecbce75196  ${RUBY_BUILD_CACHE_PATH}/ruby-${RUBY_VERSION}.tar.gz" | sha256sum -c - \
 && git clone https://github.com/rbenv/ruby-build.git /tmp/ruby-build \
 && /tmp/ruby-build/install.sh \
 && ruby-build ${RUBY_VERSION} ${RUBY_PREFIX} \
 && rm -rf /tmp/ruby-build /tmp/ruby-cache

# Ruby tools
COPY setup_ruby.sh /setup_ruby.sh
RUN --mount=type=cache,target=/root/.gem \
    chmod +x /setup_ruby.sh && /setup_ruby.sh

# ------------------------------------------------------------
# Python custom
# ------------------------------------------------------------
ARG PY_VER=3.12.6
ARG PY_PREFIX=/opt/darkmoon/python
RUN curl -fsSL https://www.python.org/ftp/python/${PY_VER}/Python-${PY_VER}.tgz -o python.tgz \
 && echo "85a4c1be906d20e5c5a69f2466b00da769c221d6a684acfd3a514dbf5bf10a66  python.tgz" | sha256sum -c - \
 && tar -xzf python.tgz \
 && cd Python-${PY_VER} \
 && ./configure --prefix=${PY_PREFIX} --enable-optimizations --with-ensurepip=install \
 && make -j$(nproc) && make install

# ------------------------------------------------------------
# Rust
# ------------------------------------------------------------
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain stable \
 && . "$HOME/.cargo/env"
ENV PATH="/root/.cargo/bin:${PATH}"

# ------------------------------------------------------------
# Python tooling
# ------------------------------------------------------------
COPY setup_py.sh /setup_py.sh
RUN --mount=type=cache,target=/root/.cache/pip \
    chmod +x /setup_py.sh && /setup_py.sh

# ------------------------------------------------------------
# SecLists — sparse: only the files actually used by agents
# ------------------------------------------------------------
RUN install -d \
      ${OUT}/seclists/Discovery/Web-Content \
      ${OUT}/seclists/Passwords \
      ${OUT}/seclists/Fuzzing \
      ${OUT}/seclists/Discovery/DNS \
 && BASE="https://raw.githubusercontent.com/danielmiessler/SecLists/master" \
 && curl -fsSL --retry 3 "${BASE}/Discovery/Web-Content/common.txt" \
      -o ${OUT}/seclists/Discovery/Web-Content/common.txt \
 && curl -fsSL --retry 3 "${BASE}/Discovery/Web-Content/big.txt" \
      -o ${OUT}/seclists/Discovery/Web-Content/big.txt \
 && curl -fsSL --retry 3 "${BASE}/Discovery/Web-Content/raft-medium-words.txt" \
      -o ${OUT}/seclists/Discovery/Web-Content/raft-medium-words.txt \
 && curl -fsSL --retry 3 "${BASE}/Discovery/Web-Content/DirBuster-2007_directory-list-2.3-medium.txt" \
      -o ${OUT}/seclists/Discovery/Web-Content/directory-list-2.3-medium.txt \
 && curl -fsSL --retry 3 "${BASE}/Discovery/DNS/subdomains-top1million-5000.txt" \
      -o ${OUT}/seclists/Discovery/DNS/subdomains-top1million-5000.txt \
 && curl -fsSL --retry 3 "${BASE}/Fuzzing/fuzz-Bo0oM.txt" \
      -o ${OUT}/seclists/Fuzzing/fuzz-Bo0oM.txt

# ============================================================
# STAGE 2 — CUDA DEVEL (GPU + CPU fallback)
# ============================================================
FROM nvidia/cuda:13.1.0-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    DM_HOME=/opt/darkmoon

# ------------------------------------------------------------
# Runtime OS dependencies + hashcat + tools (single layer)
# ------------------------------------------------------------
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    sed -i 's|http://archive.ubuntu.com|http://fr.archive.ubuntu.com|g' /etc/apt/sources.list \
 && sed -i 's|http://security.ubuntu.com|http://fr.archive.ubuntu.com|g' /etc/apt/sources.list \
 && apt-get update -o Acquire::Retries=3 \
 && apt-get install -y --no-install-recommends \
    # base runtime
    ca-certificates tzdata bash dnsutils jq curl git \
    # libs runtime
    libssl3 zlib1g libnghttp2-14 libidn2-0 libpsl5 \
    libkrb5-3 libssh2-1 libyaml-0-2 libreadline8 \
    libffi8 libgmp10 libncursesw6 libpcap0.8 \
    hydra snmp openssh-client inotify-tools acl \
    nmap medusa ncrack \
    # pip / wheels
    build-essential pkg-config libffi-dev libssl-dev \
    # Chromium / Playwright
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libx11-xcb1 \
    libxcomposite1 libxdamage1 libxrandr2 libgbm1 \
    libasound2 libpangocairo-1.0-0 libgtk-3-0 \
    # OpenCL
    ocl-icd-libopencl1 opencl-headers clinfo \
    mesa-opencl-icd intel-opencl-icd pocl-opencl-icd \
    # tools
    wget xz-utils p7zip-full zip unzip iputils-ping \
    # database / cache clients
    postgresql-client default-mysql-client redis-tools \
    # cracking + wordlist
    cewl john libcompress-raw-lzma-perl \
    # firmware / IoT
    binwalk squashfs-tools sqlite3 arp-scan netcat-openbsd nfs-common file e2fsprogs \
 && rm -rf /var/lib/apt/lists/* \
 && rm -rf /tmp/* /var/tmp/*

# ------------------------------------------------------------
# Hashcat + 7z2john + firmwalker + sasquatch (single layer)
# ------------------------------------------------------------
RUN set -eux; \
    cd /tmp; \
    wget https://hashcat.net/files/hashcat-6.2.6.7z; \
    7z x hashcat-6.2.6.7z; \
    mv hashcat-6.2.6 /opt/hashcat; \
    ln -sf /opt/hashcat/hashcat.bin /usr/local/bin/hashcat; \
    rm hashcat-6.2.6.7z; \
    wget -qO /usr/local/bin/7z2john.pl https://raw.githubusercontent.com/openwall/john/bleeding-jumbo/run/7z2john.pl; \
    printf '#!/bin/sh\nexec perl /usr/local/bin/7z2john.pl "$@"\n' > /usr/local/bin/7z2john; \
    chmod +x /usr/local/bin/7z2john /usr/local/bin/7z2john.pl; \
    git clone https://github.com/craigz28/firmwalker.git /opt/firmwalker; \
    git -C /opt/firmwalker checkout 23ff299980319b7f1b623817a176e06dda143b45; \
    ln -sf /opt/firmwalker/firmwalker.sh /usr/local/bin/firmwalker; \
    chmod +x /opt/firmwalker/firmwalker.sh; \
    # sasquatch (firmware SquashFS extraction) - best effort per build
    apt-get update && apt-get install -y --no-install-recommends wget xz-utils \
    && SASQUATCH_TAG=sasquatch-v4.5.1-6 \
    && arch="$(dpkg --print-architecture)" \
    && wget -q "https://github.com/onekey-sec/sasquatch/releases/download/${SASQUATCH_TAG}/sasquatch_1.0_${arch}.deb" -O /tmp/sasquatch.deb \
    && dpkg -i /tmp/sasquatch.deb || apt-get install -f -y \
    && rm -f /tmp/sasquatch.deb; \
    rm -rf /tmp/*

# ------------------------------------------------------------
# Node.js + Playwright (stable project install)
# ------------------------------------------------------------
# PLAYWRIGHT_CACHE_BUSTER invalidates this layer (and everything after it)
# on demand so the browsers get re-captured into the image layer without
# throwing away the 20GB+ of cached tooling above it. Bump it when you need
# to reinstall Playwright/Chromium. The BuildKit cache mounts below persist
# the npm + browser downloads across builds, so this layer only ever
# re-downloads when the buster changes.
ARG PLAYWRIGHT_CACHE_BUSTER=1
WORKDIR /opt/darkmoon

RUN --mount=type=cache,target=/root/.npm \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && npm init -y \
 && npm install playwright \
 && PLAYWRIGHT_BROWSERS_PATH=/opt/darkmoon-browsers npx playwright install chromium \
 && npm cache clean --force

# Pin Playwright to the on-image browser path at runtime too.
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/darkmoon-browsers

# ------------------------------------------------------------
# Google Cloud SDK (gcp agent): gcloud + gsutil + bq via official tarball
# az (Azure CLI) and aws are installed into /opt/darkmoon/python by setup_py.sh
# ------------------------------------------------------------
ARG GCLOUD_VERSION=490.0.0
RUN curl -fsSL "https://dl.google.com/dl/cloudsdk/channels/rapid/downloads/google-cloud-cli-${GCLOUD_VERSION}-linux-x86_64.tar.gz" -o /tmp/gcloud.tgz \
 && tar xzf /tmp/gcloud.tgz -C /opt \
 && rm -f /tmp/gcloud.tgz \
 && /opt/google-cloud-sdk/install.sh --quiet --usage-reporting false --path-update false --command-completion false \
 && ln -sf /opt/google-cloud-sdk/bin/gcloud /usr/local/bin/gcloud \
 && ln -sf /opt/google-cloud-sdk/bin/gsutil /usr/local/bin/gsutil \
 && ln -sf /opt/google-cloud-sdk/bin/bq /usr/local/bin/bq \
 && gcloud --version | head -1

# ------------------------------------------------------------
# Core artefacts copiés depuis builder
# ------------------------------------------------------------
COPY --from=builder /out /out
COPY --from=builder /opt/darkmoon /opt/darkmoon

# ------------------------------------------------------------
# Environment runtime
# ------------------------------------------------------------
ENV PATH="/opt/darkmoon/curl/bin:/opt/darkmoon/python/bin:/opt/darkmoon/ruby/bin:${PATH}" \
    LD_LIBRARY_PATH="/usr/lib/aarch64-linux-gnu:/usr/lib/x86_64-linux-gnu:/opt/darkmoon/curl/lib:/opt/darkmoon/python/lib:/opt/darkmoon/ruby/lib"

RUN ln -s /opt/darkmoon/python/bin/python3 /usr/local/bin/python \
 && ln -s /opt/darkmoon/python/bin/pip3 /usr/local/bin/pip

# ------------------------------------------------------------
# Wordlists & data
# ------------------------------------------------------------
RUN mkdir -p /usr/share/wordlists /usr/share/dirb \
 && ln -sfn /out/seclists /usr/share/seclists \
 && ln -sfn /usr/share/seclists /usr/share/wordlists/seclists \
 && ln -sfn /out/wordlists/dirb /usr/share/dirb/wordlists \
 && ln -sfn /usr/share/seclists ${DM_HOME}/seclists

# ------------------------------------------------------------
# Full rockyou.txt (134 MB) — required for hash cracking
# SecLists only ships fragments; download the real one from
# the canonical GitHub release mirror and place it where
# tools (hashcat, john, hydra) expect it.
# ------------------------------------------------------------
RUN curl -fsSL --max-redirs 5 \
      "https://github.com/brannondorsey/naive-hashcat/releases/download/data/rockyou.txt" \
      -o /usr/share/wordlists/rockyou.txt \
 && ln -sf /usr/share/wordlists/rockyou.txt \
          /usr/share/seclists/Passwords/rockyou.txt \
 && echo "[OK] rockyou.txt $(wc -l < /usr/share/wordlists/rockyou.txt) lines"

# The NVIDIA container runtime only mounts the driver libraries when these are
# declared. Without them a container started with `--gpus all` still sees no GPU,
# which is why hashcat silently fell back to CPU pthreads on every deployment.
# Harmless on hosts with no NVIDIA GPU: the runtime simply ignores them.
ENV NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility

ENV SECLISTS=/usr/share/seclists \
    NUCLEI_TEMPLATES=${DM_HOME}/nuclei-templates

# ------------------------------------------------------------
# Binary and wrapper installations
# ------------------------------------------------------------
RUN test -d /out/bin || { echo "ERROR: /out/bin directory not found"; exit 1; } \
 && test "$(ls -A /out/bin 2>/dev/null)" || { echo "ERROR: /out/bin is empty"; exit 1; }

RUN for bin in /out/bin/*; do \
      install -m 755 "$bin" "/usr/local/bin/$(basename "$bin")"; \
    done

# Canonical toolbox inventory + manifest-driven verifier. Enables offline,
# reproducible verification of the image without touching running services.
COPY tools/toolbox-manifest.json /opt/darkmoon/toolbox/manifest.json
COPY tools/verify_toolbox.py /opt/darkmoon/toolbox/verify_toolbox.py
COPY tools/verify-toolbox.sh /opt/darkmoon/toolbox/verify-toolbox.sh
COPY tools/tests/smoke_gpu_hash.sh /opt/darkmoon/toolbox/tests/smoke_gpu_hash.sh
RUN install -d /opt/darkmoon/toolbox \
 && chmod 644 /opt/darkmoon/toolbox/manifest.json /opt/darkmoon/toolbox/verify_toolbox.py \
 && chmod +x /opt/darkmoon/toolbox/verify-toolbox.sh /opt/darkmoon/toolbox/tests/smoke_gpu_hash.sh

# ------------------------------------------------------------
# Post-install validation minimale
# ------------------------------------------------------------
RUN command -v nuclei >/dev/null \
 && command -v finalrecon >/dev/null \
 && command -v node >/dev/null \
 && node -e "require('playwright')"

# ------------------------------------------------------------
# Nuclei bootstrap
# ------------------------------------------------------------
RUN mkdir -p /root/nuclei-templates \
 && cp -a ${NUCLEI_TEMPLATES}/. /root/nuclei-templates/ || true \
 && nuclei -tl >/dev/null 2>&1 || true

# ------------------------------------------------------------
# Hardening
# ------------------------------------------------------------
RUN apt-get purge -y login passwd libpam* gnupg* apt || true \
 && rm -rf /etc/apt /var/lib/apt /var/cache/apt

RUN mkdir -p /var/lib/dpkg \
 && : > /var/lib/dpkg/status \
 && rm -rf /var/lib/dpkg/info /var/lib/dpkg/updates

# Shared workspace used by the OpenCode orchestrator and every toolbox-backed
# subagent command. Compose bind-mounts the host's ./shared directory here.
ENV DARKMOON_SHARED_DIR=/output \
    DARKMOON_UID=1000 \
    DARKMOON_GID=1000
RUN install -d -o 1000 -g 1000 -m 2775 "${DARKMOON_SHARED_DIR}"
WORKDIR ${DARKMOON_SHARED_DIR}

COPY conf/entrypoint-darkmoon.sh /entrypoint-darkmoon.sh
RUN sed -i 's/\r$//' /entrypoint-darkmoon.sh \
 && chmod +x /entrypoint-darkmoon.sh

ENTRYPOINT ["/entrypoint-darkmoon.sh"]
CMD ["bash","-lc", "sleep infinity"]
