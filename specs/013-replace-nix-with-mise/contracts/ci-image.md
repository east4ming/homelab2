# 契约：CI 镜像与流水线（宿主机构建）

## 镜像

| 项 | 值 |
| --- | --- |
| 名称 | `ghcr.io/east4ming/homelab2-ci` |
| tag | `latest`（CI 拉取）+ `sha-<short>`（审计/回滚） |
| 可见性 | public（CI 拉取无需凭据） |
| 定义 | `.woodpecker/ci/Dockerfile` |
| 构建入口 | `scripts/build-ci-image`（维护者在宿主机执行） |
| 基础镜像 | `debian:13-slim`，按 digest 固定 |
| 构建输入 | `.mise.toml`、`.python-version`、`pyproject.toml`、`uv.lock`、`.woodpecker/ci/Dockerfile` |
| 重建时机 | 上述输入变化后，合并前由维护者重建；CI 不构建 |
| 大小 | 2026-10-31 精简后 `842MB`（`docker image inspect .Size`） |

镜像内必须提供：

- mise（2026.10.22）与 `.mise.toml` 解析出的 helm、dyff、shellcheck；
- uv（0.13.6）与 `/opt/venv`（`uv sync --frozen --only-group ci`；`ci` 组只有 pre-commit）；
- `git`、`diffutils`、`ca-certificates`、`curl`；
- `PATH` 包含 `/opt/venv/bin` 与 mise shims；`MISE_TRUSTED_CONFIG_PATHS` 包含 `/woodpecker` 与 `/src`；
- 不包含 go/opentofu/ansible/kubectl/kustomize/gotestsum/docker CLI，也不包含任何 Nix 文件或命令。

## 构建与发布

- 维护者需先在宿主机执行 `docker login ghcr.io`（PAT 需 `write:packages`，只存 docker credential store）。
- `scripts/build-ci-image` 执行 `docker buildx build --platform linux/amd64 --push --provenance=false`，同时推送 `latest` 与 `sha-<short>`，并输出 digest；digest 记录到对应 PR。
- 通过 index/manifest annotation 设置 `org.opencontainers.image.source`（链接到 `east4ming/homelab2`）与 `org.opencontainers.image.description`，使 GHCR package 归到仓库下并有说明；`--provenance=false` 避免产生 `unknown/unknown` 的 attestation manifest。
- 构建失败时不推送半成品；不得回退到 `nixos/nix` 或 `nixery.dev`。
- 首次推送后把 GHCR package 设为 public；之后 CI 直接匿名拉取。

## 流水线契约

| workflow | 镜像 | pull | 命令 |
| --- | --- | --- | --- |
| `static-checks` | `ghcr.io/east4ming/homelab2-ci:latest` | `true` | `SKIP=tofu_fmt pre-commit run --all-files` |
| `helm-diff` | 同上 | `true` | `./scripts/helm-diff ...`（matrix：system/platform/apps） |

- CI 不包含镜像构建步骤，不使用 Woodpecker secret，不使用 `privileged`。
- 工具版本测试（需要 Go）与 `tofu_fmt`（需要 opentofu）只在本地执行；CI 显式跳过。

## 失败语义

- 镜像不存在/拉取失败（GHCR 不可达或 package 非 public）→ 步骤失败并指出镜像名与 tag。
- 镜像未重建（`latest` 过期）→ CI 仍可能通过，但结果不代表当前 pre-commit/helm 版本；由本地 `TestToolsVersions` 与 PR 检查清单兜底。
- helm 缺失/版本不符 → `helmlint` 或 helm-diff 失败。
- 出现 Nix 引用 → pre-commit `no-nix` 失败并输出文件与行号。
