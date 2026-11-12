# deepseek-harness

DeepSeek Harness（DSH）单用户 Web 实例，以 vendored 的上游 Helm Chart 部署到 homelab2。
本目录是 [runzhliu/deepseek-harness-docker](https://github.com/runzhliu/deepseek-harness-docker)
`charts/deepseek-harness` 的本地副本，追加了 homelab2 需要的卷、Ingress 与 NetworkPolicy 放行规则。

- 上游 commit：`043714057c0c2ef53a5023a3117c5f25fe5af62c`
- 上游 Chart 版本：`0.1.29`，本目录版本：`0.1.29-homelab.1`
- 镜像：`docker.io/runzhliu/deepseek-harness:0.2.2-rc.2-r1-market.1`（市场变体；手动 Helm 用
  `--set image.tag=0.2.2-rc.2-r1-market.1`，ArgoCD 使用 `values.yaml` 的同一值）
- 部署：ArgoCD ApplicationSet 自动发现 `apps/deepseek-harness`，namespace 也是 `deepseek-harness`

## 与上游的差异

| 差异 | 原因 |
| --- | --- |
| `service-tailscale` ClusterIP | Tailscale L7 Ingress 要求后端 Service 有 ClusterIP；上游 Headless 不能直接用 |
| `ingress-web` / `ingress-desktop` | 两个 tailnet 入口；Web Ingress 另把 `/novnc-*` 路由到 6080，供 UI 内桌面入口使用 |
| `pvc-workspace` / `pvc-tools` / `pvc-skills` | 20Gi/20Gi/1Gi RWO；带 keep/prune 注解 |
| StatefulSet 卷与 env | 挂载工作区/工具/skills；把 `XDG_*` 从 `/tmp` 覆盖到工具卷；`desktop.publicPort=443` |
| `resources.limits` | Constitution 要求显式 limits |
| `networkPolicy.ingress` | 默认拒绝，只放行 3080/6080；源地址选择器在本集群会被 Cilium SNAT 破坏（见下文） |
| **无 initContainer** | 工具、配置、skills 由维护者在 Pod 启动后手动一次性执行 |

## 部署顺序

1. 创建 Secret（在 ArgoCD 同步前；否则 Pod 因 `envFrom` 缺失无法启动）：

   ```sh
   scripts/bootstrap-deepseek-harness
   ```

   只接受 `DEEPSEEK_API_KEY`、`GITHUB_API_TOKEN`；不创建 `DSH_CONFIG_TOKEN`。

2. 合并到 `master`，等 ArgoCD 创建 namespace/PVC/Service/Ingress/Pod。
3. Pod Ready 后执行一次性任务：

   ```sh
   scripts/install-dsh-tools
   scripts/sync-dsh-config --source "$HOME/.dsh"
   scripts/sync-dsh-skills
   ```

4. 访问：

   - Web：`https://dsh.west-beta.ts.net`（未认证 401；从日志取 token）
   - 桌面：`https://dsh-desktop.west-beta.ts.net`（无认证，仅 tailnet）
   - Web UI 侧栏的“浏览器桌面”走 `https://dsh.west-beta.ts.net/novnc-*`

## 一次性工具安装

`scripts/install-dsh-tools` 把 `files/install-tools.sh` 复制到 Pod `/tmp` 后 `kubectl exec` 执行。
脚本把 uv/mise 与工具装到工具卷：

- uv：`specify-cli`、`pre-commit`、`pyrefly`、`yamllint`
- mise：`gh`、`jq`、`yq`、`codegraph`、`clawhub`、`ax`、`dcg`、`mq`、`atuin`

`atuin` 显式使用 `aqua:atuinsh/atuin`，避免容器内没有 Rust 工具链。完成后写入
`/workspace/.local/.dsh-tools-version`。工具卷重建后重跑同一命令；日常重启不需要。

## 一次性配置同步

配置同步在维护者本机完成，不在集群内 clone：

```sh
# 直接使用本机活配置
scripts/sync-dsh-config --source "$HOME/.dsh"

# 或使用本机已认证的 gh 拉取私库
scripts/sync-dsh-config --repo east4ming/dsh-config --revision <ref>
```

脚本流程：本地白名单复制 → 容器化改写 → tar → `kubectl cp` → 容器内解包 →
`CI=true pnpm install --no-frozen-lockfile` → 写 `/home/node/.dsh/.dsh-config-source` →
`kubectl rollout restart statefulset/deepseek-harness`。

改写包括：

- `/home/casey/.dsh` → `/home/node/.dsh`
- codegraph/atuin/dcg → `/workspace/.local/share/mise/shims/*`
- `agent-default-model.provider` → `deepseek-official`（API Key 路由）
- 删除 profile 的 `dshmarket` 依赖/bundle（市场镜像内置 1.66.9）
- 置空 StyleFerry 的 tool-hooks post（容器内没有该仓库）
- 追加 pnpm 10 的 `onlyBuiltDependencies`
- skill lock / integrations 路径

不会复制 `sessions/`、`storages/`、`.credentials.yaml`、`dsh-chat-import/`、`node_modules/`。
集群内没有配置仓库凭据；本机 `gh` token 不进入 Pod。

## skills

```sh
scripts/sync-dsh-skills
```

把本机 `~/.agents/skills` 解包到 `/workspace/.agents/skills`（1Gi PVC）。不删除远端额外 skill；
skills 内容不提交到 Git。

## 持久化与备份

| PVC | 大小 | 说明 |
| --- | --- | --- |
| `dsh-home-deepseek-harness-0` | 10Gi | profiles、node_modules、sessions、storages、凭据 |
| `deepseek-harness-workspace` | 20Gi | `/workspace` |
| `deepseek-harness-tools` | 20Gi | uv/mise/tools |
| `deepseek-harness-skills` | 1Gi | `/workspace/.agents/skills` |

四块 PVC 都是后续**手动备份**对象。本 Chart 不创建 VolSync ReplicationSource，也不修改
`scripts/backup-coverage`。在备份配置完成前，`./scripts/backup-coverage` 会列出这四块 PVC，这是预期。

## 升级与回滚

- 升级上游 Chart：重新复制上游 `charts/deepseek-harness`，逐项重放本目录新增的卷/Ingress/NP/env；
  不要直接覆盖本地差异。镜像 tag 在 `values.yaml` 显式固定，不使用 `latest`。
- 升级镜像：改 `image.tag`，ArgoCD 同步；PVC 保留。降级前确认 DSH 数据卷兼容性。
- 回滚：ArgoCD Sync 到上一个 tag；四块 PVC 保留。代码回滚用 `git revert`。

## Ingress 与 Host/Origin

DSH 的 `/api` 浏览器信任栅栏要求 `Host` 是回环、绑定 IP，或 `--trusted-host` 声明的 authority；否则
`/api/remote.mux` WebSocket 返回 403，UI 左下角一直“重新连接中”，权限页报
`permission catalog has no active Host connection`。Chart 在 `args` 中自动追加：

```text
--public-url https://<ingress.web.host>
--trusted-host <ingress.web.host>
```

新增/修改 Ingress 主机名时无需改模板；改 `ingress.web.host` 即可。

## NetworkPolicy 说明

最初尝试只放行 `tailscale/ingress-proxies`（namespaceSelector + podSelector）。实测该规则在本集群无效：
Cilium 的 `ipv4NativeRoutingCIDR` 是 `192.168.3.0/24`，跨节点 Pod 流量在到达目标 Pod 前被 masquerade 成节点 IP，
源身份变成 `world`；ingress 的 namespace/pod selector 与 ipBlock 都匹配不到，Tailscale 代理连接 3080/6080
超时。临时允许全部 ingress 后立即恢复 401/200。

当前策略因此只限制**端口**：默认拒绝其他端口，放行 3080/6080。DSH 的 ClusterIP 不发布到集群外，Tailscale
Ingress 仍是唯一外部入口；集群内任意 Pod 可访问这两个端口。若要把源限制收紧回 ingress proxies，需要先把
Cilium 的 native routing CIDR 调整为覆盖 Pod CIDR（`10.42.0.0/16`），这是独立的集群网络变更，未在本 PR 中做。

## 已知限制

- noVNC 无认证；仅 tailnet。Tailscale ACL 是唯一边界。
- NetworkPolicy 只限制端口，不限制源；见上文 Cilium SNAT 说明。
- `GITHUB_API_TOKEN` 只用于 mise 的 GitHub 安装限流；`gh` 登录需手动完成，本 Chart 不注入 `GH_TOKEN`。
- 市场镜像内置 `dshmarket@1.66.9`，低于本机 `1.73.17`；升级镜像时统一。
- `dsh-chat-import` 不同步；`integrations` 中指向本机项目的路径改写为 `/workspace`。
- 工具/配置/skills 都是手动一次性任务；漏跑时 DSH 仍可启动，但工具/插件不完整。
- 4Gi 内存上限；若 OOM，只调 `values.yaml`。
