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

镜像内必须提供：

- mise（2026.10.22）与 `.mise.toml` 声明的全部工具（`mise install` 结果）；
- uv（0.13.6）与 `/opt/venv`（`uv sync --frozen --all-groups` 结果）；
- docker CLI 29.9.2（仅命令行，满足版本检查；无守护进程）；
- `git`、`make`、`diffutils`、`ca-certificates`、`curl`；
- `PATH` 包含 `/opt/venv/bin` 与 mise shims；`MISE_TRUSTED_CONFIG_PATHS` 包含 `/woodpecker` 与 `/src`；
- 不包含任何 Nix 文件或命令。

## 构建与发布

- 维护者需先在宿主机执行 `docker login ghcr.io`（PAT 需 `write:packages`，只存 docker credential store）。
- `scripts/build-ci-image` 执行 `docker buildx build --platform linux/amd64 --push`，同时推送 `latest` 与 `sha-<short>`，并输出 digest；digest 记录到对应 PR。
- 构建失败时不推送半成品；不得回退到 `nixos/nix` 或 `nixery.dev`。
- 首次推送后把 GHCR package 设为 public；之后 CI 直接匿名拉取。

## 流水线契约

| workflow | 镜像 | pull | 命令 |
| --- | --- | --- | --- |
| `static-checks` | `ghcr.io/east4ming/homelab2-ci:latest` | `true` | `make -C test filter=ToolsVersions`、`pre-commit run --all-files` |
| `helm-diff` | 同上 | `true` | `./scripts/helm-diff ...`（matrix：system/platform/apps） |

- CI 不包含镜像构建步骤，不使用 Woodpecker secret，不使用 `privileged`。
- `static-checks` 的 tools-versions 触发路径：`.mise.toml`、`pyproject.toml`、`uv.lock`、`.woodpecker/ci/**`、`test/**`。

## 失败语义

- 镜像不存在/拉取失败（GHCR 不可达或 package 非 public）→ 步骤失败并指出镜像名与 tag。
- 镜像未重建（`latest` 过期）→ CI 仍可能通过，但结果不代表当前工具版本；由 PR 检查清单与本地 `TestToolsVersions` 兜底。
- 工具版本越界 → `ToolsVersions` 失败，输出具体工具与期望区间。
- 出现 Nix 引用 → pre-commit `no-nix` 失败并输出文件与行号。
