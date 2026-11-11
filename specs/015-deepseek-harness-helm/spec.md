# Feature Specification: 以 Helm Chart 在 homelab2 安装 DeepSeek Harness

**Feature Branch**: `015-deepseek-harness-helm`

**Created**: 2026-11-11

**Status**: Draft

**Input**: 以 Helm Chart 形式安装 <https://github.com/runzhliu/deepseek-harness-docker>。要求：DSH home 持久化 10Gi；通过
`workspace.existingClaim` 挂载另一块 20Gi RWO 工作区 PVC；配置 Tailscale Ingress，并评估该 chart 默认的
拒绝 Pod 入站流量 NetworkPolicy 对 Tailscale Ingress 的影响；另建一条 Tailscale Ingress 暴露无认证的 noVNC
桌面（仅 tailnet 内可达）；显式使用市场变体镜像 `0.2.2-rc.1-r1-market.1`；按给定方式从本机环境变量注入
`DEEPSEEK_API_KEY`、`GITHUB_API_TOKEN` 到 `dsh-provider-credentials` Secret；先启动 DSH 容器，再通过
`kubectl exec` 执行一次性工具安装与 DSH 配置更新（配置来源为本机 `gh` 拉取的私有仓库或本机
`/home/casey/.dsh`，用 `kubectl cp` 同步）并处理与容器环境的不兼容；安装配置中涉及的
DSH 插件；持久化安装 uv 与 mise 以及它们管理的工具（uv：
specify-cli、pre-commit、pyrefly、yamllint；mise：gh、jq、codegraph、yq、clawhub、ax、dcg、mq，并核实 atuin
是否可由 mise 安装）；工具目录 20Gi RWO；同步 `/home/casey/.agents/skills` 并持久化到 1Gi RWO；四块 PVC 是
备份对象（备份由用户后续手动配置）；按 `docs/reference/versioning.md` 完成分支、提交、标签、Changelog 与
Gitea/GitHub 双远端发布。

## 背景与现状

本特性把本机正在使用的 DSH（DeepSeek Harness）运行环境迁到 homelab2 集群，并纳入本仓库的 GitOps 与版本管理。
现有仓库没有 DSH 相关应用；`apps/*` 由 ArgoCD ApplicationSet 自动发现（应用名与命名空间均为目录名，已启用
`CreateNamespace=true`、`automated prune + selfHeal`）。默认 StorageClass 为 `standard-rwo`（RWO，Ceph RBD）。

### 上游 Helm Chart 的现状与缺口

已核对 `runzhliu/deepseek-harness-docker` 仓库中的 `charts/deepseek-harness`（Chart 0.1.29，appVersion
`0.2.2-rc.1`）。它只包含 StatefulSet、Headless Service、NetworkPolicy 与 `dsh-home` 的 volumeClaimTemplate：

| 能力 | 上游 Chart 现状 | 对本需求的影响 |
| --- | --- | --- |
| 镜像 | 默认 `docker.io/runzhliu/deepseek-harness:0.2.2-rc.1-r1`，可 `image.tag` 覆盖 | 需显式固定市场变体 tag；该 tag 已在 Docker Hub 核实存在 |
| DSH home | `persistence.size`，默认 5Gi，RWO，StatefulSet volumeClaimTemplate；删除 StatefulSet 时保留 | 需改为 10Gi |
| 工作区 | `workspace.existingClaim`，挂载到 `/workspace` | 可用；但 20Gi PVC 需要由本仓库创建或预先存在 |
| Ingress | **没有 Ingress 模板** | 需在本仓库交付层新增两条 Tailscale Ingress（Web 3080、桌面 6080） |
| 额外卷 | **没有 extraVolumes / extraVolumeMounts** | 工具 20Gi、skills 1Gi 两块 PVC 无法只靠 values 挂载，必须扩展 Chart |
| NetworkPolicy | 默认 `networkPolicy.enabled=true`、`ingress: []`，即拒绝所有入站 | 会阻断 Tailscale Ingress 代理到 DSH Pod 的流量，需显式放行 3080 与 6080 |
| Service | `clusterIP: None` 的 Headless Service | Tailscale L7 Ingress 要求后端 Service 有 ClusterIP，不能直接复用；交付层需新增 ClusterIP Service |
| 安全上下文 | 非 root UID/GID 1000、只读根文件系统、drop ALL、`/tmp` 与 `/dev/shm` 为 emptyDir | 工具与配置只能写入显式挂载的 PVC |
| 容器环境 | `HOME=/workspace`、`DSH_HOME=/home/node/.dsh`、`XDG_CACHE_HOME=/tmp/.cache`、`XDG_CONFIG_HOME=/tmp/.config`、`XDG_DATA_HOME=/tmp/.local/share` | uv/mise 默认会写 `/tmp`，仅挂 PVC 不足以持久化，必须覆盖 XDG 路径 |
| Web 端口 | 3080（DSH Web）；6080（noVNC 桌面，上游明确无认证） | 两者都通过 Tailscale Ingress 暴露；6080 无认证，但仅 tailnet 内可达，不发布到公网 |

上游 Chart 没有 Helm 仓库地址，只能从 Git 仓库获取。本仓库既有做法是把依赖 chart 的 tgz vendored 到
`apps/<name>/charts/`，应用目录自包含，ArgoCD 不做跨目录引用。因此本特性需要一个可审计的上游 Chart 副本或
等价交付层，并记录相对上游的差异。

### Tailscale Ingress 与 NetworkPolicy 评估

已确认集群使用 Tailscale Operator 1.104.2，并创建了 `ProxyGroup/ingress-proxies`（4 副本）。实际运行中的
代理 Pod 位于 `tailscale` 命名空间，带有以下标签：

- `tailscale.com/managed=true`
- `tailscale.com/parent-resource-type=proxygroup`
- `tailscale.com/parent-resource=ingress-proxies`

现有应用都通过 `ingressClassName: tailscale` + `tailscale.com/proxy-group: ingress-proxies` 暴露。Ingress
代理最终访问 DSH Pod 的 `3080`（Web）与 `6080`（noVNC 桌面）端口，在 Cilium 下入站 NetworkPolicy 按目的 Pod
执行。**上游 Service 是 Headless（`clusterIP: None`），而 Tailscale L7 Ingress 要求后端 Service 有
ClusterIP，因此不能直接复用，必须新增一个 ClusterIP Service 专供 Ingress。** 上游 Chart 的 `ingress: []`
是 deny-all，因此**默认 NetworkPolicy 会阻断 Tailscale Ingress**；kubelet 对 `127.0.0.1:3080/6080` 的探针
不受 Pod 入站策略影响，仍可正常工作。**实测发现按 `tailscale/ingress-proxies` 标签放行的规则无效**：本集群
Cilium 的 `ipv4NativeRoutingCIDR` 是 `192.168.3.0/24`，跨节点 Pod 流量在目标侧已被 masquerade 成节点 IP，
源身份变成 `world`；namespace/pod selector 与 ipBlock 均匹配不到。结论：保留默认拒绝，但只按**端口**放行
`3080/TCP` 与 `6080/TCP`，其余入站继续拒绝。把源收紧回 ingress proxies 需要先调整 Cilium native routing
覆盖 Pod CIDR（`10.42.0.0/16`），属于独立的集群网络变更，不在本特性内。

noVNC 本身没有认证，但本 tailnet 只有维护者一人使用，且 Ingress 不发布到公网；因此接受「tailnet 内任意设备
可访问桌面」的风险，由 Tailscale ACL 作为唯一网络边界。文档必须明确这一点。为了让 Web UI 里的「浏览器桌面」
入口也能工作，Web Ingress 需要同时把版本化 `/novnc-*` 路径（含其 `websockify` 子路径）路由到 6080，并把
`DSH_DESKTOP_PUBLIC_PORT` 设为 `443`，使前端构造同源 URL 而不是 `host:6080`；另有一条独立主机名的 Ingress
用于直接打开完整桌面。

### 本机 DSH 配置与容器环境的不兼容点

`east4ming/dsh-config` 是**私有仓库**，跟踪 profile、local plugin、local preset 与部分 skills；运行时状态/
凭据被 `.gitignore` 排除。配置同步不再在集群内 clone：先启动 DSH 容器，再由维护者在本机用已认证的 `gh`
拉取私库（或直接选择本机 `/home/casey/.dsh` 的配置），本地完成容器化改写后用 `kubectl cp` 写入 Pod 的
`$DSH_HOME`，最后在容器内执行一次 `pnpm install`。因此集群侧不需要 `DSH_CONFIG_TOKEN` 或任何仓库凭据。
容器与本机（`/home/casey/.dsh`）的差异已逐项核对：

| 项目 | 本机配置现状 | 容器中的差异 | 处理要求 |
| --- | --- | --- | --- |
| 配置来源 | 私有仓库 + 本机 `/home/casey/.dsh` | 集群内不做 Git 认证 | 本机 `gh repo clone` 或直接选本机目录；本地改写后 `kubectl cp`；不需要 `DSH_CONFIG_TOKEN` |
| 本地插件/预设依赖 | `profiles/web/package.json` 使用 `link:/home/casey/.dsh/local-plugins/...`、`link:/home/casey/.dsh/local-presets` | 容器内 DSH home 是 `/home/node/.dsh` | 同步后改写为容器路径或相对路径 |
| 预设组件 | `local-presets/cordis.patch.yml` 用绝对路径引用 `/home/casey/.dsh/local-presets/components/*.mjs` | 同上 | 同步后改写 |
| dcg 守卫 | tool-hooks 直接指向 `/home/casey/.local/share/mise/installs/.../dcg` | 工具改由容器内 mise 安装 | 改写为容器内 shim/路径 |
| StyleFerry 钩子 | post-execute 调用 `/home/casey/projects/StyleFerry/scripts/auto-release-tag.sh` | 容器内没有该仓库 | 禁用该条 post hook，保留 dcg pre hook |
| MCP codegraph | 指向本机 mise 安装的 `codegraph` | 容器内需重新安装 | 改写为容器内 mise shim |
| MCP atuin | 指向 `/home/casey/.atuin/bin/atuin` | 需在容器内提供 atuin | mise registry 同时提供 `aqua:atuinsh/atuin` 与 `cargo:atuin`，**可以安装**；改用 mise 安装并改写路径 |
| 默认模型路由 | `agent-default-model.provider: deepseek-account`（账号授权） | 账号授权保存在 `.credentials.yaml`，未随配置同步；注入的是 API Key | 改为 `deepseek-official`（唯一读取 `DEEPSEEK_API_KEY` 的路由）；两条路由不会互相回退 |
| 市场插件 | profile 依赖并启用 `dshmarket@1.73.17` | 市场镜像已内置 `dshmarket@1.66.9`，且镜像 patch 也会插入 `dsh-market` 行 | 从同步 profile 的 bundle 中移除 `dshmarket`，以市场镜像内置版本为准，避免重复行与版本歧义；在文档记录版本差异 |
| 依赖构建批准 | `pnpm-workspace.yaml` 使用 `allowBuilds`（pnpm 11 语义） | 镜像固定 pnpm 10.15.1；实测 10.15.1 对 `allowBuilds` 打印 "Ignored build scripts"，`onlyBuiltDependencies` 才会执行构建 | 同步时补充 `onlyBuiltDependencies: [node-pty, cloudflared, protobufjs]`，否则原生依赖可能缺失 |
| pnpm 锁文件 | `link:/home/casey/...` 写入 lockfile；`packageManager` 未声明 | 镜像 pnpm 10.15.1 可读 lockfile 9.0，但 link 路径变化后 frozen 安装会失败 | 首次安装允许按改写后的 manifest 更新 profile lockfile；配置源仍以固定 SHA 为准 |
| dsh-pet peer | 配置仓库有兼容脚本，额外固定 `@deepseek-ai/dsh-credentials`、`dsh-home-paths` 0.1.1-rc.2 | 直接安装可能因 peer 解析失败 | 执行等价处理，或验证 dsh-pet 能加载；失败时按插件降级规则处理 |
| GitHub Token | 同步配置的插件里没有 `GITHUB_API_TOKEN` 消费者；它的真正消费者是 mise | mise 的 token 优先级明确包含 `GITHUB_API_TOKEN`（仅次于 `MISE_GITHUB_TOKEN`），用于 GitHub 安装限流 | 直接作为环境变量注入即可，**不要**映射为 `GH_TOKEN`；`gh` 的人机登录由用户后续手动完成，不在本特性范围 |
| 本机绝对路径 | `skills/.skills_store_lock.json` 的 `installDir` 指向 `/home/casey/.dsh/skills/...` | 容器路径不同 | 同步时改写为 `/home/node/.dsh/skills/...` |

### 工具链与 skills

本机 `~/.config/mise/config.toml` 列出的工具远多于本次需求，本次只安装明确要求的集合：

- uv 工具：`specify-cli`、`pre-commit`、`pyrefly`、`yamllint`
- mise 全局工具：`gh`、`jq`、`@colbymchenry/codegraph`（npm）、`yq`、`clawhub`（npm）、
  `yusukebe/ax`、`Dicklesworthstone/destructive_command_guard`、`harehare/mq`、`atuin`
- 不安装本机 config 中的 node/rust/go 等工具；镜像已自带 Node 24。

`~/.agents/skills` 当前约 53MB、73 个目录。DSH 的 skill 发现顺序中，`<agentsHome>/skills` 是用户级根；
容器 `HOME=/workspace`，因此目标路径是 `/workspace/.agents/skills`。homelab2 仓库是 public，skills 内容不应
提交到 Git；同步应是从本机到集群 PVC 的可重复操作，而不是 GitOps 内容。

### 版本与发布

按 `docs/reference/versioning.md`：主题分支 `015-deepseek-harness-helm` → PR → `master`（ArgoCD 自动同步）；
Conventional Commits；合并并通过线上验证后打 annotated tag `vYYYY.MM.DD`（同日第二个快照用 `.2`）；更新
`docs/reference/changelog.md`；在 Gitea（权威）与 GitHub（镜像）各建 Release，并双侧核对 tag。

## 目标与非目标

**目标**：在集群内得到一个可重复部署、可升级、可回滚的单用户 DSH 实例；四类状态分别落在四块 RWO PVC 上；
Tailscale 网络可访问 Web UI 与 noVNC 桌面；本机 DSH 配置、插件、工具和 skills 在容器内可用且重启不丢；密钥
不进入 Git。

**非目标**：多副本/多租户高可用；公网暴露；给 noVNC 增加认证（接受 tailnet 内无认证，见风险）；自动配置
VolSync/备份策略（四块 PVC 必须列为备份对象，备份由用户后续手动完成）；在集群内重建本机全部开发工具链；
修改上游 DSH 源码；把本机 `~/.agents/skills` 提交到 public 仓库。

## User Scenarios & Testing

### User Story 1 - 从 tailnet 访问 DSH Web 与 noVNC 桌面（Priority: P1）

作为 homelab2 的维护者，我希望在任意加入 tailnet 的设备上打开 DSH Web 并完成一次模型对话，也能直接打开
容器内的 noVNC 桌面；不依赖 `kubectl port-forward`，也不把服务暴露到公网。

**Why this priority**: 这是实例可用的最低标准；NetworkPolicy 与 Ingress 的交互是本需求最容易出错的部分。

**Independent Test**: 从非 `tailscale` 命名空间的 Pod 访问 DSH Pod 的 9222 被拒绝，访问 3080 得到 401、
访问 6080 得到 200（Cilium SNAT 使源选择器失效，策略只按端口放行）；在 tailnet 内用浏览器打开
`https://dsh.west-beta.ts.net`，未带 token 时返回 401，从 Pod 日志取得一次性 token 后能加载 UI 并完成一次
模型对话；打开 `https://dsh-desktop.west-beta.ts.net` 可进入 noVNC 桌面；Web UI 内的「浏览器桌面」入口也能
打开同一桌面。

**Acceptance Scenarios**:

1. **Given** 应用已同步且 Pod Ready，**When** 从非 `tailscale` 命名空间的 Pod 访问 DSH Pod IP:9222，
   **Then** 连接被 NetworkPolicy 拒绝；访问 3080 得到 401、访问 6080 得到 200（源选择器受 Cilium SNAT
   限制，策略只按端口放行）。
2. **Given** 同上，**When** 从 tailnet 浏览器访问 Web Ingress 主机名，**Then** Ingress 经
   `ingress-proxies` 到达 DSH，未认证请求返回 401。
3. **Given** 运维者从 Pod 日志取得带 token 的启动 URL，**When** 打开该 URL，**Then** token 换取 Cookie 并进入
   UI，模型调用使用注入的 API Key 成功完成，无需交互登录。
4. **Given** tailnet 设备，**When** 打开桌面 Ingress 主机名，**Then** 无认证进入 noVNC 桌面；从 Web UI 的
   「浏览器桌面」入口打开时，也进入同一桌面（同源 `/novnc-*` 路径）。
5. **Given** 公网设备或非 tailnet 设备，**When** 尝试访问两条 Ingress，**Then** 不可达。

---

### User Story 2 - 四块状态卷在重启、重装后仍然保留（Priority: P1）

作为维护者，我希望 DSH 配置与会话、工作区文件、工具链安装结果、skills 各自持久化，Pod 重建或 Helm 重装后
不需要重新初始化。

**Why this priority**: 容器根文件系统只读，且镜像重建频繁；没有持久化就没有可用的长期实例。

**Independent Test**: 分别在四块 PVC 写入标记文件，删除 Pod、卸载并重装应用，标记文件仍在，且 DSH 会话与
工具命令仍可用。

**Acceptance Scenarios**:

1. **Given** 首次安装完成，**When** 查看 PVC，**Then** `/home/node/.dsh` 为 10Gi、`/workspace` 为 20Gi、
   工具卷为 20Gi、skills 卷为 1Gi，均为 RWO 且 Bound。
2. **Given** 已写入标记文件，**When** 删除 Pod 让其重建，**Then** 标记文件仍在，DSH 仍能启动。
3. **Given** 已写入标记文件，**When** 卸载 Helm release 后重装，**Then** 四块 PVC 未被删除，标记文件仍在。
4. **Given** 工具卷已初始化，**When** Pod 重启，**Then** uv/mise 及其工具无需重新下载即可执行。

---

### User Story 3 - 本机 DSH 配置与插件在容器内可用（Priority: P1）

作为 DSH 用户，我希望容器里的 profile、插件、预设、技能与我在本机使用的保持一致；与容器不兼容的绝对路径、
认证路由和构建批准被显式修正，而不是静默失效。

**Why this priority**: 没有配置同步，这个实例只是一个空白 DSH，无法承载我的实际工作流。

**Independent Test**: 在 Pod 运行后执行一次同步脚本（本机 `gh` 或 `/home/casey/.dsh` + `kubectl cp`），
Pod 内 `$DSH_HOME` 出现同步来源标记；profile 中列出的插件全部出现在插件列表且启动日志没有加载错误；市场
页面存在；`deepseek-flash` 对话可用。

**Acceptance Scenarios**:

1. **Given** DSH Pod 已运行，且本机有可用的 `gh` 认证或 `~/.dsh` 配置源，**When** 执行一次性同步脚本，
   **Then** `profiles/web`、`profiles/headless`、`local-plugins`、`local-presets`、`skills` 等配置已落到
   `$DSH_HOME`，且 `/home/casey/...` 绝对路径已不存在；集群内没有配置仓库凭据。
2. **Given** 配置中包含 `@local/dsh-tool-hooks`，**When** Agent 执行一次破坏性 bash 命令，**Then** dcg 守卫
   能拦截或拒绝；StyleFerry 的 post hook 因目标仓库不存在而被禁用，不产生每次工具调用的失败日志。
3. **Given** 插件清单包含第三方插件，**When** 同步脚本完成 `pnpm install` 并重启 Pod，**Then** 插件均安装
   成功；确实无法在容器运行的插件被显式禁用并在文档中记录原因，其余插件不受影响。
4. **Given** 市场变体镜像，**When** 打开插件市场，**Then** 市场 UI 可用且不出现重复 `dsh-market` 行。
5. **Given** 本机配置发生变化，**When** 重新执行同步脚本，**Then** 新配置覆盖旧配置，会话/凭据等运行时
   状态未被清空；同步来源与时间可在 Pod 内审计。

---

### User Story 4 - 工具链随 PVC 持久化，并可被 Agent 调用（Priority: P1）

作为 DSH Agent，我希望在容器 shell 中直接使用 uv、mise 以及它们安装的 CLI，重启后仍然存在。

**Why this priority**: 配置中的 MCP 与工具钩子依赖 codegraph、atuin、dcg 等二进制；工具丢失会让插件降级。

**Independent Test**: 在 DSH 的 bash 工具中运行 `uv tool list`、`mise ls --global`、`atuin --version`、
`codegraph --version`、`dcg --version`、`gh --version` 等，全部成功；删除 Pod 后再次执行仍成功。

**Acceptance Scenarios**:

1. **Given** 首次手动安装完成，**When** 检查工具，**Then** 四个 uv 工具与九个 mise 工具都已安装，`atuin` 也由
   mise 安装。
2. **Given** 工具已安装，**When** 通过 DSH bash 工具执行命令，**Then** PATH 包含工具 bin 与 mise shims，
   Agent 无需绝对路径即可调用。
3. **Given** 工具卷已填充且网络不可用，**When** Pod 重启，**Then** 已有工具仍可执行；安装器不应重复下载。
4. **Given** 工具安装脚本失败，**When** 查看脚本输出，**Then** 非零退出并指出失败项；Pod 仍可运行，但工具
   不完整，重跑脚本应能收敛。

---

### User Story 5 - skills 与本机同步并持久化（Priority: P2）

作为 DSH 用户，我希望容器内的 skill 目录包含本机 `~/.agents/skills` 的内容，并在 Pod 重建后保留。

**Why this priority**: skills 是可选的个人能力；但配置中若引用了它们，缺失会导致任务不可用。

**Independent Test**: 本机新增一个测试 skill 后执行同步命令，DSH 技能目录中出现该 skill；重启 Pod 后仍在。

**Acceptance Scenarios**:

1. **Given** 本机 skills 目录，**When** 执行文档中的同步命令，**Then** 容器 `/workspace/.agents/skills` 包含
   本机同名目录，DSH 能发现新增 skill。
2. **Given** skills 已同步，**When** Pod 重建，**Then** skills 仍在 1Gi PVC 上。
3. **Given** homelab2 是 public 仓库，**When** 检查 Git 历史，**Then** 不包含 skills 内容与其可能附带的私有材料。

---

### User Story 6 - 密钥从本机环境注入且不泄露（Priority: P2）

作为维护者，我希望用本机环境变量创建 `dsh-provider-credentials`，Chart 只引用 Secret 名；仓库中没有任何真实密钥。

**Why this priority**: 仓库是 public；一次误提交就是永久泄露。

**Independent Test**: 从干净 checkout 执行部署脚本，Secret 中至少存在两个 provider 键；`git grep` 找不到密钥值；
Pod 环境变量来自 Secret。

**Acceptance Scenarios**:

1. **Given** 本机环境变量已设置，**When** 执行 bootstrap，**Then** 创建/更新 Secret
   `dsh-provider-credentials`，包含 `DEEPSEEK_API_KEY`、`GITHUB_API_TOKEN`，且 values 中
   `credentials.existingSecret` 指向它。
2. **Given** 环境变量缺失或为空，**When** 执行 bootstrap，**Then** 脚本失败并给出明确提示，不创建空 Secret。
3. **Given** 应用运行，**When** 查看 Pod 环境变量，**Then** 两个键来自 Secret；`GITHUB_API_TOKEN` 可被 mise
   直接读取用于 GitHub 安装限流；不存在为 `gh` 额外注入的 `GH_TOKEN`，`gh` 登录由用户后续手动完成。
4. **Given** 仓库内容，**When** 搜索密钥形态，**Then** 只有占位符与文档命令，没有真实值。

---

### User Story 7 - 按仓库版本规范发布（Priority: P2）

作为仓库维护者，我希望这次变更走完整的分支、PR、标签、Changelog 与双远端 Release 流程，便于回滚。

**Why this priority**: 本仓库以标签定位已知良好状态；不发布就无法回溯。

**Independent Test**: `git ls-remote --tags` 在两个远端都能看到新 tag；Gitea 与 GitHub 都有对应 Release；
Changelog 有条目；ArgoCD 应用为 Synced/Healthy。

**Acceptance Scenarios**:

1. **Given** 实现完成并已合并，**When** 打 annotated tag 并推送，**Then** Gitea 与 GitHub 的 tag 都存在且指向
   同一提交。
2. **Given** 标签已推送，**When** 创建 Release，**Then** 两侧标题/正文与 Changelog 条目一致，Gitea 为权威、
   GitHub 为镜像。
3. **Given** 发布完成，**When** 查看 ArgoCD，**Then** `deepseek-harness` 应用 Synced/Healthy，PVC 与 Ingress 就绪。

### Edge Cases

- **上游 Chart 升级**：上游新增/修改 StatefulSet、NetworkPolicy 或 env 时，本地副本会漂移；必须有明确的升级
  检查清单与 diff 记录，不能直接覆盖本地新增的卷、Ingress 与放行规则。
- **Cilium SNAT 使源选择器失效**：`ipv4NativeRoutingCIDR=192.168.3.0/24` 会把跨节点 Pod 流量 masquerade
  成节点 IP，源身份变成 `world`；按 `tailscale/ingress-proxies` 标签或 ipBlock 放行都匹配不到。当前策略
  只按端口放行；若要收紧源，需要先调整 Cilium native routing 覆盖 Pod CIDR，这是独立集群变更。
- **Secret 不存在**：Pod 会停在 CreateContainerConfigError；部署顺序必须先建 Secret，ArgoCD 重试后才可用。
- **配置同步是手动任务**：本机 `gh` 未登录、选择的源目录缺文件、`kubectl cp` 中断或 `pnpm install` 失败时，
  同步脚本必须明确报错；Pod 上的旧配置可能处于部分更新状态，重跑脚本应可收敛；同步后需重启 Pod 才保证
  DSH 以新 profile 启动。
- **工具安装是手动任务**：工具卷为空或重建后，必须重新执行一次性安装脚本；未执行时 DSH 仍可启动，但
  codegraph/atuin/dcg 等工具不可用，插件按降级规则处理。
- **插件无法加载**：单个第三方插件（如依赖 Electron/外部服务）失败不应拖垮整个 profile；必须显式禁用并记录。
- **10Gi DSH home 增长**：profile `node_modules`、会话、缓存共用 10Gi；需要监控并在文档给出扩容方式。
- **RWO 卷与节点**：StatefulSet 单副本，PVC 与节点绑定；节点不可用时 Pod 可能无法调度，需接受这一限制。
- **市场镜像版本**：镜像内置 `dshmarket` 版本低于本机配置；升级镜像 tag 时才提升，不能靠 profile 覆盖。
- **无 token 访问**：Web Ingress 上直接访问根路径返回 401 是预期行为，不应被误判为故障；桌面 Ingress 与
  `/novnc-*` 路径则按设计无认证。
- **`GITHUB_API_TOKEN` 用途**：它只用于 mise 的 GitHub 安装限流；`gh` 不会因此自动登录，需要用户后续手动
  `gh auth login`，这属于预期状态而不是故障。
- **桌面暴露面**：noVNC 无认证且可执行浏览器操作；任何 tailnet 设备都能访问。若 tailnet 成员或 ACL 发生变化，
  必须重新评估是否继续暴露。

## Requirements

### Functional Requirements

- **FR-001**: 交付必须作为 `apps/deepseek-harness` 应用目录被现有 ArgoCD ApplicationSet 自动发现，部署到
  `deepseek-harness` 命名空间；不得修改 ApplicationSet 的通用规则来为单个应用开后门。
- **FR-002**: 镜像必须显式固定为 `docker.io/runzhliu/deepseek-harness:0.2.2-rc.1-r1-market.1`（市场变体），
  不得依赖 `latest` 或 Chart 默认 tag。
- **FR-003**: 交付层必须保留上游 Chart 的单副本 StatefulSet、Headless Service、只读根文件系统、非 root
  安全上下文、探针、`dsh-home` PVC 保留策略等行为；相对上游的每处差异必须可审计、可说明。
- **FR-004**: Chart values 必须设置 `credentials.existingSecret=dsh-provider-credentials`，容器环境变量由该
  Secret 提供。
- **FR-005**: 部署流程必须提供幂等 bootstrap：从当前机器环境变量读取 `DEEPSEEK_API_KEY` 与
  `GITHUB_API_TOKEN`，校验非空后创建/更新同命名空间 Secret；真实值不得出现在仓库、日志或命令回显中。
- **FR-006**: DSH home 必须使用 10Gi、`ReadWriteOnce` 的持久卷，挂载到 `/home/node/.dsh`。
- **FR-007**: 工作区必须使用 20Gi、`ReadWriteOnce` 的持久卷，通过 `workspace.existingClaim` 挂载到
  `/workspace`；目标 PVC 可由本应用创建或预先存在，但名称必须在 values 中显式声明。
- **FR-008**: 工具链必须使用独立的 20Gi、`ReadWriteOnce` 持久卷，并保证 uv、mise 的二进制、数据、配置、
  shim、缓存与全局工具都位于该卷，而非 `/tmp` 或容器根文件系统。
- **FR-009**: skills 必须使用独立的 1Gi、`ReadWriteOnce` 持久卷，挂载到 `/workspace/.agents/skills`，并显式
  设置 agents home，使 DSH 能发现该目录下的 skills。
- **FR-010**: 四块 PVC 必须在 Pod 删除、Helm 卸载与 ArgoCD prune 后保留；不得因重新同步或升级被删除或重建。
- **FR-011**: 必须提供 Web Tailscale Ingress：`ingressClassName: tailscale`、
  `tailscale.com/proxy-group: ingress-proxies`、主机名 `dsh.west-beta.ts.net`、TLS 由 Tailscale 提供；
  `/` 后端指向 DSH 的 3080，版本化 `/novnc-*` 路径（含 `websockify`）后端指向 6080，并把
  `DSH_DESKTOP_PUBLIC_PORT` 设为 `443`，使 Web UI 内的桌面入口构造同源 URL。
- **FR-012**: 必须保留 NetworkPolicy 的默认拒绝语义，只放行 3080/TCP 与 6080/TCP 的入站流量，其余端口继续
  拒绝。源限制（仅 `tailscale/ingress-proxies`）在本集群受 Cilium `ipv4NativeRoutingCIDR=192.168.3.0/24`
  的 SNAT 影响无法生效；必须把这一限制与后续「调整 Cilium native routing 覆盖 Pod CIDR 再收紧」的记录写进
  文档，不能静默假装源选择器有效。
- **FR-013**: 必须另建一条 Tailscale Ingress（`dsh-desktop.west-beta.ts.net`）直接把 6080/noVNC 暴露给
  tailnet，用于直接打开完整桌面；不存在公网入口。该桌面无认证是显式接受的设计，不是遗漏；文档必须写明
  tailnet ACL 是唯一访问边界。
- **FR-014**: 通过 Ingress 访问时，DSH 的启动 token/Cookie 流程必须可用：未认证请求返回 401，携带 Pod 日志中的
  一次性 token 可换取 Cookie 并加载 UI；WebSocket/流式响应必须可穿过 Tailscale 代理，且 Ingress 主机名必须
  通过 `--trusted-host` 加入 DSH 的 Host/Origin 信任列表（否则 `/api` WebSocket 返回 403，UI 显示“重新连接中”）。
- **FR-015**: 必须提供**一次性手动同步流程**：先启动 DSH 容器，再由维护者在本机用已认证的 `gh` 拉取私有
  `east4ming/dsh-config`（或直接选择本机 `/home/casey/.dsh` 的配置），本地完成容器化改写后通过 `kubectl cp`
  写入 `$DSH_HOME`，并在容器内执行 `pnpm install`。集群内不得需要 `DSH_CONFIG_TOKEN` 或任何仓库凭据；同步
  不得删除 `sessions/`、`storages/`、`.credentials.yaml` 等运行时数据。
- **FR-016**: 同步必须处理已确认的容器不兼容点：绝对路径改写、provider 改为 API Key 路由、
  `dshmarket` 去重、StyleFerry 钩子禁用、pnpm 10 的构建批准、dsh-pet peer 兼容、skill lock 路径改写。
- **FR-017**: 同步后的 web/headless profile 中列出的 DSH 插件必须完成安装并可被 DSH 加载；确实无法在容器运行
  的插件必须显式禁用并在文档记录原因与影响，不能让单个插件失败导致整个 profile 无法启动。
- **FR-018**: 市场变体必须可用：插件市场页面能打开，且不出现重复的市场配置行；镜像内置的 dshmarket 版本与
  本机配置版本的差异必须记录在文档中。
- **FR-019**: 必须提供**一次性手动安装流程**，在容器内把 uv/mise 及工具安装到持久化的工具卷，并通过它们安装
  `specify-cli`、`pre-commit`、`pyrefly`、`yamllint`（uv）以及
  `gh`、`jq`、`@colbymchenry/codegraph`、`yq`、`clawhub`、`yusukebe/ax`、
  `Dicklesworthstone/destructive_command_guard`、`harehare/mq`、`atuin`（mise）；工具卷重建后重跑同一流程。
- **FR-020**: `atuin` 必须通过 mise 安装（registry 已提供 `aqua:atuinsh/atuin` 与 `cargo:atuin`）；本机配置中的
  MCP 路径必须改写为容器内可执行路径。若 `atuin mcp` 在容器内不可用，可禁用该 MCP 行，但 CLI 本身必须可用。
- **FR-021**: 工具 bin 目录与 mise shims 必须进入 DSH 进程及其子进程的 PATH，使 Agent 的 bash 工具能直接调用
  这些命令。
- **FR-022**: 必须提供从本机 `/home/casey/.agents/skills` 到 skills PVC 的可重复同步方式；同步后的内容在 Pod
  重建后保留；skills 内容不得提交到本 public 仓库。
- **FR-023**: 默认模型必须使用 `deepseek-official` 路由与 `DEEPSEEK_API_KEY`，在无交互登录的情况下完成一次
  模型调用；不得依赖未同步的 `deepseek-account` 账号授权。
- **FR-024**: `GITHUB_API_TOKEN` 必须作为环境变量暴露给 DSH 进程；mise 会原生读取它用于 GitHub 安装限流
  （token 优先级中位于 `MISE_GITHUB_TOKEN` 之后），不得改名为 `GH_TOKEN`，也不得为 `gh` 额外注入认证变量；
  `gh` 登录由用户后续手动完成，文档只需说明该变量用途。
- **FR-025**: 配置同步完成后必须重启 Pod（或明确验证 HMR 已加载新配置）才视为生效；工具安装不要求重启，
  但工具卷重建后必须重跑；镜像 tag 变化时 Pod 模板必须变化以触发滚动重启。
- **FR-026**: 必须提供运维文档，覆盖：首次部署顺序（Secret → 启动 → 工具安装 → 配置同步 → 重启）、
  本机 `gh`/`~/.dsh` 两种配置来源、`kubectl cp` 同步命令、Web Ingress 与 401/token 使用、noVNC 桌面入口与
  无认证风险、skills 同步、工具清单、PVC 容量与手动备份、回滚边界、已知不兼容与禁用项。
- **FR-027**: 必须按 `docs/reference/versioning.md` 完成主题分支、Conventional Commits、PR、annotated tag、
  `docs/reference/changelog.md` 条目，以及 Gitea 与 GitHub 双远端 Release；两侧 tag 必须指向同一提交。
- **FR-028**: 必须提供可回滚路径：上一个 tag 可用于 ArgoCD Sync；回滚不得删除或重建四块 PVC；文档必须说明
  镜像降级时 DSH 数据卷的兼容边界。
- **FR-029**: 四块 PVC 必须作为备份对象记录在运维文档中；**不得**在 `scripts/backup-coverage` 的
  `is_exempt()` 中为它们添加豁免。备份配置由用户后续手动完成，本特性只保证 PVC 名称/容量/保留策略可被备份
  工具识别。

### Key Entities

- **DSH home PVC**：10Gi RWO，保存 profiles、node_modules、settings、sessions、storages 与凭据。
- **Workspace PVC**：20Gi RWO，保存 Agent 工作文件；通过 `workspace.existingClaim` 挂载。
- **Tools PVC**：20Gi RWO，保存 uv/mise 及所有全局工具、shim、缓存与配置。
- **Skills PVC**：1Gi RWO，保存从本机同步的 `~/.agents/skills` 内容。
- **Provider credentials Secret**：`dsh-provider-credentials`，至少包含 `DEEPSEEK_API_KEY` 与
  `GITHUB_API_TOKEN`；Chart 仅引用其名称。集群内不需要私有 dsh-config 的凭据。
- **Config sync source**：本机 `gh` 拉取的私有仓库目录，或本机 `/home/casey/.dsh` 中选定的配置；只在维护者
  本机存在，不进集群 Secret。
- **Manual sync marker**：Pod 内 `$DSH_HOME/.dsh-config-source`，记录同步来源与时间，供审计；不参与自动
  滚动。
- **Web Tailscale Ingress**：`dsh.west-beta.ts.net`，`/` → 3080，`/novnc-*` → 6080，经共享 ingress proxies。
- **Desktop Tailscale Ingress**：`dsh-desktop.west-beta.ts.net` → 6080，仅 tailnet 可达，无认证。
- **Backup targets**：四块 PVC 全部是后续手动备份对象；不得在 `scripts/backup-coverage` 中豁免。
- **Config revision**：dsh-config 的固定提交 SHA；写入 values 并反映到 Pod 模板注解。
- **Release tag**：CalVer 快照，关联 Changelog 与双远端 Release。

## Success Criteria

### Measurable Outcomes

- **SC-001**: 从 tailnet 设备打开 `https://dsh.west-beta.ts.net`，未认证时 100% 返回 401；使用 Pod 日志中的
  token 后 2 分钟内进入 UI。
- **SC-002**: 四块 PVC 全部 Bound，容量分别为 10Gi/20Gi/20Gi/1Gi，访问模式均为 RWO；在写入标记文件后删除
  Pod、卸载并重装应用，四份标记文件 100% 仍存在。
- **SC-003**: Pod 重启后，`uv tool list` 列出 4 个工具，`mise ls --global` 列出 9 个工具（含 atuin），
  `atuin --version`、`codegraph --version`、`dcg --version`、`gh --version` 均成功，且无需重新下载。
- **SC-004**: 执行一次性配置同步后，profile 中列出的插件全部安装；DSH 启动日志无插件加载错误；市场页面可
  打开且无重复市场行。
- **SC-005**: 在 UI 中发起一次 `deepseek-flash` 对话并成功返回，不出现登录提示；证明 API Key 路由生效。
- **SC-006**: 从非 `tailscale` 命名空间 Pod 到 DSH Pod:9222 的连接被拒绝；3080 返回 401、6080 返回 200
  （策略只按端口放行，源选择器受 Cilium SNAT 限制）；从 tailnet 访问 3080/6080 都成功。
- **SC-007**: `git` 历史与工作区中不存在真实 `DEEPSEEK_API_KEY`/`GITHUB_API_TOKEN` 值，也不存在私有
  dsh-config 的凭据；Pod 内两个变量存在且来自 Secret。
- **SC-008**: 发布后，Gitea 与 GitHub 均存在同一 tag 与 Release；Changelog 有条目；ArgoCD
  `deepseek-harness` 为 Synced/Healthy。
- **SC-009**: 在 Pod 运行后执行一次本机同步脚本（`gh` 或 `/home/casey/.dsh` 来源）即可把配置写入
  `$DSH_HOME`，`$DSH_HOME/.dsh-config-source` 记录来源/时间；集群内没有配置仓库凭据。
- **SC-010**: 从 tailnet 打开桌面 Ingress 主机名可进入 noVNC；从 Web UI 的「浏览器桌面」入口也能进入同一
  桌面；非 tailnet 设备不可达。
- **SC-011**: 四块 PVC 未被 `scripts/backup-coverage` 豁免；文档列出四块 PVC 作为后续手动备份对象。

## Assumptions

- Ingress 主机名采用仓库既有命名习惯：Web `dsh.west-beta.ts.net`，桌面 `dsh-desktop.west-beta.ts.net`；
  如需改名，只改 values/文档，不影响架构。
- noVNC 无认证是显式接受的设计：tailnet 只有维护者一人使用，且不发布到公网；Tailscale ACL 是唯一访问边界。
  若 tailnet 扩展给他人使用，需要重新评估（加认证或停止暴露）。
- 工作区 PVC 由本应用创建并命名为 `deepseek-harness-workspace`（20Gi RWO），再通过
  `workspace.existingClaim` 引用；若维护者已有 PVC，可在 values 中替换名称。
- 配置同步是一次性手动任务：维护者在本机用已认证的 `gh` 拉取私有 dsh-config，或直接选择本机
  `/home/casey/.dsh` 的配置；本地改写后用 `kubectl cp` 写入 Pod。同步来源与时间写入
  `$DSH_HOME/.dsh-config-source` 供审计，不要求 values 固定 SHA。
- 集群内不需要私有 dsh-config 的凭据；本机 `gh` 的登录状态就是私有仓库的访问凭据，不进入集群 Secret。
- 四块 PVC 是后续手动备份对象；本特性不配置 VolSync/备份策略，也不修改 `scripts/backup-coverage` 的豁免表。
- 工具安装是一次性手动任务：首次部署或工具卷重建后运行安装脚本；未运行时 DSH 仍可启动，但相关工具缺失。
- 默认使用 API Key 路由 `deepseek-official`；不把本机 `.credentials.yaml` 账号授权搬到集群。若用户希望账号
  登录，可在 Web 内登录并由 10Gi home 持久化，但这不作为默认验收路径。
- 市场镜像内置 `dshmarket@1.66.9`，本机配置为 `1.73.17`；以镜像内置版本为准，避免重复配置行；升级镜像时
  再统一版本。
- `GITHUB_API_TOKEN` 只用于 mise 的 GitHub 安装限流；mise 原生识别该变量。`gh` 需要用户后续手动登录，
  本特性不注入 `GH_TOKEN`。
- skills 同步是本机 → 集群 PVC 的一次性/可重复操作，不是 GitOps 内容；原因是 homelab2 public 且 skills 体积
  约 53MB、可能含私有材料。
- 工具版本沿用 mise/uv 的默认解析（通常为最新稳定版），首次安装后记录实际版本；不额外引入版本锁定机制。
- 集群具备访问 Docker Hub、npm、GitHub 与 PyPI 的出站能力；首次启动与手动安装需要网络，之后依赖 PVC 缓存。
- 单副本是上游 Chart 的明确设计；本特性不尝试扩容或高可用。
- 默认 StorageClass `standard-rwo` 可用；不新引入存储类。

## 依赖、风险与边界

- **依赖**：Tailscale Operator（已存在 `ingress-proxies`）、Cilium NetworkPolicy 执行、ArgoCD ApplicationSet、
  `standard-rwo` StorageClass、Docker Hub 镜像、本机 `gh` 登录状态、本机环境变量与 skills 目录。
- **风险**：上游 Chart 无 Helm 仓库，vendored 副本需要人工跟进；手动同步/安装依赖维护者本机环境，可能漏跑或
  漂移；pnpm 10 与配置的 pnpm 11 语义差异可能继续出现；第三方插件在无桌面/无外部服务的容器中可能部分失效；
  10Gi home 可能被 node_modules 与会话占满；Headless Service 与两条 Tailscale Ingress 的组合需要在验收中实测；
  noVNC 无认证，任何 tailnet 设备都可操作浏览器，Tailscale ACL 配置错误会直接扩大暴露面；NetworkPolicy 只能
  按端口放行，集群内任意 Pod 都可访问 3080/6080，收紧源需要先修正 Cilium native routing。
- **边界**：公网不可达；不实现多用户；不修改 DSH 源码；不把 skills 或密钥提交到本仓库；noVNC 仅在 tailnet
  内暴露；备份由用户后续手动配置，本特性只保证 PVC 可被识别。
