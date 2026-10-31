# Feature Specification: 全面移除 Nix（本地改用 mise，CI/服务器镜像改用公共或自建镜像）

**Feature Branch**: `013-replace-nix-with-mise`

**Created**: 2026-10-31

**Status**: Draft

**Input**: User description: "全面移除 nix：本地的开发工具/脚本等使用 mise（本地已安装）代替；cicd 或服务器端的镜像使用主流的或开源的镜像代替（如果没有满足需求的可以自己 build 一个）"（澄清补充：Python 由 uv 管理，Python 以外的工具由 mise 管理；验收平台为 Linux x86_64；自建 CI 镜像发布到 GHCR）

## 背景与现状

截至 2026-10-31，Nix 在仓库中的落点如下：

| 位置 | 现状 | 影响 |
| --- | --- | --- |
| 本地开发环境 | `flake.nix` 定义 default 与 `ci` 两个 devShell，`flake.lock` 钉住 nixpkgs 26.05；`.envrc` 用 direnv 进入；`run_nix_develop.sh` 再包一层 | 贡献者必须安装 Nix 并启用 flakes，首次下载以 GB 计 |
| Python 工具链 | 旧 devShell 用 nixpkgs 的 python3 提供 jinja2/kubernetes/mkdocs-material/netaddr/pexpect/rich；文档依赖另由 `requirements.txt` 固定；`system/kubevirt/tests` 已用 uv，但根目录脚本的 Python 依赖没有声明，`uv.lock` 被 `.gitignore` 忽略 | 迁移后需由 uv 统一解释器、依赖与 Python 工具，且本地、CI、镜像同源 |
| CI 静态检查 | `.woodpecker/static-checks.yaml` 两个步骤都用 `nixos/nix` 镜像，分别执行 `nix develop --command make -C test filter=ToolsVersions` 与 `nix develop .#ci --command pre-commit run --all-files` | 流水线依赖 Nix 商店与 nixpkgs；`nixery.dev` 冷构建曾直接超时 |
| CI Helm diff | `.woodpecker/helm-diff.yaml` 使用 `nixery.dev/shell/git/python3/kubernetes-helm/diffutils/dyff` | 按需构建的非主流镜像，冷启动不可控 |
| 测试 | `test/tools_test.go` 的 `TestToolsNixShell` 直接调用 `nix develop`；`TestToolsVersions` 的版本区间按 nixpkgs 26.05 校准 | 没有 Nix 就无法在本地跑完整测试入口 |
| 文档与元数据 | `docs/concepts/development-shell.md`、`docs/installation/sandbox.md`、`docs/installation/production/{deployment,configuration}.md`、`docs/getting-started/user-onboarding.md`、README 技术栈表、`test/README.md`、`scripts/take-screenshots` 的 TODO、`docs/reference/architecture/decision-records.md`、`docs/reference/roadmap.md` | 新贡献者与服务器初始化仍被指引安装 Nix |

**服务器/集群现状**：`metal/`、`system/`、`platform/`、`apps/`、`external/` 的 Ansible 任务与 Kubernetes 清单中没有 Nix 安装或 Nix 基础镜像（已扫描确认），因此"服务器端镜像"目前没有存量 Nix；但安装文档要求初始控制器安装 Nix，属于服务器侧工具链依赖，同样需要移除。

**替代条件**：维护者机器已安装 mise（2026.10.22）与 uv（0.13.6）。工具分工已确定：**Python 生态（解释器、虚拟环境、依赖以及 Python 编写的 CLI 工具）由 uv 管理，Python 以外的语言与 CLI 工具由 mise 管理**。mise 可覆盖大部分 CLI 工具，但 docker 守护进程、iproute2、locales、SSH 客户端等属于操作系统能力，不能由 mise 提供，必须在文档中显式列为系统前置条件，不能静默缺失。仓库内已有 uv 先例（`system/kubevirt/tests/pyproject.toml`），但根目录脚本的 Python 依赖尚未声明，且 `uv.lock` 当前被 `.gitignore` 忽略——这是本特性需要补齐的缺口。

**目标**：Nix 从本地工具链、CI 镜像、测试与用户文档中彻底消失。本地由 mise（非 Python 工具）与 uv（Python 解释器、依赖与 Python 工具）提供等价工具集；CI 使用公共主流/开源镜像，必要时由本仓库构建并发布到 GHCR；服务器侧不再出现 Nix。

## Clarifications

### Session 2026-10-31

- Q: 自建 CI 镜像采用哪种形态？ → A: 单个预构建镜像，static-checks 与 helm-diff 两条流水线共用。
- Q: Python 依赖如何组织（uv 的清单形态）？ → A: 根 `pyproject.toml` + 受版本控制的 `uv.lock`，文档与脚本依赖用 dependency groups。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 在没有 Nix 的机器上获得等价的本地开发环境（Priority: P1）

作为 homelab2 的维护者或新贡献者，我希望只安装 mise 与 uv、按文档执行环境准备命令，就得到与旧 Nix devShell 等价的工具集（非 Python 工具由 mise 提供，Python 环境与 Python 工具由 uv 管理），从而在完全不安装 Nix/flakes 的机器上修改配置、跑测试和构建集群。

**Why this priority**: 本地环境是每一次改动的必经入口；CI 是第二道门禁。先把开发者入口从 Nix 解耦，才能让后续 CI 与文档的迁移建立在可日常验证的基础上。

**Independent Test**: 在一台未安装 Nix 的 Ubuntu 机器（已安装 mise 与 uv）上，只按文档操作，能运行 `make -C test filter=Tools` 与 `pre-commit run --all-files` 并通过。

**Acceptance Scenarios**:

1. **Given** 一台没有 Nix 的 Ubuntu 机器且已安装 mise 与 uv，**When** 按开发环境文档执行环境准备，**Then** 旧 devShell 中的每个非 Python 工具由 mise 提供或明确列为系统前置条件（含最低版本），Python 解释器、依赖与 Python 编写的 CLI 工具由 uv 提供，且没有工具静默缺失。
2. **Given** 环境已准备，**When** 运行 `make -C test filter=Tools`，**Then** 工具版本检查与"开发环境可用"检查通过，且过程中没有调用 `nix`。
3. **Given** 需要构建文档，**When** 运行文档中给出的文档构建命令，**Then** mkdocs 可用，且其依赖来自根 `pyproject.toml` 的文档依赖组并由 `uv.lock` 锁定。
4. **Given** 第一次接触项目的新贡献者，**When** 只阅读开发环境文档，**Then** 文档中不存在安装或运行 Nix 的步骤。

---

### User Story 2 - CI 不再使用 Nix 镜像（Priority: P2）

作为维护者，我希望 PR 流水线在公共主流/开源镜像（或本仓库自建镜像）上完成静态检查与 Helm diff，使 CI 不再依赖 Nix 商店、Nix 缓存或按需构建的 nixery.dev 镜像，而且检查结果与迁移前一致。

**Why this priority**: CI 是合入的硬性门禁。当前两条 pipeline 的所有步骤都跑在 Nix 镜像里，是本地迁移完成后最后一块硬依赖；不解决它，"移除 Nix"就只是半成品。

**Independent Test**: 对 `system`、`platform`、`apps` 任一 stack 提交 PR，触发 static-checks 与 helm-diff 两条流水线；所有步骤的镜像都不是 Nix 镜像，检查项与结果和迁移前等价。

**Acceptance Scenarios**:

1. **Given** static-checks 流水线，**When** 在 PR 上运行，**Then** tools-versions 与 pre-commit 两个步骤都运行在非 Nix 镜像上，且检查项与迁移前完全一致（9 个工具版本检查 + 全部 pre-commit hooks）。
2. **Given** helm-diff 流水线，**When** 对任一 stack 提交 PR，**Then** 在非 Nix 镜像上完成 Helm 渲染与 dyff 对比，输出格式与迁移前一致。
3. **Given** 现有公共镜像满足不了某一步骤的工具组合，**When** 采用自建镜像，**Then** 镜像定义在仓库内、构建可复现（固定基础镜像与工具版本）、发布到 GHCR，static-checks 与 helm-diff 共用这一个预构建镜像，并在镜像定义或工具版本变化时自动重建；镜像内不包含也不调用 Nix。
4. **Given** CI 运行环境与本地开发环境，**When** 执行工具版本检查，**Then** 两边满足同一组版本约束，且由同一份测试实现校验。
5. **Given** 无镜像缓存的冷启动，**When** 运行任一条 pipeline，**Then** 总时长相对迁移前实测基线不劣化超过 20%。

---

### User Story 3 - 仓库、文档与服务器侧彻底去 Nix 化并可防止回潮（Priority: P3）

作为维护者，我希望仓库里不再有 Nix 制品、Nix 测试、Nix 说明与 Nix TODO，同时有一条自动门禁阻止它们回来，使新贡献者不会误入歧途，服务器镜像也不会悄悄重新引入 Nix。

**Why this priority**: 前两个故事解决"能用"，本故事解决"不再出现"。没有门禁，残留的文档链接和脚本注释会继续误导使用者，迁移成果会逐步退化。

**Independent Test**: 扫描全部受版本控制的文件，除历史记录与本次 spec 目录外，Nix 引用为 0；提交一个包含 Nix 引用的测试 PR，门禁失败并指出位置。

**Acceptance Scenarios**:

1. **Given** 迁移完成，**When** 扫描仓库文件，**Then** `flake.nix`、`flake.lock`、`.envrc`、`run_nix_develop.sh` 不再存在，活动代码、配置与用户文档中没有 `nix` 命令、Nix 镜像或 Nix 包引用。
2. **Given** 迁移完成，**When** 阅读 sandbox 与 production 安装文档、用户 onboarding、README 技术栈表，**Then** 指引使用 mise/uv 与系统包，不要求安装 Nix；新增 ADR 记录迁移决策并明确取代此前的 Nix 相关 ADR，历史 changelog 与既有 ADR 保留。
3. **Given** 有人重新提交 Nix 制品、Nix 命令或 Nix 镜像引用，**When** 发起 PR，**Then** 自动门禁失败并指出文件与行号；历史记录（changelog、既有 ADR）与 `specs/` 目录不计入违规。
4. **Given** 服务器端与集群镜像清单，**When** 检查部署步骤，**Then** 没有任何镜像或部署流程依赖 Nix；后续新增镜像同样不得引入 Nix。

---

### Edge Cases

- **mise 或 uv 未安装、版本过旧**：环境准备脚本必须给出明确错误与安装链接，而不是静默失败或回退到 Nix。
- **mise 无对应后端的工具**（如 docker 守护进程、iproute2、locales、OpenSSH、bmake、libisoburn 一类系统级组件）：必须显式列为系统前置条件，或改用可被版本管理的等价工具；不得出现"旧 devShell 有、新环境没有且无说明"的情况。
- **平台差异**：仅部分平台可用的工具（如 bmake、libisoburn）需在文档中写明，测试如需跳过必须显式标注原因，不得静默跳过。
- **镜像仓库不可达或凭据缺失**：CI 必须明确失败并指出缺失的凭据/仓库，不得回退到 `nixos/nix` 或 `nixery.dev`。
- **工具版本更新**：更新 mise 声明的版本或 CI 镜像内版本时，版本约束测试必须在同一 PR 内同时暴露本地与 CI 的不兼容。
- **历史文档中出现 Nix**：changelog、既有 ADR、旧 spec 属于历史记录，不视为违规；防回潮门禁需要准确排除这些路径。
- **Python 依赖分裂**：文档构建依赖与脚本运行依赖来源不同；两者 MUST 通过根 `pyproject.toml` 的 dependency groups 合并为同一份清单，`uv.lock` MUST 入库（修正当前 `.gitignore` 忽略它的现状），不能依赖 Nix 提供。
- **工具与已部署服务的兼容性**：旧 devShell 中个别工具版本是按线上服务校准的（如 kanidm CLI 对应已部署服务端），迁移时不能只求"装得上"，必须保留这些兼容约束。
- **本机没有 docker 守护进程**：依赖容器的目标（k3d、docker compose、镜像构建）必须给出清晰错误或文档化前置条件。
- **受限网络/离线**：首次环境准备需要访问工具下载源；文档必须说明这一前置条件。

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 仓库 MUST NOT 再包含 Nix 制品（`flake.nix`、`flake.lock`、`.envrc`、`run_nix_develop.sh`）或调用 `nix` 的入口脚本。
- **FR-002**: 本地开发环境的非 Python 工具 MUST 由仓库内受版本控制的 mise 配置声明；Python 解释器、虚拟环境、依赖以及 Python 编写的 CLI 工具 MUST 由 uv 管理；MUST 提供一条文档化命令完成两者安装。
- **FR-003**: 新本地环境 MUST 与旧 devShell 工具集等价：旧 devShell 的每个非 Python 工具要么由 mise 提供，要么显式列为系统前置条件（含最低版本），不允许静默缺失。
- **FR-004**: Python 解释器版本与依赖 MUST 由 uv 从仓库根部的 `pyproject.toml` 解析，并由受版本控制的 `uv.lock` 锁定；文档构建与脚本运行依赖 MUST 通过 dependency groups 纳入同一清单；本地开发、CI 镜像与文档镜像 MUST 从同一来源安装；MUST NOT 依赖 Nix 提供 Python 包。
- **FR-005**: 现有工具版本约束测试 MUST 在 mise 环境与 CI 中继续执行；`TestToolsNixShell` MUST 被替换为同时验证 mise 工具与 uv Python 环境可用的等价检查。
- **FR-006**: CI 的所有步骤 MUST 运行在不含 Nix 的镜像上；镜像 MUST 来自公共主流/开源镜像，或由本仓库构建并发布到 GHCR 的镜像。
- **FR-007**: 若需要自建 CI 镜像：定义 MUST 存于仓库；MUST 为单个预构建镜像，static-checks 与 helm-diff 两条流水线 MUST 共用同一镜像与同一工具版本；构建 MUST 可复现（固定基础镜像与工具版本）；MUST 发布到 GHCR（`ghcr.io`；集群未配置 Gitea registry，不作为发布目标）；MUST 在定义或工具版本变化时自动重建；凭据 MUST 仅通过 CI secret 注入。
- **FR-008**: CI 工具版本 MUST 与本地声明（mise 与 uv）满足同一组版本约束，并由同一实现校验。
- **FR-009**: CI 检查能力 MUST 保持等价：static-checks 的 9 个工具版本检查与全部 pre-commit hooks、helm-diff 的 3 个 stack 对比，不得通过减少检查换取通过。
- **FR-010**: 用户文档 MUST 更新：开发环境页（改为 mise + uv）、sandbox 前置条件、production deployment/configuration、onboarding、README 技术栈表、`docs/reference/roadmap.md` 的 NIX 小节、test README、脚本中的 Nix TODO；文档 MUST NOT 再要求安装 Nix 或 flakes。
- **FR-011**: MUST 新增 ADR 记录迁移决策与取代关系；历史 changelog 与既有 ADR 保留（可标注 superseded），不重写历史。
- **FR-012**: MUST 提供自动门禁防止 Nix 回潮：检测 Nix 制品、`nix` 命令、Nix 镜像引用；排除历史记录与 `specs/` 目录。
- **FR-013**: 服务器端/集群镜像与部署步骤 MUST NOT 依赖 Nix；若实现过程中发现存量依赖，MUST 按与 CI 镜像相同的规则（FR-006/FR-007）替换为公共镜像或自建镜像；后续新增镜像同样不得引入 Nix。
- **FR-014**: 移除 Nix 不得改变部署行为：Makefile 目标、脚本参数与输出保持原样，只改变环境入口。
- **FR-015**: mise 配置、uv 锁文件与 CI 自建镜像中的版本 MUST 纳入依赖更新流程（自动化或文档化手动流程），避免本地与 CI 版本漂移。

### Key Entities *(include if feature involves data)*

- **开发工具清单（Dev Tool Manifest）**：仓库内由 mise 声明的非 Python 工具集；关键属性是工具名、固定版本、后端、适用平台，以及对应的版本约束测试。
- **Python 环境（uv）**：由仓库根 `pyproject.toml` 与 `uv.lock` 管理解释器版本、依赖分组与 Python CLI 工具；关键属性是解释器版本、依赖分组、锁文件是否入库，以及本地、CI、镜像三处是否同源。
- **CI 镜像（CI Image）**：两条流水线共用的单个镜像；关键属性是基础镜像及固定引用、内置工具及版本、构建定义、发布仓库（GHCR）、触发重建的条件。
- **流水线步骤（Pipeline Step）**：关键属性是触发路径、使用的镜像、执行命令与所覆盖的检查项。
- **Nix 引用基线（Nix Reference Baseline）**：允许保留 Nix 字样的历史路径清单（changelog、既有 ADR、`specs/`），供防回潮门禁判定。

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 一台未安装 Nix 的 Ubuntu 机器（已安装 mise 与 uv）按文档操作，在 15 分钟内（含首次下载）获得可用环境，且 `make -C test filter=Tools` 与 `pre-commit run --all-files` 通过。
- **SC-002**: 活动文件（代码、配置、脚本、用户文档）中的 Nix 引用数为 0；扫描命中仅限历史记录与本次 spec 目录。
- **SC-003**: PR 上的 static-checks 与 helm-diff 流水线全部通过，0 个步骤使用 `nixos/nix` 或 `nixery.dev` 镜像，检查项数量与迁移前一致（9 个工具 + 全部 hooks + 3 个 stack）。
- **SC-004**: 本地与 CI 的工具版本检查 0 处越界；更新版本来源的 PR 在本地与 CI 两边同时通过。
- **SC-005**: 冷启动 pipeline 总时长相对迁移前实测基线不劣化超过 20%。
- **SC-006**: 新贡献者按文档操作全程执行 0 条 `nix` 命令；文档中"安装 Nix"类步骤数为 0。
- **SC-007**: 提交包含 Nix 引用的测试 PR 时，防回潮门禁在 1 次流水线内失败并指出具体文件与行号。
- **SC-008**: 在干净环境中只使用仓库内受版本控制的 Python 依赖来源即可完成安装，严格锁定模式下 0 个依赖落在清单之外，且本地与 CI 安装结果一致。

## Assumptions

- 维护者机器已安装 mise（用户已确认）与 uv；mise 版本需支持仓库内的配置格式，uv 版本需支持锁文件格式。
- 平台范围已确认（用户澄清）：Linux x86_64（Ubuntu 24.04+/26.04）为验收范围；macOS 等平台不在本特性验收范围内。
- 工具分工已确认（用户澄清）：Python 解释器、虚拟环境、依赖与 Python 编写的 CLI 工具由 uv 管理，mise 只管理 Python 以外的工具；mise 不接管 Python。
- docker/containerd、iproute2、locales、SSH 客户端等宿主机能力继续由操作系统提供，并在文档中列明；mise 与 uv 均不负责守护进程。
- 自建 CI 镜像发布目标已确认（用户澄清）：GHCR；homelab2 集群未配置 Gitea registry，不作为发布目标，CI 需具备 GHCR 推送凭据。
- 历史 changelog、既有 ADR 与旧 spec 不重写；迁移决策通过新增 ADR 表达取代关系。
- 旧 devShell 的工具清单即为迁移基线；裁剪"看似未使用"的工具属于独立决策，不在本特性范围内。
- 依赖更新自动化（如 Renovate）需覆盖 mise 配置与镜像版本；若工具不支持，则采用文档化的手动更新流程。
- CI runner 可拉取公共镜像，并具备构建镜像所需的 docker/buildkit 能力。

## 不在本次范围

- 把项目或其他服务迁移到 NixOS、或引入 Nix 的替代包管理生态（本特性方向相反）。
- 更换 CI 引擎（Woodpecker）、更换镜像仓库供应商或调整集群网络架构。
- 删除旧 devShell 中工具所对应的功能或脚本；本特性只迁移获取工具的方式，不改变脚本职责。
