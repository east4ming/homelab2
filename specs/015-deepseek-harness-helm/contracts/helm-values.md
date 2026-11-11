# 契约：Helm Values 与渲染结果

应用目录：`apps/deepseek-harness/`。Chart 名称 `deepseek-harness`，ArgoCD release/namespace 均为
`deepseek-harness`。

## 必填/关键 values

| Key | 类型 | 值 | 说明 |
| --- | --- | --- | --- |
| `image.repository` | string | `docker.io/runzhliu/deepseek-harness` | 上游默认 |
| `image.tag` | string | `0.2.2-rc.1-r1-market.1` | 市场变体；不可用 `latest` |
| `image.pullPolicy` | string | `IfNotPresent` | 不可变 tag |
| `persistence.enabled` | bool | `true` | dsh-home volumeClaimTemplate |
| `persistence.size` | string | `10Gi` | |
| `persistence.storageClass` | string | `standard-rwo` | |
| `persistence.accessModes` | list | `[ReadWriteOnce]` | |
| `workspace.existingClaim` | string | `deepseek-harness-workspace` | 传给上游 StatefulSet |
| `workspace.create` | bool | `true` | Chart 创建同名 PVC |
| `workspace.size` | string | `20Gi` | |
| `workspace.storageClass` | string | `standard-rwo` | |
| `tools.size` | string | `20Gi` | 工具卷 |
| `tools.storageClass` | string | `standard-rwo` | |
| `skills.size` | string | `1Gi` | skills 卷 |
| `skills.storageClass` | string | `standard-rwo` | |
| `credentials.existingSecret` | string | `dsh-provider-credentials` | 主容器 envFrom；只含两个 provider key |
| `desktop.publicPort` | int | `443` | Web UI 构造桌面 URL 用 |
| `service.port` | int | `3080` | Web |
| `service.desktopPort` | int | `6080` | noVNC |
| `ingress.web.host` | string | `dsh.west-beta.ts.net` | |
| `ingress.desktop.host` | string | `dsh-desktop.west-beta.ts.net` | |
| `ingress.className` | string | `tailscale` | |
| `ingress.annotations` | map | `tailscale.com/proxy-group: ingress-proxies` | |
| `networkPolicy.enabled` | bool | `true` | 保留上游默认 |
| `networkPolicy.ingress` | list | 见 `contracts/runtime.md` | 只放行 ingress proxies |
| `resources.requests` | map | `cpu: 250m, memory: 1Gi` | |
| `resources.limits` | map | `cpu: 2, memory: 4Gi` | Constitution IV |

## 渲染结果（必须存在）

| 资源 | 数量/名称 | 关键断言 |
| --- | --- | --- |
| StatefulSet | `deepseek-harness` | 1 副本；**没有 initContainers**；4 类卷挂载；只读根 FS；非 root |
| Headless Service | `deepseek-harness` | `clusterIP: None`；端口 3080/6080 |
| Tailscale Backend Service | `deepseek-harness-tailscale` | `type: ClusterIP`；端口 http/desktop；非空 ClusterIP |
| Ingress | `deepseek-harness` | host `dsh...`；`/`→http，`/novnc-`→desktop |
| Ingress | `deepseek-harness-desktop` | host `dsh-desktop...`；`/`→desktop |
| NetworkPolicy | `deepseek-harness` | policyTypes Ingress；仅 3080/6080 来自 ingress-proxies |
| PVC | `deepseek-harness-workspace` | 20Gi RWO；keep/prune=false |
| PVC | `deepseek-harness-tools` | 20Gi RWO；keep/prune=false |
| PVC | `deepseek-harness-skills` | 1Gi RWO；keep/prune=false |
| volumeClaimTemplate | `dsh-home` | 10Gi RWO；StatefulSet 删除后保留 |
| ConfigMap | 无 | 手动脚本不在 Chart 内挂载 |

## 不允许

- `image.tag: latest` 或空 tag。
- 用 Headless Service 作为 Ingress backend。
- `networkPolicy.ingress: []`（会阻断 Tailscale）或放行整个 `tailscale` 命名空间。
- 在 values 中出现真实密钥、token、私有仓库凭据。
- 省略 `resources.limits`。
- 将 6080 暴露为 NodePort/LoadBalancer 或公网 Ingress。
- 在 Chart 中挂载手动安装/同步脚本的 ConfigMap（手动任务通过 `kubectl cp` 执行）。
- 在 `scripts/backup-coverage` 中为四块 DSH PVC 添加豁免；它们必须作为后续手动备份对象暴露。
