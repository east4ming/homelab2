# 实施方案：DSH 在集群内以 cluster-admin 管理集群

**Branch**: `016-dsh-cluster-admin` | **Date**: 2026-11-13 | **Spec**: [spec.md](spec.md)
**目标集群**: 生产 homelab2（ArgoCD 自动同步 `master`）

## 判定摘要

| 问题 | 现状 | 结论 |
| --- | --- | --- |
| Pod 有没有身份 | `automountServiceAccountToken: false`，无 SA | 建专用 SA，Pod 显式 `serviceAccountName` + 自动挂载 token |
| 给多大权限 | 无 | 绑定内置 `cluster-admin`；不自定义 ClusterRole |
| 凭据怎么进来 | 没有 | kubelet 挂载 SA token；`kubectl` 自动使用 in-cluster 配置，不放 kubeconfig |
| `kubectl` 从哪来 | 工具卷上的 mise 工具（未列入清单） | 把 `kubectl` 加入 `install-tools.sh` 的 mise 清单与校验 |
| 安全边界 | 仅 tailnet | 文档写明「能进 DSH = 集群 root」，并给出收回权限的方法 |
| 发布 CLI | 文档写 `tea` | 更新为 `gt`（Gitea 官方 CLI 现名）；历史任务记录保留并加注 |

## 变更清单

| 路径 | 改动 |
| --- | --- |
| `apps/deepseek-harness/templates/rbac.yaml` | 新增 `ServiceAccount` 与指向 `cluster-admin` 的 `ClusterRoleBinding` |
| `apps/deepseek-harness/templates/statefulset.yaml` | `serviceAccountName` + `automountServiceAccountToken: true` |
| `apps/deepseek-harness/Chart.yaml` | `version: 0.1.29-homelab.2` |
| `apps/deepseek-harness/files/install-tools.sh` | mise 清单与校验加入 `kubectl` |
| `apps/deepseek-harness/README.md` | 差异表、集群权限章节（验证命令、安全边界、收回方法）、工具清单、限制 |
| `docs/reference/versioning.md` | Release 命令 `tea` → `gt`（位置参数 tag、`-R`、`--verify-tag`） |
| `specs/015-deepseek-harness-helm/{quickstart,plan,tasks}.md` | 可执行文档改用 `gt`；历史任务项注明当时的 `tea` |
| `specs/016-dsh-cluster-admin/*` | 本特性的 spec/plan/tasks |
| `AGENTS.md` | 当前 Plan 指针指向本文件 |
| `docs/reference/changelog.md` | 新增 `v2026.11.13` 条目 |

渲染结果（关键片段）：

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: deepseek-harness
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: deepseek-harness
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: cluster-admin
subjects:
  - kind: ServiceAccount
    name: deepseek-harness
    namespace: deepseek-harness
```

## 为什么不用自定义 ClusterRole

内置 `cluster-admin` 覆盖了「任何资源、任何 namespace、任何动词」，包括 CRD、子资源、`kubectl auth
reconcile`、`kubectl apply --server-side`。自己拼一份等价 ClusterRole 会在新增 CRD/API group 时静默失效，
而需求就是「方便管理整个集群」。`system/helm-dashboard` 已有同样先例。

## 安全边界

- 进入 DSH（Web 401 + cookie，或 tailnet 内 noVNC 无认证）即等价于集群管理员。
- DSH 不能暴露到公网；Tailscale ACL 是唯一网络边界。
- 收回：删除 `ClusterRoleBinding/deepseek-harness`，或把绑定换成只读 ClusterRole；SA token 本身不删除。

## 验证计划

| 验证 | 方式 | 通过条件 |
| --- | --- | --- |
| Chart 语法 | `helm lint apps/deepseek-harness` | 0 退出 |
| 渲染契约 | `helm template` + `yq` 断言 | 1 SA、1 ClusterRoleBinding（`roleRef.name=cluster-admin`）、Pod 的 `serviceAccountName` 与 `automountServiceAccountToken: true` |
| 代码质量 | `pre-commit run --all-files` | 全部通过 |
| 文档构建 | `mkdocs build --strict` | 通过 |
| 线上身份 | Pod 内 `kubectl auth can-i '*' '*' --all-namespaces`、`kubectl get nodes` | `yes` / 列出节点 |
| 跨入口 | 维护者机器 `kubectl exec ... -- kubectl get nodes` | 成功 |
| 收权 | 临时删 CRB 后 `kubectl get nodes` | `Forbidden`；恢复 CRB 后恢复 |
| 发布 | 双侧 tag/Release 与 Changelog | 一致 |

## 风险与回退

- **爆炸半径**：`cluster-admin` 本身没有技术缓解，靠「单人 + tailnet」边界；文档写明，不要公网暴露。
- **自重启**：Pod template 变更触发 StatefulSet 重建，正在运行的 DSH 会话会中断；会话数据在 PVC 上，
  重启后可继续。发布动作在 ArgoCD 同步窗口之前完成。
- **kubectl 缺失**：工具卷重建后 `kubectl` 不在 PATH；重跑 `scripts/install-dsh-tools`。
- **回退**：`git revert` 合并提交，ArgoCD 同步上一状态；或只删 `ClusterRoleBinding` 收回权限。

## 发布

1. 更新 `docs/reference/changelog.md`（`v2026.11.13`）。
2. `git tag -a v2026.11.13 -m "状态快照：DSH 获得集群管理权限"`，推送 Gitea + GitHub，双侧复核。
3. `gt release create v2026.11.13 -R ops/homelab2 --title v2026.11.13 --notes-file ... --verify-tag`；
   `gh release create v2026.11.13 -R east4ming/homelab2 --verify-tag --title ... --notes-file ...`。
