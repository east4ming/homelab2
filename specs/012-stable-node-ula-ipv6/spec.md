# Feature Specification: 节点 IPv6 身份改用站点 ULA（摆脱 ISP 前缀漂移）

**Feature Branch**: `012-stable-node-ula-ipv6`

**Created**: 2026-10-30

**Status**: Implemented

**Input**: User description: 执行方案 A —— 把节点 node-ip 的 IPv6 从 ISP 下发的 GUA 改为固定站点 ULA，使 ISP 前缀轮换不再波及 k3s / Cilium；并回答「GUA→ULA 是否需要改路由器」

## 背景与现状

本集群是双栈（`specs/009-dual-stack-network`）：`cluster-cidr` 含
`fdb5:92d0:b067:4200::/56`，`service-cidr` 含 `fdb5:92d0:b067:4300::/112`，
节点 IPv6 此前取**主接口上第一个全局地址**，即 ISP 通过 RA/SLAAC 下发的 GUA
（`240e:3a3:…`）。

这个取值方式有两个结构性缺陷：

1. **ISP 前缀是漂移的。** 2026-10-29 逐台重启后，ISP 把委派前缀从
   `240e:3a3:20ba:ae43::/64` 换成了 `240e:3a3:2002:6440::/64`。节点接口地址跟着变，
   但 `/etc/rancher/k3s/config.yaml` 里的 `node-ip` 是字面量，于是：
   - kubelet 每 10 秒报 `failed to validate secondaryNodeIP`，Node 对象的 IPv6
     InternalIP 停在旧地址；
   - Cilium agent 启动时把旧地址写进 `CiliumNode`，`auto-direct-node-routes` 装不出
     跨节点 IPv6 直连路由 —— **跨节点 IPv6 pod 网络实际上是断的**，只是没人踩到；
   - hostNetwork pod（semaphore/mysql）的 IPv6 EndpointSlice 指向不存在的地址；
   - 每次漂移都要改 4 台配置 + 滚动重启 k3s + 滚动重启 cilium agent（2026-10-29 人工
     做过一遍）。
2. **GUA 不是集群该拿来做身份的东西。** 节点身份只需要「局域网内稳定可达」，
   不需要公网可路由；用 GUA 等于把集群内部的寻址绑在运营商策略上。

站点 ULA `fdb5:92d0:b067::/48` 已经在用（Pod /56、Service /112），从中划一个
`/64` 给节点是最小改动。

## User Scenarios & Testing

### User Story 1 - 节点身份不再随 ISP 前缀变化（Priority: P1）

作为 homelab2 运维者，我希望 ISP 前缀漂移后，k3s / Cilium / EndpointSlice 完全
不受影响，不需要任何人工操作。

**Independent Test**: 把某台节点接口上的 GUA 前缀改掉（或换到另一个
`240e:` 前缀），k3s 不重启、`kubectl get node -o wide` 的 IPv6 InternalIP 不变、
Cilium 直连路由与跨节点 IPv6 pod 连通性不变。

**Acceptance Scenarios**:

1. **Given** 4 台节点已配置 ULA 并重启 k3s，**When** 查看 `Node.status.addresses`，
   **Then** 每台节点只有**一个** IPv6 InternalIP，且落在
   `fdb5:92d0:b067:1::/64` 内（与 inventory 的 `node_ipv6` 一致）。
2. **Given** 同上，**When** 查看 `cilium-dbg node list`，**Then** 4 台的 IPv6 列为
   各自 ULA，且 `ip -6 route` 出现 `fdb5:92d0:b067:420N::/64 via <对方 ULA>`。
3. **Given** 同上，**When** 在两个不同节点的 pod 之间做 IPv6 连接，**Then** 通。
4. **Given** 同上，**When** 检查 k3s journal，**Then** `secondaryNodeIP` 报错为 0。

### User Story 2 - 重装节点即可自愈（Priority: P2）

作为运维者，我希望新装机器的 netplan 里天然带 ULA，跑完 Ansible 不需要手工补地址。

**Independent Test**: 读取 `metal/roles/pxe_server/templates/user-data.j2`，netplan 的
`addresses` 同时包含 IPv4 与 `node_ipv6`；`metal/roles/prerequisites` 会写
`/etc/netplan/60-homelab-ula.yaml`。

### User Story 3 - 路由器不需要改动（Priority: P3）

作为运维者，我想确认切换 ULA 不需要动路由器（`192.168.3.1`）。

**Independent Test**: 只读查看路由器 `uci show network` / `dhcp`：LAN 是 br-lan
桥，节点间 IPv6 走二层转发，路由器不参与；路由器没有 ULA 配置、也不需要新增。

## Requirements

- **FR-001** 节点 `node-ip` 的 IPv6 取 inventory 中的固定值 `node_ipv6`
  （站点 ULA），不得再运行时探测 GUA。
- **FR-002** `node_ipv6` 必须由 netplan 持久化到主接口（`network_interface`），
  且必须在 k3s 启动前存在；k3s role 缺地址时**直接失败**并给出手工修复提示。
- **FR-003** 新装机器的 cloud-init user-data 必须包含该 ULA。
- **FR-004** GUA 保留在接口上，继续承担出站/NAT；IPv4 地址与默认路由不变。
- **FR-005** 地址规划（`/64` 与主机位映射）必须在仓库中有唯一出处，并在文档里记录。
- **FR-006** 变更必须可通过 `TestNodeAddressing`（集群验收）复核。

## Success Criteria

- **SC-001** 4 台节点 `Node.status` 的 IPv6 InternalIP 全部在 `fdb5:92d0:b067:1::/64`。
- **SC-002** 4 台节点 k3s journal 中 `secondaryNodeIP` 计数为 0。
- **SC-003** Cilium 的 4 条跨节点 IPv6 直连路由存在，跨节点 pod IPv6 连通。
- **SC-004** 三个业务命名空间（rsshub / lobe-chat / semaphore）保持 Running，应用 HTTP 可用。
- **SC-005** ISP 前缀再次漂移时，`Node.status.addresses`、Cilium 路由、EndpointSlice 不变。

## Out of Scope

- 不改 Pod / Service 的 IPv6 网段（保持 `/56`、`/112`）。
- 不改 `ipv6-native-routing-cidr`（仍为 Pod `/56`；节点→节点流量本就是二层直达）。
- 不改路由器；不引入 DHCPv6 静态租约。
- 不把 GUA 从接口移除。
