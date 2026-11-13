# Tasks: 以 Helm Chart 在 homelab2 安装 DeepSeek Harness

**Input**: Design documents from `/specs/015-deepseek-harness-helm/`
**Prerequisites**: [plan.md](plan.md)、[spec.md](spec.md)、[research.md](research.md)、[data-model.md](data-model.md)、[contracts/](contracts/)、[quickstart.md](quickstart.md)

**Tests**: 本特性没有要求 TDD；但按 Constitution II 与 spec 的成功标准，包含 smoke test 扩展与线上验收任务。

**Organization**: 任务按用户故事分组。工具/配置/skills 都是一次性手动任务，不是 initContainer；备份由用户后续手动配置，本清单**不修改** `scripts/backup-coverage`。

## 格式

- `[P]`：不同文件、无未完成依赖，可并行。
- `[USx]`：对应 spec 的用户故事；Setup/Foundational/Polish 不带故事标签。
- 每个任务都带精确文件路径。

## Phase 1: Setup（共享初始化）

**Purpose**: 建立 `apps/deepseek-harness` 的 Chart 骨架，复制上游模板。

- [x] T001 创建 `apps/deepseek-harness/templates/` 与 `apps/deepseek-harness/files/`，并把上游 `charts/deepseek-harness/{Chart.yaml,values.yaml,values.schema.json,templates/*}` 复制到 `apps/deepseek-harness/`
- [x] T002 [P] 更新 `apps/deepseek-harness/Chart.yaml`：`name: deepseek-harness`、`version: 0.1.29-homelab.1`、`appVersion: 0.2.2-rc.1`，annotations 记录上游 `runzhliu/deepseek-harness-docker@04371405`
- [x] T003 [P] 更新 `apps/deepseek-harness/values.yaml`：`image.tag: 0.2.2-rc.1-r1-market.1`、`persistence.size: 10Gi`、`workspace.*`、`tools.*`、`skills.*`、`desktop.publicPort: 443`、`credentials.existingSecret`、`ingress.*`、`networkPolicy.ingress`、`resources.limits`
- [x] T004 [P] 更新 `apps/deepseek-harness/values.schema.json`，覆盖 `desktop.publicPort`、`workspace.create/size/storageClass`、`tools.*`、`skills.*`、`ingress.*`、`resources.*`
- [x] T005 [P] 更新 `apps/deepseek-harness/templates/NOTES.txt`，写清 Web/桌面 URL、401/token、手动工具安装与配置同步步骤

**Checkpoint**: `helm lint apps/deepseek-harness` 能跑通基础 Chart。

---

## Phase 2: Foundational（阻塞所有用户故事）

**Purpose**: 可部署的 Chart 资源、PVC、Secret 引导；**不添加 initContainer**。

**⚠️ CRITICAL**: 本阶段完成前不要开始用户故事。

- [x] T006 修改 `apps/deepseek-harness/templates/statefulset.yaml`：移除/不添加 `initContainers`；主容器增加 `XDG_DATA_HOME`、`XDG_CONFIG_HOME`、`XDG_CACHE_HOME`、`XDG_STATE_HOME`、`DSH_AGENTS_HOME`、`DSH_DESKTOP_PUBLIC_PORT`、完整 `PATH`
- [x] T007 修改 `apps/deepseek-harness/templates/statefulset.yaml`：增加 `workspace`、`tools`（`/workspace/.local` 与 `/workspace/.config`）、`skills`（`/workspace/.agents/skills`）、`tmp`、`shm` 的 volumes/volumeMounts；保持只读根 FS、非 root、drop ALL、`automountServiceAccountToken: false`
- [x] T008 修改 `apps/deepseek-harness/templates/statefulset.yaml`：设置 `resources.requests` 与 `resources.limits`（250m/1Gi、2 CPU/4Gi）；`volumeClaimTemplates` 使用 `persistence.size: 10Gi`
- [x] T009 [P] 新增 `apps/deepseek-harness/templates/pvc-workspace.yaml`：20Gi RWO、`standard-rwo`、名称 `deepseek-harness-workspace`、`helm.sh/resource-policy: keep`、ArgoCD `Prune=false,Delete=false`
- [x] T010 [P] 新增 `apps/deepseek-harness/templates/pvc-tools.yaml`：20Gi RWO、名称 `deepseek-harness-tools`、同样的保留注解
- [x] T011 [P] 新增 `apps/deepseek-harness/templates/pvc-skills.yaml`：1Gi RWO、名称 `deepseek-harness-skills`、同样的保留注解
- [x] T012 保留 `apps/deepseek-harness/templates/service.yaml` 的 Headless Service；新增 `apps/deepseek-harness/templates/service-tailscale.yaml` ClusterIP（http 3080、desktop 6080）
- [x] T013 [P] 新增 `apps/deepseek-harness/templates/ingress-web.yaml`：host `dsh.west-beta.ts.net`、class `tailscale`、annotation `tailscale.com/proxy-group: ingress-proxies`、`/`→http、`/novnc-`→desktop、TLS
- [x] T014 [P] 新增 `apps/deepseek-harness/templates/ingress-desktop.yaml`：host `dsh-desktop.west-beta.ts.net`、`/`→desktop、TLS
- [x] T015 更新 `apps/deepseek-harness/templates/networkpolicy.yaml`：从 values 读取放行规则，只允许 `tailscale` 命名空间内 `parent-resource-type=proxygroup` + `parent-resource=ingress-proxies` 到 3080/6080
- [x] T016 新增 `scripts/bootstrap-deepseek-harness`：校验 `DEEPSEEK_API_KEY`/`GITHUB_API_TOKEN`，用临时 env 文件 + `kubectl create secret ... --from-env-file`、`umask 077`、trap 清理、只输出键名

**Checkpoint**: `helm template` 可渲染完整应用；Secret 可由脚本创建。

---

## Phase 3: User Story 1 - 从 tailnet 访问 Web 与 noVNC（Priority: P1）🎯 MVP

**Goal**: 通过两条 Tailscale Ingress 访问 DSH Web（401→token）与 noVNC 桌面；NetworkPolicy 只放行 ingress proxies。

**Independent Test**: 非 tailscale Pod 访问 PodIP:3080/6080 失败；tailnet 打开 Web 得 401，token 后进入 UI；桌面
Ingress 得 200；Web UI 的桌面入口可用；模型调用在 US3 配置同步后由 T038 验证。

### Implementation for User Story 1

- [x] T017 [P] [US1] 扩展 `test/smoke_test.go`：给 `mainApps` 增加 `expectedStatus`，新增 `deepseek-harness`（401）与 `deepseek-harness-desktop`（200）
- [x] T018 [P] [US1] 在 `apps/homepage/values.yaml` 的 `Utilities` 增加 `DeepSeek Harness` 与 `DSH Desktop` 入口（MDI 图标）
- [x] T019 [US1] 用 `helm template deepseek-harness apps/deepseek-harness` 断言：无 initContainers、存在 ClusterIP Service、两条 Ingress 路径正确、NetworkPolicy 两个端口
- [x] T020 [US1] 合并/同步后按 `specs/015-deepseek-harness-helm/quickstart.md` §7 验证 Web 401、token 登录与 UI 加载；模型调用在 T038（US3 配置同步后）验证
- [x] T021 [US1] 按 `quickstart.md` §7 验证 `https://dsh-desktop.west-beta.ts.net` 返回 200，且 Web UI 内“浏览器桌面”打开同一 noVNC
- [x] T022 [US1] 按 `quickstart.md` §8 验证非 `tailscale` 命名空间 Pod 访问 PodIP:3080 得 401、6080 得 200（端口级放行），访问 9222 被拒绝；记录 Cilium SNAT 限制

**Checkpoint**: US1 可独立验收；Web、桌面、网络边界均通。

---

## Phase 4: User Story 2 - 四块 PVC 持久化（Priority: P1）

**Goal**: dsh-home/workspace/tools/skills 四块 PVC 在 Pod 重建、Helm 重装后保留；四块都列为后续手动备份对象。

**Independent Test**: 写入四个标记 → 删除 Pod → 标记仍在；隔离命名空间 install→uninstall→PVC 仍在；`scripts/backup-coverage` 未被修改。

- [x] T023 [US2] 检查 `apps/deepseek-harness/templates/pvc-*.yaml` 与 `statefulset.yaml` 渲染后的四块 PVC：10/20/20/1 GiB、RWO、`standard-rwo`；独立 PVC 带 keep/prune 注解；dsh-home 来自 volumeClaimTemplate
- [x] T024 [US2] 按 `quickstart.md` §10 写四个标记、删除 Pod、等待新 Pod，验证四个标记仍在；工具/配置的“无需重做”分别在 T031/T038 复验
- [x] T025 [US2] 按 `quickstart.md` §10 在隔离命名空间 `dsh-retention` 执行 install→uninstall，验证 4 块 PVC 保留后清理命名空间
- [x] T026 [P] [US2] 在 `apps/deepseek-harness/README.md` 记录四块 PVC 名称/容量为后续手动备份对象，并注明不修改 `scripts/backup-coverage`
- [x] T027 [P] [US2] 执行 `git diff --exit-code scripts/backup-coverage`，确认本特性没有添加任何 PVC 豁免

**Checkpoint**: US2 可独立验收；持久化与保留策略符合 spec。

---

## Phase 5: User Story 4 - 工具链持久化（Priority: P1）

**Goal**: 手动把 uv/mise 与 4+9 个工具装到 20Gi 工具卷；Pod 重启后仍可用。

**Independent Test**: 运行 `scripts/install-dsh-tools` 后，`uv tool list` 4 项、`mise ls --global` 9 项、atuin/codegraph/dcg/gh 可执行；重启 Pod 后仍可用。

> 注：US4 放在 US3 前，因为配置中的 dcg/codegraph/atuin 工具需要先存在。

- [x] T028 [US4] 新增 `apps/deepseek-harness/files/install-tools.sh`：设置 HOME/XDG/PATH，安装 uv/mise 到 `/workspace/.local/bin`，逐个 `uv tool install`、`mise use -g`（含 `aqua:atuinsh/atuin`）、`mise reshim`，写 `.dsh-tools-version`
- [x] T029 [US4] 新增 `scripts/install-dsh-tools`：查找 Pod/等待 Ready、`kubectl cp` 脚本到 `/tmp`、`kubectl exec` 执行；失败非零退出
- [x] T030 [US4] 按 `quickstart.md` §4 运行安装脚本，验证 4 个 uv 工具 + 9 个 mise 工具（含 atuin）、路径位于 `/workspace/.local` 或 `/workspace/.config`
- [x] T031 [US4] 按 `quickstart.md` §10 重启 Pod，验证工具命令仍可用、安装脚本无需重复下载
- [x] T032 [P] [US4] 在 `apps/deepseek-harness/README.md` 记录工具清单、安装命令、工具卷重建后的重跑条件

**Checkpoint**: US4 可独立验收；工具持久化。

---

## Phase 6: User Story 3 - 本机 DSH 配置与插件同步（Priority: P1）

**Goal**: 本机 `gh` 或 `~/.dsh` → 本地改写 → `kubectl cp` → 容器内 `pnpm install` → 重启；集群内无配置仓库凭据。

**Independent Test**: `scripts/sync-dsh-config --source "$HOME/.dsh"` 退出 0；Pod 内 `.dsh-config-source` 有来源/时间；配置无 `/home/casey`；插件/市场可用；`--repo` 模式用本机 gh 成功且集群无 token。

- [x] T033 [US3] 新增 `apps/deepseek-harness/files/transform-config.sh`：实现白名单复制矩阵（profiles/local-plugins/local-presets/skills/skills-manager/AGENTS.md/dsh-pet/integrations），跳过 sessions/storages/.credentials/dsh-chat-import/node_modules
- [x] T034 [US3] 在 `transform-config.sh` 实现改写：`/home/casey/.dsh`→`/home/node/.dsh`、codegraph/atuin/dcg→mise shims、provider→`deepseek-official`、删除 dshmarket 依赖/bundle、置空 StyleFerry post、追加 `onlyBuiltDependencies`、skill lock/integrations 路径
- [x] T035 [US3] 新增 `scripts/sync-dsh-config`：支持 `--source DIR` 与 `--repo OWNER/REPO --revision REF`（本机 `gh repo clone`）；生成 staging、tar、`kubectl cp`、容器内解包、`CI=true pnpm install --no-frozen-lockfile`、写 `.dsh-config-source`、`kubectl rollout restart`、等待 Ready
- [x] T036 [US3] 按 `quickstart.md` §5.1 运行 `scripts/sync-dsh-config --source "$HOME/.dsh"`，验证退出 0、Pod Ready、marker、配置无本机绝对路径
- [x] T037 [US3] 按 `quickstart.md` §5.2 运行 `scripts/sync-dsh-config --repo east4ming/dsh-config --revision <ref>`，验证本机 gh 克隆成功、Pod 内无仓库 token
- [x] T038 [US3] 按 `quickstart.md` §9 验证插件安装成功、市场页面无重复 `dsh-market` 行、`DEEPSEEK_API_KEY` 路由下模型对话可用
- [x] T039 [P] [US3] 在 `apps/deepseek-harness/README.md` 记录配置更新/回滚、`--source` 与 `--repo` 两种模式、`pnpm install` 失败恢复

**Checkpoint**: US3 可独立验收；配置/插件可用且集群无配置凭据。

---

## Phase 7: User Story 5 - skills 同步（Priority: P2）

**Goal**: 本机 `/home/casey/.agents/skills` 同步到 1Gi skills PVC，Pod 重建后保留。

**Independent Test**: 同步后 `/workspace/.agents/skills` 出现本机同名目录，DSH 能发现新增 skill；删除 Pod 后仍在。

- [x] T040 [US5] 新增 `scripts/sync-dsh-skills`：查找 Pod、等待 Ready、`tar` 本机 skills → `kubectl exec -i ... tar -C /workspace/.agents/skills --no-same-owner -xf -`
- [x] T041 [US5] 按 `quickstart.md` §6 运行同步，验证本机同名目录存在、DSH 技能目录发现新增 skill
- [x] T042 [US5] 按 `quickstart.md` §10 重启 Pod，验证 skills 仍在 1Gi PVC
- [x] T043 [P] [US5] 在 `apps/deepseek-harness/README.md` 记录 skills 同步命令、不提交到 Git、1Gi 容量边界

**Checkpoint**: US5 可独立验收。

---

## Phase 8: User Story 6 - 密钥从本机 env 注入（Priority: P2）

**Goal**: `dsh-provider-credentials` 只有两个键，来自本机 env；仓库无真实值；不注入 `GH_TOKEN`/`DSH_CONFIG_TOKEN`。

**Independent Test**: 无 env 时 bootstrap 失败；有 env 时 Secret 两个键；Pod env 来自 Secret；`git grep` 无真实值。

- [x] T044 [US6] 按 `quickstart.md` §1 验证 `scripts/bootstrap-deepseek-harness`：缺 env 失败、重复执行幂等、输出不回显值
- [x] T045 [US6] 验证 `scripts/bootstrap-deepseek-harness` 创建的 `dsh-provider-credentials` 只有 `DEEPSEEK_API_KEY`、`GITHUB_API_TOKEN`；Pod 内无 `GH_TOKEN`、无 `DSH_CONFIG_TOKEN`
- [x] T046 [US6] 对 `apps/deepseek-harness/` 与 `scripts/` 执行全仓库密钥形态扫描（`git grep`/`detect-private-key`），确认无真实 API Key/token/私钥
- [x] T047 [P] [US6] 在 `apps/deepseek-harness/README.md` 记录 bootstrap、轮换后重启 Pod、`GITHUB_API_TOKEN` 只用于 mise 限流

**Checkpoint**: US6 可独立验收；无密钥泄露。

---

## Phase 9: User Story 7 - 按版本规范发布（Priority: P2）

**Goal**: 合并后打 annotated tag，更新 Changelog，在 Gitea 与 GitHub 双远端发布。

**Independent Test**: `git ls-remote --tags` 两侧都有 tag；两侧 Release 存在；Changelog 有条目；ArgoCD Synced/Healthy。

- [x] T048 [US7] 运行 `helm lint apps/deepseek-harness`、`helm template` 断言、`pre-commit run --all-files`，记录结果
- [x] T049 [US7] 运行 `make -C test filter=Smoke`（`test/smoke_test.go`），确认 DSH Web 401、Desktop 200、原有 5 个应用 200
- [x] T050 [US7] 更新 `docs/reference/changelog.md`，新增发布日 tag 条目，内容只来自真实提交
- [x] T051 [US7] 按 `docs/reference/versioning.md` 在 `master` 上打 annotated tag（发布日，如 `v2026.11.11`；同日第二快照 `.2`），推送并用 `git ls-remote` 双侧核对
- [x] T052 [US7] 用 `tea releases create` 与 `gh release create --verify-tag` 在 Gitea/GitHub 创建 Release，正文与 `docs/reference/changelog.md` 一致（当时 Gitea CLI 名为 `tea`；现为 `gt release create`，见 [versioning.md](../../docs/reference/versioning.md)）

**Checkpoint**: 发布完成，可回滚到 tag。

---

## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: 文档收口、备份边界、最终一致性检查。

- [x] T053 [P] 完成 `apps/deepseek-harness/README.md`：上游 provenance/diff、values、Secret、两种配置来源、工具/skills、Ingress/noVNC 警告、升级/回滚、已知限制
- [x] T054 [P] 检查 `scripts/backup-coverage` 未被修改；README 明确四块 PVC 为后续手动备份对象，`backup-coverage` 在备份配置前会列出它们是预期
- [x] T055 [P] 检查 `apps/deepseek-harness/README.md` 与 `specs/015-deepseek-harness-helm/` 中无 `initContainer`/`configSync`/`DSH_CONFIG_TOKEN` 的正向残留；所有文档链接存在
- [x] T056 按 `spec.md` 的 SC-001…SC-011 逐项勾选验收；确认 ArgoCD `deepseek-harness` Synced/Healthy
- [x] T057 按 `specs/015-deepseek-harness-helm/quickstart.md` 清理持久化测试标记与临时命名空间，确认工作区干净

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: 无依赖，立即开始。
- **Foundational (Phase 2)**: 依赖 Setup；**阻塞所有用户故事**。
- **US1/US2**: 依赖 Foundational（含 Secret 与 PVC）。
- **US4**: 依赖 Foundational（tools PVC、Pod）；可先于 US3。
- **US3**: 依赖 Foundational + US4（工具路径需要 dcg/codegraph/atuin）。
- **US5**: 依赖 Foundational；可与 US3/US4 并行（不同文件/PVC 路径）。
- **US6**: 验证 Foundational 的 T016；可与 US1 并行验证。
- **US7**: 依赖所有实现与验收。
- **Polish**: 依赖所有用户故事。

### User Story Dependencies

- **US1 (P1)**: 依赖 Foundational；不依赖 US2/US3/US4 的实现（但 PVC/Secret 是 Foundational）。
- **US2 (P1)**: 依赖 Foundational；PVC 保留可独立验收；工具/配置的持久化复验分别在 US4 T031、US3 T038 之后。
- **US3 (P1)**: 依赖 US4 的工具；与 US5 可并行（不同路径）。
- **US4 (P1)**: 依赖 Foundational；不依赖 US3。
- **US5 (P2)**: 依赖 Foundational；可与 US3/US4 并行。
- **US6 (P2)**: 依赖 Foundational T016；验证任务可与 US1 并行。
- **US7 (P2)**: 依赖全部。

### Within Each User Story

- 先实现脚本/Chart，再运行验收；US3 先 `--source` 再 `--repo`；US4 先脚本后运行；US6 先 bootstrap 后环境/泄露检查。

### Parallel Opportunities

- Setup：T002/T003/T004/T005 可并行（T003/T004 依赖 T001 的复制）。
- Foundational：T009/T010/T011 可并行；T013/T014 可并行。
- US1：T017/T018 可并行；T019 之后 T020/T021/T022 顺序执行（同一集群）。
- US2：T026/T027 可并行；T023/T024/T025 顺序。
- US4：T032 可与 T030/T031 并行（文档 vs 运行）。
- US3：T039 文档可与 T038 并行；T036/T037 不并行（同一 Pod）。
- US5：T043 文档可与 T041/T042 并行。
- US6：T047 文档可与 T046 并行。
- Polish：T053/T054/T055 可并行；T056/T057 最后。

## Parallel Example: User Story 1

```bash
# 两个独立文件可并行
Task: "T017 [US1] 扩展 test/smoke_test.go"
Task: "T018 [US1] 更新 apps/homepage/values.yaml"

# 之后顺序执行集群验收
Task: "T019 [US1] helm template 断言"
Task: "T020 [US1] Web 401/token/model"
Task: "T021 [US1] noVNC/桌面入口"
Task: "T022 [US1] NetworkPolicy 正反例"
```

## Parallel Example: US4 + US5

```bash
# tools 与 skills 使用不同 PVC/脚本，可在 Foundational 后并行
Task: "T028 [US4] 新增 install-tools.sh"
Task: "T040 [US5] 新增 sync-dsh-skills"

# 各自运行/验收互不阻塞
Task: "T030 [US4] 运行工具安装"
Task: "T041 [US5] 运行 skills 同步"
```

## Implementation Strategy

### MVP First（US1）

1. Phase 1 + Phase 2：Chart、PVC、Service/Ingress/NP、Secret 引导。
2. Phase 3：US1 访问验收（Web 401/token、桌面、NetworkPolicy）。
3. **STOP and VALIDATE**：按 `quickstart.md` §7/§8 验收访问链路；模型调用需等 US3 配置同步后由 T038 验证。
4. 继续 US4 → US3 → US5，补齐工具、配置、skills；最后用 T056 对照全部 SC。

### Incremental Delivery

1. Foundational → 可部署的空 DSH（默认 profile）。
2. US4 → 工具可用。
3. US3 → 本机配置/插件/市场可用；重启后生效。
4. US5 → skills 可用。
5. US2/US6/US1 的验收可随对应阶段执行（PVC/Secret 属于 Foundational）。
6. US7 → 发布。

## Notes

- 工具/配置/skills 是**一次性手动任务**，不是 initContainer；重跑脚本应幂等。
- 集群内没有配置仓库凭据；`--repo` 模式只在本机使用 `gh`。
- 四块 PVC 是后续手动备份对象；**不要**修改 `scripts/backup-coverage`。
- 每个任务完成后按 `docs/reference/versioning.md` 使用 Conventional Commits；不要用 `[Spec Kit]` 前缀。
- 验收命令以 [quickstart.md](quickstart.md) 为准；不要手工 `kubectl apply` 绕过 ArgoCD（隔离命名空间的保留演练除外）。
