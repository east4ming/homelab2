# KubeVirt + CDI — k3s GitOps 部署

## 架构

通过 ArgoCD ApplicationSet 自动发现并部署到 k3s 集群。所有组件运行在 `kubevirt` 命名空间。

```text
KubeVirt Operator → virt-api + virt-controller + virt-handler (DaemonSet)
CDI Operator      → cdi-deployment + cdi-uploadproxy
```

## 安全配置

### 方式 1: 内联 SSH 公钥

修改 `values.yaml`，不提交到 Git（本地覆盖或 Ansible Vault）：

```yaml
vm:
  sshPublicKey: "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA..."
```

### 方式 2: 外部 cloud-init Secret（推荐，public repo 安全）

```bash
# 手动创建 Secret
kubectl create secret generic my-vm-cloudinit -n kubevirt \
  --from-literal=userdata='#cloud-config
hostname: demo-vm
password: atomic
chpasswd:
  expire: false
ssh_pwauth: true
ssh_authorized_keys:
  - ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA...
'
```

修改 `values.yaml`：
```yaml
vm:
  cloudInitSecretName: "my-vm-cloudinit"
```

设置 `cloudInitSecretName` 后，模板不会渲染 `demo-vm-cloudinit` Secret，VM 直接引用外部 Secret。结合 External Secrets Operator 可自动从 Gitea/外部 KMS 同步。

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

## 部署备注

本次部署踩过的坑，记录在此以免遗忘。

### 前置条件

- **硬件虚拟化**：Intel N100 支持 VT-x，需确认所有节点 `/dev/kvm` 存在且 `kvm_intel` 模块已加载
- **KVM 默认密码禁用**：cloud-init `lock_passwd: true`，只能通过 SSH 密钥或 `virtctl console` 登录

### 关键问题与修复

| # | 问题 | 根因 | 修复 |
|---|------|------|------|
| 1 | CDI 资源命名空间不一致 | 上游 CDI operator 硬编码 `namespace: cdi`，ArgoCD ApplicationSet 部署到 `namespace: kubevirt` | `sed` 全局替换为 `namespace: kubevirt` |
| 2 | CR 与 CRD 同批部署失败 | ArgoCD 校验 CR 时 CRD 尚未注册 | CR 资源加 `argocd.argoproj.io/sync-options: SkipDryRunOnMissingResource=true` |
| 3 | cloud-init 字段名错误 | KubeVirt v1 API 字段为 `secretRef`，非 `userDataSecretRef` | 修正为 `secretRef` |
| 4 | cloud-init Secret key 大小写 | KubeVirt 期望 key 为 `userdata`（全小写），非 `userData` | 修正为 `userdata` |
| 5 | **Cilium netkit MAC 地址** | Cilium `bpf.datapathMode: netkit` 将 pod MAC 设为 `00:00:00:00:00:00` | 切换到 `bpf.datapathMode: netkit-l2`（Cilium ≥ v1.17.3） |
| 6 | `customizeComponents` patch 格式 | Operator 期望 JSON Patch 数组（RFC 6902），非 strategic merge 对象 | `type: json` + `patch: '[{"op":"replace","path":"/spec/replicas","value":1}]'` |
| 7 | VM spec 更新后不生效 | KubeVirt VirtualMachine 类似 StatefulSet OnDelete 策略，`spec.template` 变更不自动重启 | 删除 VMI 触发重建：`kubectl delete vmi -n kubevirt demo-vm` |

### Cilium netkit 与 KubeVirt 兼容性

Cilium `bpf.datapathMode: netkit` 不分配有效 pod MAC 地址。已切换为 `netkit-l2`。

参考：[kubevirt/kubevirt#13782](https://github.com/kubevirt/kubevirt/issues/13782) [cilium/cilium#37265](https://github.com/cilium/cilium/issues/37265)

### KubeVirt VM 更新策略

VirtualMachine 的 `spec.template` 变更后，已运行的 VMI **不会自动重启**。更新步骤：

```bash
# 1. 修改 VM spec（通过 GitOps 或 kubectl edit）
# 2. 删除 VMI，VM controller 立即用新 spec 重建
kubectl delete vmi -n kubevirt demo-vm

# 或使用 virtctl
virtctl restart -n kubevirt demo-vm
```

> 删除 VMI 不影响 VM 资源本身，也不影响持久化磁盘数据。

### Replicas 缩容

homelab 单副本即可（`kubevirt.replicas: 1`）。三处需修改：
- `virt-operator`：operator Deployment 模板直接参数化
- `virt-api` + `virt-controller`：KubeVirt CR 的 `customizeComponents.patches`（JSON Patch 格式）
