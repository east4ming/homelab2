# Rook-Ceph v1.20.0 CSI ServiceAccount 命名不匹配 Bug 及修复方案

## 背景

从 rook-ceph v1.19.6 升级到 v1.20.0 后，Ceph mon 数据被升级为 Tentacle ondisk format (v20)，无法降级回 v19.x。同时 v1.20.0 的 CSI operator 存在 ServiceAccount 命名不一致的 bug。

## Bug 症状

升级到 v1.20.0 后，以下 Deployment 和 DaemonSet 无法创建 Pod：

| 组件 | 报错 |
|---|---|
| `rook-ceph.cephfs.csi.ceph.com-ctrlplugin` | `serviceaccount "cephfs-ctrlplugin-sa" not found` |
| `rook-ceph.rbd.csi.ceph.com-ctrlplugin` | `serviceaccount "rbd-ctrlplugin-sa" not found` |
| `rook-ceph.cephfs.csi.ceph.com-nodeplugin` | `nodes is forbidden: ... cannot get resource "nodes"` |
| `rook-ceph.rbd.csi.ceph.com-nodeplugin` | `nodes is forbidden: ... cannot get resource "nodes"` |

## 根因

Rook v1.20.0 的 **CSI operator**（`ceph-csi-controller-manager`）在创建 CSI Deployment/DaemonSet 时，引用的 ServiceAccount 名称使用**旧命名风格**（无 `ceph-csi-` 前缀）：

- `cephfs-ctrlplugin-sa`
- `rbd-ctrlplugin-sa`
- `cephfs-nodeplugin-sa`
- `rbd-nodeplugin-sa`

但 Helm chart 创建的 ServiceAccount 使用**新命名风格**（带 `ceph-csi-` 前缀）：

- `ceph-csi-cephfs-ctrlplugin-sa`
- `ceph-csi-rbd-ctrlplugin-sa`
- `ceph-csi-cephfs-nodeplugin-sa`
- `ceph-csi-rbd-nodeplugin-sa`

名称不匹配导致 Pod 无法通过 ServiceAccount 校验。

### RBAC 权限缺失链

通过拷贝创建的旧风格 SA 缺少**三层 RBAC 权限**，每一层都会导致不同的问题：

| 层级 | 缺失的绑定 | 影响组件 | 症状 |
|---|---|---|---|
| 1. ClusterRoleBinding（集群资源） | `ceph-csi-{type}-ctrlplugin-crb`、`ceph-csi-{type}-nodeplugin-crb` | ctrlplugin, nodeplugin | 无法 list csinodes/volumeattachments/persistentvolumes |
| 2. RoleBinding（Leader Election） | `ceph-csi-leader-election-rolebinding` | ctrlplugin | CSI attacher/resizer/snapshotter 无法 acquire leader lease，volume attach/detach 超时 |
| 3. ClusterRoleBinding（Node 权限） | `ceph-csi-{type}-nodeplugin-crb`、`{type}-csi-nodeplugin` | nodeplugin | 无法 get nodes 信息 |

## 集群环境信息

- **Rook 版本**: v1.20.0
- **Ceph 版本**: v20.2.1 (Tentacle)
- **CSI Operator**: quay.io/cephcsi/ceph-csi-operator:v1.0.1
- **Kubernetes**: k3s
- **部署方式**: Helm umbrella chart（rook-ceph + rook-ceph-cluster + snapshot-controller）

## Workaround 方案

### 第一步：创建缺失的 ServiceAccount

基于已有的新风格 SA 拷贝创建旧风格 SA：

```bash
# 创建 ctrlplugin SA
kubectl get sa -n rook-ceph ceph-csi-cephfs-ctrlplugin-sa -o yaml \
  | sed 's/name: ceph-csi-cephfs-ctrlplugin-sa/name: cephfs-ctrlplugin-sa/' \
  | kubectl apply -f -

kubectl get sa -n rook-ceph ceph-csi-rbd-ctrlplugin-sa -o yaml \
  | sed 's/name: ceph-csi-rbd-ctrlplugin-sa/name: rbd-ctrlplugin-sa/' \
  | kubectl apply -f -

# 创建 nodeplugin SA
kubectl get sa -n rook-ceph ceph-csi-cephfs-nodeplugin-sa -o yaml \
  | sed 's/name: ceph-csi-cephfs-nodeplugin-sa/name: cephfs-nodeplugin-sa/' \
  | kubectl apply -f -

kubectl get sa -n rook-ceph ceph-csi-rbd-nodeplugin-sa -o yaml \
  | sed 's/name: ceph-csi-rbd-nodeplugin-sa/name: rbd-nodeplugin-sa/' \
  | kubectl apply -f -
```

### 第二步：绑定 RBAC 权限（三层全部）

旧风格 SA 缺少三层 RBAC 绑定，必须全部补齐：

#### 2a. NodePlugin ClusterRoleBinding（集群级 node 访问权限）

```bash
# cephfs nodeplugin
kubectl patch clusterrolebinding ceph-csi-cephfs-nodeplugin-crb --type=json \
  -p='[{"op": "add", "path": "/subjects/-", "value": {"kind": "ServiceAccount", "name": "cephfs-nodeplugin-sa", "namespace": "rook-ceph"}}]'

kubectl patch clusterrolebinding cephfs-csi-nodeplugin-role --type=json \
  -p='[{"op": "add", "path": "/subjects/-", "value": {"kind": "ServiceAccount", "name": "cephfs-nodeplugin-sa", "namespace": "rook-ceph"}}]'

# rbd nodeplugin
kubectl patch clusterrolebinding ceph-csi-rbd-nodeplugin-crb --type=json \
  -p='[{"op": "add", "path": "/subjects/-", "value": {"kind": "ServiceAccount", "name": "rbd-nodeplugin-sa", "namespace": "rook-ceph"}}]'

kubectl patch clusterrolebinding rbd-csi-nodeplugin --type=json \
  -p='[{"op": "add", "path": "/subjects/-", "value": {"kind": "ServiceAccount", "name": "rbd-nodeplugin-sa", "namespace": "rook-ceph"}}]'
```

#### 2b. CtrlPlugin ClusterRoleBinding（集群级 CSI 资源权限）

ctrlplugin 需要 list/watch csinodes、volumeattachments、persistentvolumes：

```bash
# cephfs ctrlplugin
kubectl patch clusterrolebinding ceph-csi-cephfs-ctrlplugin-crb --type=json \
  -p='[{"op": "add", "path": "/subjects/-", "value": {"kind": "ServiceAccount", "name": "cephfs-ctrlplugin-sa", "namespace": "rook-ceph"}}]'

# rbd ctrlplugin
kubectl patch clusterrolebinding ceph-csi-rbd-ctrlplugin-crb --type=json \
  -p='[{"op": "add", "path": "/subjects/-", "value": {"kind": "ServiceAccount", "name": "rbd-ctrlplugin-sa", "namespace": "rook-ceph"}}]'
```

#### 2c. Leader Election RoleBinding（leases 权限——关键！）

ctrlplugin 中的 csi-attacher、csi-resizer、csi-snapshotter 需要通过 leases 进行 leader election。**如果缺少这个权限，attacher 永远无法成为 leader，导致所有 VolumeAttach/Detach 操作超时：**

```bash
kubectl patch rolebinding ceph-csi-leader-election-rolebinding -n rook-ceph --type=json \
  -p='[
    {"op": "add", "path": "/subjects/-", "value": {"kind": "ServiceAccount", "name": "rbd-ctrlplugin-sa", "namespace": "rook-ceph"}},
    {"op": "add", "path": "/subjects/-", "value": {"kind": "ServiceAccount", "name": "cephfs-ctrlplugin-sa", "namespace": "rook-ceph"}}
  ]'
```

**诊断命令：** 如果 attacher 日志中出现以下错误，说明缺少 leases 权限：
```
E... leaderelection.go:461] "Error retrieving lease lock" err="leases.coordination.k8s.io ... is forbidden: User ... cannot get resource \"leases\"..."
```

修复后（并重启 Pod）应看到：
```
Normal  LeaderElection  ... became leader
```

### 第三步：重启 CSI Pod 使 RBAC 生效

```bash
# 重启 ctrlplugin Deployment
kubectl rollout restart deploy -n rook-ceph \
  rook-ceph.cephfs.csi.ceph.com-ctrlplugin \
  rook-ceph.rbd.csi.ceph.com-ctrlplugin

# 删除 nodeplugin Pod（DaemonSet 会自动重建）
kubectl delete pods -n rook-ceph -l app=rook-ceph.cephfs.csi.ceph.com-nodeplugin
kubectl delete pods -n rook-ceph -l app=rook-ceph.rbd.csi.ceph.com-nodeplugin
```

### 第四步：清理残留资源

RBAC 修复后，CSI attacher 恢复正常，但升级期间会产生大量残留资源需要手动清理。

#### 4a. 删除过期的 Leader Election Leases

旧 Pod 持有的 lease 可能阻止新 attacher 成为 leader：

```bash
kubectl delete lease -n rook-ceph \
  external-attacher-leader-rook-ceph-cephfs-csi-ceph-com \
  external-attacher-leader-rook-ceph-rbd-csi-ceph-com 2>/dev/null
```

#### 4b. 强制清理卡死的 VolumeAttachment

升级期间 CSI attacher 不可用，会产生大量带有 `deletionTimestamp` 但 `attached: true` 的 VolumeAttachment。这些需要移除 finalizer 才能删除：

```bash
# 列出所有卡在删除中的 VA
kubectl get volumeattachment -o jsonpath='{range .items[?(@.metadata.deletionTimestamp)]}{.metadata.name}{" — attached: "}{.status.attached}{"\n"}{end}'

# 强制清除所有卡死 VA 的 finalizer
kubectl get volumeattachment -o jsonpath='{range .items[?(@.metadata.deletionTimestamp)]}{.metadata.name}{"\n"}{end}' | while read va; do
  [ -z "$va" ] && continue
  kubectl patch volumeattachment "$va" --type=merge -p '{"metadata":{"finalizers":null}}'
  echo "cleared: $va"
done
```

**诊断命令：** 如果 PVC 挂载日志出现 Multi-Attach error 或 timed out waiting for external-attacher，大概率是残留 VA 未清理。

#### 4c. 重启受影响的业务 Pod

RBAC 和 VA 清理后，之前因 CSI 不可用而卡住的业务 Pod 需要删除重建：

```bash
# 删除卡在 ContainerCreating/PodInitializing 的业务 Pod
# 示例（gitea）：
kubectl delete pod -n gitea -l app.kubernetes.io/name=gitea

# 批量清理所有非 Running 的 Pod（排除 volsync 和已知应用问题的 Pod）：
kubectl get pods -A --no-headers | grep -v -E 'Running|Completed|volsync' | while read ns pod rest; do
  kubectl delete pod "$pod" -n "$ns" --force --grace-period=0 2>/dev/null
done
```

### 第五步：验证修复

#### CSI 组件验证

```bash
# 1. 所有 rook-ceph Pod 应 Running
kubectl get pods -n rook-ceph | grep -v -E 'Running|Completed'

# 2. CephCluster 状态应为 Ready
kubectl get cephcluster -n rook-ceph

# 3. Ceph 健康状态（HEALTH_WARN 中 Telemetry 告警可忽略）
kubectl exec -n rook-ceph deploy/rook-ceph-tools -- ceph status
```

#### Attacher Leader Election 验证

修复后，attacher/resizer/snapshotter 应成功成为 leader：

```bash
# 查看 leader election 事件（应有 5 个 became leader）
kubectl get events -n rook-ceph --sort-by='.lastTimestamp' | grep LeaderElection | tail -5
```

预期输出示例：
```
Normal  LeaderElection  ... external-attacher-leader-rook-ceph-rbd-csi-ceph-com became leader
Normal  LeaderElection  ... external-attacher-leader-rook-ceph-cephfs-csi-ceph-com became leader
Normal  LeaderElection  ... external-resizer-rook-ceph-rbd-csi-ceph-com became leader
Normal  LeaderElection  ... external-snapshotter-leader-rook-ceph-rbd-csi-ceph-com became leader
Normal  LeaderElection  ... external-snapshotter-leader-rook-ceph-cephfs-csi-ceph-com became leader
```

#### 业务 Pod 验证

```bash
# 确认使用 rook PV 的业务 Pod 均正常（排除 volsync 和已知非 rook 问题的 Pod）
kubectl get pods -A --no-headers | grep -v -E 'Running|Completed|volsync'
```

#### 残留 VolumeAttachment 验证

```bash
# 确认无卡死的 VA
kubectl get volumeattachment -o jsonpath='{range .items[?(@.metadata.deletionTimestamp)]}{.metadata.name}{"\n"}{end}' | wc -l
# 输出应为 0
```

---

## 附录：RBAC 绑定映射总表

以下表格记录了从「旧 SA 名称」→「需要绑定的 ClusterRoleBinding/RoleBinding」的完整映射：

| 旧 SA 名称 | 绑定的 CRB/RoleBinding | 授予的权限 | 类型 |
|---|---|---|---|
| `cephfs-nodeplugin-sa` | `ceph-csi-cephfs-nodeplugin-crb` | nodes get/list | ClusterRoleBinding |
| `cephfs-nodeplugin-sa` | `cephfs-csi-nodeplugin-role` | nodes get/list | ClusterRoleBinding |
| `rbd-nodeplugin-sa` | `ceph-csi-rbd-nodeplugin-crb` | nodes get/list | ClusterRoleBinding |
| `rbd-nodeplugin-sa` | `rbd-csi-nodeplugin` | nodes get/list | ClusterRoleBinding |
| `cephfs-ctrlplugin-sa` | `ceph-csi-cephfs-ctrlplugin-crb` | csinodes, volumeattachments, persistentvolumes | ClusterRoleBinding |
| `rbd-ctrlplugin-sa` | `ceph-csi-rbd-ctrlplugin-crb` | csinodes, volumeattachments, persistentvolumes | ClusterRoleBinding |
| `cephfs-ctrlplugin-sa` | `ceph-csi-leader-election-rolebinding` | leases (leader election) | RoleBinding |
| `rbd-ctrlplugin-sa` | `ceph-csi-leader-election-rolebinding` | leases (leader election) | RoleBinding |

## 注意事项

1. **这是一个 workaround，不是永久修复。** Rook operator 在 reconcile 时可能会删除这些手动创建的 SA，届时需要重新执行上述步骤。

2. **不要降级到 v1.19.x。** Ceph mon 数据已被升级为 Tentacle ondisk format，旧版 Ceph 无法读取，强行降级会导致 mon 永久 crash。

3. **ArgoCD 自动同步应保持关闭。** 如果 ArgoCD 启用了自动同步，可能会回写 SA 配置导致冲突。建议在 Rook 发布官方修复前保持手动管理。

4. **相关上游 Issue**: 可以关注 [rook/rook#16956](https://github.com/rook/rook/issues/16956) 及相关 CSI operator 问题的修复进展。

## 相关文件

- Helm Chart: `system/rook-ceph/Chart.yaml`
- Values: `system/rook-ceph/values.yaml`
- 部署目标: `rook-ceph` namespace
