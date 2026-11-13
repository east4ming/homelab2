#!/bin/bash
# One-time tool install inside the running DSH container.
# Run through scripts/install-dsh-tools; paths are persisted on the tools PVC.
set -euo pipefail

export HOME="${HOME:-/workspace}"
export XDG_DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$HOME/.local/cache}"
export XDG_STATE_HOME="${XDG_STATE_HOME:-$HOME/.local/state}"
export PATH="$HOME/.local/bin:$XDG_DATA_HOME/mise/shims:$PATH"

mkdir -p "$HOME/.local/bin" "$XDG_DATA_HOME" "$XDG_CONFIG_HOME" "$XDG_CACHE_HOME" "$XDG_STATE_HOME"

if ! command -v uv >/dev/null 2>&1; then
  echo "==> installing uv into $HOME/.local/bin"
  curl -LsSf https://astral.sh/uv/install.sh |
    env UV_INSTALL_DIR="$HOME/.local/bin" UV_NO_MODIFY_PATH=1 sh
fi

if ! command -v mise >/dev/null 2>&1; then
  echo "==> installing mise into $HOME/.local/bin"
  curl -fsSL https://mise.run |
    env MISE_INSTALL_PATH="$HOME/.local/bin/mise" sh
fi

export PATH="$HOME/.local/bin:$XDG_DATA_HOME/mise/shims:$PATH"

echo "==> installing uv tools"
for package in specify-cli pre-commit pyrefly yamllint; do
  if ! uv tool list 2>/dev/null | grep -qE "(^|[[:space:]])${package} "; then
    uv tool install "$package"
  fi
  if ! uv tool list 2>/dev/null | grep -qE "(^|[[:space:]])${package} "; then
    echo "ERROR: uv tool $package was not installed" >&2
    exit 1
  fi
done

echo "==> installing mise tools"
# aqua is explicit for atuin so the prebuilt binary is used instead of cargo.
MISE_YES=1 mise use -g --yes \
  gh@latest \
  kubectl@latest \
  jq@latest \
  'github:mikefarah/yq@latest' \
  'npm:@colbymchenry/codegraph@latest' \
  'npm:clawhub@latest' \
  'github:yusukebe/ax@latest' \
  'github:Dicklesworthstone/destructive_command_guard@latest' \
  'github:harehare/mq@latest' \
  'aqua:atuinsh/atuin@latest'
MISE_YES=1 mise install --yes
mise reshim

# mikefarah/yq's GitHub asset is named yq_linux_amd64; expose it as yq.
# The aqua: backend verifies with cosign, which fails on this cluster's egress.
if ! command -v yq >/dev/null 2>&1; then
  yq_asset="$(mise where github:mikefarah/yq 2>/dev/null || true)/yq_linux_amd64"
  if [ -x "$yq_asset" ]; then
    ln -sf "$yq_asset" "$HOME/.local/bin/yq"
  fi
fi

echo "==> verifying tools"
for command in uv mise atuin codegraph dcg gh kubectl jq yq ax mq clawhub pre-commit pyrefly yamllint; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "ERROR: $command is not on PATH" >&2
    exit 1
  fi
done

marker="$HOME/.local/.dsh-tools-version"
{
  date -u '+%Y-%m-%dT%H:%M:%SZ'
  uv --version
  mise --version
  uv tool list
  mise ls --global
} >"$marker"

echo "==> tools installed; marker: $marker"
