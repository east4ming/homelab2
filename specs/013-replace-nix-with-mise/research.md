# Phase 0 研究：全面移除 Nix

**Date**: 2026-10-31 | **Spec**: [spec.md](spec.md)

## 结论摘要

- **本地**：非 Python 工具由 mise 声明并固定版本；Python 解释器、依赖与 Python CLI 工具由 uv（根 `pyproject.toml` + 入库的 `uv.lock`）管理；入口为 `mise run setup`。
- **CI**：单个自建镜像 `ghcr.io/east4ming/homelab2-ci:latest`，从同一份 `.mise.toml` / `uv.lock` 构建；由维护者在宿主机执行 `scripts/build-ci-image` 构建并推送（同时推送 `sha-<short>`），`static-checks` 与 `helm-diff` 只拉取该镜像执行，不使用 Woodpecker secret 或特权步骤。
- **测试**：`TestToolsNixShell` 替换为 `TestToolsDevEnv`；9 个工具版本检查保留，版本区间按新来源重新基线化（git 改为 `>=2.47`）。
- **防回潮**：pre-commit 本地 hook + `scripts/check-no-nix`，CI 的 pre-commit 步骤自动执行。
- **例外**：`kanidm` CLI 没有 mise 后端、也没有官方预编译发行版；用官方 `kanidm/tools` 容器包装成 `bin/kanidm`（服务器端仍保持 1.3.3，不升级服务端）。

## Decision 1：mise 与 uv 的工具分工

**Decision**：Python 生态（解释器、虚拟环境、依赖、Python CLI 工具）全部交给 uv；其余工具交给 mise 或操作系统包。工具清单以旧 devShell 为基线逐项映射，不允许静默缺失。

**Rationale**：用户明确要求；uv 提供锁文件与 dependency groups，mise 提供跨工具版本管理与 aqua/ubi/core 后端，二者都可被 CI 镜像复用。

**Alternatives considered**：

- 全部交给 mise（含 `pypi:`/`pipx:` 后端）：Python 依赖会有两套版本来源，且 `uv.lock` 无法复用。
- 全部交给 uv（通过 `uv tool install` 管理 Helm 等非 Python 工具）：uv 不负责非 Python 二进制。

### 工具映射（旧 devShell → 新提供者）

版本为 2026-10-31 从 mise registry / `mise ls-remote` / PyPI 实际查询所得；最终以 `.mise.toml` 与 `uv.lock` 为准。

| 旧 devShell 项 | 新提供者 | 固定版本（候选） | 说明 |
| --- | --- | --- | --- |
| ansible | uv `dev` group | 14.5.0（ansible-core 2.21.5） | 满足 `ansible --version` ≈ 2.21.x 的现有约束 |
| ansible-lint | uv `dev` group | 26.10.1 | |
| pre-commit | uv `dev` group | 4.7.0 | 满足 `>=4.5,<5` |
| yamllint | uv `dev` group | 1.38.0 | |
| jinja2 / kubernetes / netaddr / pexpect / rich | uv `scripts` group | 以 `uv.lock` 为准 | requests 由 kubernetes 传递引入 |
| mkdocs-material 及文档依赖 | uv `docs` group | 从 `requirements.txt` 迁移并锁定 | 文档依赖单一来源 |
| go | mise `core:go` | 1.26.10 | 满足 `>=1.26,<1.27` |
| gotestsum | mise `aqua:gotestyourself/gotestsum` | 1.13.0 | |
| helm | mise `aqua:helm/helm` | 3.20.2 | 满足 `>=3.20,<4` |
| kubectl | mise `aqua:kubernetes/kubernetes/kubectl` | 1.36.6 | 满足 `>=1.36,<1.37` |
| kustomize | mise `aqua:kubernetes-sigs/kustomize` | 5.8.3 | 满足 `>=5.8,<6` |
| opentofu | mise `aqua:opentofu/opentofu` | 1.11.14 | 满足 `>=1.11,<2` |
| argocd | mise `aqua:argoproj/argo-cd` | 3.5.6 | |
| dyff | mise `aqua:homeport/dyff` | 1.12.0 | |
| jq | mise `aqua:jqlang/jq` | 1.8.2 | |
| k9s | mise `aqua:derailed/k9s` | 0.51.0 | |
| k3d | mise `aqua:k3d-io/k3d` | 5.9.0 | |
| neovim | mise `aqua:neovim/neovim` | 0.12.6 | |
| shellcheck | mise `aqua:koalaman/shellcheck` | 0.11.0 | |
| docker / docker-compose | 操作系统 | Docker Engine 29.x + Compose v2 | 守护进程与 CLI 属于宿主机能力 |
| git | 操作系统 | >= 2.47 | Debian 13 为 2.47.3；本地 Ubuntu 26.04 更高 |
| diffutils / make / bmake / iproute2 / locales / openssh-client / xorriso / 7zip / qrencode / wireguard-tools | 操作系统 | 发行版默认 | `libisoburn` 对应 `xorriso`；`p7zip` 对应 `7zip`/`p7zip-full` |
| kanidm_1_11 | **例外**：`bin/kanidm` 包装 `kanidm/tools:1.11.2` | 1.11.2 | 见 Decision 2 |

**Alternatives considered（os 包 vs mise）**：`git`、`iproute2`、`locales`、`openssh` 等都有 mise 后端或可替代实现，但它们与宿主内核/守护进程耦合，交给发行版更稳定；`kanidm` 见下。

## Decision 2：kanidm CLI 的例外处理

**Decision**：不把 `kanidm` 交给 mise。仓库提供 `bin/kanidm`（bash），通过 Docker 调用官方 `kanidm/tools:1.11.2` 镜像，并把 `~/.cache/kanidm_tokens` 与 `~/.config/kanidm` 挂载进去；`[env] _.path` 把 `bin/` 加入 PATH，`scripts/onboard-user` 无需修改。

**Rationale**：

- mise registry 无 `kanidm`；GitHub Releases 只有发布说明、没有客户端二进制，`github:`/`ubi:` 后端装不了。
- 官方仅提供发行版包（Ubuntu 走非官方 PPA）、`cargo install kanidm_tools` 或 `kanidm/tools` 容器。cargo 首次编译在 N100 上会显著超过 15 分钟的本地环境目标。
- Docker 本来就是本项目的系统前置条件；容器版本可显式固定，且与当前 devShell 的 1.11 客户端一致；服务端仍锁在 chart 的 1.3.3，不在本特性中升级。

**Alternatives considered**：

- `cargo:kanidm_tools@1.11.2`：可复现，但构建重、需要 Rust 工具链，违背 SC-001。
- Ubuntu PPA 安装：引入第三方 apt 源，与"一条命令"目标冲突，且版本不可控。
- 从基线中删除：`scripts/onboard-user` 实际调用 `kanidm`，不能静默缺失。

**风险**：使用容器要求本机 Docker 守护进程可用，且需要 `--network host` 才能访问 Tailscale 暴露的 Kanidm；文档需写明。

## Decision 3：Python 环境（uv）

**Decision**：

- 仓库根新增 `pyproject.toml`，使用 PEP 735 dependency groups：`scripts`（脚本运行依赖）、`dev`（ansible、ansible-lint、pre-commit、yamllint）、`docs`（原 `requirements.txt` 的 30 个固定版本）。
- 提交 `uv.lock`；从 `.gitignore` 移除 `uv.lock`；新增 `.python-version`（3.13）。
- 设置 `[tool.uv] package = false`（本仓库不是 Python 包）。
- 删除 `requirements.txt`；文档 Dockerfile 改用 uv 安装 `docs` group 后构建。

**Rationale**：单一依赖来源，本地、CI 镜像与文档镜像同源；uv 0.13.6 已支持 `--all-groups`、`--frozen`、`uv export`。

**Alternatives considered**：

- 保留 `requirements.txt` 作为文档依赖：会形成两套清单，Dockerfile 注释也明确要求单一来源。
- 每个脚本用 PEP 723 内联依赖：分散，pre-commit/ansible 这类工具仍需集中安装。

**验证**：`ansible 14.5.0 → ansible-core 2.21.5`、`pre-commit 4.7.0` 均在现有版本约束内（PyPI 元数据实测）。

## Decision 4：CI 自建镜像（宿主机构建）

**Decision**：一个预构建镜像，`dockerfile: .woodpecker/ci/Dockerfile`，由维护者在宿主机构建并推送到 GHCR；CI 只拉取。

- 基础镜像：`debian:13-slim`（按 digest 固定），apt 安装 `git make diffutils ca-certificates curl xz-utils unzip`。
- mise：用官方安装脚本并固定 `MISE_VERSION=v2026.10.22`；`COPY .mise.toml` 后按需 `mise install <tool...>`。
- uv：从官方 `ghcr.io/astral-sh/uv:<0.13.6>` 镜像复制二进制；`UV_PROJECT_ENVIRONMENT=/opt/venv`、`uv sync --frozen --only-group ci --only-group scripts`。
- docker CLI：从 `docker:29.9.2-cli`（digest 固定）复制 `/usr/local/bin/docker`，满足 `docker --version` 检查。
- PATH：`/opt/venv/bin`、`$MISE_DATA_DIR/shims` 在前；`MISE_TRUSTED_CONFIG_PATHS` 覆盖构建目录与 Woodpecker workspace（`/woodpecker`）。
- 内容：CI 所需的 mise 子集（helm、kubectl、kustomize、opentofu、go、gotestsum、dyff、shellcheck；版本仍由 `.mise.toml` 解析）+ uv `ci`/`scripts` 组（`ci` 只含 ansible-core 与 pre-commit，不含 ansible bundle/ansible-lint/yamllint）。排除 argocd/k9s/k3d/neovim 与 `docs` 组：首版全量镜像 3.57GB，k8s agent 拉取超时（`trying and failing to pull image`）。
- 构建入口：`scripts/build-ci-image`（宿主机执行）：`docker buildx build --platform linux/amd64 --push`，同时推送 `latest` 与 `sha-<short>`；需要宿主机已 `docker login ghcr.io`。
- 可见性：GHCR package 设为 public，CI 拉取无需凭据；推送凭据仅在维护者宿主机。

**Rationale**：没有任何现成公共镜像同时提供 ansible、go、helm、kubectl、kustomize、tofu、pre-commit、dyff 与 docker CLI；自建镜像同时满足"版本与本地同源"和"单镜像"两个已确认决策。用户选择在宿主机构建，避免为 CI 增加 Docker agent 或 k8s 特权 Pod。

**Alternatives considered**：

- 每 pipeline 一个小镜像：用户已选择单镜像。
- 公共基础镜像 + 运行时 `mise install`：每次冷启动下载全部工具，风险超出 SC-005 的 20% 预算。
- 宿主机新增 Woodpecker Docker agent（workflow labels 路由）：自动化最好，但需要常驻服务与 agent token；用户本次选择手动构建，此方案保留为后续升级路径。
- 使用 `nixos/nix`/`nixery.dev`：本特性要移除的目标。

## Decision 5：Woodpecker 流水线

**Decision**：

- 不新增 `ci-image` workflow；CI agent 保持现有 k8s backend，只拉取镜像。
- `static-checks.yaml`、`helm-diff.yaml` 的步骤镜像改为 `ghcr.io/east4ming/homelab2-ci:latest`，并设置 `pull: true`，避免 agent 使用缓存的旧镜像。
- `static-checks` 的 tools-versions 路径触发条件改为 `.mise.toml`、`pyproject.toml`、`uv.lock`、`.woodpecker/ci/**`、`test/**`。
- `TestToolsVersions` 的 9 项检查保持不变；pre-commit 步骤继续 `--all-files`。
- 重建契约：凡改动 `.mise.toml`、`pyproject.toml`、`uv.lock` 或 `.woodpecker/ci/Dockerfile`，维护者必须在合并前从当前分支执行 `scripts/build-ci-image` 并记录输出的 digest；工具版本 PR 的验证依赖这一步。

**Rationale**：与用户选择的"宿主机 Docker 构建"一致，不需要 Woodpecker secret、特权步骤或额外 agent；CI 只负责拉取与执行。代价是镜像重建不再自动，必须依赖文档化流程。

**Operational prerequisites（需人工配置）**：

- 宿主机创建 GHCR PAT（`write:packages`），执行 `docker login ghcr.io`；PAT 不进入仓库。
- 首次推送后把 `ghcr.io/east4ming/homelab2-ci` package 设为 public（CI 无拉取凭据）。
- 记录迁移前最近 5 次成功 PR pipeline 的耗时作为 SC-005 基线。
- 不再需要 Woodpecker 的 `ghcr_*` secret；无 `privileged` 步骤。

**Alternatives considered**：

- per-commit tag：没有 CI 构建步骤时，PR 对应的 tag 不存在，无法被消费。
- 可变 `latest` 之外的固定 tag：需要每次构建后改 workflow YAML，维护成本更高；`latest` + `sha-<short>` 兼顾简单与审计。
- k8s 特权 Pod/DinD：与现有 agent 配置冲突，且 Woodpecker k8s backend 对 privileged 支持有已知问题。

## Decision 6：测试与版本约束

**Decision**：

- `test/tools_test.go`：删除 `TestToolsNixShell`，新增 `TestToolsDevEnv`：`mise exec -- true`（mise 能解析并加载项目工具环境）+ `uv run --frozen python -c "import rich, kubernetes, pexpect, jinja2, netaddr"`（uv 环境可用）。
- 保留 `TestToolsVersions` 的 9 项检查；把 git 约束从 `>=2.54` 调整为 `>=2.47,<3`，并在 `test/README.md` 说明版本区间现在来自 `.mise.toml` / `uv.lock` / 基础镜像，而不是 nixpkgs。
- `test/external_test.go` 的注释改为 mise 环境提供 OpenTofu。

**Rationale**：版本区间本来就绑定 nixpkgs（`test/README.md` 明说）；迁移后必须重新基线化，否则 Debian 13 的 git 2.47.3 无法通过。检查项数量与覆盖面不变。

**Alternatives considered**：

- 在镜像里从源码编译 git 2.54+：为一个非功能性版本增加构建复杂度。
- 用 Debian testing/sid：包版本漂移，与可复现目标冲突。

## Decision 7：防回潮门禁

**Decision**：`.pre-commit-config.yaml` 增加 `repo: local` hook `no-nix`，执行 `scripts/check-no-nix`（bash）：

- 扫描 `git ls-files` 的文件名：`flake.nix|flake.lock|.envrc|run_nix_develop.sh`。
- 扫描 tracked 文件内容：`nix` 命令/`nixos/nix`/`nixery.dev`/`nixpkgs`/`flake.*`/`.envrc`。
- 允许路径：`docs/reference/changelog.md`、`docs/reference/architecture/decision-records.md`、`specs/**`、脚本自身与 pre-commit 配置。
- CI 的 pre-commit 步骤（`--all-files`）自动覆盖 PR 门禁。

**Rationale**：pre-commit 同时提供本地快速反馈与 CI 阻断；不需要新增 Go 测试或独立 CI 检查。

**Alternatives considered**：Go 测试（只在特定路径触发，覆盖不全）、仅 CI grep（本地无反馈）。

## Decision 8：文档与历史

**Decision**：

- 重写 `docs/concepts/development-shell.md` 内容（保留路径与 mkdocs nav，避免链接大面积变更），标题改为开发环境（mise + uv）。
- 更新 `docs/installation/sandbox.md`、`docs/installation/production/{deployment,configuration}.md`、`docs/getting-started/user-onboarding.md`、`README.md` 技术栈表、`test/README.md`、`scripts/take-screenshots` 注释、`docs/reference/roadmap.md` 的 NIX 小节。
- `docs/reference/architecture/decision-records.md` 追加新 ADR（mise + uv 取代 Nix），并在旧的两条 Nix ADR 上标注 Superseded；`docs/reference/changelog.md` 作为历史保留不重写。
- 删除 `.envrc`、`flake.nix`、`flake.lock`、`run_nix_develop.sh`。

**Rationale**：符合 FR-010/FR-011；保留历史避免篡改已发布记录，门禁只放行历史路径。

## Decision 9：依赖更新

**Decision**：Renovate 已支持 `mise` 与 `pep621` manager；`uv.lock` 由 pep621/uv 相关 manager 维护。若实际运行发现 `.mise.toml` 未被更新，则添加自定义 regex manager，或在文档中写明 `mise upgrade` 手动流程（FR-015 允许）。

**Rationale**：延续现有 Renovate 自动化，不引入新工具。

## 风险与缓解

| 风险 | 缓解 |
| --- | --- |
| 工具版本变更后忘记重建 `latest` | 在 PR 检查清单与 quickstart 中列为必做项；PR 描述记录 `scripts/build-ci-image` 输出的 digest；本地 `TestToolsVersions` 先兜底 |
| `latest` 可变，审计/回滚弱 | 每次同时推送 `sha-<short>`；需要回滚时把旧 sha tag 重新标记为 `latest`；构建输出保存 digest |
| GHCR PAT 权限/轮换 | 使用 classic PAT（`write:packages`）并只存在宿主机 docker credential store；定期轮换；package public 后 CI 无需凭据 |
| 宿主机 buildx/网络不可用 | Docker 29 自带 buildx；失败时明确报错，不推送半成品，不回退 Nix |
| k8s agent 拉取不到镜像 | package 必须 public；若改为 private，需在 Woodpecker 配置 GHCR registry 凭据 |
| `mise` 在容器内需要信任配置 | 固定 `MISE_TRUSTED_CONFIG_PATHS`（构建 `/src`、运行 `/woodpecker`） |
| `uv run` 在运行期找不到镜像内 venv | `UV_PROJECT_ENVIRONMENT=/opt/venv` 固化在镜像 ENV |
| kanidm 容器方式依赖 Docker 与 host 网络 | 文档写明；保留 `cargo install kanidm_tools` 作为离线替代方案 |
| git 版本区间放宽 | 仅放宽下限到基础镜像版本，仍禁止跨大版本；在 test README 记录来源变化 |

## 未决项

无阻塞性未决项。kanidm 容器包装方案已由用户确认（2026-10-31），其余均按 spec 的澄清结果执行。
