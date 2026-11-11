# 契约：运行时、网络与手动运维

## Pod 结构

```text
containers:
  deepseek-harness (upstream image entrypoint, args: web --patch ... --no-open)
```

- **没有 initContainers**；Pod 直接启动 DSH。
- 工具安装、配置同步、skills 同步都是 Pod Ready 后的一次性手动任务，见下文。
- 主容器保留上游 entrypoint（relay、desktop、信号处理）；不得用 `command` 覆盖。

## 环境变量（主容器）

| 变量 | 值 | 来源 |
| --- | --- | --- |
| `DSH_HOME` | `/home/node/.dsh` | Chart |
| `HOME` | `/workspace` | Chart/镜像 |
| `XDG_DATA_HOME` | `/workspace/.local/share` | Chart（覆盖镜像 `/tmp`） |
| `XDG_CONFIG_HOME` | `/workspace/.config` | Chart |
| `XDG_CACHE_HOME` | `/workspace/.local/cache` | Chart |
| `XDG_STATE_HOME` | `/workspace/.local/state` | Chart |
| `DSH_AGENTS_HOME` | `/workspace/.agents` | Chart |
| `DSH_DESKTOP_PUBLIC_PORT` | `443` | `desktop.publicPort` |
| `PATH` | `/workspace/.local/bin:/workspace/.local/share/mise/shims:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin` | Chart |
| `DEEPSEEK_API_KEY` | Secret | `envFrom` |
| `GITHUB_API_TOKEN` | Secret | `envFrom`；mise 原生读取 |

**不注入** `DSH_CONFIG_TOKEN`、`GH_TOKEN`；配置仓库认证只在本机 `gh` 完成，`gh` 登录由用户后续手动完成。

## 挂载

| 卷 | 路径 | 容器 | 备注 |
| --- | --- | --- | --- |
| `dsh-home` | `/home/node/.dsh` | main | 10Gi |
| `workspace` | `/workspace` | main | 20Gi，existingClaim |
| `tools` | `/workspace/.local` | main | 20Gi |
| `tools` | `/workspace/.config` | main | 同一 PVC |
| `skills` | `/workspace/.agents/skills` | main | 1Gi |
| `tmp` | `/tmp` | main | emptyDir Memory 512Mi；`kubectl cp` 的中转目录 |
| `shm` | `/dev/shm` | main | emptyDir Memory 1Gi |

## 端口与 Ingress

| 端口 | 用途 | 暴露 |
| --- | --- | --- |
| 3080 | DSH Web | Web Ingress `/` |
| 6080 | noVNC | Web Ingress `/novnc-` + Desktop Ingress `/` |
| 9222 | CDP | 仅 Pod 内部（attach） |

**Ingress backend**：必须指向 `deepseek-harness-tailscale`（ClusterIP）。不得指向 Headless Service。

### NetworkPolicy 契约

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: deepseek-harness
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/name: deepseek-harness
      app.kubernetes.io/instance: deepseek-harness
  policyTypes: [Ingress]
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: tailscale
          podSelector:
            matchLabels:
              tailscale.com/parent-resource-type: proxygroup
              tailscale.com/parent-resource: ingress-proxies
      ports:
        - { protocol: TCP, port: 3080 }
        - { protocol: TCP, port: 6080 }
```

- 不放行则 Tailscale 代理无法到达 Pod（默认 deny-all）。
- kubelet 探针（127.0.0.1）不受影响。
- 不限制 egress；DSH 需访问模型/GitHub/npm/PyPI。

## 手动运维契约

### 1. 工具安装（一次性）

```sh
scripts/install-dsh-tools
```

- 本机脚本找 Pod、等待 Ready，`kubectl cp apps/deepseek-harness/files/install-tools.sh <pod>:/tmp/`，
  再 `kubectl exec -- bash /tmp/install-tools.sh`。
- 容器内脚本设置 `HOME`/`XDG_*`/`PATH`，安装 uv/mise 与清单工具到工具卷，写
  `/workspace/.local/.dsh-tools-version`。
- 无需重启；Pod env 已包含工具目录。工具卷重建后重跑。

### 2. 配置同步（一次性）

```sh
# 直接用本机活配置
scripts/sync-dsh-config --source "$HOME/.dsh"

# 或用本机已认证的 gh 拉取私库
scripts/sync-dsh-config --repo east4ming/dsh-config --revision <ref>
```

- 本机 `transform-config.sh` 复制白名单文件并改写，打 tar 包。
- `kubectl cp` 到 `<pod>:/tmp/dsh-config-sync.tar`。
- `kubectl exec` 解包到 `/home/node/.dsh`，写 `.dsh-config-source`，在 `profiles/web` 执行
  `CI=true pnpm install --no-frozen-lockfile`。
- 成功后 `kubectl rollout restart statefulset/deepseek-harness`，等待 Ready。
- 集群内不使用配置仓库凭据；本机 `gh` token 不进入 Pod。
- 不删除 `sessions/`、`storages/`、`.credentials.yaml`；不复制 `dsh-chat-import/`。

### 3. skills 同步（可重复）

```sh
scripts/sync-dsh-skills
```

- `tar` 本机 `~/.agents/skills` → `kubectl exec -i <pod> -- tar -C /workspace/.agents/skills --no-same-owner -xf -`。
- 不删除远端额外 skill；重启后保留。

## 健康与就绪

- 沿用上游 startup/liveness/readiness exec 探针：3080 返回 401、6080 vnc.html 可访问、9222 CDP 可访问。
- Pod `Ready` 后才执行手动安装/同步；Ingress 可能先于 Pod Ready，验收需等待。

## 安全边界

- 容器：非 root UID/GID 1000、只读根文件系统、drop ALL、no-new-privileges、`automountServiceAccountToken: false`。
- 手动 `kubectl cp/exec` 以 UID 1000 运行，只写 PVC 与 `/tmp`。
- noVNC 无认证；仅 tailnet Ingress，Tailscale ACL 是唯一边界。不得加公网入口。
- Secret 不进入 values/Git；只通过 `dsh-provider-credentials` 注入。

## 备份

- 四块 PVC 都是后续手动备份对象；本特性不创建 ReplicationSource，也不修改
  `scripts/backup-coverage`。
- 在用户配置备份前，`./scripts/backup-coverage` 会列出四块 PVC，这是预期状态，不是本特性失败。
