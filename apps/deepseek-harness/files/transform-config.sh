#!/bin/bash
# Prepare a container-ready DSH config tree from a local source.
# Usage: transform-config.sh <source-dir> <staging-dir>
# Runs on the maintainer machine; never writes to the source.
set -euo pipefail

src="${1:?usage: transform-config.sh <source-dir> <staging-dir>}"
out="${2:?usage: transform-config.sh <source-dir> <staging-dir>}"

[ -d "$src" ] || { echo "ERROR: source directory not found: $src" >&2; exit 1; }
[ -f "$src/profiles/web/package.json" ] || {
  echo "ERROR: $src does not look like a DSH home (profiles/web/package.json missing)" >&2
  exit 1
}
command -v jq >/dev/null 2>&1 || { echo "ERROR: jq is required" >&2; exit 1; }
command -v yq >/dev/null 2>&1 || { echo "ERROR: yq is required" >&2; exit 1; }

mkdir -p "$out"
mkdir -p "$out/profiles/web" "$out/profiles/headless" "$out/local-plugins" \
  "$out/local-presets" "$out/skills" "$out/skills-manager" "$out/dsh-pet" "$out/integrations"

copy_file() {
  local rel="$1"
  [ -e "$src/$rel" ] || return 0
  mkdir -p "$out/$(dirname "$rel")"
  cp -a "$src/$rel" "$out/$rel"
}

copy_tree() {
  local rel="$1"
  [ -d "$src/$rel" ] || return 0
  mkdir -p "$out/$rel"
  cp -a "$src/$rel/." "$out/$rel/"
}

# Only tracked/config files; runtime state and credentials stay behind.
copy_file AGENTS.md
copy_file skills-manager/repositories.json
for profile in web headless; do
  for file in package.json pnpm-lock.yaml pnpm-workspace.yaml .npmrc cordis.yml cordis.patch.yml compatibility.json; do
    copy_file "profiles/$profile/$file"
  done
done
copy_tree local-plugins
copy_tree local-presets
copy_tree skills
copy_tree dsh-pet

# Integrations: only config/workspaces/language, never state.json or bot state.
if [ -d "$src/integrations" ]; then
  while IFS= read -r -d '' file; do
    rel="${file#"$src/"}"
    mkdir -p "$out/$(dirname "$rel")"
    cp -a "$file" "$out/$rel"
  done < <(find "$src/integrations" -type f \
    \( -name config.json -o -name workspaces.json -o -name interface-language.json \) -print0)
fi

rewrite_text() {
  local path
  while IFS= read -r -d '' path; do
    sed -i \
      -e 's#/home/casey/\.dsh#/home/node/.dsh#g' \
      -e 's#/home/casey/\.local/share/mise/installs/npm-colbymchenry-codegraph/latest/bin/codegraph#/workspace/.local/share/mise/shims/codegraph#g' \
      -e 's#/home/casey/\.atuin/bin/atuin#/workspace/.local/share/mise/shims/atuin#g' \
      -e 's#/home/casey/\.local/share/mise/installs/github-dicklesworthstone-destructive-command-guard/latest/dcg#/workspace/.local/share/mise/shims/dcg#g' \
      -e 's#/home/casey/projects/my-stock#/workspace#g' \
      "$path"
  done < <(find "$out/profiles" "$out/local-plugins" "$out/local-presets" \
    "$out/skills-manager" "$out/integrations" -type f -print0 2>/dev/null)
  if [ -f "$out/skills/.skills_store_lock.json" ]; then
    sed -i 's#/home/casey/\.dsh#/home/node/.dsh#g' "$out/skills/.skills_store_lock.json"
  fi
}
rewrite_text

web_patch="$out/profiles/web/cordis.patch.yml"
if [ -f "$web_patch" ]; then
  yq -i '(.[] | select(.id == "agent-default-model") | .config.provider) = "deepseek-official"' "$web_patch"
  # The local patch disables @xmanrui/dsh-im, but that bundle is not in the
  # profile bundle list, so the override targets a missing entry and DSH warns.
  yq -i 'del(.[] | select(.id == "xmanrui-dsh-im"))' "$web_patch"
fi

web_manifest="$out/profiles/web/package.json"
if [ -f "$web_manifest" ]; then
  tmp="$(mktemp)"
  jq 'del(.dependencies.dshmarket) | .dsh.profile.bundles |= map(select(. != "dshmarket"))' \
    "$web_manifest" >"$tmp"
  mv "$tmp" "$web_manifest"
fi

tool_hooks="$out/local-plugins/dsh-tool-hooks/cordis.patch.yml"
if [ -f "$tool_hooks" ]; then
  # StyleFerry's release hook points at a local checkout that does not exist in
  # the container; keep the dcg pre-hook, drop the post-hook.
  yq -i '(.[] | select(.insert[]?.id == "dsh-tool-hooks") | .insert[] | select(.id == "dsh-tool-hooks") | .config.post) = []' "$tool_hooks"
fi

pnpm_workspace="$out/profiles/web/pnpm-workspace.yaml"
if [ -f "$pnpm_workspace" ] && ! grep -q '^onlyBuiltDependencies:' "$pnpm_workspace"; then
  # pnpm 10 ignores allowBuilds; these are the native packages the profile needs.
  printf '\nonlyBuiltDependencies:\n  - node-pty\n  - cloudflared\n  - protobufjs\n' >>"$pnpm_workspace"
fi

for dir in profiles local-plugins local-presets skills-manager integrations; do
  if grep -R -n -- '/home/casey/.dsh' "$out/$dir" 2>/dev/null; then
    echo "ERROR: stale /home/casey/.dsh path remains under $out/$dir" >&2
    exit 1
  fi
done

echo "==> transformed config staged at $out"
