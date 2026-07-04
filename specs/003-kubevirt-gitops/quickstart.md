# Phase 1: 快速上手 — KubeVirt GitOps 部署

**Feature**: 003-kubevirt-gitops | **Date**: 2026-07-04

## 前置条件

- k3s 集群已安装 ArgoCD（ApplicationSet 自动发现已配置）
- 集群已配置持久化存储（Rook-Ceph，StorageClass: `standard-rwo`、`standard-rwx`）
- **所有集群节点 `/dev/kvm` 已可用**（验证：`ls -la /dev/kvm`，应显示 `crw-rw---- 1 root kvm`）
  - 如缺少 `/dev/kvm`：安装 `qemu-kvm` 包，加载 `kvm_intel` 内核模块
- 本地已安装 `kubectl`（kubeconfig 指向目标集群）
- 本地已安装 `virtctl`（KubeVirt CLI 工具）

## 快速开始

### 1. 部署 KubeVirt

提交 Helm Chart 到 Git 仓库后，ArgoCD 自动同步部署。

```bash
# 检查 KubeVirt 组件状态
kubectl get kv -n kubevirt kubevirt
# 期望: NAME AGE PHASE / kubevirt <age> Deployed

kubectl get pods -n kubevirt
# 期望: virt-operator, virt-api, virt-controller (Deployment) + virt-handler (DaemonSet) 全部 Running

# 确认 CDI 就绪
kubectl get cdi -n kubevirt
# 期望: NAME AGE PHASE / cdi <age> Deployed
```

### 2. 创建虚拟机

VM 清单随 KubeVirt Helm Chart 一同部署（或独立提交）。

```bash
# 检查 VM 状态
kubectl get vm -n kubevirt
# 期望: NAME AGE STATUS / demo-vm <age> Running

kubectl get vmi -n kubevirt
# 期望: NAME AGE PHASE / demo-vm <age> Running

# 检查 DataVolume 镜像导入状态
kubectl get dv -n kubevirt
# 期望: NAME PHASE / demo-vm-rootdisk Succeeded
```

### 3. 访问虚拟机控制台

```bash
# 串行控制台（登录后执行命令）
virtctl console -n kubevirt demo-vm

# VNC 图形界面（需要 virtctl vnc 支持）
virtctl vnc -n kubevirt demo-vm
```

### 4. 管理虚拟机生命周期

```bash
# 停止
virtctl stop -n kubevirt demo-vm

# 启动
virtctl start -n kubevirt demo-vm

# 重启
virtctl restart -n kubevirt demo-vm
```

### 5. 验证数据持久化

```bash
# 1. 通过 console 登录 VM，写入测试文件
virtctl console -n kubevirt demo-vm
# (VM 内) echo "persistence-test-$(date)" > /data/test.txt

# 2. 重启 VM
virtctl restart -n kubevirt demo-vm

# 3. 重新连接，验证文件存在
virtctl console -n kubevirt demo-vm
# (VM 内) cat /data/test.txt
# 期望: persistence-test-<timestamp>
```

## 清理

```bash
# 停止 VM
virtctl stop -n kubevirt demo-vm

# 删除 VM（保留 PVC）
kubectl delete vm -n kubevirt demo-vm

# 如需完全清理（删除 PVC 和数据）
kubectl delete pvc -n kubevirt -l kubevirt.io/created-by
```
