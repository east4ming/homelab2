# 快速验证：DeepSeek Harness Helm 安装

> 在实施分支 `015-deepseek-harness-helm` 上按顺序执行；生产变更通过 PR → `master` → ArgoCD。
> 工具安装、配置同步、skills 同步都是一次性手动任务，必须在 Pod 启动后执行。

## 0. 前置

| 依赖 | 检查 |
| --- | --- |
| kubectl 可访问 homelab2 | `kubectl get nodes` |
| helm | `helm version --short` |
| 本机在 tailnet 内 | `tailscale status` |
| 本机 env 有 `DEEPSEEK_API_KEY`、`GITHUB_API_TOKEN` | `test -n "$DEEPSEEK_API_KEY" && test -n "$GITHUB_API_TOKEN"` |
| 本机 skills | `test -d "$HOME/.agents/skills"` |
| （可选）本机 `gh` 已登录，用于 `--repo` 模式 | `gh auth status` |
| 本机有 `jq`、`yq`、`tar` | `jq --version; yq --version; tar --version` |

## 1. 创建 Secret（在合并/首次同步之前）

```sh
export DEEPSEEK_API_KEY=...
export GITHUB_API_TOKEN=...

scripts/bootstrap-deepseek-harness
```

预期：

- 输出只列键名，不打印值。
- `kubectl -n deepseek-harness get secret dsh-provider-credentials -o jsonpath='{.data}'` 包含
  `DEEPSEEK_API_KEY`、`GITHUB_API_TOKEN`；没有 `DSH_CONFIG_TOKEN`。
- 脚本可重复执行；不会产生空 Secret。

## 2. 本地渲染与门禁

```sh
helm lint apps/deepseek-harness
helm template deepseek-harness apps/deepseek-harness \
  --namespace deepseek-harness > /tmp/dsh-render.yaml

# 关键断言
yq -e 'select(.kind == "StatefulSet") | (.spec.template.spec.initContainers // []) | length == 0' /tmp/dsh-render.yaml
yq -e 'select(.kind == "Service" and .metadata.name == "deepseek-harness-tailscale") | .spec.type == "ClusterIP"' /tmp/dsh-render.yaml
yq -e 'select(.kind == "Ingress" and .metadata.name == "deepseek-harness") | .spec.rules[0].http.paths | length == 2' /tmp/dsh-render.yaml
yq -e 'select(.kind == "Ingress" and .metadata.name == "deepseek-harness-desktop") | .spec.rules[0].host == "dsh-desktop.west-beta.ts.net"' /tmp/dsh-render.yaml
yq -e 'select(.kind == "NetworkPolicy") | .spec.ingress[0].ports | length == 2' /tmp/dsh-render.yaml
```

```sh
pre-commit run --files \
  apps/deepseek-harness/Chart.yaml apps/deepseek-harness/values.yaml \
  apps/deepseek-harness/values.schema.json apps/deepseek-harness/templates/*.yaml \
  apps/deepseek-harness/files/*.sh scripts/bootstrap-deepseek-harness \
  scripts/install-dsh-tools scripts/sync-dsh-config scripts/sync-dsh-skills \
  apps/homepage/values.yaml test/smoke_test.go
```

预期：`helm lint` 通过；渲染断言全部退出 0；yamllint/helmlint/shellcheck/private-key 无失败。

## 3. 合并与 ArgoCD 同步

1. 推送分支，创建 PR，按 `docs/reference/versioning.md` 使用 Conventional Commits。
2. 合并到 `master`；ArgoCD ApplicationSet 自动创建 `deepseek-harness` 应用与命名空间。
3. 观察：

```sh
kubectl -n deepseek-harness get pod,svc,ingress,pvc,networkpolicy -o wide
POD=$(kubectl -n deepseek-harness get pod -l app.kubernetes.io/name=deepseek-harness \
  -o jsonpath='{.items[0].metadata.name}')
kubectl -n deepseek-harness logs "$POD" -c deepseek-harness --tail=50 | grep -E 'dsh web:|error|plugin'
```

预期：Pod 直接 Ready（没有 init 阶段）；日志有 `dsh web: ...token=...`；无插件加载错误（此时尚未同步配置，
使用镜像默认 profile）。

## 4. 一次性安装工具

```sh
scripts/install-dsh-tools
```

预期：

- 脚本复制 `install-tools.sh` 到 `/tmp` 并执行；uv/mise/工具装到工具卷。
- `kubectl -n deepseek-harness exec "$POD" -c deepseek-harness -- bash -lc '
    export HOME=/workspace
    export XDG_DATA_HOME=/workspace/.local/share XDG_CONFIG_HOME=/workspace/.config
    export PATH=/workspace/.local/bin:/workspace/.local/share/mise/shims:$PATH
    uv tool list; mise ls --global
  '`
- 4 个 uv 工具 + 9 个 mise 工具（含 atuin）。
- 无需重启；后续 exec 直接可用。

## 5. 一次性同步配置

### 5.1 直接用本机 `~/.dsh`

```sh
scripts/sync-dsh-config --source "$HOME/.dsh"
```

### 5.2 或使用本机 `gh` 拉取私有仓库

```sh
scripts/sync-dsh-config --repo east4ming/dsh-config --revision <ref>
```

脚本会：复制白名单配置 → 本地改写 → tar → `kubectl cp` → 容器内解包 → `pnpm install` → 写
`$DSH_HOME/.dsh-config-source` → `kubectl rollout restart statefulset/deepseek-harness` → 等待 Ready。

```sh
# 重启后刷新 Pod 名
POD=$(kubectl -n deepseek-harness get pod -l app.kubernetes.io/name=deepseek-harness \
  -o jsonpath='{.items[0].metadata.name}')
```

预期：

- 命令退出 0；Pod 重启后 Ready。
- `kubectl -n deepseek-harness exec "$POD" -c deepseek-harness -- cat /home/node/.dsh/.dsh-config-source`
  有来源/时间。
- `profiles/web`、`local-plugins`、`local-presets`、`skills` 等到位；配置中无 `/home/casey/.dsh`。
- 插件安装成功；市场页面可用；`dshmarket` 为镜像内置 1.66.9。
- 集群内没有 `DSH_CONFIG_TOKEN`。

## 6. 同步本机 skills

```sh
scripts/sync-dsh-skills
```

预期：`/workspace/.agents/skills` 出现本机同名目录；DSH 技能目录能发现新增 skill；1Gi PVC 未满。

## 7. Tailscale 访问

```sh
curl -k -sS -o /dev/null -w '%{http_code}\n' https://dsh.west-beta.ts.net
# 预期 401（未认证）

kubectl -n deepseek-harness logs "$POD" | grep 'dsh web:'
# 打开打印出的带 token URL；进入 UI 后做一次 deepseek-flash 对话

curl -k -sS -o /dev/null -w '%{http_code}\n' https://dsh-desktop.west-beta.ts.net
# 预期 200（noVNC 无认证）
```

- Web UI 侧栏的“浏览器桌面”入口应打开同一 noVNC；它走
  `https://dsh.west-beta.ts.net/novnc-...`。
- UI 左下角不应显示“重新连接中”；若显示，说明 `/api/remote.mux` WebSocket 被 403，检查 Chart 是否把
  `ingress.web.host` 传给了 `--trusted-host`（设置页权限报 `permission catalog has no active Host connection`
  是同一根因）。
- noVNC 无认证是预期行为；只能从 tailnet 访问。

## 8. NetworkPolicy 正反例

```sh
POD_IP=$(kubectl -n deepseek-harness get pod -l app.kubernetes.io/name=deepseek-harness \
  -o jsonpath='{.items[0].status.podIP}')

kubectl -n default run dsh-np-test --rm -i --restart=Never \
  --image=curlimages/curl --command -- \
  curl -m 3 -sS -o /dev/null -w '%{http_code}\n' "http://${POD_IP}:3080"
# 预期：401（策略按端口放行；Cilium SNAT 使源选择器失效）

kubectl -n default run dsh-np-deny --rm -i --restart=Never \
  --image=curlimages/curl --command -- \
  curl -m 3 -sS -o /dev/null -w '%{http_code}\n' "http://${POD_IP}:9222"
# 预期：超时/连接失败（9222 不在放行端口列表）
```

- 从 tailnet 访问 3080/6080 成功（第 7 步）。
- 3080/6080 对集群内 Pod 可达（源身份被 SNAT 成节点 IP，无法只放行 ingress proxies）；9222 等未列端口被拒。
- 这是已知取舍；收紧源需要先调整 Cilium native routing 覆盖 Pod CIDR。

## 9. 工具、配置、插件

```sh
kubectl -n deepseek-harness exec "$POD" -c deepseek-harness -- bash -lc '
  export HOME=/workspace
  export XDG_DATA_HOME=/workspace/.local/share XDG_CONFIG_HOME=/workspace/.config
  export PATH=/workspace/.local/bin:/workspace/.local/share/mise/shims:$PATH
  uv --version; mise --version
  uv tool list
  mise ls --global
  atuin --version; codegraph --version; dcg --version; gh --version
  cat /home/node/.dsh/.dsh-config-source
'
```

预期：

- `uv tool list`：specify-cli、pre-commit、pyrefly、yamllint。
- `mise ls --global`：gh、jq、codegraph、yq、clawhub、ax、dcg、mq、atuin。
- 插件列表与同步配置一致；市场页面可用且无重复行；`dshmarket` 版本为镜像内置 1.66.9。

## 10. 持久化验证

```sh
kubectl -n deepseek-harness exec "$POD" -c deepseek-harness -- bash -lc '
  touch /home/node/.dsh/.persist-home
  touch /workspace/.persist-workspace
  touch /workspace/.local/.persist-tools
  touch /workspace/.agents/skills/.persist-skills
'
kubectl -n deepseek-harness delete pod "$POD"
# 等待新 Pod Ready
kubectl -n deepseek-harness exec <newpod> -c deepseek-harness -- bash -lc '
  ls -l /home/node/.dsh/.persist-home /workspace/.persist-workspace \
        /workspace/.local/.persist-tools /workspace/.agents/skills/.persist-skills
'
```

预期：四个标记都存在；工具命令无需重装即可用；配置无需重同步。

验证完成后清理标记：

```sh
kubectl -n deepseek-harness exec <newpod> -c deepseek-harness -- bash -lc '
  rm -f /home/node/.dsh/.persist-home /workspace/.persist-workspace \
        /workspace/.local/.persist-tools /workspace/.agents/skills/.persist-skills
'
```

### 卸载保留演练（隔离命名空间，可选但推荐）

```sh
helm install dsh-retention apps/deepseek-harness -n dsh-retention --create-namespace
kubectl -n dsh-retention get pvc
helm uninstall dsh-retention -n dsh-retention
kubectl -n dsh-retention get pvc   # 预期：PVC 仍存在
kubectl delete namespace dsh-retention
```

注意：该演练会创建 4 块 PVC（10Gi/20Gi/20Gi/1Gi）并删除命名空间；只用于验证 keep/prune 注解，不接触生产命名空间。若 Ceph 容量紧张，可跳过并在 PR 记录原因。

## 11. 备份边界（用户后续手动操作）

- 四块 PVC 都是备份对象：`dsh-home-deepseek-harness-0`、`deepseek-harness-workspace`、
  `deepseek-harness-tools`、`deepseek-harness-skills`。
- 本特性**不修改** `scripts/backup-coverage`，也不创建 ReplicationSource。
- 在用户配置备份之前，`./scripts/backup-coverage` 会列出这四块 PVC。这是预期状态，不是本特性的失败；
  备份配置完成后再作为门禁运行。

## 12. 发布

1. 确认 ArgoCD `deepseek-harness` 为 Synced/Healthy；上面所有验收通过。
2. 更新 `docs/reference/changelog.md`，标题为新 tag。
3. 打 annotated tag（按发布日，检查同日是否已有）：

```sh
git checkout master
git pull --ff-only origin master
git tag -a v2026.11.11 -m "状态快照：部署 DeepSeek Harness（市场变体）"
git push origin master v2026.11.11
git ls-remote --tags origin | grep v2026.11.11
git ls-remote --tags https://github.com/east4ming/homelab2.git | grep v2026.11.11
```

4. 双远端 Release：

```sh
gt release create v2026.11.11 -R ops/homelab2 \
  --title v2026.11.11 --notes-file /tmp/release-note.md --verify-tag
gh release create v2026.11.11 -R east4ming/homelab2 --verify-tag \
  --title v2026.11.11 --notes-file /tmp/release-note.md
```

## 13. 回滚

- 用 ArgoCD 将 `deepseek-harness` Sync 到上一个 tag；四块 PVC 保留。
- 代码回滚用 `git revert`，不要重写 `master`。
- 镜像降级前先确认 DSH 数据卷兼容性；备份由用户后续手动配置，必要时先手工保留 `dsh-home`。

## 已知限制

- noVNC 无认证；仅 tailnet。
- `GITHUB_API_TOKEN` 仅用于 mise 限流；`gh` 需手动 `gh auth login`。
- 市场镜像内置 `dshmarket@1.66.9`，低于本机 `1.73.17`；升级镜像 tag 时统一。
- `dsh-chat-import` 不同步；`integrations` 中指向本机项目的路径改写为 `/workspace`。
- 工具/配置/skills 是手动一次性任务；漏跑时 DSH 仍可启动，但工具/插件不完整。
- 4Gi 内存上限若导致 OOM，只调 values，不改结构。
