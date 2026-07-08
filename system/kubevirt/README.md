# KubeVirt + CDI — k3s GitOps 部署

## 架构

通过 ArgoCD ApplicationSet 自动发现并部署到 k3s 集群。所有组件运行在 `kubevirt` 命名空间。

```text
KubeVirt Operator → virt-api + virt-controller + virt-handler (DaemonSet)
CDI Operator      → cdi-deployment + cdi-uploadproxy
```

## 当前范围

此 Helm Chart 只部署 **KubeVirt 平台 + CDI**。虚拟机创建不在 Chart 中管理。

VM 示例保留在 `examples/demo-vm.yaml`，供后续参考。Ubuntu Cloud Image 的 cloud-init 登录问题待解决后重新纳入。

## 快速运维

### 检查状态

```bash
kubectl get kv -n kubevirt kubevirt
kubectl get cdi -n kubevirt cdi
kubectl get pods -n kubevirt
```

### 创建虚拟机（手动）

使用 KubeVirt 官方 lab 中的 Cirros 示例验证平台可用：

```bash
# 官方 lab: https://kubevirt.io/labs/kubernetes/lab1
kubectl apply -f https://kubevirt.io/labs/manifests/vm.yaml
virtctl console -n default testvm
# 用户名 cirros，密码 gocubsgo
```

参考 VM 定义见 `examples/demo-vm.yaml`。

## 故障排查

| 症状 | 检查命令 | 常见原因 |
|------|----------|---------|
| virt-handler 未就绪 | `kubectl logs -n kubevirt -l kubevirt.io=virt-handler` | `/dev/kvm` 不可用 |
| VM 无法启动 | `kubectl describe vmi -n <ns> <vm>` | 镜像/网络配置错误 |
| KubeVirt 状态 Degraded | `kubectl describe kv -n kubevirt kubevirt` | Operator 未就绪 |

## 版本信息

| 组件 | 版本 | 来源 |
|------|------|------|
| KubeVirt | v1.8.4 | GitHub releases |
| CDI | v1.65.0 | GitHub releases |

## 部署备注

### 前置条件

- **硬件虚拟化**：Intel N100 支持 VT-x，需确认所有节点 `/dev/kvm` 存在且 `kvm_intel` 模块已加载

### 关键问题与修复

| # | 问题 | 根因 | 修复 |
|---|------|------|------|
| 1 | CDI 资源命名空间不一致 | 上游 CDI operator 硬编码 `namespace: cdi` | `sed` 全局替换为 `namespace: kubevirt` |
| 2 | CR 与 CRD 同批部署失败 | ArgoCD 校验 CR 时 CRD 尚未注册 | `SkipDryRunOnMissingResource=true` |
| 3 | cloud-init Secret key | KubeVirt 期望 key 为 `userdata`（全小写） | 修正为 `userdata` |
| 4 | Cilium netkit MAC 地址 | netkit 模式 pod MAC 为全零 | 切换到 `bpf.datapathMode: netkit-l2` |
| 5 | `customizeComponents` patch | Operator 期望 JSON Patch 数组 | `type: json` + RFC 6902 格式 |
| 6 | VM spec 更新不生效 | VirtualMachine 类似 OnDelete 策略 | `kubectl delete vmi` 触发重建 |

### Cilium netkit 与 KubeVirt 兼容性

Cilium `bpf.datapathMode: netkit` 不分配有效 pod MAC 地址。已切换为 `netkit-l2`。

参考：[kubevirt/kubevirt#13782](https://github.com/kubevirt/kubevirt/issues/13782) [cilium/cilium#37265](https://github.com/cilium/cilium/issues/37265)

### Replicas 缩容

homelab 单副本即可（`kubevirt.replicas: 1`）。三处需修改：
- `virt-operator`：operator Deployment 模板直接参数化
- `virt-api` + `virt-controller`：KubeVirt CR 的 `customizeComponents.patches`（JSON Patch 格式）
