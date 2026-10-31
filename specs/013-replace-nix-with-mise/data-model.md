# Phase 1 数据模型：开发工具、Python 环境与 CI 镜像

本特性没有运行时数据库；这里的"数据模型"指仓库内需要保持一致的声明式实体及其校验规则。

## 实体

### DevTool（mise 管理的非 Python 工具）

| 字段 | 说明 | 约束 |
| --- | --- | --- |
| name | 工具名（mise registry 名） | 唯一；与旧 devShell 项一一对应 |
| version | 固定版本 | 精确版本（非 `latest`）；满足 `tools_test.go` 约束 |
| backend | `core` / `aqua` / `github` 等 | 必须在该平台可安装 |
| binary | 提供的可执行文件名 | 至少一个；`tools_test.go` 检查的名字必须在其中 |
| platform | 支持平台 | 至少 `linux-x86_64` |
| constraint | 版本守卫区间 | 与 `test/tools_test.go` 一致 |
| sourceOfTruth | `.mise.toml` | 唯一来源 |

### PythonDependency（uv 管理的依赖/工具）

| 字段 | 说明 | 约束 |
| --- | --- | --- |
| package | PyPI 包名 | 唯一（同一 group 内） |
| group | `scripts` / `dev` / `docs` | PEP 735 dependency group |
| constraint | 版本约束 | 在 `pyproject.toml` 声明 |
| lockedVersion | 锁定版本 | 由 `uv.lock` 记录并入库 |
| usedBy | 脚本/文档/hook | 必须是仓库中真实存在的消费点 |
| pythonVersion | 解释器版本 | `.python-version` 固定为 3.13 |

**校验**：`uv lock --check` 通过；`uv sync --frozen --all-groups` 在干净环境可完成；`uv.lock` 未被忽略。

### CIImage

| 字段 | 值/说明 | 约束 |
| --- | --- | --- |
| name | `ghcr.io/east4ming/homelab2-ci` | 小写；唯一 |
| tag | `latest`（CI 消费）+ `sha-<short>`（审计/回滚） | `latest` 为可变指针；每次构建必须同时推送 sha tag |
| baseImage | `debian:13-slim`（digest 固定） | 升级需改 Dockerfile 并由 Renovate/人工更新 |
| miseVersion | `2026.10.22` | 与本地最低要求一致 |
| uvVersion | `0.13.6` | 官方镜像复制，digest 固定 |
| dockerCli | `29.9.2` | 从 `docker:29.9.2-cli` 复制 |
| toolsSource | 构建时复制 `.mise.toml` + `pyproject.toml` + `uv.lock` | 与本地同源 |
| env | `PATH`、`MISE_DATA_DIR`、`UV_PROJECT_ENVIRONMENT`、`MISE_TRUSTED_CONFIG_PATHS` | 运行期可被步骤直接使用 |
| visibility | public（GHCR package） | 消费步骤无需拉取凭据 |
| buildDefinition | `.woodpecker/ci/Dockerfile` + `scripts/build-ci-image` | 宿主机执行；CI 不构建；禁止 Nix |
| rebuildPolicy | 工具版本/镜像定义变更时由维护者重建并记录 digest | 手动流程；quickstart 列为合并前必做项 |

**校验**：镜像内 9 个工具版本满足约束；`docker --version`、`mise --version`、`uv --version` 可执行；`mise exec -- true` 与 `uv run --frozen python -c ...` 成功。

### PipelineWorkflow / Step

| 字段 | 说明 | 约束 |
| --- | --- | --- |
| workflowFile | `.woodpecker/*.yaml` | 每个文件是一个 workflow |
| name | 文件名去掉扩展名 | 用于日志/文档引用 |
| image | 步骤镜像 | 非 Nix；固定为 `ghcr.io/east4ming/homelab2-ci:latest` |
| pull | `true` | 强制拉取 `latest`，避免使用 agent 缓存旧镜像 |
| commands | 执行命令 | 与迁移前检查项等价 |
| when | 触发条件 | 默认分支 PR/push；path 过滤按新版本来源更新 |
| secrets | 无 | CI 不构建/推送镜像，不需要 GHCR secret |

### NixReferenceBaseline

允许保留 Nix 字样的路径（防回潮门禁白名单）：

| 路径 | 理由 |
| --- | --- |
| `docs/reference/changelog.md` | 已发布历史，不重写 |
| `docs/reference/architecture/decision-records.md` | 历史 ADR 与新增取代说明 |
| `specs/**` | 本特性及旧特性的规格/计划 |
| `scripts/check-no-nix` | 门禁脚本自身的匹配规则 |
| `.pre-commit-config.yaml` | 门禁注册项名字 |

**校验**：白名单之外的文件名与内容命中数为 0；白名单内的命中不阻断。

## 关系

- `DevTool` 与 `PythonDependency` → `CIImage`：镜像构建时从两者读取版本，保证本地/CI 同源。
- `CIImage` → `PipelineWorkflow/Step`：消费步骤拉取 `latest`（`pull: true`）；镜像重建是维护者的手动前置，不在 pipeline 内。
- `NixReferenceBaseline` → 门禁：只用于判定，不参与构建。
