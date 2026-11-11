# 契约：一次性 DSH 配置同步（本机 → Pod）

## 适用前提

- DSH Pod 已由 ArgoCD 部署并 Ready。
- 维护者本机已具备 `kubectl`、`jq`、`yq`、`tar`。
- 若使用 `--repo` 模式，本机 `gh auth status` 正常；若直接使用本机 `~/.dsh`，不需要 `gh`。

## 输入

| 输入 | 说明 | 约束 |
| --- | --- | --- |
| `--source DIR` | 默认 `$HOME/.dsh`；直接选本机活配置 | 只读源；不修改本机 |
| `--repo OWNER/REPO --revision REF` | 用本机 `gh repo clone` 拉取私有 dsh-config 到临时目录 | 复用本机 gh 认证；集群无凭据 |
| transformer | `apps/deepseek-harness/files/transform-config.sh` | 本机执行；yq/jq/sed |
| target | Pod 的 `/home/node/.dsh` | 通过 `kubectl cp` + `tar` |
| pnpm | 容器内 pnpm 10.15.1 | `pnpm install --no-frozen-lockfile` |

**不输入**：`DSH_CONFIG_TOKEN`、集群内的 Git 凭据、私有仓库 URL 凭据。

## 复制矩阵

| 源 | 目标 | 删除策略 | 说明 |
| --- | --- | --- | --- |
| `AGENTS.md` | `$DSH_HOME/AGENTS.md` | 覆盖 | 用户工作协议 |
| `profiles/web/*` 白名单文件 | `$DSH_HOME/profiles/web/` | 只覆盖文件 | 不删除 `node_modules`、`.plugin-manager` |
| `profiles/headless/*` 白名单文件 | `$DSH_HOME/profiles/headless/` | 只覆盖文件 | 无依赖 |
| `local-plugins/` | `$DSH_HOME/local-plugins/` | 镜像 | 无运行时数据 |
| `local-presets/` | `$DSH_HOME/local-presets/` | 镜像 | 无运行时数据 |
| `skills/` | `$DSH_HOME/skills/` | 复制不删除 | 保留运行时安装的 skill |
| `skills-manager/repositories.json` | `$DSH_HOME/skills-manager/` | 覆盖 | |
| `dsh-pet/` | `$DSH_HOME/dsh-pet/` | 覆盖 | |
| `integrations/` | `$DSH_HOME/integrations/` | 覆盖 | 路径改写 |
| `dsh-chat-import/` | 不同步 | — | 含本机 `.claude` 路径的缓存 |
| `sessions/`、`storages/`、`.credentials.yaml` | 不触碰 | — | 运行时/凭据 |
| `node_modules/`、`.plugin-manager/`、缓存 | 不同步 | — | 由容器内 pnpm 管理 |

## 改写规则

| 目标 | 规则 | 验证 |
| --- | --- | --- |
| 本机 DSH 路径 | `/home/casey/.dsh` → `/home/node/.dsh` | 配置目录 `grep` 无命中（`skills/` 内容除外） |
| codegraph | `/home/casey/.../codegraph` → `/workspace/.local/share/mise/shims/codegraph` | MCP 行可启动 |
| atuin | `/home/casey/.atuin/bin/atuin` → `/workspace/.local/share/mise/shims/atuin` | `atuin --version` |
| dcg | `/home/casey/.../dcg` → `/workspace/.local/share/mise/shims/dcg` | 破坏性命令被拦截 |
| provider | `deepseek-account` → `deepseek-official` | 模型调用无登录提示 |
| dshmarket | 从 `profiles/web/package.json` 的 dependencies 与 bundles 删除 | 市场无重复行 |
| StyleFerry | tool-hooks `config.post` 置空 | 启动日志无每次调用失败 |
| pnpm 构建 | `pnpm-workspace.yaml` 追加 `onlyBuiltDependencies: [node-pty, cloudflared, protobufjs]` | `pnpm install` 构建原生模块 |
| integrations | `/home/casey/projects/my-stock` → `/workspace` | 路径不存在时插件不报错 |

## 传输与执行

```text
本机 staging/
  → tar -cf /tmp/dsh-config-sync.tar .
  → kubectl cp /tmp/dsh-config-sync.tar <pod>:/tmp/dsh-config-sync.tar
  → kubectl exec <pod> -- tar --no-same-owner -C /home/node/.dsh -xf /tmp/dsh-config-sync.tar
  → kubectl exec <pod> -- bash -lc 'cd /home/node/.dsh/profiles/web && CI=true pnpm install --no-frozen-lockfile'
  → kubectl exec <pod> -- sh -c 'printf "%s\n" "<source> <revision/time>" > /home/node/.dsh/.dsh-config-source'
  → kubectl rollout restart statefulset/deepseek-harness
  → kubectl rollout status statefulset/deepseek-harness
```

- `kubectl cp` 的容器内中转目录是 `/tmp`（emptyDir，512Mi）；tar 包小于该限制。
- 失败时脚本非零退出；不写 `.dsh-config-source`；允许重跑。
- 同步期间 DSH 可能看到部分文件；成功后的重启保证进程以完整新配置启动。
- 不在 Pod 内保存本机 `gh` token；`--repo` 模式的 token 只在本机进程内存/gh 配置中。

## 幂等性

- 每次同步都从源重新生成 staging 并覆盖目标白名单文件；重复执行结果一致。
- 不删除 `sessions/`、`storages/`、`.credentials.yaml`、`node_modules`。
- `pnpm install` 允许更新 PVC 上的 lockfile（link 路径变化后 frozen 会失败）。
- `.dsh-config-source` 记录来源/时间，供审计；不参与自动滚动。
- 配置源变化不会自动触发同步；必须手动重跑脚本。

## 插件安装契约

- `pnpm install` 使用镜像内 pnpm 10.15.1；`onlyBuiltDependencies` 必须生效（实测 10.15.1 忽略
  `allowBuilds`）。
- 安装完成后，profile 中每个 dependency 都存在；DSH 启动日志无 `plugin load` 错误。
- 无法在容器运行的插件：在 `profiles/web/cordis.patch.yml` 中 `disabled: true` 并记录原因；不得因单个插件
  阻塞整个 profile。
- dsh-pet 若因 peer 解析失败，按配置仓库的 `scripts/apply-20260829.sh` 追加
  `@deepseek-ai/dsh-credentials` 与 `dsh-home-paths` 0.1.1-rc.2；否则保持默认。

## 失败语义

| 场景 | 行为 |
| --- | --- |
| 源目录不存在/缺关键文件 | 本机脚本立即失败，不复制 |
| 本机 `gh` 未登录（`--repo`） | 立即失败，提示 `gh auth status` 或改用 `--source` |
| `kubectl cp` 中断 | 失败；Pod 旧配置可能部分更新；重跑覆盖 |
| `pnpm install` 失败 | 失败；不写 `.dsh-config-source`；不重启；旧 node_modules 保留（可能部分更新） |
| `yq`/`jq` 缺失 | 本机脚本失败，提示安装 |
| 配置改写残留 `/home/casey/.dsh` | 脚本失败，不复制 |
