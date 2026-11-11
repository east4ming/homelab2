# 实施方案：以 Helm Chart 在 homelab2 安装 DeepSeek Harness

**Branch**: `015-deepseek-harness-helm` | **Date**: 2026-11-11 | **Spec**: [spec.md](spec.md)
**目标集群**: 生产 homelab2（ArgoCD 自动同步 `master`） | **上游基线**: `runzhliu/deepseek-harness-docker@04371405`

## 摘要

新增 `apps/deepseek-harness`（扁平 Helm Chart，vendored 上游 Chart 0.1.29），把本机 DSH 运行环境搬进集群：

- 镜像固定市场变体 `0.2.2-rc.1-r1-market.1`。
- 四块 RWO PVC：`dsh-home` 10Gi、workspace 20Gi、tools 20Gi、skills 1Gi；全部在卸载/重同步后保留。
- **不使用 initContainer**：Pod 直接启动 DSH；工具安装、DSH 配置同步、skills 同步都是一次性手动任务，
  通过 `kubectl exec` / `kubectl cp` 完成，结果落在 PVC 上。
- 配置来源是本机 `gh` 拉取的私有 dsh-config，或本机 `/home/casey/.dsh`；本地改写后用 `kubectl cp` 写入
  Pod，再在容器内 `pnpm install`。集群内不需要配置仓库凭据。
- 新增 ClusterIP Service 供 Tailscale 使用（上游 Headless 不能做 L7 后端），两条 Tailscale Ingress：
  3080 Web、6080 noVNC；Web Ingress 同时路由 `/novnc-*` 以支持 UI 内桌面入口。
- NetworkPolicy 保留默认拒绝，但只按端口放行 3080/6080；源选择器受 Cilium SNAT 限制（见风险）。
- 密钥走用户指定的 `dsh-provider-credentials` Secret，bootstrap 脚本从本机 env 创建；不进 Git。
- 四块 PVC 是后续手动备份对象；本特性**不修改** `scripts/backup-coverage` 的豁免表。
- 按 `docs/reference/versioning.md` 发布。

## 技术上下文

| 项 | 值 |
| --- | --- |
| 语言/格式 | Helm/YAML、Bash（手动安装/同步脚本）、Go（smoke test） |
| 主要依赖 | 上游镜像 `docker.io/runzhliu/deepseek-harness:0.2.2-rc.1-r1-market.1`；Tailscale Operator 1.104.2；Cilium；ArgoCD ApplicationSet；pnpm 10.15.1（镜像内置）；uv/mise（手动安装到 PVC）；本机 `gh`（配置来源） |
| 存储 | 4 × RWO PVC（10/20/20/1 GiB），SC `standard-rwo`；`dsh-home` 用 StatefulSet volumeClaimTemplate，其余独立 PVC |
| 测试 | `helm lint`、`helm template` + yq 断言、`pre-commit`（yamllint/helmlint/shellcheck/private-key）、扩展 `test/smoke_test.go`（Web 401 / Desktop 200）、线上 tailnet/NetworkPolicy/PVC 验证 |
| 目标平台 | homelab2 k3s（Linux amd64），Tailscale MagicDNS，单副本 |
| 项目类型 | GitOps 应用 Chart + 一次性运维脚本（本机 + 容器内） |
| 性能 | 单用户；requests 250m/1Gi，limits 2 CPU/4Gi；`/dev/shm` 1Gi；不改变 Cilium 调优 |
| 约束 | 只读根文件系统、非 root、无公网入口；noVNC 无认证但仅 tailnet；Secret 不入库；4 块 PVC 不随应用删除 |
| 规模 | 1 个 DSH 实例、4 块 PVC、2 条 Ingress；镜像约 1.5–2GB + 插件 node_modules |

## Constitution Check

*GATE: 通过后才进入实现；Phase 1 设计后复核。*

| 原则 | 判定 | 说明 |
| --- | --- | --- |
| I. 代码质量 | PASS | YAML 过 yamllint、Chart 过 helmlint、脚本过 shellcheck；无密钥/大文件 |
| II. 测试标准 | PASS（有例外） | `helm template` 断言 + 扩展 smoke test + 线上验收；不改变 StorageClass/Ceph 配置，不需要 dbench；`make smoke-test` 继续覆盖原有 5 个服务 |
| III. 用户体验一致性 | PASS（有例外） | 只用 Tailscale Ingress、MagicDNS `*.west-beta.ts.net`；新增 Homepage 入口；DSH 用自身 token/Cookie，noVNC 无认证（见 Complexity Tracking） |
| IV. 性能要求 | PASS | 显式 requests + limits；不改 Cilium/k3s 参数；单副本 + 4Gi 上限，资源影响已评估 |
| V. 优先使用中文 | PASS | plan/research/文档/提交信息用中文 |
| 安全与合规 | PASS（有例外） | Secret 不入库；bootstrap 从本机 env 创建；noVNC 仅 tailnet；无公网。ESO/SSO 例外见下 |
| 开发与部署工作流 | PASS（有例外） | `apps/deepseek-harness` 含 Chart.yaml + values.yaml；ArgoCD 部署。工具/配置是 PVC 上的运行时数据，用一次性 `kubectl exec/cp` 维护，不进入集群清单 |

**例外**（必须在 Complexity Tracking 中保留理由）：

1. Secret 用命令式 `kubectl create secret`，不用 ESO——用户明确指定该流程；值仍来自本机 env，不进 Git。
2. DSH 使用内置 token/Cookie，noVNC 无认证，不接 Kanidm/Dex——上游单用户设计；noVNC 仅 tailnet，用户明确接受。
3. 工具安装、配置同步与 skills 同步是**一次性手动任务**，不通过 initContainer/ArgoCD 自动执行——用户明确
   要求先启动容器、再 `kubectl exec` 手动执行；配置数据是 PVC 上的运行时状态，不是集群清单。
4. 四块 PVC 的备份由用户后续手动配置；本特性不实现 VolSync/备份策略，也不豁免 `backup-coverage`。

**Phase 1 复核**：新增 ClusterIP Service、两条 Ingress、四块 PVC 与手动脚本不引入新的门禁违规；例外仍为上述
4 项。设计没有修改 Cilium、StorageClass、ArgoCD 全局配置。

## 项目结构

### 文档（本特性）

```text
specs/015-deepseek-harness-helm/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── helm-values.md
│   ├── runtime.md
│   └── config-sync.md
└── checklists/requirements.md
```

### 代码（仓库）

```text
apps/deepseek-harness/
├── Chart.yaml                    # 名称 deepseek-harness，version 0.1.29-homelab.1，记录上游
├── values.yaml                   # 平铺上游 values + tools/skills/ingress/resources
├── values.schema.json            # 上游 schema + 新字段
├── README.md                     # 运维/升级/回滚/手动同步/差异说明
├── files/
│   ├── install-tools.sh          # 在容器内执行：uv/mise/工具 → 工具卷
│   └── transform-config.sh       # 在本机执行：配置容器化改写
└── templates/
    ├── _helpers.tpl              # 上游 helpers（保留）
    ├── statefulset.yaml          # 上游 + 卷/env/resources/注解（无 initContainer）
    ├── service.yaml              # Headless（保留，StatefulSet serviceName）
    ├── service-tailscale.yaml    # 新增 ClusterIP，Ingress 后端
    ├── networkpolicy.yaml        # 上游 + 放行 3080/6080
    ├── ingress-web.yaml          # 新增；/ → 3080，/novnc- → 6080
    ├── ingress-desktop.yaml      # 新增；/ → 6080
    ├── pvc-workspace.yaml        # 新增 20Gi
    ├── pvc-tools.yaml            # 新增 20Gi
    ├── pvc-skills.yaml           # 新增 1Gi
    └── NOTES.txt                 # 更新访问/手动步骤说明

scripts/
├── bootstrap-deepseek-harness    # 从本机 env 创建/更新 Secret（两个键）
├── install-dsh-tools             # 本机 wrapper：cp install-tools.sh → exec
├── sync-dsh-config               # 本机 wrapper：gh/~/.dsh → 改写 → kubectl cp → pnpm install → 重启
└── sync-dsh-skills               # 本机 skills → PVC

apps/homepage/values.yaml         # 新增 DSH Web/Desktop 入口
test/smoke_test.go                # 增加 expectedStatus + DSH Web/Desktop
docs/reference/changelog.md       # 发布时新增条目
AGENTS.md                         # plan 指针
```

**结构决定**：采用扁平 Chart（不是 subchart）。上游没有 Helm 仓库，且必须扩展 StatefulSet（卷）与新增
Ingress；扁平结构让 values 与上游同名、差异可逐行审阅，ArgoCD 不需要额外 post-renderer。

## Phase 0 研究结论

完整决策见 [research.md](research.md)。关键结论：

1. **Tailscale L7 Ingress 不接受 Headless Service**：`addIngressBackend` 校验 `ClusterIP`；必须新增
   `deepseek-harness-tailscale` ClusterIP Service，Headless 仅保留给 StatefulSet。
2. **Tailscale 只支持 Prefix 路径**；同一 Ingress 可有多条 Prefix → 多后端，因此 `/` 与 `/novnc-` 可分流。
3. **NetworkPolicy 必须放行 3080/6080 端口**；按 `tailscale/ingress-proxies` 标签的源选择器在本集群无效：
   Cilium `ipv4NativeRoutingCIDR=192.168.3.0/24` 把跨节点 Pod 流量 SNAT 成节点 IP，源身份变成 `world`。
   当前只按端口放行，收紧源需要独立修正 Cilium native routing。
4. **不使用 initContainer**：Pod 直接启动 DSH；工具/配置/skills 通过 `kubectl exec/cp` 手动一次完成，
   避免把长耗时安装放进 Pod 启动路径，也符合用户指定的操作方式。
5. **配置同步不需要集群凭据**：本机 `gh` 已认证，或直接使用本机 `~/.dsh`；本地改写后 `kubectl cp`。
6. **市场镜像内置 dshmarket 1.66.9**，与本机 1.73.17 重复；从 profile 删除 dshmarket，使用镜像内置。
7. **provider 必须从 `deepseek-account` 改为 `deepseek-official`**；API Key 路由只认 `DEEPSEEK_API_KEY`。
8. **镜像 pnpm 10.15.1 忽略 `allowBuilds`**，需追加 `onlyBuiltDependencies`（实测）。
9. **XDG 指向 /tmp**，必须覆盖到工具卷，uv/mise 才会持久化。
10. **atuin 可由 mise 安装**（aqua/cargo），无需跳过。
11. **四块 PVC 是备份对象**；不改 `scripts/backup-coverage`，用户后续手动配置备份。

## Phase 1 设计结论

- 数据模型见 [data-model.md](data-model.md)：4 块 PVC、Secret、手动同步状态、ToolSet、2 条 Ingress、
  ClusterIP backend、NetworkPolicy、备份对象。
- 契约见 [contracts/helm-values.md](contracts/helm-values.md)、[contracts/runtime.md](contracts/runtime.md)、
  [contracts/config-sync.md](contracts/config-sync.md)。

## 实施步骤

### 1. Chart 骨架与上游差异记录

- 复制上游 `charts/deepseek-harness/{Chart.yaml,values.yaml,values.schema.json,templates/*}` 到
  `apps/deepseek-harness/`。
- `Chart.yaml`：`name: deepseek-harness`、`version: 0.1.29-homelab.1`、`appVersion: 0.2.2-rc.1`，
  annotations 记录上游 repo/commit；`sources` 指向上游。
- 保留 `_helpers.tpl`、探针、安全上下文、`persistentVolumeClaimRetentionPolicy`。
- `values.yaml` 保持上游 key；新增：
  - `image.tag: 0.2.2-rc.1-r1-market.1`
  - `desktop.publicPort: 443`
  - `workspace.create/size/storageClass`、`tools.*`、`skills.*`
  - `ingress.web/desktop.*`
  - `networkPolicy.ingress` 放行规则
  - `resources.requests/limits`
- 不新增 `configSync`/`init` 等被否决的抽象；手动步骤写进 README。
- `values.schema.json` 同步新增字段；不引入 `additionalProperties: false`（保持上游宽松）。
- 验证：`helm lint`；`helm template` 中 StatefulSet/Service 与上游 diff 只包含预期字段。

### 2. StatefulSet：卷、env、resources（无 init）

- 主容器新增 env：`XDG_*`、`DSH_AGENTS_HOME`、`DSH_DESKTOP_PUBLIC_PORT`（来自 `desktop.publicPort`）、
  完整 `PATH`。
- volumeMounts：`dsh-home`、`workspace`、`tools`（`/workspace/.local` 与 `/workspace/.config`）、
  `skills`、`tmp`、`shm`。
- volumes：新增 `tools`、`skills`；`workspace` 使用 `workspace.existingClaim`；**不添加 initContainers**。
- `resources` 加 limits；保持 `readOnlyRootFilesystem`、`runAsNonRoot`、drop ALL、`automountServiceAccountToken: false`。
- `volumeClaimTemplates`：`persistence.size: 10Gi`、`storageClass: standard-rwo`。
- 移除上游 `args`? 保留 `web --patch ... --no-open`；主容器入口不变。
- 验证：渲染后没有 `initContainers`；挂载路径、env、limits、volumeClaimTemplate 与契约一致。

### 3. Service / Ingress / NetworkPolicy

- `service.yaml`：保持 Headless（`clusterIP: None`）。
- `service-tailscale.yaml`：ClusterIP，selector 同 StatefulSet，端口 http 3080 / desktop 6080，
  `ipFamilyPolicy: PreferDualStack`。
- `ingress-web.yaml`：host `dsh.west-beta.ts.net`，class `tailscale`，annotation proxy-group，
  paths `/`→http、`/novnc-`→desktop，TLS host。
- `ingress-desktop.yaml`：host `dsh-desktop.west-beta.ts.net`，path `/`→desktop，TLS host。
- `networkpolicy.yaml`：从 values 读取放行规则；默认拒绝其他端口，只放行 3080/6080。源选择器因 Cilium
  SNAT（`ipv4NativeRoutingCIDR=192.168.3.0/24`）无法匹配，README 记录后续收紧条件。
- 验证：`helm template` 断言语义；上线后 `curl` 401/200、非 tailscale Pod 被拒。

### 4. 一次性工具安装

#### `apps/deepseek-harness/files/install-tools.sh`（在容器内执行）

- `#!/bin/bash`、`set -euo pipefail`、`umask 077`。
- 设置 `HOME=/workspace`、`XDG_*`、`PATH`（与 Pod env 一致）。
- 若 uv/mise 不存在，用官方安装脚本装到 `/workspace/.local/bin`。
- 逐个 `uv tool install`（specify-cli、pre-commit、pyrefly、yamllint），已装则跳过。
- `mise use -g` 9 个工具（含 `aqua:atuinsh/atuin`）；`mise install`；`mise reshim`。
- 写 `/workspace/.local/.dsh-tools-version`（uv/mise 版本 + `uv tool list` + `mise ls --global`）。
- 全部命令输出到 stderr/stdout，不打印 token。

#### `scripts/install-dsh-tools`（本机 wrapper）

- 找 Pod（labels），等待 Ready。
- `kubectl cp apps/deepseek-harness/files/install-tools.sh <pod>:/tmp/install-tools.sh`。
- `kubectl exec -i <pod> -- bash /tmp/install-tools.sh`。
- 不要求重启；PATH 已在 Pod env 中包含工具目录，后续 exec 立即可用。

- 验证：shellcheck；执行后 `uv tool list`、`mise ls --global` 满足清单；Pod 重启后仍可用。

### 5. 一次性配置同步

#### `apps/deepseek-harness/files/transform-config.sh`（在本机执行）

- 输入：`$1` 源目录（本机 `~/.dsh` 或 `gh repo clone` 的临时目录）、`$2` 输出 staging 目录。
- 复制矩阵按 `contracts/config-sync.md`；不复制 `sessions/`、`storages/`、`.credentials.yaml`、
  `dsh-chat-import/`、`node_modules/`。
- 改写：`/home/casey/.dsh` → `/home/node/.dsh`；codegraph/atuin/dcg → mise shims；provider →
  `deepseek-official`；删除 dshmarket 依赖/bundle；置空 StyleFerry post；追加 `onlyBuiltDependencies`；
  skill lock/integrations 路径。
- 使用本机 `sed`/`jq`/`yq`；先写临时文件再 `mv`。
- 最后检查：配置目录中不得残留 `/home/casey/.dsh`（`skills/` 内容除外）。

#### `scripts/sync-dsh-config`（本机 orchestrator）

- 参数：
  - `--source DIR`：默认 `$HOME/.dsh`，直接选本机配置；
  - `--repo OWNER/REPO --revision REF`：用本机 `gh repo clone` 拉到临时目录并 checkout（复用本机 gh 认证）。
- 调用 `transform-config.sh` 生成 staging。
- 打 tar 包 → `kubectl cp <pod>:/tmp/dsh-config-sync.tar`。
- `kubectl exec`：
  - `tar --no-same-owner -C /home/node/.dsh -xf /tmp/dsh-config-sync.tar`
  - `cd /home/node/.dsh/profiles/web && CI=true pnpm install --no-frozen-lockfile`
  - 写 `$DSH_HOME/.dsh-config-source`（来源、revision/时间）
- 成功后 `kubectl rollout restart statefulset/deepseek-harness`（或删除 Pod），等待 Ready。
- 任一步失败即退出非零；不写成功 marker；允许重跑收敛。
- 集群内不需要 `DSH_CONFIG_TOKEN`；本机 `gh` token 不进入集群。

- 验证：shellcheck；`--source ~/.dsh` 与 `--repo ... --revision ...` 两种路径；Pod 内配置路径无本机绝对
  路径；`pnpm install` 成功；重启后插件/市场可用；sessions/credentials 未丢失。

### 6. 独立 PVC

- `pvc-workspace.yaml`：20Gi，`standard-rwo`，名称 `deepseek-harness-workspace`，keep/prune=false。
- `pvc-tools.yaml`：20Gi，`deepseek-harness-tools`。
- `pvc-skills.yaml`：1Gi，`deepseek-harness-skills`。
- 都带 `helm.sh/resource-policy: keep` 与 `argocd.argoproj.io/sync-options: Prune=false,Delete=false`。
- `workspace.create` 控制是否创建；`workspace.existingClaim` 始终传给 StatefulSet。
- 验证：渲染后 PVC 数量/大小/注解；临时命名空间安装→卸载→PVC 仍在。

### 7. 运维脚本

#### `scripts/bootstrap-deepseek-harness`

- 校验 `DEEPSEEK_API_KEY`、`GITHUB_API_TOKEN` 非空；不再有 `DSH_CONFIG_TOKEN`。
- 创建 namespace（`--dry-run=client -o yaml | kubectl apply -f -`）。
- 临时 env 文件（`umask 077`、trap 清理）→ `kubectl create secret ... --from-env-file=... --dry-run=client -o yaml |
  kubectl apply -f -`。
- 只输出键名/结果，不回显值；可重复执行。
- 验证：shellcheck；无 env 时失败；重复执行幂等。

#### `scripts/sync-dsh-skills`

- 找 Pod（labels），等待 Ready。
- `tar -C "$HOME/.agents/skills" -cf - . | kubectl exec -i <pod> -- tar -C /workspace/.agents/skills --no-same-owner -xf -`。
- 不删除远端额外 skill；输出复制数量；可重复执行。
- 验证：shellcheck；同步后目录存在；重启 Pod 后仍在。

### 8. Homepage、smoke test、备份文档

- `apps/homepage/values.yaml` 在 `Utilities` 增加 `DeepSeek Harness`（Web）与 `DSH Desktop`（noVNC），
  icon 用 MDI（如 `mdi-robot-outline`/`mdi-monitor`）。
- `test/smoke_test.go`：
  - 给 `mainApps` 增加 `expectedStatus int`；现有 5 项填 200。
  - 增加 `{"deepseek-harness", "deepseek-harness", 401}` 与
    `{"deepseek-harness-desktop", "deepseek-harness", 200}`。
  - 自定义校验 `statusCode == app.expectedStatus`。
- **不修改** `scripts/backup-coverage`。在 README 列出四块 PVC 作为后续手动备份对象；`backup-coverage` 在
  用户配置备份前会列出它们，这是预期状态，不是本特性的失败。
- 验证：`go test ./... -run Smoke`（需集群与 tailnet）；`git diff --exit-code scripts/backup-coverage`。

### 9. 文档

- `apps/deepseek-harness/README.md`：
  - 上游 provenance（repo、commit、chart 版本）、与上游差异。
  - values 表、Secret bootstrap、两种配置来源（`gh` / `~/.dsh`）、`kubectl cp` 同步、`pnpm install`、重启。
  - 一次性工具安装与重跑条件。
  - 两条 Ingress 与 noVNC 无认证警告；UI 桌面入口与 `desktop.publicPort=443` 的关系。
  - 工具清单、镜像升级、PVC/备份边界、回滚、已知限制。
- 更新 `AGENTS.md` 的 SPECKIT plan 指针到本文件。
- 发布时更新 `docs/reference/changelog.md`。

### 10. 本地验证与上线

1. `helm lint`、`helm template` 断言、`pre-commit`。
2. 创建/更新 Secret（`scripts/bootstrap-deepseek-harness`）。
3. PR → 合并 `master`；ArgoCD 同步。
4. 按 [quickstart.md](quickstart.md)：Pod Ready → 工具安装 → 配置同步（自动重启）→ skills 同步 → token 登录
   → 模型调用 → 桌面 → NetworkPolicy 正反例 → 四块 PVC 持久化。
5. 若失败：修脚本/values，重跑手动步骤或重新同步；不通过手工 `kubectl apply` 绕过 ArgoCD（隔离命名空间的
   保留演练除外）。

### 11. 发布

- 更新 Changelog；确认 ArgoCD Synced/Healthy 与全部验收。
- `git tag -a v2026.11.11`（按发布日；同日第二快照用 `.2`），推送并双侧核对。
- Gitea `tea releases create` + GitHub `gh release create`（正文与 Changelog 一致）。

## 验证计划

| 验证 | 方式 | 通过条件 |
| --- | --- | --- |
| Chart 语法 | `helm lint` | 0 退出 |
| 渲染契约 | `helm template` + `yq` 断言 | **无 initContainers**、ClusterIP service、2 Ingress、2 端口 NP、4 PVC、limits、tag |
| 代码质量 | `pre-commit`（yamllint/helmlint/shellcheck/private-key） | 全部通过 |
| 镜像 tag | Docker Hub manifest / 渲染值 | `0.2.2-rc.1-r1-market.1` 存在且被引用 |
| Smoke | `make -C test filter=Smoke` | Web 401、Desktop 200、原有 5 项 200 |
| NetworkPolicy | 非 tailscale Pod `curl` PodIP:9222 被拒；3080 得 401、6080 得 200；tailnet 成功 |
| 认证 | 浏览器 token URL | 401→Cookie→UI |
| 模型 | UI 发一次 `deepseek-flash` | 无登录提示，返回内容 |
| 工具安装 | `scripts/install-dsh-tools` | 4 + 9 个工具；路径在工具卷 |
| 配置同步 | `scripts/sync-dsh-config --source ~/.dsh` | 配置落盘；`.dsh-config-source` 有记录；无本机绝对路径 |
| 配置同步（gh） | `scripts/sync-dsh-config --repo east4ming/dsh-config --revision <ref>` | 私库拉取成功；集群内无 token |
| 插件 | DSH 启动日志 + 插件/市场页 | 无加载错误；无重复市场行 |
| skills | 同步后目录 | 本机同名目录存在；重启后保留 |
| 持久化 | 四标记 + 删 Pod | 标记仍在；工具/配置无需重做 |
| 卸载保留 | 隔离命名空间 install→uninstall | 4 块 PVC 仍在 |
| 备份边界 | `git diff --exit-code scripts/backup-coverage` | 脚本未被本特性修改；README 列出四块 PVC |
| 回滚 | ArgoCD Sync 旧 tag | 应用恢复，PVC 保留 |

## 风险与回退

| 风险 | 缓解 |
| --- | --- |
| 手动同步/安装漏跑或漂移 | README 给出明确顺序与检查命令；`.dsh-config-source` 审计；重跑幂等 |
| 本机 `gh` 未登录 | 默认 `--source ~/.dsh` 不依赖 gh；`--repo` 模式要求 `gh auth status` |
| `kubectl cp` 中断/`pnpm install` 失败 | 脚本非零退出；不写来源 marker；重跑收敛；必要时先备份 dsh-home |
| Tailscale 多后端路径不生效 | 保留独立 Desktop Ingress 作为必达路径；Web UI 桌面按钮降级为文档直接 URL |
| 插件在容器内不兼容 | 逐个验证；在 profile patch 中 `disabled: true` 并记录，不阻塞主体验收 |
| 4Gi limit 导致 OOM | 观察 `kubectl top`/OOMKilled；只调 values |
| 10Gi home 被 node_modules/会话占满 | 监控；文档给出扩容/清理方式；不擅自改大小 |
| 上游 Chart 升级漂移 | `README` 记录 upstream commit + diff 清单；升级时逐项重放本地新增 |
| pnpm 10 与配置 pnpm 11 语义差异 | `onlyBuiltDependencies`；安装日志检查 `Ignored build scripts` |
| 备份尚未配置 | 四块 PVC 保留策略与名称已固定；README 列为后续手动备份对象；`backup-coverage` 会明确列出未覆盖项 |
| RWO 节点绑定 | 单副本；接受节点不可用时的不可调度；不做多副本 |
| noVNC 暴露面 | 仅 tailnet Ingress；Tailscale ACL 为唯一边界；不公网、不加 NodePort |
| NetworkPolicy 只能按端口放行 | Cilium `ipv4NativeRoutingCIDR=192.168.3.0/24` 把跨节点 Pod 流量 SNAT 成节点 IP，源身份变成 `world`；源选择器/ipBlock 均不匹配。当前默认拒绝其他端口、只放行 3080/6080；收紧源需独立修正 Cilium native routing |

**回退**：`git revert` 合并提交；ArgoCD 同步上一个 tag；四块 PVC 保留。镜像降级前确认 DSH 数据卷兼容；
备份由用户后续配置，必要时先手工保留 `dsh-home`（会话/凭据）再操作。

## Complexity Tracking

| 例外/复杂度 | 为什么需要 | 更简单的替代为何被拒绝 |
| --- | --- | --- |
| 命令式 Secret（非 ESO） | 用户明确给出 `kubectl create secret` 流程，值来自本机 env | ESO 需要先把值写入集群 external Secret，多一步且不符合用户指定流程；Secret 仍未入库 |
| DSH 内置认证 + noVNC 无认证 | 上游单用户设计；noVNC 本身无认证；仅 tailnet | 接 Kanidm/Dex 需要反向代理/认证层，用户明确接受单人 tailnet 的边界 |
| Vendored 扁平 Chart | 上游无 Helm 仓库，且必须加卷/Ingress | subchart/post-renderer 都需要额外机制，且无法避免修改 StatefulSet |
| 手动工具/配置/skills 同步 | 用户明确要求先启动容器，再 `kubectl exec` 一次性执行；避免长耗时 init | initContainer 会拖慢每次启动，且被用户明确否决；GitOps 不适合私库配置与个人 skills |
| 删除 profile 的 dshmarket / 版本 1.66.9 | 市场镜像已内置市场，重复行会冲突 | 保留 1.73.17 会与镜像 patch 的 `dsh-market` 行重复，且版本来源不确定 |
| 四块 PVC 不豁免 backup-coverage | 用户要求备份；备份由用户后续手动配置 | 在脚本里豁免会掩盖未备份事实；VolSync 自动配置超出本次范围 |
| 4Gi 内存上限 | Constitution IV 要求 limits；Chromium 需要余量 | 沿用上游无 limits 违反宪法；2Gi 可能 OOM |
| NetworkPolicy 端口级放行 | 实测 Cilium SNAT 使 Tailscale 代理源标签在目标侧不可见；按端口放行是当前唯一可工作的最小策略 | 改 Cilium native routing 覆盖 Pod CIDR 是集群级网络变更，超出本特性；完全关闭 NetworkPolicy 会连端口限制也丢失 |

## 待确认/前置

1. **本机 `gh` 认证**：`--repo` 模式需要 `gh auth status` 正常；否则用默认 `--source ~/.dsh`。
2. **配置来源选择**：默认 `~/.dsh` 是活配置（可能含本机运行状态），脚本只选白名单目录；若希望只从私库
   同步，使用 `--repo` 模式。
3. **Tailscale 多后端 Ingress 实测**：代码支持，但上线首日必须验证 `/novnc-` 路径；失败则按回退方案。
4. **插件加载结果**：`dsh-pet`、`dsh-mini-remote`、`dsh-wechat` 等需逐个看日志；不兼容者禁用并记录。
5. **资源上限**：4Gi 是否足够以线上 OOM 记录为准，必要时只调 values。
6. **备份**：用户后续手动配置；本特性只保证四块 PVC 名称/容量/保留策略可被备份工具识别。
