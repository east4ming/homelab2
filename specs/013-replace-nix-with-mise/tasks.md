# Tasks: 全面移除 Nix（本地 mise + uv，CI 宿主机构建镜像）

**Input**: Design documents from `/specs/013-replace-nix-with-mise/`

**Prerequisites**: plan.md、spec.md、research.md、data-model.md、contracts/、quickstart.md

**Tests**: 本仓库 Constitution 要求 TDD 与工具版本门禁，因此包含测试任务（`test/tools_test.go`、门禁验证 PR）；不引入新测试框架。

**Organization**: 按用户故事分组；P1 为 MVP。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 不同文件、无未完成依赖，可并行
- **[Story]**: US1 / US2 / US3
- 所有路径相对仓库根目录

## Path Conventions

- 单仓库（Ansible/Helm/GitOps）；配置与脚本位于仓库根、`scripts/`、`.woodpecker/`、`test/`、`docs/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 记录基线、确认前置条件，不改动功能

- [X] T001 在 `specs/013-replace-nix-with-mise/quickstart.md` 的“第 0 步”下记录迁移前最近 5 次成功 PR pipeline 的总耗时（来自 Woodpecker）
- [X] T002 在 `specs/013-replace-nix-with-mise/quickstart.md` 记录宿主机前置确认结果（`mise --version`、`uv --version`、`docker buildx version`、`docker login ghcr.io` 成功）
- [X] T003 [P] 确认 Renovate 能更新 `.mise.toml` 与 `uv.lock`；若不能，更新 `renovate.json5` 增加 customManager 或写明手动升级流程

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 本地/CI 共用的版本来源与环境入口，阻塞所有用户故事

**⚠️ CRITICAL**: 本阶段完成前不要开始用户故事

- [X] T004 创建 `.mise.toml`：写入 research.md 工具表中的精确版本（helm 3.20.2、kubectl 1.36.6、kustomize 5.8.3、opentofu 1.11.14、go 1.26.10、gotestsum 1.13.0、argocd 3.5.6、dyff 1.12.0、jq 1.8.2、k9s 0.51.0、k3d 5.9.0、neovim 0.12.6、shellcheck 0.11.0），设置 `[env] _.path = ["bin", ".venv/bin"]` 与 `[tasks.setup]`（执行 `mise install --yes` + `uv sync --all-groups`）
- [X] T005 [P] 创建 `pyproject.toml`：`requires-python = ">=3.13"`、`[tool.uv] package = false`，PEP 735 dependency groups：`scripts`（jinja2、kubernetes、netaddr、pexpect、rich）、`dev`（ansible 14.5.x、ansible-lint、pre-commit 4.7.x、yamllint）、`docs`（迁移 `requirements.txt` 的全部固定版本）
- [X] T006 [P] 创建 `.python-version`，内容为 `3.13`
- [X] T007 执行 `uv lock` 生成 `uv.lock`，再运行 `uv sync --frozen --all-groups` 验证依赖可解析（依赖 T005、T006）
- [X] T008 修改 `.gitignore`：删除 `uv.lock` 忽略行，保留 `.venv/`
- [X] T009 运行 `mise trust`、`mise run setup`，确认幂等，并用 `mise exec -- helm version --short`、`uv run --frozen python -c "import rich,kubernetes,pexpect,jinja2,netaddr"` 验证（验证 `.mise.toml`/`pyproject.toml`；依赖 T004–T008）

**Checkpoint**: 本地版本来源就绪，US1/US2 可开始

---

## Phase 3: User Story 1 - 在没有 Nix 的机器上获得等价的本地开发环境 (Priority: P1) 🎯 MVP

**Goal**: 只用 mise + uv 获得旧 devShell 的等价工具集，删除全部 Nix 制品，测试与文档不再依赖 Nix。

**Independent Test**: 在未安装 Nix 的 Ubuntu 机器执行 `mise run setup` 后，`make -C test filter=Tools`、`pre-commit run --all-files`、`uv run --frozen mkdocs build --strict` 全部通过，且全程无 `nix` 命令。

### Tests for User Story 1 ⚠️

> 先写/改测试，再删 Nix；`TestToolsDevEnv` 在环境就绪前应失败或无法运行

- [X] T010 [US1] 在 `test/tools_test.go` 删除 `TestToolsNixShell`，新增 `TestToolsDevEnv`：从项目根执行 `mise exec -- true` 与 `uv run --frozen python -c "import rich, kubernetes, pexpect, jinja2, netaddr"`
- [X] T011 [US1] 在 `test/tools_test.go` 将 git 版本约束从 `>= 2.54.0` 调整为 `>= 2.47.0, < 3.0.0`，并在 `test/README.md` 说明区间来源改为 `.mise.toml`/`uv.lock`/基础镜像（依赖 T010，同文件顺序修改）

### Implementation for User Story 1

- [X] T012 [P] [US1] 创建 `bin/kanidm`（bash）：检测 Docker，透传 TTY，挂载 `~/.cache/kanidm_tokens` 与 `~/.config/kanidm`，执行 `docker run --rm --network host kanidm/tools:1.11.2 /sbin/kanidm "$@"`；`chmod +x`
- [X] T013 [P] [US1] 重写 `docs/concepts/development-shell.md`：标题改为开发环境，说明 mise + uv 安装、`mise trust`/`mise run setup`、`mise activate`、验证命令、系统前置条件（Docker、git、make、iproute2、xorriso、7zip、qrencode、wireguard-tools、locales、openssh-client）
- [X] T014 [P] [US1] 更新 `test/README.md`：运行命令去掉 `nix develop`，补充 `TestToolsDevEnv` 行与版本区间来源说明
- [X] T015 [P] [US1] 更新 `test/external_test.go` 第 19 行注释：OpenTofu 由 mise 环境提供，不再引用 `flake.nix`
- [X] T016 [US1] 更新 `Dockerfile`：构建阶段复制 uv 二进制，使用 `uv sync --frozen --only-group docs` 后执行 `.venv/bin/mkdocs build --strict`；删除 `requirements.txt`
- [X] T017 [US1] 删除 `.envrc`、`flake.nix`、`flake.lock`、`run_nix_develop.sh`（依赖 T012–T016 完成，避免中途丢失文档/依赖）
- [X] T018 [US1] 运行本地验收：`mise run setup` → `make -C test filter=Tools` → `pre-commit run --all-files` → `uv run --frozen mkdocs build --strict`；失败时修复 `.mise.toml`、`pyproject.toml`、`test/tools_test.go`、`docs/concepts/development-shell.md`（依赖 T010–T017）
- [X] T019 [US1] 运行 `bin/kanidm --help` 验证容器包装可用（需 Docker 与网络）；在 `docs/concepts/development-shell.md` 记录该命令及“服务器端仍为 1.3.3、不升级”的说明

**Checkpoint**: US1 独立可用；本地不再需要 Nix

---

## Phase 4: User Story 2 - CI 不再使用 Nix 镜像 (Priority: P2)

**Goal**: 单个宿主机构建镜像供 static-checks / helm-diff 拉取，CI 不构建、不需要 secret 或特权步骤。

**Independent Test**: 宿主机 `scripts/build-ci-image` 成功推送 `latest` 与 `sha-<short>`；PR 上两条 pipeline 使用该镜像并通过，检查项与迁移前一致，且无镜像构建步骤。

### Tests for User Story 2 ⚠️

- [X] T020 [US2] 创建 `.woodpecker/ci/Dockerfile`：`debian:13-slim` digest 固定；apt 安装 git/make/diffutils/ca-certificates/curl/xz-utils/unzip；从 `ghcr.io/astral-sh/uv:0.13.6` 复制 uv；从 `docker:29.9.2-cli` 复制 `/usr/local/bin/docker`；安装 mise 2026.10.22；复制 `.mise.toml`/`.python-version`/`pyproject.toml`/`uv.lock` 后执行 `mise install` 与 `uv sync --frozen --all-groups`；设置 PATH、`MISE_TRUSTED_CONFIG_PATHS`、`UV_PROJECT_ENVIRONMENT=/opt/venv`
- [X] T021 [US2] 创建 `scripts/build-ci-image`（bash）：检查 `docker info` 与 ghcr 登录；执行 `docker buildx build --platform linux/amd64 --push -f .woodpecker/ci/Dockerfile -t ghcr.io/east4ming/homelab2-ci:latest -t ghcr.io/east4ming/homelab2-ci:sha-$(git rev-parse --short HEAD) .` 并打印 digest；`chmod +x`
- [X] T022 [P] [US2] 更新 `.woodpecker/static-checks.yaml`：两个步骤 `image: ghcr.io/east4ming/homelab2-ci:latest`、`pull: true`；tools-versions 的 path 触发改为 `.mise.toml`、`pyproject.toml`、`uv.lock`、`.woodpecker/ci/**`、`test/**`
- [X] T023 [P] [US2] 更新 `.woodpecker/helm-diff.yaml`：步骤 `image: ghcr.io/east4ming/homelab2-ci:latest`、`pull: true`；其余命令与 matrix 不变

### Implementation for User Story 2

- [X] T024 [US2] 在宿主机执行 `scripts/build-ci-image`，记录 `latest` 与 `sha-<short>` 的 digest 到 `specs/013-replace-nix-with-mise/quickstart.md`（依赖 T020、T021）
- [X] T025 [US2] 首次推送后把 GHCR package `homelab2-ci` 设为 public：已通过 GitHub UI 切换；匿名 `docker pull` 验证通过，记录在 `specs/013-replace-nix-with-mise/quickstart.md`
- [X] T026 [US2] 本地镜像冒烟：`docker run -e MISE_TRUSTED_CONFIG_PATHS=/woodpecker -v "$PWD:/woodpecker/src" -w /woodpecker/src ghcr.io/east4ming/homelab2-ci:latest sh -c 'make -C test filter=Tools && pre-commit run --all-files'`（验证 `.woodpecker/ci/Dockerfile`；依赖 T024）
- [ ] T027 [US2] 推送分支并创建 PR，确认两条 pipeline 只拉取镜像、无构建步骤，检查项与迁移前一致；记录冷启动耗时并与 T001 基线比较（≤ ×1.2）；结果写入 `specs/013-replace-nix-with-mise/quickstart.md`（依赖 T022–T026；阻塞：T025 未完成前 CI 无法匿名拉取镜像）

**Checkpoint**: US2 独立可用；CI 无 Nix 镜像

---

## Phase 5: User Story 3 - 仓库、文档与服务器侧彻底去 Nix 化并可防止回潮 (Priority: P3)

**Goal**: 清除剩余文档/脚本中的 Nix 指引，加入 pre-commit 门禁，并证明门禁能阻断回归。

**Independent Test**: 白名单外 `git grep` 无 Nix 命中；含 `nixos/nix` 的测试 PR 被 `no-nix` hook 拒绝并指出文件/行号。

### Tests for User Story 3 ⚠️

- [X] T028 [US3] 创建 `scripts/check-no-nix`（bash）：检查 `git ls-files` 中 `flake.nix|flake.lock|.envrc|run_nix_develop.sh` 文件名；`git grep -n -I -i -E` 扫描 Nix 命令/`nixos/nix`/`nixery.dev`/`nixpkgs`/`flake.*`/`.envrc`；允许 `docs/reference/changelog.md`、`docs/reference/architecture/decision-records.md`、`specs/**`、脚本自身、`.pre-commit-config.yaml`；`chmod +x`
- [X] T029 [US3] 在 `.pre-commit-config.yaml` 增加 `repo: local` hook `no-nix`：`entry: scripts/check-no-nix`、`language: script`、`pass_filenames: false`、`always_run: true`
- [X] T030 [P] [US3] 更新 `README.md` 技术栈表：删除 Nix 行，替换为 mise（工具版本管理）与 uv（Python 环境）
- [X] T031 [P] [US3] 更新 `docs/getting-started/user-onboarding.md`：Nix+direnv 改为 mise+uv
- [X] T032 [P] [US3] 更新 `docs/installation/sandbox.md`：bastion 包列表与 `nix develop` 改为系统包 + `mise run setup`
- [X] T033 [P] [US3] 更新 `docs/installation/production/deployment.md`：`nix develop` 改为 `mise run setup`
- [X] T034 [P] [US3] 更新 `docs/installation/production/configuration.md`：删除 apt 安装 Nix 段，改为安装 mise/uv + `mise run setup`
- [X] T035 [P] [US3] 更新 `docs/reference/roadmap.md`：`### NIX Packages` 小节改名为开发工具小节，删除 Nix 表述
- [X] T036 [P] [US3] 更新 `docs/reference/architecture/decision-records.md`：新增 ADR（mise + uv 取代 Nix，2026-10-31），并在两条旧 Nix ADR 上标注 Superseded；保留历史 changelog 不动

### Implementation for User Story 3

- [X] T037 [US3] 运行 `git grep -n -i -w nix` 与文件名扫描，确认仅白名单路径命中；修复遗漏；结果写入 `specs/013-replace-nix-with-mise/quickstart.md`（依赖 T017、T028、T030–T036）
- [X] T038 [US3] 构造临时测试提交（在 `tmp/` 或测试分支加入含 `nixos/nix` 的文件），确认 `no-nix` hook 失败并输出文件/行号，然后移除（依赖 T029、T037）
- [X] T039 [US3] 运行 `pre-commit run --all-files`，确保 `scripts/check-no-nix` 通过 shellcheck、`.woodpecker/static-checks.yaml`/`.woodpecker/helm-diff.yaml` 通过 yamllint、`check-executables-have-shebangs` 通过；修复失败（依赖 T028、T029、T022、T023）

**Checkpoint**: US3 独立可用；门禁生效

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T040 按 `specs/013-replace-nix-with-mise/quickstart.md` 第 5 节的 SC 映射逐项验证，把结果与耗时写入 quickstart.md（本地 SC-001/002/004/006/008 已通过；SC-003/005/007 的 CI 部分待 T025/T027）
- [ ] T041 将 `specs/013-replace-nix-with-mise/spec.md` 的 Status 改为 `Implemented`，并在 checklists/requirements.md Notes 记录最终验收结论（依赖 T040）
- [ ] T042 复核 `git status`/`git diff` 无范围外改动；确认 `test/README.md`、`docs/concepts/development-shell.md` 中的命令与实际一致；准备 PR 描述（含镜像 digest、基线耗时、SC-00x 证据）

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: 无依赖，可立即开始
- **Foundational (Phase 2)**: 依赖 Setup；阻塞所有用户故事
- **US1 / US2 (Phase 3–4)**: 依赖 Foundational；两者文件基本不重叠，可由不同人并行
- **US3 (Phase 5)**: 依赖 Foundational；T028/T029 可先写，T037 起需 US1 的删除完成
- **Polish (Phase 6)**: 依赖 US1–US3 完成

### User Story Dependencies

- **US1 (P1)**: 依赖 Phase 2；不依赖 US2/US3
- **US2 (P2)**: 依赖 Phase 2；可与 US1 并行（镜像构建读取同一份 `.mise.toml`/`pyproject.toml`/`uv.lock`）
- **US3 (P3)**: 依赖 Phase 2；文档与门禁可先做，最终扫描依赖 US1 的 Nix 制品删除

### Within Each User Story

- 测试先于实现（T010/T011 先改，T018 验证）
- 共享文件按顺序：`test/tools_test.go`（T010 → T011）；`pre-commit`（T029 → T039）
- 其它文档任务文件互不重叠，可并行

### Parallel Opportunities

- Phase 2：T005 与 T006 可并行；T004 独立
- US1：T012–T016 文件互不重叠，可并行（T016 删除 `requirements.txt` 与 T013 文档无冲突）
- US2：T022 与 T023 可并行
- US3：T030–T036 可并行；T028 与 T030–T036 可并行

---

## Parallel Example: User Story 1

```bash
# 以下任务文件互不重叠，可同时进行：
# T012 bin/kanidm
# T013 docs/concepts/development-shell.md
# T014 test/README.md
# T015 test/external_test.go
# T016 Dockerfile + requirements.txt
```

## Parallel Example: User Story 3

```bash
# 文档与门禁脚本可并行：
# T028 scripts/check-no-nix
# T030 README.md
# T031 docs/getting-started/user-onboarding.md
# T032 docs/installation/sandbox.md
# T033 docs/installation/production/deployment.md
# T034 docs/installation/production/configuration.md
# T035 docs/reference/roadmap.md
# T036 docs/reference/architecture/decision-records.md
```

---

## Implementation Strategy

### MVP First (US1)

1. Phase 1 + Phase 2
2. Phase 3（US1）
3. **STOP & VALIDATE**：无 Nix 机器上按 quickstart 第 1 节验证
4. 此时本地已完全脱离 Nix，可作为 MVP 交付

### Incremental Delivery

1. US1 → 本地环境可用（MVP）
2. US2 → CI 切换镜像，PR 门禁恢复
3. US3 → 文档清零 + 防回潮门禁
4. Polish → SC 逐项验收并记录

### Notes

- 每个任务完成后可提交；Constitution 要求中文提交信息
- 工具版本变更或 Dockerfile 变更后，必须重跑 `scripts/build-ci-image`（T024）再让 CI 通过
- 禁止用“减少检查项”换取通过；`TestToolsVersions` 9 项检查必须全部保留
