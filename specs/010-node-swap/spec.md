# Feature Specification: 节点交换内存（Node Swap）

**Feature Branch**: `010-node-swap`

**Created**: 2026-10-17

**Status**: Draft

**Input**: User description: 根据 Kubernetes 博客《Scaling Kubernetes Workloads with Node Swap》，为 homelab2 集群启用 node swap；按 AGENTS.md 完成开发流程、补全文档并发布版本。

## 背景与现状

Kubernetes 自 v1.34 起 [NodeSwap 正式可用（GA）](https://kubernetes.io/docs/reference/node/swap-behavior/)；本集群为 k3s `v1.36.5+k3s1`，4 台节点全部是 cgroup v2。

实测现状（2026-10-17）：

| 项目 | 现状 | 结论 |
| --- | --- | --- |
| 宿主 swap | 4 台节点均有 `/swap.img`（3×4 GiB + 1×8 GiB），`swapon --show` 非空 | 已具备 |
| kubelet `failSwapOn` | 全部 `false`（k3s 内置默认） | 已具备 |
| Node 上报 swap | `node.status.nodeInfo.swap.capacity` 全部非空 | 已具备 |
| `memorySwap.swapBehavior` | 全部为空 → 默认 **NoSwap** | **缺口** |
| Pod `memory.swap.max` | 容器级为 `0`（少量未托管的 sandbox cgroup 为 `max`） | 工作负载不能用 swap |

因此本特性的功能改动只有一处：把 kubelet 的 `memorySwap.swapBehavior` 从默认 `NoSwap` 改成 `LimitedSwap`，并通过 metal 层固化为可重复、可回退的配置。

## User Scenarios & Testing

### User Story 1 - Burstable 工作负载可以使用 swap（Priority: P1）

作为 homelab2 运维者，我希望符合条件的工作负载能在节点内存压力下把空闲匿名页换出，从而在 4 台 N100 小内存节点上提高 Pod 密度、缓冲内存尖峰，而不是只能被 OOM 杀掉。

**Why this priority**: 这是本特性的全部业务价值；没有它，其余配置只是文档。

**Independent Test**: 在节点上创建一个 `requests.memory < limits.memory` 的 Burstable Pod，检查其容器 cgroup 的 `memory.swap.max` 大于 0；创建 `requests == limits` 的 Guaranteed Pod，检查其 `memory.swap.max == 0`。

**Acceptance Scenarios**:

1. **Given** kubelet 已加载 `LimitedSwap`，**When** 创建 memory request 64 MiB、limit 256 MiB 的 Pod，**Then** 其容器 `memory.swap.max` 按 `(request / nodeTotalMemory) × totalPodsSwapAvailable` 计算出一个正数。
2. **Given** 同一节点，**When** 创建 memory request == limit 的 Guaranteed Pod，**Then** 其容器 `memory.swap.max == 0`（上游明确禁止 Guaranteed Pod 使用 swap）。
3. **Given** 同一节点，**When** 创建没有 memory request/limit 的 BestEffort Pod，**Then** 其容器 `memory.swap.max == 0`。
4. **Given** kube-system 中的关键 Pod（如 apiserver/etcd），**When** 检查其 cgroup，**Then** `memory.swap.max == 0`（关键 Pod 不受 LimitedSwap 影响）。

### User Story 2 - 配置可重复、可回退（Priority: P1）

作为 homelab2 运维者，我希望 node swap 是 metal 层声明的状态，而不是节点上手工改出来的，这样重建节点或重跑 Ansible 后行为一致，且能明确回退到 NoSwap。

**Why this priority**: 本仓库的契约是「Git 是集群状态的唯一来源」；只改线上而不入库会在下次重装时丢失。

**Independent Test**: 重跑 `make -C metal cluster` 的相关任务不产生第二次变更（幂等）；删除 drop-in 并重启 k3s 后，kubelet 配置回到 `memorySwap: {}`。

**Acceptance Scenarios**:

1. **Given** drop-in 已落盘，**When** 再次执行 k3s role，**Then** 文件内容与权限不变、不触发重启。
2. **Given** 需要回退，**When** 移除 `90-swap.conf` 并重启 k3s，**Then** kubelet `/configz` 的 `memorySwap` 回到空值，新 Pod 的 `memory.swap.max` 回到 0。

### User Story 3 - 可观测、可排障（Priority: P2）

作为 homelab2 运维者，我希望能用现成命令确认「哪些节点有 swap、工作负载用了多少 swap、当前 kubelet 是什么行为」，而不是只能读源码。

**Why this priority**: swap 降低可预测性；没有观测手段就无法判断收益与回退时机。

**Independent Test**: 文档中的 `kubectl top nodes --show-swap`、`nodeInfo.swap.capacity`、`/configz`、Pod cgroup 检查命令均可直接执行并得到预期结果。

**Acceptance Scenarios**:

1. **Given** 集群已启用 LimitedSwap，**When** 执行 `kubectl top nodes --show-swap`，**Then** 输出包含 SWAP 列而不是报错。
2. **Given** 任一节点，**When** 读取 `/api/v1/nodes/<node>/proxy/configz`，**Then** `kubeletconfig.memorySwap.swapBehavior == "LimitedSwap"`。

### Edge Cases

- **控制面节点**：上游建议控制面不配置 swap，但本集群 4 台节点都没有 taint、都在跑工作负载，因此 4 台统一启用；关键静态 Pod 仍然拿不到 swap。
- **重建节点**：swap 文件由 Ubuntu 安装器默认创建，不在本仓库管理；若新节点没有 swap，kubelet 配置仍合法，但功能静默无效。文档必须写明如何检查。
- **swap 未加密**：上游强烈建议加密 swap；当前 `/swap.img` 未加密，属已知风险，不在本次范围。
- **调度器不感知 swap**：swap 不参与调度计算，可能出现 noisy neighbor；只把它当内存尖峰的保险，不当作 RAM 的替代。
- **k3s 默认值漂移**：k3s 当前默认 `failSwapOn: false`；drop-in 中显式重复该值，避免未来 k3s 改默认后 kubelet 拒绝启动。

## Requirements

### Functional Requirements

- **FR-001**: metal 层 MUST 在所有节点（server 与 agent）下发 kubelet 配置，使 `memorySwap.swapBehavior == LimitedSwap`。
- **FR-002**: 配置 MUST 通过 k3s 支持的 kubelet drop-in 目录 `{{ k3s_data_dir }}/agent/etc/kubelet.conf.d` 下发，文件 MUST 以 `.conf` 结尾并排在 k3s 自带的 `00-k3s-defaults.conf` 之后，以覆盖默认值。
- **FR-003**: 配置 MUST NOT 覆盖或删除 k3s 每次启动重写的 `00-k3s-defaults.conf`。
- **FR-004**: 配置 MUST 显式声明 `failSwapOn: false`，与博客给出的上游配置一致。
- **FR-005**: 配置变化 MUST 通过既有 handler 重启 k3s 生效；重复执行 MUST 幂等。
- **FR-006**: 本特性 MUST NOT 修改宿主 swap 文件、分区或 `/etc/fstab`，也 MUST NOT 修改任何工作负载的 QoS。
- **FR-007**: 文档 MUST 说明 LimitedSwap 的适用条件（Burstable、request < limit、非关键 Pod）与 swap 额度公式。
- **FR-008**: 文档 MUST 提供启用、验证与回退步骤，并链接上游博客与 Kubernetes 参考文档。

### Key Entities

- **KubeletConfiguration drop-in**：`90-swap.conf`，包含 `failSwapOn` 与 `memorySwap.swapBehavior`。
- **Ansible k3s role**：负责创建 drop-in 目录、渲染文件、通知重启。

## Success Criteria

### Measurable Outcomes

- **SC-001**: 4 台节点的 kubelet `/configz` 均返回 `memorySwap.swapBehavior == "LimitedSwap"`。
- **SC-002**: 测试用 Burstable Pod 的容器 `memory.swap.max > 0`；Guaranteed 与 BestEffort 测试 Pod 为 `0`。
- **SC-003**: `kubectl get nodes` 全部 `Ready`，`kubectl top nodes --show-swap` 正常输出。
- **SC-004**: 重复执行 k3s role 不产生第二次文件变更或重启。
- **SC-005**: 回退步骤在文档中可执行，回退后新 Pod 的 `memory.swap.max` 回到 `0`。

## Out of Scope

- 加密 swap、独立 swap 分区/磁盘、swap 容量调整。
- swap-aware 调度、按节点 taint 隔离 swap 节点。
- 工作负载 QoS 调整（把 Guaranteed 改成 Burstable）。
- 新增 swap 监控面板或告警（node-exporter/kubelet 已暴露原始指标）。
