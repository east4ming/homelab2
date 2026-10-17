# 启用节点交换内存（Node Swap）

本页说明 homelab2 如何启用 Kubernetes 的节点 swap（NodeSwap）。集群是 k3s
`v1.36.5+k3s1`；NodeSwap 自 Kubernetes v1.34 起 GA。

## 前提

- **cgroup v2**：`stat -f -c %T /sys/fs/cgroup` 输出 `cgroup2fs`。cgroup v1 不支持。
- **节点上已有启用的 swap**：`swapon --show` 非空。本仓库的节点由 Ubuntu 安装器
  创建 `/swap.img`（16 GiB 节点 4 GiB、32 GiB 节点 8 GiB），未纳入 Ansible 管理。
- **SSD/NVMe**：swap 在慢速磁盘上会拖慢整个节点。当前 `/swap.img` 与根分区同在 NVMe。

## 仓库里的配置

`metal/roles/k3s` 把下面的 kubelet drop-in 写到
`/var/lib/rancher/k3s/agent/etc/kubelet.conf.d/90-swap.conf`：

```yaml
apiVersion: kubelet.config.k8s.io/v1beta1
kind: KubeletConfiguration
failSwapOn: false
memorySwap:
  swapBehavior: LimitedSwap
```

三个容易踩的点：

- **只设 `failSwapOn: false` 不够**。k3s 本来就默认 `failSwapOn: false`，kubelet
  也能带着 swap 启动，但 `memorySwap` 的默认值是 `NoSwap`，Pod 的
  `memory.swap.max` 仍然是 `0`。必须显式设 `swapBehavior`。
- **drop-in 不会被 k3s 覆盖**。k3s 每次启动重写同目录下的
  `00-k3s-defaults.conf`；`90-swap.conf` 按文件名字典序排在它后面，覆盖其中的
  `memorySwap` 默认值。
- **控制面也会应用**。本集群 4 台节点都没有 taint、都在跑工作负载，因此 4 台统一
  启用；关键 Pod 仍然拿不到 swap（见下）。

## LimitedSwap 对谁生效

| Pod / 容器 | 能否使用 swap |
| --- | --- |
| Burstable，且 memory request < limit | ✅ |
| Burstable，但 memory request == limit | ❌ |
| Guaranteed | ❌ |
| BestEffort | ❌ |
| 关键 Pod（`kube-system` 静态 Pod 等） | ❌ |

swap 额度由 kubelet 自动计算：

```
(containerMemoryRequest / nodeTotalMemory) × totalPodsSwapAvailable
```

例如 16 GiB 节点、4 GiB swap，request 为 64 MiB 的容器约能使用 16 MiB swap。
调度器**不感知** swap，它只是内存尖峰的保险，不是 RAM 的替代；不要把 request
压到远低于实际工作集。

## 启用与生效

标准路径是重跑 metal 层（会重启 k3s；建议在维护窗口执行）：

```sh
make -C metal cluster
```

只改了这个 drop-in 时，本仓库的上线方式是逐台重启 k3s（避免 3 台 master 同时
重启导致 etcd 短暂失去 quorum）。无论用哪种方式，配置落盘后必须重启 k3s 才会
被 kubelet 读取。

## 验证

```sh
# 1. kubelet 实际配置
kubectl get --raw "/api/v1/nodes/<node>/proxy/configz" \
  | jq '.kubeletconfig | {failSwapOn, memorySwap}'
# { "failSwapOn": false, "memorySwap": { "swapBehavior": "LimitedSwap" } }

# 2. 节点是否上报 swap 容量
kubectl get nodes -o go-template='{{range .items}}{{.metadata.name}}: {{if .status.nodeInfo.swap.capacity}}{{.status.nodeInfo.swap.capacity}}{{else}}<unknown>{{end}}{{"\n"}}{{end}}'

# 3. swap 使用量（刚启用时应为 0，代表"可用"而不是"已用"）
kubectl top nodes --show-swap
kubectl top pods -A --show-swap | head
```

用测试 Pod 确认 QoS 差异（验证完删除）：

```sh
kubectl run swap-check --image=busybox:1.36 --restart=Never \
  --overrides='{"spec":{"containers":[{"name":"swap-check","image":"busybox:1.36","command":["sleep","3600"],"resources":{"requests":{"memory":"64Mi"},"limits":{"memory":"256Mi"}}}]}}'
kubectl exec swap-check -- cat /sys/fs/cgroup/memory.swap.max   # > 0
kubectl delete pod swap-check
```

## 回退

把行为改回 `NoSwap`（临时、逐台）：

```sh
sudo rm /var/lib/rancher/k3s/agent/etc/kubelet.conf.d/90-swap.conf
sudo systemctl restart k3s
```

永久回退需要改仓库（删除该 drop-in 模板与任务）后重跑 metal；否则下次
`make -C metal cluster` 会重新写回。已经运行的 Pod 需要重建才会应用新的
cgroup 限制。

## 风险与限制

- **swap 未加密**：`/swap.img` 是明文。若节点会运行不可信负载，应按上游建议
  使用加密 swap；本仓库未管理。
- **控制面**：上游建议控制面不配置 swap。本集群控制面同时跑工作负载，故保留
  swap；Guaranteed 与关键 Pod 不受影响。
- **noisy neighbor**：swap 不参与调度，内存使用不可预测的 Pod 可能让邻居换出。
  优先只给"峰值高、常驻低"的 Burstable 工作负载。
- **驱逐阈值**：上游建议把 kubelet 内存驱逐阈值设在略低于
  `vm.min_free_kbytes`，让内核先换出再驱逐。本集群未显式配置内存驱逐阈值，
  保持 kubelet 默认。
- **观测**：kubelet 的 `/metrics/resource` 暴露 `node_swap_usage_bytes`、
  `container_swap_usage_bytes`、`container_swap_limit_bytes`；也可以用
  `kubectl top --show-swap`。

## 参考

- [Kubernetes 博客：Scaling Kubernetes Workloads with Node Swap](https://kubernetes.io/blog/2026/10/05/scaling-kubernetes-workloads-with-node-swap/)
- [Linux Node Swap Behaviors](https://kubernetes.io/docs/reference/node/swap-behavior/)
- [Swap memory management](https://kubernetes.io/docs/concepts/cluster-administration/swap-memory-management/)
