# syntax=docker/dockerfile:1

FROM ghcr.io/astral-sh/uv:0.13.6@sha256:af22a52f5eafef3d78e551599d405c02df61919d18028f0cea8eda93bc9986d0 AS uv

FROM debian:13-slim@sha256:f6b08b09a05725f9431502d3b5714f5c4576e82c1a84fa1debe0c24a7e0c3ec4

LABEL org.opencontainers.image.source="https://github.com/east4ming/homelab2" \
      org.opencontainers.image.description="Homelab2 CI static checks (pre-commit)"

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        diffutils \
        git \
        unzip \
        xz-utils

RUN curl -fsSL -o /tmp/mise-install.sh https://mise.run \
    && MISE_VERSION=v2026.10.22 MISE_INSTALL_PATH=/usr/local/bin/mise sh /tmp/mise-install.sh \
    && rm -f /tmp/mise-install.sh

COPY --from=uv /uv /uvx /usr/local/bin/

ENV MISE_DATA_DIR=/opt/mise \
    MISE_CACHE_DIR=/tmp/mise-cache \
    MISE_TRUSTED_CONFIG_PATHS=/src:/woodpecker \
    MISE_EXEC_AUTO_INSTALL=0 \
    UV_CACHE_DIR=/tmp/uv-cache \
    UV_PYTHON_INSTALL_DIR=/opt/uv-python \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:/opt/mise/shims:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

WORKDIR /src

COPY .mise.toml .python-version pyproject.toml uv.lock ./
# 只保留 pre-commit 需要的工具（helm/helmlint、shellcheck、dyff 供 helm-diff）。
# 版本仍来自 .mise.toml（bare name 解析配置版本）。
# 缓存目录使用 BuildKit cache mount，不进入镜像层。
RUN --mount=type=cache,target=/tmp/mise-cache \
    --mount=type=cache,target=/tmp/uv-cache \
    mise install --yes \
        helm \
        dyff \
        shellcheck \
    && uv sync --frozen --only-group ci
