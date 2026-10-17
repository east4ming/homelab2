# 实施方案：节点交换内存（Node Swap，LimitedSwap）

**Date**: 2026-10-17 | **目标集群**: 生产 homelab2（k3s v1.36.5+k3s1，4 节点，Ubuntu 26.04，cgroup v2）
**上游依据**: [Kubernetes 博客：Scaling Kubernetes Workloads with Node Swap](https://kubernetes.io/blog/2026/10/05/scaling-kubernetes-workloads-with-node-swap/)（2026-10-05）
**参考**: [Linux Node Swap Behaviors](https://kubernetes.io/docs/reference/node/swap-behavior/)、[Swap memory management](https://kubernetes.io/docs/concepts/cluster-administration/swap-memory-management/)

---

## 1. 判定摘要

| 需求 | 现状 | 本次动作 |
| --- | --- | --- |
| 宿主 swap | ✅ 4 台节点均有 `/swap.img` 且已 `swapon` | 不改 |
| cgroup v2 | ✅ 4 台均为 `cgroup2fs` | 不改 |
| kubelet 容忍 swap | ✅ `failSwapOn: false`（k3s 内置默认） | 显式写入 drop-in |
| 工作负载可用 swap | ❌ `memorySwap: {}` → 默认 NoSwap，容器 `memory.swap.max=0` | **改为 LimitedSwap** |
| 可观测性 | ✅ `nodeInfo.swap.capacity`、`kubectl top --show-swap` 已可用 | 写进文档 |

**结论**：功能改动只有一处——kubelet 配置 `memorySwap.swapBehavior: LimitedSwap`；其余都是把它固化、验证与写文档。

## 2. 取证（2026-10-17 实测）

```console
$ kubectl get nodes -o wide
n100-cheshi-0   Ready   ...   v1.36.5+k3s1   Ubuntu 26.04.1 LTS   7.0.0-38-generic   containerd://2.3.4-k3s1.36
n100-jumper-0   Ready   control-plane,etcd,master   v1.36.5+k3s1   ...
n100-jumper-1   Ready   control-plane,etcd,master   v1.36.5+k3s1   ...
n100-jumper-2   Ready   control-plane,etcd,master   v1.36.5+k3s1   ...

$ kubectl top nodes --show-swap
NAME            CPU(cores)   CPU(%)   MEMORY(bytes)   MEMORY(%)   SWAP(bytes)   SWAP(%)
n100-cheshi-0   709m         17%      10980Mi         34%         0Mi           0%
...             # 列存在，说明 metrics-server 已支持 swap

$ kubectl get --raw /api/v1/nodes/n100-jumper-0/proxy/configz | jq '.kubeletconfig | {failSwapOn, memorySwap}'
{ "failSwapOn": false, "memorySwap": {} }   # 空 = 默认 NoSwap
```

宿主侧：

```console
$ ssh n100-jumper-0 'free -m | awk "/Swap:/{print \$2}"; stat -f -c %T /sys/fs/cgroup'
4095
cgroup2fs
```

k3s 侧（源码 `pkg/daemons/agent/agent.go`，v1.36.5+k3s1）：

- `FailSwapOn: utilsptr.To(false)` —— k3s 默认不因 swap 拒绝启动。
- kubelet 启动参数包含 `--config-dir=/var/lib/rancher/k3s/agent/etc/kubelet.conf.d`。
- 每次启动重写 `00-k3s-defaults.conf`（含 `memorySwap: {}`），不会清理目录中的其他文件。
- drop-in 文件按文件名字典序处理，`.conf` 后缀才会加载；`90-swap.conf` 在 `00-...` 之后，覆盖默认值。

上游行为（Kubernetes 1.36）：

- `memorySwap.swapBehavior` 默认 `NoSwap`；只设 `failSwapOn: false` 时工作负载仍不能使用 swap。
- `LimitedSwap` 只对 **Burstable** 且 **memory request != limit** 的容器生效；Guaranteed、BestEffort、关键 Pod（`IsCriticalPod`）一律 `NoSwap`。
- 额度公式：`(containerMemoryRequest / nodeTotalMemory) × totalPodsSwapAvailable`。
- 调度器不感知 swap；上游建议控制面不配置 swap，并建议加密 swap。

## 3. 实现

### 3.1 新增 drop-in 模板

`metal/roles/k3s/templates/kubelet-swap.conf.j2`：

```yaml
apiVersion: kubelet.config.k8s.io/v1beta1
kind: KubeletConfiguration
failSwapOn: false
memorySwap:
  swapBehavior: LimitedSwap
```

静态内容，无 Jinja 变量；落盘为 `/var/lib/rancher/k3s/agent/etc/kubelet.conf.d/90-swap.conf`，`root:root 0600`。

### 3.2 k3s role

- `defaults/main.yml` 新增 `k3s_kubelet_config_dir: "{{ k3s_data_dir }}/agent/etc/kubelet.conf.d"`。
- `tasks/main.yml` 在「Ensure config directories exist」之后：
  1. 确保 drop-in 目录存在（`0700`，与 k3s 自身一致）；
  2. 渲染 `90-swap.conf`；
  3. `notify: Restart k3s`（复用既有 handler）。
- 不新增依赖、不改 k3s unit、不改宿主机。

### 3.3 文档

- 新增 `docs/how-to-guides/node-swap.md`：背景、适用条件、额度公式、验证、回退、风险。
- `mkdocs.yml` 的 How-to guides 下增加条目。
- `docs/reference/changelog.md` 新增 `v2026.10.17.2` 条目。
- `AGENTS.md` 的 SPECKIT 当前 Plan 指向本文件。

## 4. 上线（滚动，逐节点）

**风险点**：drop-in 变化会触发 k3s 重启。3 台 master 同时重启会短暂丢失 etcd quorum，因此**不直接跑整个 play**，而是用一个串行临时 play（`serial: 1`）逐台应用：

1. 先 worker `n100-cheshi-0`：写 drop-in → 重启 k3s → 等 Node Ready → 检查 `/configz`。
2. 再 master `n100-jumper-0`、`-1`、`-2` 逐台重复；每台之间确认 `kubectl get nodes` 与 etcd 成员健康。
3. 不重启节点、不驱逐 Pod；k3s 重启期间容器继续运行。

> 为什么不用 `make -C metal cluster`：`roles/guard` 要求操作者提供 `zz-secrets.yml`（本工作区没有），且默认并行重启 4 台。临时 play 只做本次新增的两个任务，不触碰 registries/tailscale 等敏感配置。

## 5. 验证

| 检查 | 命令 | 期望 |
| --- | --- | --- |
| kubelet 配置 | `kubectl get --raw /api/v1/nodes/<n>/proxy/configz \| jq '.kubeletconfig.memorySwap'` | `{"swapBehavior":"LimitedSwap"}` |
| 节点 swap 容量 | `kubectl get nodes -o go-template=...nodeInfo.swap.capacity` | 4 台均非 `<unknown>` |
| 运行状态 | `kubectl get nodes` / `kubectl top nodes --show-swap` | 全部 Ready；无报错 |
| Burstable Pod | 创建 request 64Mi / limit 256Mi 的 Pod，读容器 cgroup `memory.swap.max` | > 0 |
| Guaranteed / BestEffort | 创建 request == limit、以及无 request/limit 的 Pod | `0` |
| 幂等 | 再次渲染 drop-in | `changed=false`，无重启 |

测试 Pod 验证后删除。

## 6. 风险与回退

| 风险 | 影响 | 缓解 |
| --- | --- | --- |
| k3s 重启 | 单节点 kubelet/控制面组件短暂重启，容器不重启 | 逐台串行；master 之间确认 quorum |
| swap 在根分区 NVMe 上 | 与系统进程争 I/O | 仅 4/8 GiB；文档说明可按需换独立盘 |
| swap 未加密 | 内存明文落盘 | 文档列为已知风险，不在本次范围 |
| 调度器不感知 swap | noisy neighbor | 只用 Burstable；文档给出回退 |
| 新节点无 swap | 功能静默无效 | 文档给出 `swapon --show`/`nodeInfo.swap.capacity` 检查 |

**回退**：删除 `90-swap.conf` → `systemctl restart k3s`（逐台）→ 新 Pod 的 `memory.swap.max` 回到 0。已运行的 Pod 需要重建才会应用新限制。

## 7. 变更文件

- `metal/roles/k3s/defaults/main.yml`
- `metal/roles/k3s/tasks/main.yml`
- `metal/roles/k3s/templates/kubelet-swap.conf.j2`（新增）
- `docs/how-to-guides/node-swap.md`（新增）
- `mkdocs.yml`
- `docs/reference/changelog.md`
- `AGENTS.md`
- `specs/010-node-swap/{spec,plan,tasks}.md`（新增）
