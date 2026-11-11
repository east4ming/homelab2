# Phase 0 研究：以 Helm Chart 安装 DeepSeek Harness

**Date**: 2026-11-11 | **Spec**: [spec.md](spec.md) | **上游 Chart 基线**: `runzhliu/deepseek-harness-docker@04371405`（Chart 0.1.29，appVersion 0.2.2-rc.1）

## 结论摘要

- **上游 Chart 不能原样使用**：没有 Ingress、没有额外卷；且其唯一 Service 是 Headless，Tailscale Operator 的
  L7 Ingress 明确要求后端 Service 有 ClusterIP，因此必须新增一个 ClusterIP Service 专供 Tailscale 使用。
- **Chart 交付形态**：把上游 Chart 的模板 vendored 到 `apps/deepseek-harness/`，形成一个扁平的、可审计的
  Chart（不再套 subchart），保留上游 values 名称与安全上下文，新增工具卷、skills 卷、工作区 PVC、两条
  Ingress、NetworkPolicy 放行规则、资源 limits。
- **不使用 initContainer**：Pod 直接启动 DSH；工具安装、配置同步、skills 同步都是维护者在容器启动后通过
  `kubectl exec` / `kubectl cp` 执行的一次性任务。结果落在 PVC 上，Pod 重启后仍保留。
- **配置同步不需要集群凭据**：本机用已认证的 `gh` 拉取私有 dsh-config，或直接选择本机 `/home/casey/.dsh`
  的配置；本地完成容器化改写后 `kubectl cp` 到 Pod，再在容器内 `pnpm install`。集群侧没有
  `DSH_CONFIG_TOKEN`。
- **容器化改写**：绝对路径、provider 路由、市场插件去重、StyleFerry 钩子、pnpm 10 构建批准、skill lock 路径。
- **工具持久化**：覆盖镜像里指向 `/tmp` 的 `XDG_*`，把 uv/mise 的数据、配置、shim、缓存与二进制全部放到
  20Gi 工具卷；`GITHUB_API_TOKEN` 由 mise 原生读取。
- **noVNC**：新增 ClusterIP Service + 两条 Tailscale Ingress；Web Ingress 同时把版本化 `/novnc-*` 路径
  路由到 6080，并把 `DSH_DESKTOP_PUBLIC_PORT` 设为 443，保证 Web UI 内的桌面入口也能工作。
- **备份**：四块 PVC 都是备份对象，由用户后续手动配置；不修改 `scripts/backup-coverage` 的豁免表。
- **安全取舍**：noVNC 无认证是显式接受的设计；仅 tailnet 可达，Tailscale ACL 是唯一边界。

## Decision 1：Chart 交付形态

**Decision**：在 `apps/deepseek-harness/` 下放一份扁平的 Chart，直接复制并修改上游
`charts/deepseek-harness` 的模板；`Chart.yaml` 的 `version` 用 `0.1.29-homelab.1`，`appVersion` 保持
`0.2.2-rc.1`，并用 annotations 记录上游仓库与 commit `04371405`。

**Rationale**：

- 上游没有 Helm 仓库，只有 Git 目录；ArgoCD 的 `apps/*` 发现机制要求每个应用目录含 `Chart.yaml` +
  `values.yaml`。
- 扁平 Chart 让 values 与上游完全同名（`image`、`persistence`、`workspace`、`networkPolicy`），
  用户熟悉的 `--set image.tag=...` 仍然有效；若用 subchart，所有值要加一层 `deepseek-harness:`，
  且新增卷/Ingress 仍要改 subchart，收益为零。
- 本仓库已有 vendored chart 先例（`apps/acme-ewhisper/charts/app-template-5.3.0.tgz`）；此处只是
  把“依赖 chart”换成“可读的源码副本”，便于审阅每一处差异。

**Alternatives considered**：

- 依赖 `file://charts/deepseek-harness` 的 subchart：需要额外目录和双层 values，且仍要修改 subchart。
- 用 `helm --post-renderer` / Kustomize patch：ArgoCD ApplicationSet 未配置 post-renderer，增加一条
  非标准部署路径。
- 直接用上游 Chart + 独立 manifests：无法给 StatefulSet 加 volumeMounts，也绕开了 ArgoCD 的单目录契约。

**差异清单（对上游）**：新增 `pvc-workspace.yaml`、`pvc-tools.yaml`、`pvc-skills.yaml`、
`service-tailscale.yaml`、`ingress-web.yaml`、`ingress-desktop.yaml`；修改 `statefulset.yaml`
（卷、env、resources）、`networkpolicy.yaml`（放行值由 values 提供）、`values.yaml`、
`values.schema.json`、`NOTES.txt`。上游的探针、UID/GID、只读根文件系统、drop ALL、`dsh-home` 保留策略不变。

## Decision 2：Tailscale Ingress 需要额外的 ClusterIP Service

**Decision**：保留上游 Headless Service 作为 StatefulSet 的 `serviceName`；新增
`<fullname>-tailscale` ClusterIP Service（端口 `http` 3080、`desktop` 6080），两条 Ingress 都指向它。

**Rationale**：

- 上游 Service 是 `clusterIP: None`。Tailscale Operator 的 L7 Ingress 在解析后端时读取 Service 的
  `ClusterIP`，Headless Service 没有 ClusterIP，会被判定为 `InvalidIngressBackend`，Ingress 不会工作。
  证据：`cmd/k8s-operator/ingress.go` 的 `addIngressBackend` 在校验 `svc.Spec.ClusterIP` 为空时直接
  报错；这不是靠 values 能绕过的。
- 新增一个 ClusterIP Service 只增加一个对象，不改变 StatefulSet 的稳定网络标识；Tailscale 代理访问
  ClusterIP，再由 kube-proxy 转发到唯一 Pod。
- Tailscale L7 Ingress 只支持 `Prefix` 路径类型；本方案只用 Prefix，符合限制。

**Alternatives considered**：

- 把上游 Service 改成 ClusterIP：会破坏 StatefulSet 的 headless `serviceName` 语义，且偏离上游。
- 用 Layer 3 Service（`type: LoadBalancer` + `ingressClassName: tailscale`）暴露 3080/6080：需要两个
  独立 tailnet 设备与端口，不能复用现有 HTTP Ingress/HTTPS 证书，且无法在同一个 443 下做路径分流。
- 用 `kubectl port-forward`：不满足“从 tailnet 直接访问”的需求。

## Decision 3：两条 Ingress 与 noVNC 路径

**Decision**：

- Web Ingress（`deepseek-harness`，host `dsh.west-beta.ts.net`）：
  - `/` → ClusterIP Service 的 `http`（3080）
  - `/novnc-` → 同一 Service 的 `desktop`（6080），覆盖 noVNC 的版本化资源与 `websockify` 子路径
- Desktop Ingress（`deepseek-harness-desktop`，host `dsh-desktop.west-beta.ts.net`）：
  - `/` → `desktop`（6080）
- 容器 env `DSH_DESKTOP_PUBLIC_PORT=443`（新增 `desktop.publicPort`），使 Web UI 的
  `desktopUrl()` 生成 `https://dsh.west-beta.ts.net/novnc-...`，而不是 `host:6080`。

**Rationale**：

- 上游 `dsh-browser-desktop` 的 `desktopUrl(port, path)` 以 `window.location` 为基准，只改端口；
  如果只加一条 6080 的独立主机名，Web UI 的“浏览器桌面”按钮仍会指向 Web 主机的 6080 端口，无法打开。
- 把 `/novnc-*` 放到 Web Ingress 的同一 host 下，浏览器同源、同证书、同 tailnet 设备；`websockify`
  也落在同一前缀下。Tailscale L7 Ingress 支持多个 Prefix 后端（`ingress.go` 对 `rule.HTTP.Paths`
  逐项调用 `addIngressBackend`），因此一个 Ingress 两个后端可行。
- 独立 Desktop Ingress 仍然保留，满足“直接打开完整桌面”的入口，也便于排障。

**Alternatives considered**：

- 只加独立 Desktop Ingress：实现最简单，但 Web UI 内的桌面按钮失效；不满足用户实际使用路径。
- 给 noVNC 加认证：上游 noVNC 无认证；在反向代理前加 Basic Auth 需要额外组件（Caddy/oauth2-proxy），
  用户明确接受“仅 tailnet 无认证”，不引入新组件。
- 把整个 Web 也改成 6080：不可行，DSH Web 固定 3080。

**风险/兜底**：若 Tailscale Operator 版本对多后端 Ingress 的行为不符预期，保留独立 Desktop Ingress
作为必达路径；Web UI 的桌面按钮降级为文档中的直接 URL，并在 README 记录。验收时用实际请求确认两个路径。

## Decision 4：NetworkPolicy 放行（实测修正）

**Decision**：保留上游默认拒绝，但 `networkPolicy.ingress` 只按**端口**放行 3080/TCP 与 6080/TCP；不使用
`namespaceSelector`/`podSelector`/`ipBlock` 作为来源限制。

```yaml
ingress:
  - ports:
      - { protocol: TCP, port: 3080 }
      - { protocol: TCP, port: 6080 }
```

**Rationale**：最初按 `tailscale/ingress-proxies` 的 namespace + pod 标签放行。线上实测 Tailscale 代理访问
DSH 超时；`ingress-proxies` 日志为 `dial tcp 10.43.158.91:3080: connect: connection timed out`。Cilium
monitor 显示：

```text
Policy verdict: ... ingress, action deny, match none, 192.168.3.154:xxx -> 10.42.2.176:3080 tcp SYN
xx drop (Policy denied) ... identity 6->48792
```

源地址是节点 IP `192.168.3.154`、身份 `world`，不是代理 Pod 的 `10.42.1.76`/identity 59997。原因是本集群
Cilium 的 `ipv4NativeRoutingCIDR=192.168.3.0/24`，跨节点 Pod 流量在目标侧已被 masquerade 成节点 IP；K8s
NetworkPolicy 的 namespace/pod selector 与 ipBlock 都无法匹配。临时允许全部 ingress 后 Web 立即恢复 401、
桌面 200；只按端口放行的策略同样有效。

**Alternatives considered**：

- 放行整个 `tailscale` 命名空间：实测同样超时（源身份已丢失），无法解决问题。
- 放行节点 CIDR / Pod CIDR 的 ipBlock：实测仍被 deny（源身份为 `world`，policy match none）。
- 关闭 NetworkPolicy：能工作，但连端口限制也丢失；端口级策略是更小的让步。
- 修改 Cilium `ipv4NativeRoutingCIDR` 覆盖 Pod CIDR：这是正确的根因修复，但属于集群级网络变更，影响所有
  Pod-to-Pod 流量，不在本特性内；README 记录为后续收紧条件。

**安全取舍**：ClusterIP 不发布到集群外，Tailscale Ingress 仍是唯一外部入口；集群内任意 Pod 可访问
3080/6080（Web 仍需 token，noVNC 无认证）。这与「仅 tailnet 外部可达」不冲突，但比原计划的「仅代理 Pod」
范围宽；必须明确记录，不能假装源选择器有效。

## Decision 5：不使用 initContainer，改为一次性手动任务

**Decision**：StatefulSet 只有主容器，直接启动 DSH。维护者在 Pod Ready 后执行：

1. `scripts/install-dsh-tools`：复制并执行 `install-tools.sh`，把 uv/mise/工具装到工具卷。
2. `scripts/sync-dsh-config`：本机准备配置、改写、`kubectl cp`、容器内 `pnpm install`，最后重启 Pod。
3. `scripts/sync-dsh-skills`：本机 skills → skills PVC。

**Rationale**：

- 用户明确要求先启动 DSH 容器，再通过 `kubectl` 进入容器执行一次性安装/配置更新；initContainer 被否决。
- 工具安装与配置同步需要网络、可能耗时数分钟；放在 init 会拖慢每次 Pod 启动，而且失败会让 Pod 起不来。
  手动执行让 DSH Web 先可用，失败可诊断、可重跑。
- 结果落在 PVC 上，Pod 重启不丢；只有工具卷重建或配置变更时才需要重跑。
- Chart 更简单：没有 initContainer、没有 init ConfigMap、没有 `configSync` values/注解。

**Alternatives considered**：

- 两个 initContainer（工具 → 配置）：自动化最好，但被用户明确否决，且首次启动慢、失败面大。
- entrypoint 包装：会覆盖上游 relay/desktop/信号处理，风险大。
- Job/Helm hook：与 StatefulSet 启动无顺序保证，仍需处理凭据与配置来源。

**代价**：首次部署是“先上线空 DSH，再手动补齐工具/配置”，需要 README 与 quickstart 明确顺序；漏跑时
DSH 仍可启动，但工具/插件缺失。用 `.dsh-tools-version` 与 `.dsh-config-source` 记录状态。

## Decision 6：配置来源与同步（本机 gh 或 ~/.dsh）

**Decision**：`scripts/sync-dsh-config` 支持两种来源：

- 默认 `--source "$HOME/.dsh"`：直接选本机活配置中的白名单文件；
- `--repo east4ming/dsh-config --revision <ref>`：用本机已认证的 `gh repo clone` 拉到临时目录并 checkout。

本地 `transform-config.sh` 负责复制/改写，打 tar 包后用 `kubectl cp` 写入 Pod 的 `/tmp`，再 `kubectl exec`
解包到 `$DSH_HOME` 并 `pnpm install`。成功后写 `$DSH_HOME/.dsh-config-source`，并
`kubectl rollout restart statefulset/deepseek-harness`。

**Rationale**：

- 私库认证留在本机 `gh`，集群不需要 `DSH_CONFIG_TOKEN`，Secret 只有两个 provider key。
- 配置改写需要 `yq`/`jq`，本机已具备；容器内不需要额外 init 工具链。
- `kubectl cp` 是用户指定的同步方式；tar 包避免逐文件 cp 的多次连接与部分失败。
- 手工选择白名单目录，避免把 `sessions/`、`storages/`、`.credentials.yaml`、`dsh-chat-import/` 搬进集群。

**Alternatives considered**：

- 集群内 `git clone` + 只读 token：需要额外 Secret，且用户明确要求改用本机 `gh`/`kubectl cp`。
- 把配置提交到 homelab2：public 仓库，含私有路径/个人信息，拒绝。
- 用 `kubectl cp` 整个 `~/.dsh`：会带会话/凭据/缓存，体积大且不可控。

**失败语义**：本机 `gh` 未登录、源目录缺文件、`kubectl cp` 中断、`pnpm install` 失败都返回非零；不写来源
marker；重跑收敛。同步期间 DSH 可能看到部分文件，完成后重启保证一致。

## Decision 7：配置改写清单

| 改写 | 原因 |
| --- | --- |
| `/home/casey/.dsh` → `/home/node/.dsh` | 容器 DSH home 路径 |
| codegraph/atuin/dcg → `/workspace/.local/share/mise/shims/*` | 工具由容器内 mise 安装 |
| `agent-default-model.provider`: `deepseek-account` → `deepseek-official` | 注入的是 API Key；账号路由不会回退 |
| 删除 profile 的 `dshmarket` 依赖/bundle | 市场镜像内置 1.66.9，重复行会冲突 |
| 置空 tool-hooks `config.post` | StyleFerry 仓库不在容器内 |
| `pnpm-workspace.yaml` 追加 `onlyBuiltDependencies` | 镜像 pnpm 10.15.1 忽略 `allowBuilds` |
| skill lock/integrations 路径 | 本机绝对路径不存在 |
| 不复制 `dsh-chat-import/` | 含本机 `.claude` 导入缓存 |
| 保留 `sessions/`、`storages/`、`.credentials.yaml` | 运行时/凭据，不是配置 |

**Rationale**：逐条改写比“整盘搬 .dsh”可控，也不会把本机机密带进集群。`dsh-config` 仍是配置源，但同步
的是“改写后的配置”，不是原始仓库。

## Decision 8：默认模型路由

**Decision**：同步后把 `agent-default-model.provider` 改为 `deepseek-official`，模型保持
`deepseek-flash`、`reasoningEffort: high`；不把本机 `.credentials.yaml` 的账号授权带入集群。

**Rationale**：本机配置使用 `deepseek-account`，该路由只读取账号 provider 保存的 grant；注入的是
`DEEPSEEK_API_KEY`。DSH 的两条路由不会互相回退（`dsh-llm-deepseek` 文档明确）。`deepseek-official`
的 `apiKeyEnv` 就是 `DEEPSEEK_API_KEY`，可无交互完成模型调用。账号登录仍可由用户在 Web 内完成，
写入 10Gi home 并持久化，但不作为默认验收路径。

**Alternatives considered**：

- 在容器 Web 内登录账号：可行但需要人工交互，且会让“注入 API Key”失去意义。
- 继续 `deepseek-account`：会因缺少账号 grant 报登录提示，不满足 SC-005。

## Decision 9：工具链持久化与安装

**Decision**：

- 覆盖镜像 `XDG_CACHE_HOME=/tmp/.cache`、`XDG_CONFIG_HOME=/tmp/.config`、`XDG_DATA_HOME=/tmp/.local/share`，
  设为：
  - `XDG_DATA_HOME=/workspace/.local/share`
  - `XDG_CONFIG_HOME=/workspace/.config`
  - `XDG_CACHE_HOME=/workspace/.local/cache`
  - `XDG_STATE_HOME=/workspace/.local/state`
- 工具卷挂到 `/workspace/.local` 与 `/workspace/.config`；`PATH` 前置
  `/workspace/.local/bin:/workspace/.local/share/mise/shims`。
- `HOME=/workspace` 保持；uv/mise 二进制装到 `/workspace/.local/bin`。
- `install-tools.sh`（手动执行）安装 uv/mise，再：
  - `uv tool install` specify-cli、pre-commit、pyrefly、yamllint
  - `mise use -g` gh、jq、yq、`npm:@colbymchenry/codegraph`、`npm:clawhub`、`github:yusukebe/ax`、
    `github:Dicklesworthstone/destructive_command_guard`、`github:harehare/mq`、`aqua:atuinsh/atuin`
- 工具列表写入 `/workspace/.local/.dsh-tools-version` 标记；重跑时检查已存在项。

**Rationale**：镜像把 XDG 指向 `/tmp` 是刻意的（只读根文件系统 + 可丢弃缓存）；仅挂 PVC 而不改 XDG，
uv/mise 仍会写 `/tmp`，重启即丢。mise 的 npm/GitHub/aqua 后端会读取 `GITHUB_API_TOKEN`（官方 token
优先级表：`MISE_GITHUB_TOKEN` → `GITHUB_API_TOKEN` → `GITHUB_TOKEN`），不需要改名。
`atuin` 的 registry 同时有 `aqua:atuinsh/atuin` 与 `cargo:atuin`；显式用 aqua 预编译，避免容器内
没有 Rust 工具链。

**Alternatives considered**：

- 只挂 `/home/node/.local`：`HOME=/workspace`，uv/mise 仍按 XDG 写 `/tmp`，不生效。
- 把工具装进镜像：需要自建镜像与发布流水线，违背“用上游镜像”的约束。
- 用 `uv` 管理所有工具：uv 不提供 gh/jq/yq 等非 Python 二进制。
- 用 `mise` 管理 Python 工具：用户明确要求 uv tool install，且 uv 的隔离环境更适合。

## Decision 10：PVC、保留与备份

**Decision**：

- `dsh-home`：StatefulSet volumeClaimTemplate，10Gi RWO，`standard-rwo`，上游
  `persistentVolumeClaimRetentionPolicy` 保留。
- `workspace`：独立 PVC 20Gi RWO，名称 `deepseek-harness-workspace`，
  `workspace.existingClaim` 指向它。
- `tools`：独立 PVC 20Gi RWO，名称 `deepseek-harness-tools`。
- `skills`：独立 PVC 1Gi RWO，名称 `deepseek-harness-skills`。
- 三个独立 PVC 加 `helm.sh/resource-policy: keep` 与
  `argocd.argoproj.io/sync-options: Prune=false,Delete=false`。
- **四块 PVC 都是备份对象**；本特性不实现 VolSync/备份策略，**不修改** `scripts/backup-coverage` 的
  `is_exempt()`。README 列出 PVC 名称与容量，用户后续手动配置备份。

**Rationale**：RWO + 单副本；`standard-rwo` 是默认 SC。ArgoCD `prune: true` 会删除应用目录内的
PVC，如果不加 keep/prune 注解，一次误删应用就会丢会话与工作区。备份是用户明确的后续手动任务；
在 `backup-coverage` 里豁免会掩盖“尚未备份”，所以不豁免。在用户配置备份前，
`./scripts/backup-coverage` 会列出这四块 PVC，这是预期状态。

**Alternatives considered**：

- 用 emptyDir：重启丢数据，直接违背 spec。
- 四块都做成 volumeClaimTemplates：`workspace.existingClaim` 语义会丢失，且独立 PVC 更便于备份工具按名识别。
- 在 `backup-coverage` 里豁免：与用户“需要备份”的指示冲突。

## Decision 11：资源限制

**Decision**：主容器 `requests: cpu 250m / memory 1Gi`，`limits: cpu 2 / memory 4Gi`；`/dev/shm` 1Gi，
`/tmp` 512Mi（上游默认）。

**Rationale**：Constitution IV 要求显式 requests + limits；上游只给 requests。DSH + Chromium + 插件
需要比普通 web 应用更多内存；4Gi 上限在 4×N100（约 64GB）上可接受。`/dev/shm` 1Gi 是 Chromium 的
最低舒适值。没有 initContainer，因此不存在 init 资源叠加问题。

**Alternatives considered**：

- 沿用上游“只有 requests”：违反 Constitution。
- 2Gi limit：可能 OOM（Chromium + Node + 插件）。
- 8Gi limit：超出单应用合理预算，且会挤压其他服务。

## Decision 12：密钥注入与 bootstrap

**Decision**：保留用户给定的 `kubectl create secret generic dsh-provider-credentials` 流程，新增
`scripts/bootstrap-deepseek-harness`：

- 校验 `DEEPSEEK_API_KEY`、`GITHUB_API_TOKEN` 非空；
- 用临时 env 文件 + `--from-env-file`，`umask 077`，`trap` 清理；不回显值；
- 创建/更新 Secret（`--dry-run=client -o yaml | kubectl apply -f -`）；
- 命名空间不存在时先创建（ArgoCD 之后会接管）。

**Rationale**：用户明确要求用 Secret 注入，且仓库 public；ESO 需要先把值放进 `global-secrets`，
多一步且用户没有要求。脚本把“容易手滑”的部分（空值、漏键、值回显）固化。集群内没有配置仓库 token，
Secret 只有两个 provider key。

**Alternatives considered**：

- ESO + `global-secrets`：Constitution 的默认；但需要把本机 env 先写入集群 external Secret，且用户
  明确给了 `kubectl create secret` 流程。作为后续升级路径记录在 README。
- 把 Secret 写进 Helm values：直接违反“Secret 永不入库”。
- `--from-literal`：值会出现在进程参数；用 env 文件更稳。

## Decision 13：测试与验收

**Decision**：

- 静态：`helm lint`、`helm template` + `yq` 断言（无 initContainers、PVC 数量/大小/注解、两条 Ingress、
  NetworkPolicy 端口、env、resources、image tag）。
- 仓库门禁：`pre-commit run --files apps/deepseek-harness/** scripts/* test/smoke_test.go`
  （yamllint/helmlint/shellcheck/eof/private-key）。
- 集群：扩展 `test/smoke_test.go`，Web Ingress 期望 401、Desktop Ingress 期望 200；现有 5 个应用仍 200。
- 线上：手动工具安装 → 配置同步（自动重启）→ skills 同步 → token 登录、模型调用、插件/市场、
  NetworkPolicy 正反例、PVC 持久化。
- `backup-coverage` 不作为本特性门禁：四块 PVC 在用户配置备份前会被列出；验证脚本未被修改即可。

**Rationale**：DSH 需要认证，不能直接套用现有“200 即通过”的 smoke 断言；加 `expectedStatus` 是最小改动。
手动步骤是一次性任务，必须用 quickstart 固化顺序，否则容易漏跑。

**Alternatives considered**：

- 只做 `helm template`：发现不了 ClusterIP/NetworkPolicy/Ingress 的真实行为。
- 只做人工浏览器验收：不可重复，无法进 CI/回归。
- 把工具/配置放回 initContainer：被用户明确否决。

## 未决项

1. **Tailscale 多后端 Ingress 的实测**：代码路径支持，但需用实际请求验证；不成立时回退到独立
   Desktop Ingress + 文档化直接 URL。
2. **4Gi 内存上限是否足够**：上线后观察 OOM；不足时只调 values。
3. **插件逐个加载结果**：`dsh-pet`/`dsh-mini-remote`/`dsh-wechat` 等可能与容器能力有差异；按插件
   降级规则禁用并记录，不阻塞主体验收。
4. **备份**：用户后续手动配置；本特性只保证四块 PVC 名称/容量/保留策略可被识别，不修改
   `scripts/backup-coverage`。
