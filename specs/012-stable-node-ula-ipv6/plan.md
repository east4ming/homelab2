# 实施方案：节点 IPv6 身份改用站点 ULA

**Date**: 2026-10-30 | **目标集群**: 生产 homelab2（k3s v1.36.5+k3s1，4 节点，Ubuntu 26.04，内核 7.0.0-42）
**前置事故**: 2026-10-29 AppArmor 信号投递故障（[specs/011](../011-fix-apparmor-signal/plan.md)）的同一轮重启里，ISP 前缀从
`240e:3a3:20ba:ae43::/64` 轮换为 `240e:3a3:2002:6440::/64`，`node-ip` 中的 IPv6 随之过期。
**本次是否执行**: 是。用户已确认方案 A。

---

## 1. 判定摘要

| 问题 | 现状 | 结论 |
| --- | --- | --- |
| 节点 IPv6 来源 | k3s role 运行时取「主接口第一个全局地址」（SLAAC GUA） | 身份绑在运营商前缀上，不可持续 |
| 前缀漂移后果 | kubelet 报 `secondaryNodeIP`；`CiliumNode` 与 EndpointSlice 留旧地址；**跨节点 IPv6 直连路由缺失**（实测） | 漂移不只是告警，而是 IPv6 pod 网络静默失效 |
| 修复方向 | 节点 IPv6 改用站点 ULA `fdb5:92d0:b067:1::/64`，GUA 仅保留出站 | 前缀再怎么变，集群身份不变 |
| 是否需要改 Cilium 配置 | 否：agent 从 Node 对象读节点地址；`ipam: cluster-pool` 只分配 Pod 网段 | 只需 agent 重启刷新 `CiliumNode` |
| 是否需要改路由器 | 否：LAN 是 br-lan 桥，节点间 IPv6 是二层转发，路由器不参与该 `/64` | 只做只读核查 |

## 2. 取证（2026-10-29/30 实测）

### 2.1 前缀确实漂移

```console
# 接口上的实际地址
$ ip -6 -br addr show scope global       # 4 台一致：240e:3a3:2002:6440::/64
# config.yaml 里写的（旧前缀）
$ grep '^node-ip:' /etc/rancher/k3s/config.yaml
node-ip: 192.168.3.174,240e:3a3:20ba:ae43:2e0:4cff:fe72:376b
```

kubelet 每 10s 一条：

```console
E1029 kubelet_node_status.go:673] "Failed to set some node status fields"
  err="failed to validate secondaryNodeIP: node IP: \"240e:3a3:20ba:ae43:…\" not found in the host's network interfaces"
```

### 2.2 后果不止告警：IPv6 直连路由缺失

```console
$ cilium-dbg node list
n100-jumper-0   192.168.3.226   10.42.0.0/24   240e:3a3:20ba:ae43:…:379f   fdb5:92d0:b067:4200::/64   custom-resource
#                                       ^^^^^ 旧地址（agent 启动时从 Node 对象读取）

$ ip -6 route | grep fdb5      # 修复前：只有本机 pod /64
fdb5:92d0:b067:4203::/64 dev cilium_host proto kernel …
```

`auto-direct-node-routes: true` 需要按「对方节点地址」装路由；地址不存在 → 一条都不装。

### 2.3 修复后（2026-10-29 临时用 GUA 修过一轮，作为本次的对照）

只改 `config.yaml` 为当前 GUA + 重启 k3s **不够**：`cilium-dbg node list` 仍是旧地址、
`ip -6 route` 仍无跨节点路由；**逐台重启 cilium agent 后**才出现：

```console
fdb5:92d0:b067:4200::/64 via 240e:3a3:2002:6440:…:379f dev enp3s0
fdb5:92d0:b067:4201::/64 via 240e:3a3:2002:6440:…:c7d  dev enp3s0
fdb5:92d0:b067:4202::/64 via 240e:3a3:2002:6440:…:375b dev enp3s0
```

跨节点 IPv6 pod 连通性实测通（cheshi-0 → jumper-1）。

### 2.4 netplan 合并语义（决定实现方式）

节点网络由 cloud-init 写 `/etc/netplan/50-cloud-init.yaml`（静态 IPv4 + `dhcp6: yes`）。
在 jumper-1 上验证「新增文件只写 ULA」是否会把 IPv4 顶掉：

```console
$ # 临时写 /etc/netplan/60-merge-test.yaml，只含 fdb5:92d0:b067:1::12/64，然后 netplan generate
$ cat /run/systemd/network/10-netplan-enp3s0.network
[Network]
DHCP=ipv6
Address=192.168.3.174/24
Address=fdb5:92d0:b067:1::12/64      # ← 追加语义，IPv4 保留
Gateway=192.168.3.1
```

结论：独立文件 `60-homelab-ula.yaml` 只写 ULA 即安全，不必重写 cloud-init 的文件。

## 3. 设计

### 3.1 地址规划（唯一出处：`metal/inventories/prod.yml`）

| 用途 | 网段 | 说明 |
| --- | --- | --- |
| 站点 ULA | `fdb5:92d0:b067::/48` | RFC 4193，2026-10-07 引入 |
| **节点** | **`fdb5:92d0:b067:1::/64`** | **本次新增**；主机位 `::11`~`::14` |
| Pod | `fdb5:92d0:b067:4200::/56` | 每节点 /64，k3s `cluster-cidr` |
| Service | `fdb5:92d0:b067:4300::/112` | k3s `service-cidr` |

| 节点 | v4 | 新增 ULA |
| --- | --- | --- |
| n100-jumper-0 | 192.168.3.226 | `fdb5:92d0:b067:1::11` |
| n100-jumper-1 | 192.168.3.174 | `fdb5:92d0:b067:1::12` |
| n100-jumper-2 | 192.168.3.158 | `fdb5:92d0:b067:1::13` |
| n100-cheshi-0 | 192.168.3.154 | `fdb5:92d0:b067:1::14` |

GUA 继续留在 `enp3s0`/`enp2s0` 上，只用于出站与 NAT；`node-external-ip` 仍是 Tailscale 地址，不受影响。

### 3.2 代码改动（4 处）

| 文件 | 改动 |
| --- | --- |
| [metal/inventories/prod.yml](../../metal/inventories/prod.yml) | `all.vars` 增加 `dualstack_ipv6_node_cidr`；每台 host 增加 `node_ipv6` |
| [metal/roles/prerequisites/tasks/main.yml](../../metal/roles/prerequisites/tasks/main.yml) + `templates/netplan-ula.yaml.j2` + `handlers/main.yml` | 渲染 `/etc/netplan/60-homelab-ula.yaml`（0600）并 `netplan apply`；必须先于 k3s role |
| [metal/roles/k3s/tasks/main.yml](../../metal/roles/k3s/tasks/main.yml) | 删除「运行时探测 GUA 并 set_fact」，改为校验 `node_ipv6` 已在接口上，缺地址直接失败 |
| [metal/roles/pxe_server/templates/user-data.j2](../../metal/roles/pxe_server/templates/user-data.j2) | 新装机器 netplan `addresses` 直接包含 ULA |

k3s 的 `node-ip` / `kubelet-arg` 模板不变 —— 它们本来就引用 `node_ipv6`，只是取值来源从探测改成 inventory。

### 3.3 线上应用顺序（每步可验证）

1. 备份节点 `/etc/netplan/` 与路由器 `/etc/config`（操作前）。
2. 4 台写入 `60-homelab-ula.yaml` → `netplan apply` → `ip -6 addr` 确认 ULA 在接口上。
3. 4 台改 `config.yaml` 的两处 `node-ip` → **逐台**重启 k3s（worker 先，master 后）。
4. **逐台**重启 cilium agent（删 pod，不用 `rollout restart`，避免 ArgoCD 自愈把模板改动打回）。
5. 验证 Node InternalIP / `secondaryNodeIP` 计数 / `cilium-dbg node list` / IPv6 直连路由 / 跨节点 IPv6 pod 连通 / 业务命名空间。

### 3.4 为什么不是「重启一次就完事」

`node-ip` 是 kubelet 的输入，改完必须重启 k3s；而 Cilium 的节点地址由 agent 在**启动时**从
Node 对象读取并写入 `CiliumNode`，Node 对象更新**不会**让已运行的 agent 重写它（2.3 实测）。
所以最小生效路径是「k3s 重启 + cilium agent 重启」，两者都在用户授权范围内。

## 4. 验证（2026-10-30 实机）

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| Node IPv6 | `kubectl get nodes -o custom-columns=…` | cheshi-0 `::14`、jumper-0 `::11`、jumper-1 `::12`、jumper-2 `::13`，全部 `Ready` |
| 接口地址 | `ip -6 addr show dev enp3s0/enp2s0` | 每台同时有 GUA（dynamic）与 ULA（static /64） |
| kubelet 校验 | `journalctl -u k3s --since -2min \| grep -c secondaryNodeIP` | 4 台均 `0` |
| 节点间 ULA 可达 | jumper-1 `ping6` 其余 3 台 | 0% packet loss（L2，不经过路由器） |
| Cilium 节点地址 | `cilium-dbg node list` | 4 台 IPv6 列为各自 ULA，`Source=local/custom-resource` |
| IPv6 直连路由 | jumper-1 `ip -6 route \| grep fdb5` | `4200::/64 via ::11`、`4201::/64 via ::14`、`4202::/64 via ::13` |
| 跨节点 pod IPv6 | cheshi-0 pod → jumper-1 pod `nc` | 收到 `hello` / `GOT_CONNECTION` |
| hostNetwork endpoint | `kubectl -n semaphore get endpointslices` | IPv6 endpoint = `fdb5:92d0:b067:1::12` |
| 业务可用性 | 三命名空间 pod + 进程内 HTTP 探活 | 全部 Running；lobe `HTTP 302`、casdoor/semaphore `HTTP_OK`、rsshub 正常响应 |
| 集群健康 | `kubectl get pods --all-namespaces` | 无非 Running pod |
| 验收测试 | `go test -run TestNodeAddressing` | PASS（4 个子测试） |
| 路由器 | 只读：`uci show`、`ip -6 addr/route/neigh` | 无 ULA 配置、无该 `/64` 路由、无邻居表项、路由器不可达该网段 —— **无需改动** |

## 5. 备选方案与取舍

| 方案 | 取舍 |
| --- | --- |
| B. k3s 启动前用 systemd `ExecStartPre` 重算 GUA 写 config.yaml | 保留 GUA 身份；自动但每次漂移仍要重启 k3s + cilium，Node/Endpoint 全变 |
| C. 向 ISP 要静态前缀/PD | 最干净；240e 家宽通常拿不到 |
| D. 退回单栈 IPv4 | 与 specs/009 冲突；改 `cluster-cidr` 需重建 pod |
| **A. 站点 ULA（本次）** | 身份与 ISP 解耦；代价是节点地址从「公网可路由」变成「站点内可路由」（本来也不需要公网直达） |

## 6. 风险与回退

| 风险 | 缓解 |
| --- | --- |
| ULA 只在站点内可路由 | 节点间同一 br-lan 二层；外部访问走 Tailscale（`node-external-ip` 不变） |
| k3s 启动前 ULA 未就位 | k3s role 的 assert 直接失败，不会写出空/旧地址 |
| 滚动重启 k3s 影响控制面 | 逐台、等 Ready；3 个 etcd 成员只停 1 个 |
| 回退 | `git revert` 本 PR 的 metal 改动；节点上把 `config.yaml` 的 `node-ip` 改回 GUA 并重启 k3s + cilium，`60-homelab-ula.yaml` 可保留（无副作用） |
