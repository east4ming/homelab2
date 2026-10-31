# Implementation Plan: 全面移除 Nix（本地 mise + uv，CI 单镜像）

**Branch**: `013-replace-nix-with-mise` | **Date**: 2026-10-31 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/013-replace-nix-with-mise/spec.md`

## Summary

把 Nix 从本地工具链、CI 与文档中移除：本地用 mise 管理非 Python 工具、uv 管理 Python 解释器/依赖/Python CLI 工具，并提供 `mise run setup` 一条命令；CI 使用单个自建镜像 `ghcr.io/east4ming/homelab2-ci:latest`（从同一份 `.mise.toml` + `uv.lock` 构建），由维护者在宿主机执行 `scripts/build-ci-image` 构建并推送，`static-checks` / `helm-diff` 只拉取该镜像执行；删除全部 Nix 制品，替换 Nix 专用测试，加入 pre-commit 防回潮门禁。唯一实现例外是 `kanidm` CLI（无 mise 后端/无预编译发行版），用官方 `kanidm/tools` 容器包装为 `bin/kanidm`。

## Technical Context

**Language/Version**: 主要是声明式配置（TOML/YAML/Shell）；Python 3.13（uv 管理）；Go 1.26（mise）；不引入新的应用代码。

**Primary Dependencies**: mise 2026.10.22+；uv 0.13.6；Woodpecker 3.7.5；GHCR；宿主机 Docker Engine 29.x（含 buildx）；ansible 14.5.0（ansible-core 2.21.5）。

**Storage**: N/A（版本来源为 `.mise.toml`、`pyproject.toml`、`uv.lock`）。

**Testing**: `go test`（`test/tools_test.go` 的 `TestToolsVersions` + 新的 `TestToolsDevEnv`）；pre-commit 全部 hooks（含 `no-nix`）；Woodpecker 两条既有 pipeline；文档 `mkdocs build --strict`。镜像由宿主机构建，CI 不构建。

**Target Platform**: 开发机 Linux x86_64（Ubuntu 24.04+/26.04）；CI 镜像 Debian 13 slim；CI agent 保持现有 k8s backend；集群侧无变更。

**Project Type**: 基础设施/工具链仓库（Ansible + Helm + GitOps），无业务应用构建。

**Performance Goals**: 本地环境准备 ≤ 15 分钟（含首次下载，SC-001）；CI 冷启动 pipeline 总时长 ≤ 迁移前基线 × 1.2（SC-005；不再包含镜像构建，预期更快）。

**Constraints**: 不得包含任何 Nix 制品或调用；CI 单镜像；镜像由维护者在宿主机构建并推送，CI 只拉取 public GHCR 镜像；不使用 Woodpecker secret 或特权步骤；历史 changelog/ADR 不重写；文档优先中文。

**Scale/Scope**: 旧 devShell 31 项工具、2 条 CI pipeline、约 15 个文档/配置文件；新增 1 个镜像、1 个构建脚本、2 个小脚本。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原则/约束 | 本计划的落实 | 结论 |
| --- | --- | --- |
| I. 代码质量 | 新 YAML 通过 yamllint；新 shell 脚本使用 `#!/bin/bash` 并通过 shellcheck；helmlint/tofu_fmt 不受影响 | PASS |
| II. 测试标准 | 保留 9 工具版本检查；`TestToolsNixShell` → `TestToolsDevEnv`（先写测试再删 Nix）；冒烟测试不在 CI，行为不变 | PASS |
| III. 用户体验一致性 | 只改开发者入口与文档；集群服务、Ingress、SSO 无变化 | PASS |
| IV. 性能要求 | CI 冷启动设 20% 预算；不新增集群工作负载，无资源 requests/limits 变更 | PASS |
| V. 优先使用中文 | 本 plan、research、文档更新均用中文 | PASS |
| 安全与合规 | GHCR 凭据仅存宿主机 docker credential store；镜像不含 secret；保留 detect-private-key；新增门禁 | PASS |
| 开发与部署工作流 | 纯仓库声明式变更，无 GitOps 资源改动；feature branch + PR；先计划后实现 | PASS |

**Phase 1 后复核**：设计未引入新的集群资源、secret 明文或测试跳过，结论不变；无违反项，Complexity Tracking 为空。

## Project Structure

### Documentation (this feature)

```text
specs/013-replace-nix-with-mise/
├── plan.md              # 本文件
├── research.md          # Phase 0：决策、工具映射、CI/流水线设计、风险
├── data-model.md        # Phase 1：DevTool / PythonDependency / CIImage / Workflow / Baseline
├── quickstart.md        # Phase 1：本地/CI/门禁验证步骤与 SC 映射
├── contracts/
│   ├── dev-environment.md   # 本地命令与环境变量契约
│   └── ci-image.md          # 镜像内容、tag、拉取与失败语义
├── spec.md
└── tasks.md             # Phase 2（/speckit-tasks 生成，本命令不创建）
```

### Source Code (repository root)

```text
.mise.toml                     # 新增：非 Python 工具与版本、env.path、setup task
.python-version                # 新增：uv 使用的解释器版本（3.13）
pyproject.toml                 # 新增：scripts/dev/docs dependency groups
uv.lock                        # 新增并入库（从 .gitignore 移除）
bin/kanidm                     # 新增：kanidm/tools 容器包装
scripts/check-no-nix           # 新增：防回潮门禁脚本
scripts/build-ci-image         # 新增：宿主机构建并推送 CI 镜像（latest + sha）
.woodpecker/
├── ci/Dockerfile              # 新增：CI 镜像定义
├── static-checks.yaml         # 修改：改用 latest 镜像 + pull: true + 路径触发
└── helm-diff.yaml             # 修改：改用 latest 镜像 + pull: true
Dockerfile                     # 修改：文档构建改用 uv + docs group
.pre-commit-config.yaml        # 修改：新增 no-nix 本地 hook
.gitignore                     # 修改：不再忽略 uv.lock
test/
├── tools_test.go              # 修改：TestToolsDevEnv；git 版本区间重新基线化
├── README.md                  # 修改：运行方式与版本来源
└── external_test.go           # 修改：注释指向 mise 环境
docs/
├── concepts/development-shell.md              # 重写：mise + uv
├── installation/sandbox.md                    # 修改：前置条件
├── installation/production/deployment.md      # 修改：环境入口
├── installation/production/configuration.md   # 修改：安装步骤
├── getting-started/user-onboarding.md         # 修改：mise/uv
├── reference/roadmap.md                       # 修改：NIX 小节
└── reference/architecture/decision-records.md # 追加 ADR，标注旧 ADR superseded
README.md                      # 修改：技术栈表
requirements.txt               # 删除：文档依赖迁入 pyproject docs group
flake.nix / flake.lock / .envrc / run_nix_develop.sh  # 删除
AGENTS.md                      # 修改：Spec Kit 当前 Plan 指针
```

**Structure Decision**：沿用单仓库结构，不新增源码目录。变更集中在声明式配置（mise/uv/CI）、三个小脚本、测试与文档；镜像定义放在 `.woodpecker/ci/`，构建入口 `scripts/build-ci-image` 由维护者在宿主机执行。

## 设计决策摘要

详见 [research.md](research.md)：

1. **工具分工**：mise 管理非 Python 工具（精确版本），uv 管理 Python 生态；操作系统包承担 git/make/docker/iproute2 等宿主机能力。
2. **kanidm 例外**：`bin/kanidm` 包装 `kanidm/tools:1.11.2`；不引入 cargo 编译或第三方 PPA。
3. **Python 布局**：根 `pyproject.toml` + 入库 `uv.lock`，groups 为 `scripts`/`dev`/`docs`；`requirements.txt` 删除。
4. **CI 镜像**：单个 Debian 13 基础镜像，构建时按需 `mise install <tool...>`（版本仍来自 `.mise.toml`）+ `uv sync --frozen --only-group dev --only-group scripts`；docker CLI 从 `docker:29.9.2-cli` 复制；GHCR public package；由 `scripts/build-ci-image` 在宿主机构建，同时推送 `latest` 与 `sha-<short>`。首版全量镜像 3.57GB 导致 k8s agent 拉取超时，故 CI 镜像只装所需子集。
5. **流水线**：不再新增镜像构建 workflow；`static-checks` 与 `helm-diff` 使用 `ghcr.io/east4ming/homelab2-ci:latest` 并设置 `pull: true`，不使用 Woodpecker secret 或特权步骤。
6. **测试**：`TestToolsDevEnv` 验证 mise 环境与 uv 导入；git 约束放宽到 `>=2.47`，9 项检查数量不变。
7. **门禁**：pre-commit 本地 hook + `scripts/check-no-nix`，白名单只含历史记录与 `specs/`。
8. **文档与历史**：重写开发环境页、更新安装/onboarding/README/roadmap/test README；changelog 不重写，新增 ADR 并标注旧 ADR。
9. **依赖更新**：Renovate 的 mise / pep621 支持；缺失时加自定义 regex 或文档化手动流程。

## 实施阶段（供 tasks 分解）

1. **P0 准备**：记录迁移前 CI 基线；在宿主机创建 GHCR PAT（`write:packages`）并 `docker login ghcr.io`；确认 Renovate manager 行为。
2. **P1 本地**：写 `TestToolsDevEnv`（先失败）→ `.mise.toml`/`pyproject.toml`/`uv.lock`/`.python-version`/`bin/kanidm` → `mise run setup` 通过 → 删除 Nix 文件与 `requirements.txt` → 文档/README/test README → pre-commit 门禁 → 本地全量验证。
3. **P2 CI**：`.woodpecker/ci/Dockerfile` → `scripts/build-ci-image` → 宿主机构建推送 → 修改两条既有 pipeline（`latest` 镜像、`pull: true`、触发路径）→ 宿主机镜像冒烟 → PR 验证与耗时对比；首次推送后把 package 设为 public。
4. **P3 收尾**：ADR/roadmap/onboarding 更新；测试 PR 验证 `no-nix`；按 quickstart 映射逐项验收；确认 `git grep` 与 CI 均无 Nix 引用。

## 风险与缓解（摘要）

| 风险 | 缓解 |
| --- | --- |
| 工具版本变更后忘记重建 `latest` | PR 检查清单 + quickstart 必做项；PR 记录 build 输出的 digest；本地 `TestToolsVersions` 兜底 |
| `latest` 可变，回滚/审计弱 | 同时推送 `sha-<short>`；回滚时重标 `latest`；保存 digest |
| GHCR PAT 权限/轮换 | 只存宿主机 docker credential store；package public；定期轮换 |
| 宿主机 buildx/网络不可用 | Docker 29 自带 buildx；失败明确报错，不推送半成品，不回退 Nix |
| 镜像内 mise 配置未受信 | 固定 `MISE_TRUSTED_CONFIG_PATHS`（`/src`、`/woodpecker`） |
| kanidm 容器依赖 Docker 与 host 网络 | 文档写明；保留 `cargo install kanidm_tools` 作为离线替代 |
| git 版本区间放宽 | 只放宽到基础镜像版本，仍禁止跨大版本；test README 记录来源变化 |

## Complexity Tracking

无 Constitution Check 违反项。

实现例外（非 constitution 违反）：`kanidm` CLI 无法由 mise/预编译包提供，采用容器包装；用户已确认（2026-10-31）。理由与替代方案见 [research.md](research.md) Decision 2。
