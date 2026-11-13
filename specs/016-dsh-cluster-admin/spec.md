# Feature Specification: DSH 在集群内以 cluster-admin 管理集群

**Feature Branch**: `016-dsh-cluster-admin`

**Created**: 2026-11-13

**Status**: Implemented

**Input**: 用户要求「dsh 应该有 cluster-admin clusterrole 权限，以方便在 k8s 集群内管理 k8s」，并按
`AGENTS.md` 与 `docs/reference/versioning.md` 走完整开发与发布流程；同时把 Gitea 官方 CLI 的文档从
`tea` 更新为 `gt`。

## 背景与现状

DeepSeek Harness（DSH）以单副本 StatefulSet 跑在 homelab2 里，是维护者日常操作的入口：Web 侧栏终端、
内置桌面都能执行命令。但 Chart 最初按最小权限设计：

| 现状 | 影响 |
| --- | --- |
| `automountServiceAccountToken: false`，没有 `serviceAccountName` | Pod 里没有 SA token，`kubectl` 无法认证 |
| 没有 ServiceAccount / ClusterRoleBinding | 即使挂上 token 也没有任何权限 |
| `kubectl` 只在工具卷上（`scripts/install-dsh-tools` 安装） | 工具存在但没有凭据，`kubectl get nodes` 报 `no configuration` |

结果是 DSH 里能写清单、能让 ArgoCD 拉取，却不能直接查看或操作集群；每次要绕到维护者机器。

## User Scenarios & Testing

### User Story 1 - 在 DSH 里直接管理 homelab2 集群（Priority: P1）

作为 homelab2 维护者，我希望在 DSH 的终端里直接 `kubectl get nodes` / `kubectl -n <ns> ...`，
不必回维护者机器，也不用往 Pod 里塞 kubeconfig。

**Why this priority**: 这是本需求的全部目的；DSH 是唯一常驻的交互入口。

**Independent Test**: Pod Ready 后，在 DSH 终端执行 `kubectl get nodes` 返回集群节点；
`kubectl auth can-i '*' '*' --all-namespaces` 返回 `yes`；从维护者机器
`kubectl -n deepseek-harness exec statefulset/deepseek-harness -- kubectl get nodes` 同样成功。

**Acceptance Scenarios**:

1. **Given** Chart 已同步，**When** 查看 Pod，**Then** `serviceAccountName=deepseek-harness` 且
   SA token 挂载在 `/var/run/secrets/kubernetes.io/serviceaccount/`。
2. **Given** SA token 已挂载，**When** 在 Pod 内执行 `kubectl auth can-i '*' '*' --all-namespaces`，
   **Then** 输出 `yes`；`kubectl get nodes` 正常列出节点。
3. **Given** 需要收回权限，**When** 删除 `ClusterRoleBinding/deepseek-harness`，**Then** 后续
   `kubectl` 调用被 RBAC 拒绝，无需重建 Pod。
4. **Given** 工具卷是新建的，**When** 执行 `scripts/install-dsh-tools`，**Then** `kubectl` 可执行。

### User Story 2 - 文档使用当前的 Gitea CLI（Priority: P2）

作为维护者，我希望发布流程的文档写的是 `gt`（Gitea 官方 CLI 现名），避免照着旧文档执行 `tea` 失败。

**Why this priority**: 文档是发布流程的唯一入口；命令名过期会让下一次发布卡住。

**Independent Test**: 在本机执行 `gt release create --help`，参数与文档一致；
`docs/` 与 `specs/016` 中不再出现 `tea releases` 之类的可执行命令。

**Acceptance Scenarios**:

1. **Given** 已安装 `gt`，**When** 按 `docs/reference/versioning.md` 的示例创建 Release，
   **Then** 参数（位置参数 tag、`-R`、`--title`、`--notes-file`、`--verify-tag`）被 `gt` 接受。
2. **Given** 查历史记录，**When** 阅读 `specs/015` 已完成的任务项，**Then** 仍能看到当时使用 `tea`
   的事实，并指向新命令名。

### User Story 3 - 走完整发布流程（Priority: P2）

作为维护者，我希望这次改动按 `docs/reference/versioning.md` 发布，便于回滚。

**Independent Test**: 两侧远端都有 `v2026.11.13` 标签且指向同一提交；Gitea 与 GitHub 都有 Release；
`docs/reference/changelog.md` 有对应条目。

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Chart MUST 创建 `ServiceAccount`（名称取 `fullname`，位于 release namespace）。
- **FR-002**: MUST 通过 `ClusterRoleBinding` 绑定内置 `ClusterRole/cluster-admin`；MUST NOT 自定义
  一份等价 ClusterRole。
- **FR-003**: StatefulSet Pod MUST 设置 `serviceAccountName` 与 `automountServiceAccountToken: true`。
- **FR-004**: `scripts/install-dsh-tools` MUST 安装 `kubectl`，且文档 MUST 说明 Pod 内直接使用
  in-cluster 配置、不需要 `KUBECONFIG`。
- **FR-005**: README MUST 记录安全边界（谁能访问 DSH 谁就有集群 root）与收回权限的方法。
- **FR-006**: Chart `version` MUST 递增；渲染结果 MUST 通过 `helm lint` 与 `helm template` 断言。
- **FR-007**: 发布文档 MUST 使用 `gt` 的现行命令形式（`gt release create <tag> -R ...`），
  并区分「历史记录里的 `tea`」与「现在的 `gt`」。
- **FR-008**: 发布 MUST 更新 Changelog、打 annotated tag `v2026.11.13`、推送 Gitea + GitHub 并双侧复核，
  两侧建 Release。

### Edge Cases

- **Pod 重启 / token 轮换**：SA token 由 kubelet 自动轮换，`kubectl` 每次调用读取文件，无需人工续期。
- **只读根文件系统**：`kubectl` 的 cache 写到 `$HOME/.kube`（`/workspace`，可写 PVC），不受影响。
- **工具卷重建**：`kubectl` 缺失时 `scripts/install-dsh-tools` 重跑即可；RBAC 与 token 不受影响。
- **合入即自重启**：本次改动修改 Pod template，ArgoCD 同步会重建正在承载本会话的 Pod。发布步骤必须在
  同步窗口内完成，或重启后继续；这是本仓库「合并即上线」的固有行为。
- **权限收回**：删 ClusterRoleBinding 立即生效；想只读则换成只读 ClusterRole 的绑定。

## Success Criteria *(mandatory)*

- **SC-001**: Pod 内 `kubectl auth can-i '*' '*' --all-namespaces` 返回 `yes`，`kubectl get nodes` 成功。
- **SC-002**: `helm lint` 通过；`helm template` 渲染出 1 个 ServiceAccount、1 个指向 `cluster-admin` 的
  ClusterRoleBinding，Pod 的 `serviceAccountName` / `automountServiceAccountToken` 正确。
- **SC-003**: `pre-commit run --all-files` 与 `mkdocs build --strict` 通过。
- **SC-004**: `docs/reference/versioning.md` 的发布命令可直接在 `gt` 上执行；可执行文档中不再有 `tea`。
- **SC-005**: `v2026.11.13` 在两个远端存在且指向同一提交，两侧 Release 正文与 Changelog 一致。

## Assumptions

- DSH 实例是单用户、仅 tailnet 可达；授予 `cluster-admin` 是用户明确要求，接受爆炸半径。
- ArgoCD 的 `default` AppProject 允许 cluster-scoped 资源（`system/helm-dashboard` 已有先例）。
- 集群已装 `gt`；发布需要维护者的 Gitea/GitHub 凭据。
