# Phase 1 数据模型：DeepSeek Harness 实例

本特性没有业务数据库；这里的“数据模型”指集群内需要保持一致的声明式对象、持久化边界与一次性手动状态。

## 实体

### DSHHomeVolume

| 字段 | 值/说明 | 约束 |
| --- | --- | --- |
| name | `dsh-home-deepseek-harness-0`（StatefulSet volumeClaimTemplate 生成） | 稳定；卸载后保留 |
| size | 10Gi | 用户指定 |
| accessMode | ReadWriteOnce | 单副本 |
| storageClass | `standard-rwo` | 现有默认 SC |
| mountPath | `/home/node/.dsh` | `DSH_HOME` |
| retention | StatefulSet `persistentVolumeClaimRetentionPolicy: whenDeleted: Retain` | 删除 StatefulSet 不删 PVC |
| contents | profiles、node_modules、settings、sessions、storages、凭据、npm/pnpm 缓存 | 含不可重建数据；**用户后续手动备份** |

### WorkspaceVolume

| 字段 | 值/说明 | 约束 |
| --- | --- | --- |
| name | `deepseek-harness-workspace` | values 显式声明 |
| size | 20Gi | 用户指定 |
| accessMode | ReadWriteOnce | 单副本 |
| storageClass | `standard-rwo` | |
| mountPath | `/workspace` | `HOME` |
| wiring | `workspace.existingClaim: deepseek-harness-workspace` | 可替换为已有 PVC |
| retention | `helm.sh/resource-policy: keep` + ArgoCD `Prune=false,Delete=false` | 卸载/重同步不删 |
| contents | Agent 工作文件 | 用户数据；**用户后续手动备份** |

### ToolsVolume

| 字段 | 值/说明 | 约束 |
| --- | --- | --- |
| name | `deepseek-harness-tools` | |
| size | 20Gi | 用户指定 |
| accessMode | ReadWriteOnce | |
| storageClass | `standard-rwo` | |
| mountPath | `/workspace/.local` 与 `/workspace/.config` | 同一 PVC 两次挂载 |
| retention | 同 Workspace | |
| contents | uv 二进制/工具/Python/cache；mise 二进制/installs/shims/config/cache/state；npm 全局工具 | 可重建，但重启不应重装；**用户后续手动备份** |
| marker | `/workspace/.local/.dsh-tools-version` | 一次性安装完成标记 |

### SkillsVolume

| 字段 | 值/说明 | 约束 |
| --- | --- | --- |
| name | `deepseek-harness-skills` | |
| size | 1Gi | 用户指定 |
| accessMode | ReadWriteOnce | |
| storageClass | `standard-rwo` | |
| mountPath | `/workspace/.agents/skills` | DSH `<agentsHome>/skills` |
| agentsHome | `/workspace/.agents` | 显式 `DSH_AGENTS_HOME` |
| retention | 同 Workspace | |
| contents | 从本机同步的技能目录 | 约 53MB；不从 Git 部署；**用户后续手动备份** |

### ProviderCredentialsSecret

| 字段 | 值/说明 | 约束 |
| --- | --- | --- |
| name | `dsh-provider-credentials` | 与 `credentials.existingSecret` 一致 |
| key `DEEPSEEK_API_KEY` | 来自本机 env | 必填；供 `deepseek-official` 使用 |
| key `GITHUB_API_TOKEN` | 来自本机 env | 必填；mise 原生读取用于 GitHub 限流 |
| managedBy | 本机 bootstrap 脚本 | 不进 Git、不进 ArgoCD |
| lifecycle | 命名空间存在期间保留 | 命名空间删除即丢失；重跑 bootstrap 恢复 |

**不包含** `DSH_CONFIG_TOKEN`：配置同步在本机完成，集群内不需要私有仓库凭据。

### ConfigSyncRun（一次性手动任务）

| 字段 | 值/说明 | 约束 |
| --- | --- | --- |
| source | `$HOME/.dsh`（默认）或 `gh repo clone east4ming/dsh-config` 的临时目录 | 本机路径；不进集群 |
| revision | `--repo` 模式下的 git ref；`--source` 模式下记录 mtime/时间 | 审计用，不驱动滚动 |
| transformer | `apps/deepseek-harness/files/transform-config.sh` | 本机执行；yq/jq/sed |
| transport | `kubectl cp` tar 到 `/tmp`，再 `tar -C $DSH_HOME -xf` | 不复制 sessions/storages/.credentials |
| install | 容器内 `pnpm install --no-frozen-lockfile` | 使用镜像 pnpm；`onlyBuiltDependencies` |
| marker | `$DSH_HOME/.dsh-config-source` | 来源/时间；成功后才写 |
| restart | `kubectl rollout restart statefulset/deepseek-harness` | 保证新 profile 生效 |
| token | 无 | 集群内没有配置仓库凭据 |

### ToolSet（一次性手动任务）

| 组 | 工具 | 安装器 | 目标目录 |
| --- | --- | --- | --- |
| uv | specify-cli、pre-commit、pyrefly、yamllint | `uv tool install` | `$XDG_DATA_HOME/uv/tools`，bin 在 `/workspace/.local/bin` |
| mise | gh、jq、`npm:@colbymchenry/codegraph`、yq、`npm:clawhub`、`github:yusukebe/ax`、`github:Dicklesworthstone/destructive_command_guard`、`github:harehare/mq`、`aqua:atuinsh/atuin` | `mise use -g` | `$MISE_DATA_DIR/installs`，shim 在 `mise/shims` |
| bootstrap | uv、mise | 官方安装脚本 | `/workspace/.local/bin` |
| marker | `/workspace/.local/.dsh-tools-version` | 安装完成标记 | 工具卷重建后重跑 |

**校验**：`uv tool list` 列出 4 个；`mise ls --global` 列出 9 个；`atuin --version`、`codegraph --version`、
`dcg --version`、`gh --version` 可执行；所有路径在 `/workspace/.local` 或 `/workspace/.config` 下。

### WebIngress

| 字段 | 值 |
| --- | --- |
| name | `deepseek-harness` |
| host | `dsh.west-beta.ts.net` |
| className | `tailscale` |
| annotation | `tailscale.com/proxy-group: ingress-proxies` |
| paths | `/` → ClusterIP Service `http:3080`；`/novnc-` → `desktop:6080` |
| tls | Tailscale MagicDNS 证书 |

### DesktopIngress

| 字段 | 值 |
| --- | --- |
| name | `deepseek-harness-desktop` |
| host | `dsh-desktop.west-beta.ts.net` |
| className | `tailscale` |
| annotation | `tailscale.com/proxy-group: ingress-proxies` |
| paths | `/` → ClusterIP Service `desktop:6080` |
| auth | 无；仅 tailnet 可达 |

### TailscaleBackendService

| 字段 | 值 | 说明 |
| --- | --- | --- |
| name | `deepseek-harness-tailscale` | 新增；不能复用 Headless Service |
| type | ClusterIP | Tailscale Operator 要求 |
| ports | http 3080、desktop 6080 | targetPort 同名容器端口 |
| selector | 与 StatefulSet 相同的 selector labels | 唯一 Pod |
| ipFamilyPolicy | PreferDualStack | 与集群双栈一致 |

### NetworkPolicyRule

| 字段 | 值 |
| --- | --- |
| source | 不限制（Cilium SNAT 后源身份为 `world`，源选择器不可匹配） |
| ports | TCP 3080、TCP 6080 |
| other ingress | 拒绝（上游默认） |
| known ceiling | 收紧源需要先调整 Cilium `ipv4NativeRoutingCIDR` 覆盖 Pod CIDR；见 README |

### BackupTargetSet

| PVC | 备份责任 |
| --- | --- |
| `dsh-home-deepseek-harness-0` | 用户后续手动配置 |
| `deepseek-harness-workspace` | 用户后续手动配置 |
| `deepseek-harness-tools` | 用户后续手动配置（可重建，但仍列入） |
| `deepseek-harness-skills` | 用户后续手动配置（可从本机重建，但仍列入） |

**约束**：不得在 `scripts/backup-coverage` 的 `is_exempt()` 中为上述 PVC 添加豁免；用户配置备份前，
该脚本会列出它们，属预期。

## 关系

- `ProviderCredentialsSecret` → 主容器 env（`DEEPSEEK_API_KEY`、`GITHUB_API_TOKEN`）；不参与配置 clone。
- `ConfigSyncRun` → 本机 `gh`/`~/.dsh` → `kubectl cp` → `DSHHomeVolume`；`pnpm install` 使用镜像 pnpm，
  store 在 dsh-home（镜像 env `npm_config_store_dir`），`ToolsVolume` 只提供 uv/mise 工具。
- `ToolSet` → `ToolsVolume`；DSH 通过 `PATH` 使用 shims。
- `TailscaleBackendService` → 两条 Ingress；两条 Ingress 的代理来自 `ingress-proxies`；NetworkPolicy 只按端口放行（源选择器受 Cilium SNAT 限制）。
- `WorkspaceVolume` / `ToolsVolume` / `SkillsVolume` 挂载到主容器；`DSHHomeVolume` 由 StatefulSet 模板生成。
- `BackupTargetSet` → 四块 PVC；由用户后续手动接入备份。

## 状态转换

```text
[Secret 创建] → ArgoCD 部署 → Pod 启动（无 init）→ Ready
  → 手动 install-tools: 工具卷为空 → 安装 uv/mise/工具 → 写 marker
  → 手动 sync-config: 本机 gh/~/.dsh → 改写 → cp → pnpm install → 写 source marker → 重启
  → 手动 sync-skills: 本机 → skills PVC
  → 两条 Ingress 可用 → tailnet 访问

[配置变化] → 重新执行 sync-config → 重启
[镜像 tag 变化] → Pod 模板变化 → 滚动重启；工具/配置卷保留
[工具卷重建] → 重新执行 install-tools
[Secret 轮换] → 更新 Secret → 手动重启 Pod
[节点故障/RWO] → Pod 可能无法调度；PVC 与节点绑定，需要接受或迁移
[备份] → 用户后续手动配置；本特性不自动创建 ReplicationSource
```

**校验规则**：

- 四块 PVC 的 size/accessMode 必须与 spec 一致；独立 PVC 必须有 keep/prune 注解。
- `dsh-home` 不能因 StatefulSet 删除而删除。
- 手动 sync 成功前不得写 `.dsh-config-source`；失败可重跑。
- 任何 `sessions/`、`storages/`、`.credentials.yaml` 在同步前后 hash/存在性不变。
- Ingress 后端必须是 ClusterIP Service，不能是 Headless Service。
- NetworkPolicy 未放行时，非 `tailscale` Pod 到 3080/6080 必须失败。
- `scripts/backup-coverage` 不得出现四块 PVC 的豁免项。
