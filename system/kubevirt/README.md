# KubeVirt + CDI — k3s GitOps 部署

## 架构

通过 ArgoCD ApplicationSet 自动发现并部署到 k3s 集群。所有组件运行在 `kubevirt` 命名空间。

```text
KubeVirt Operator → virt-api + virt-controller + virt-handler (DaemonSet)
CDI Operator      → cdi-deployment + cdi-uploadproxy
```

## 快速运维

### 检查状态

```bash
# KubeVirt 平台状态
kubectl get kv -n kubevirt kubevirt

# CDI 状态
kubectl get cdi -n kubevirt cdi

# 所有 KubeVirt 组件
kubectl get pods -n kubevirt

# VM 列表
kubectl get vm -n kubevirt
kubectl get vmi -n kubevirt
```

### 虚拟机管理

```bash
# 创建 VM（随 Helm Chart 部署时自动创建，也可手动应用）
kubectl apply -f templates/demo-vm.yaml

# 查看 VM 状态
kubectl get vm -n kubevirt demo-vm
kubectl get vmi -n kubevirt demo-vm

# 串行控制台（启动后约 60 秒 cloud-init 完成）
virtctl console -n kubevirt demo-vm

# 生命周期
virtctl stop -n kubevirt demo-vm       # 关机
virtctl start -n kubevirt demo-vm      # 开机
virtctl restart -n kubevirt demo-vm    # 重启

# VNC 图形界面
virtctl vnc -n kubevirt demo-vm
```

### 镜像管理

```bash
# 查看 DataVolume 导入进度
kubectl get dv -n kubevirt

# 导入失败时排查
kubectl describe dv -n kubevirt demo-vm-rootdisk
kubectl logs -n kubevirt -l cdi.kubevirt.io=cdi-deployment
```

### 持久化磁盘

```bash
# 查看 VM 关联的 PVC
kubectl get pvc -n kubevirt

# 删除 VM 但保留数据磁盘
kubectl delete vm -n kubevirt demo-vm
# PVC demo-vm-datadisk 不会被删除（不在 dataVolumeTemplates 中）
```

## 故障排查

| 症状 | 检查命令 | 常见原因 |
|------|----------|---------|
| VM 无法启动 | `kubectl describe vmi -n kubevirt demo-vm` | 镜像未导入完成 |
| 控制台无响应 | `kubectl logs -n kubevirt virt-launcher-demo-vm-*` | cloud-init 未完成 |
| DataVolume 卡住 | `kubectl get dv -n kubevirt -w` | 镜像 URL 不可达 |
| virt-handler 未就绪 | `kubectl logs -n kubevirt -l kubevirt.io=virt-handler` | `/dev/kvm` 不可用 |

## 镜像更新

更新 Ubuntu Cloud Image 版本：

1. 修改 `values.yaml` 中的 `vm.image` URL
2. 删除旧 DataVolume：`kubectl delete dv -n kubevirt demo-vm-rootdisk`
3. 删除旧 PVC：`kubectl delete pvc -n kubevirt demo-vm-rootdisk`
4. 提交并 push 到 master → ArgoCD 自动同步重新导入

## 版本信息

| 组件 | 版本 | 来源 |
|------|------|------|
| KubeVirt | v1.8.4 | GitHub releases |
| CDI | v1.65.0 | GitHub releases |
| VM OS | Ubuntu 26.04 LTS | cloud-images.ubuntu.com |
