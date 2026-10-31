# syntax=docker/dockerfile:1

FROM ghcr.io/astral-sh/uv:0.13.6@sha256:af22a52f5eafef3d78e551599d405c02df61919d18028f0cea8eda93bc9986d0 AS uv
FROM docker:29.9.2-cli@sha256:5e6baf67325a79f64ed3bed6863954d5e05d0f3d4e57cbdb14809346814bbfdb AS dockercli

FROM debian:13-slim@sha256:f6b08b09a05725f9431502d3b5714f5c4576e82c1a84fa1debe0c24a7e0c3ec4

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        diffutils \
        git \
        make \
        unzip \
        xz-utils \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL -o /tmp/mise-install.sh https://mise.run \
    && MISE_VERSION=v2026.10.22 MISE_INSTALL_PATH=/usr/local/bin/mise sh /tmp/mise-install.sh \
    && rm -f /tmp/mise-install.sh

COPY --from=uv /uv /uvx /usr/local/bin/
COPY --from=dockercli /usr/local/bin/docker /usr/local/bin/docker

ENV MISE_DATA_DIR=/opt/mise \
    MISE_CACHE_DIR=/opt/mise-cache \
    MISE_TRUSTED_CONFIG_PATHS=/src:/woodpecker \
    MISE_EXEC_AUTO_INSTALL=0 \
    UV_CACHE_DIR=/opt/uv-cache \
    UV_PYTHON_INSTALL_DIR=/opt/uv-python \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:/opt/mise/shims:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

WORKDIR /src

COPY .mise.toml .python-version pyproject.toml uv.lock ./
# CI 只需要工具子集；版本仍来自 .mise.toml（bare name 解析配置版本）
RUN mise install --yes \
        helm \
        kubectl \
        kustomize \
        opentofu \
        go \
        gotestsum \
        dyff \
        shellcheck \
    && uv sync --frozen --only-group dev --only-group scripts
