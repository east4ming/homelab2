# 实施方案：k3s / Cilium / Tailscale 双栈网络（IPv4 + IPv6）

**Date**: 2026-10-03 | **目标集群**: 生产 homelab（k3s v1.36.5，4 节点，Cilium 1.20.2，Tailscale Operator 1.102.4）
**取证**: 见 [research.md](./research.md)（所有事实均标注命令输出或官方文档链接）
**本次是否执行**: 否。本文是评估 + 方案 + 回退预案，需用户确认路线与窗口后再动生产。

---

## 1. 判定摘要

| 需求 | 能否原地达成 | 结论 |
| --- | --- | --- |
| **k3s 双栈** | ⚠️ 可以，但 **k3s 官方明确不背书**（文档：*"It cannot be enabled on an existing cluster once it has been started as IPv4-only"*） | 需要动 3 台 server 的 `service-cidr` / `cluster-cidr` / `node-ip` 并重启 k3s。Kubernetes 上游**认可**"保留主族的单栈→双栈转换"，本集群因 flannel/kube-proxy/servicelb/traefik/network-policy **全部禁用**，k3s 自身的耦合面最小，是少见的适合原地转换的形态 |
| **Cilium 双栈** | ✅ 可以 | `ipv6.enabled=true` + 节点 IPv6 PodCIDR + `ipv6NativeRoutingCIDR`。**唯一硬门槛**：`ipam.mode=kubernetes` 要求每个启用的地址族都有 PodCIDR，否则 agent 卡启动 = 全集群断网 |
| **Tailscale 双栈** | ✅ **已基本达成** | 节点与 tailnet 已是双栈（`100.x` + `fd7a:115c:a1e0::/128`，36 peer 全带 IPv6）。Operator 官方支持 IPv6，**本次无需改造**，只需验证 |

**关键去风险事实**（k8s 官方文档原文）：开启双栈后，**既有 Service 的 `ipFamilyPolicy` 会被置回 `SingleStack`、ClusterIP 不变**；**新建 Service 默认仍是 `SingleStack`**。IPv6 ClusterIP 只出现在显式声明 `PreferDualStack`/`RequireDualStack` 的 Service 上。
→ 124 个既有 Service 中，**只有 1 个 `metrics-server`（PreferDualStack + 真实 ClusterIP）可能被补发 IPv6 ClusterIP**，另 9 个 headless 的 `ts-*` Service 可能多出 IPv6 endpoint。这是**唯一**的既有对象行为变化，且都是 opt-in 语义，**不是**"全集群 Service 重编号"。

---

## 1.1 已确认路线（2026-10-03 决定）

> **决定：走路线 C —— 只做节点 + tailnet 双栈，本次不动 k3s / 不开 Cilium `ipv6.enabled`。**
> **范围（是否需要 IPv6 ClusterIP）暂不决定，以演练结论为准。**

因此本文档的用法是：

| 章节 | 现在的定位 |
| --- | --- |
| §1.2 路线 C 实施清单 | **本次要做的事** |
| §6 Phase 0 | **本次要做**——演练，用来回答"是否值得升级到路线 A" |
| §6 Phase 1–7、§3、§5 | 路线 A 的完整方案，**本次不执行**，作为演练通过后可直接启用的预案 |
| §4 风险登记册、§5 备份、§7 回退 | 全量保留备查（其中 R1–R3、R5–R7、R11 与 §5 的 Ceph 导出**仅在日后走 A/B 时生效**；R4、R8–R10 与路线 C 相关） |

**选 C 的直接收益**：控制面零中断、etcd 零变更、Ceph 零风险、pod/Service 编址零变更。C 不做的事：pod 与 Service 拿不到 IPv6，集群内 IPv6 只到节点与 tailnet 层。

---

## 1.2 路线 C 实施清单

### C-1 节点层：**已达成，无需变更**，只需固化与监控

`[实测]` 4 台节点均已具备：全局 IPv6（SLAAC GUA）、经 br-lan 的默认路由且被 RA 持续刷新（research §2.1 时间序列取证）、`net.ipv6.conf.all.forwarding=1`、`net.ipv6.conf.all.accept_ra=2`。**不需要为了路线 C 改任何节点网络配置。**

| 动作 | 内容 | 备注 |
| --- | --- | --- |
| C-1.1 决策：是否把 netplan 纳入 Git | 节点 IPv6 现由 **cloud-init/netplan**（`/etc/netplan/50-cloud-init.yaml`，标注"改动不会跨重启保留"）管理；`metal/roles/prerequisites` 目前只写 sysctl，不管 netplan | 不做也不影响 C 的达成；做了可防手工漂移。**建议本次仅记录，不改**（surgical） |
| C-1.2 监控（**建议做**） | ①节点 IPv6 InternalIP vs 实际 GUA 是否一致 ②默认路由 `expires` 是否持续被刷新 ③节点 IPv6 到公网可达性 | 对应 R4；这是"节点双栈"从'能用'变成'可运维'的关键 |
| C-1.3 runbook：ISP PD 前缀漂移 | 前缀变化时的恢复步骤。**注意影响面有限**：路由器的 4 条 pod 路由走的是**节点 IPv4**，不受 IPv6 前缀影响；前缀漂移只影响 IPv6 侧（节点 GUA、以及日后若加的 IPv6 路由） | 本次只写文档，不演练（演练成本高、收益低） |

### C-2 Tailscale 层：**tailnet 侧已达成**，是否做 subnet router 由你定

`[实测]` 节点与 tailnet 已双栈：每节点 `100.x` + `fd7a:115c:a1e0::/128`，36 个 peer 全部带 IPv6 地址；Operator `v1.102.4` 官方支持 IPv6。
`[已核查]` **不需要任何 operator 配置变更**：Helm chart、deployment 模板、operator env 全集里都不存在 IPv6/dual-stack 相关的 value 或环境变量——是自动行为。

| 动作 | 内容 |
| --- | --- |
| C-2.1 验证现状（**做**） | operator / nameserver / ingress-proxies / egress-proxies 全 Ready；`ts-*` 入口从 tailnet 可访问；`tailscale status --json` 仍双栈 |
| C-2.2 **可选**：让 tailnet 能访问局域网的 IPv4+IPv6 | 当前**没有** subnet router（`AdvertiseRoutes: None`、`RouteAll: False`、无 Connector）。若需要，用 operator 的 Connector CRD（`advertiseRoutes` 支持 IPv4/IPv6 CIDR）或节点上的 `--advertise-routes`。Linux 需 `net.ipv6.conf.all.forwarding=1`（节点已满足） |
| C-2.3 `[未验证]` 先演练再决定广告哪个前缀 | ①`--snat-subnet-routes` 在 IPv6 下的语义**官方未文档化**（文档只给了 IPv4 的 `100.64.0.0/10` 回程路由，没有 `fd7a:115c:a1e0::/48` 对应说明）②广告 ISP 的 GUA `/64`（随 PD 变，需重新广告）还是引入 LAN ULA（更稳但要动路由器）③exit node 官方"完全支持 IPv6" |
| C-2.4 **明确不做**：不把 IPv6 设为 primary family | 否则单栈 Service 会变 IPv6-only，需要 tailnet 侧 `disable-ipv4` node attribute（该属性只写在 CGNAT 冲突文档中，operator 文档未提）。保持 IPv4 primary 就完全绕开该问题 |

`[已核查]` 顺带排除一个既有疑虑：官方要求"Cilium kube-proxy-replacement + socketLB 时，`tailscale.com/expose` / Tailscale LoadBalancer Service / Connector Service-CIDR 会绕过 Tailscale 防火墙规则，需开 `socketLB.hostNamespaceOnly`"。
**本集群不触发**：无 Connector、无 `tailscale.com/expose`、无 Tailscale LoadBalancer Service（29 个入口**全部是 Ingress**，而 Ingress 不在该清单内）。
→ `metal/roles/cilium/defaults/main.yml` 中注释掉的 `socketLB.hostNamespaceOnly: true` **继续保持注释**；若日后引入 Connector 或 `tailscale.com/expose`，再打开。

`[已知缺陷，仅日后走双栈时需注意]` ProxyGroup egress 的就绪判定可能只验证一个地址族就置 Ready（issue #21077，**v1.102.4 受影响**，修复 PR #21572 尚未合并）。当前单栈不受影响。

### C-3 明确不做（本次）

- 不改 k3s 的 `cluster-cidr` / `service-cidr` / `cluster-dns` / `node-ip`
- 不打开 Cilium `ipv6.enabled`，不加节点 `ipv6-pod-cidr` 注解
- 不改路由器、不改 kube-vip、不给 LB IP 池加 IPv6
- **结果**：pod 无 IPv6、Service 无 IPv6 ClusterIP、node/LB 寻址保持 IPv4；集群内 IPv6 止步于节点与 tailnet

### C-4 演练（**本次执行**，用来决定是否升级到路线 A）

把 research §6 的未验证项分成两组，**D0 现在做，D1 决定 A 之前做**：

| 组 | 项目 | 目的 |
| --- | --- | --- |
| **D0**（对 C 也有用，现在就做） | ①passwall（`dns_redirect=1`+`filter_proxy_ipv6=1`）对 pod/node 的 AAAA 解析与 IPv6 出网影响 ②Tailscale subnet router 的 IPv6 广告 + SNAT/回程（C-2.3 的未文档化项）③确认 operator 在双栈 tailnet 下的实际行为与 #21077 是否影响本集群 | 交付"节点+tailnet 双栈"的可运维版本 |
| **D1**（只为决定 A） | ①k3s 改 `service-cidr` 后 apiserver 能否启动、"全停→改→全启" vs 滚动 ②Cilium `ipam.mode=kubernetes` 下 IPv4 取 `spec.podCIDRs` + IPv6 取 Node 注解的混合来源是否被接受 ③IPv6 BPF masquerade（beta）实测 ④`metrics-server` 是否被自动补发 IPv6 ClusterIP ⑤L2 宣告的 IPv6/NDP ⑥`cluster-dns` 自动派生行为（见 §6 Phase 4 的修订） | 用数据回答 §9 的待决策项 3 |

**明确未做验证就不得进入 Phase 1–7。** D1 的 6 项全部需要同构演练集群（`metal/inventories/stag.yml` 或 `metal/k3d-dev.yaml`）。

---

## 1.3 路线重估（2026-10-03 实验后）—— 建议改走 A′

> 起因：用户明确**仍要实现双栈**，并提议"主要基于 Cilium `ipam-crd` / `ipam-cluster-pool` 文档"实现。
> 为此在本机 Docker 上用**与生产完全相同版本**的 k3s 做了对照实验（research §7，**未触碰生产**）。

### 1.3.1 对用户提议的判决：**无法覆盖 service 双栈**

| 提议 | 判决 | 原因 |
| --- | --- | --- |
| `ipam-crd` | ❌ 不可用 | 官方：*"only single IP addresses are allowed. **CIDR's are not supported.**"* 连 CIDR 块都不支持 |
| `ipam-cluster-pool` | ⚠️ 只解决 pod，且不该选 | ①**完全不碰 service** ②从现用 `ipam.mode=kubernetes` 切过去是**无文档支持的 IPAM 模式变更**，官方称最安全的方式是"装一个新集群" ③会**重新分配**各节点 IPv4 `/24`，极可能打断路由器那 4 条静态路由 |

**根本原因（实验已证）**：Service 的地址族由 **apiserver 的 `--service-cluster-ip-range`** 决定，
`ServiceCIDR` 对象只能在**已启用的族内**扩展范围。Cilium 只编程 apiserver 分配出的 ClusterIP，
**自己没有 ClusterIP 分配权**。实测：单栈集群上建 IPv6 `ServiceCIDR`（`Ready=True`）后，
`RequireDualStack` 仍被拒 —— *"this cluster is not configured for dual-stack services"*。

### 1.3.2 但 k3s 侧的风险已被实测**大幅下调**

原方案最让人却步的是 R1（"apiserver 可能起不来 / 控制面全停"）。实验把这条从**未知**变成了**已知且可控**：

| 原担忧 | 实测结果 | 影响 |
| --- | --- | --- |
| R1 apiserver 因 ServiceCIDR 不匹配而拒绝启动 | ❌ **不成立**。三个 flag 一起改成双栈后 **API ~15s 就绪、无 fatal**，`kubernetes` ServiceCIDR 对象被**原地更新**为双栈 | R1 从 🔴 降为 🟡：失败模式是**确定性 fail-fast**，配错只报清晰错误，**不损坏 etcd**（同一份 etcd 经历过一次 fatal 退出后仍正常启动） |
| R5 `metrics-server` 可能被补发 IPv6 ClusterIP | ❌ **不成立**。实测 `[10.43.142.140]` **未变**；`kubernetes`、`dstest` 等也全部未变 | R5 从 🟡 降为 🟢：**既有 Service 的爆炸半径实测 = 1 个对象（kube-dns）** |
| 双栈是否需要动 Cilium IPAM 模式 | ❌ **不需要**。既有 Node 永远拿不到 IPv6 podCIDR（实测仍 `["10.42.0.0/24"]`），用 Node 注解即可，**保持 `ipam.mode=kubernetes` 不动** | 避开了 Cilium 明确警告的"IPAM 模式变更" |

**新增的两条硬约束（实验发现，必须写进实施）：**

1. **`cluster-cidr` / `service-cidr` / `node-ip` 三者必须同时改、且地址族形状一致**（k3s 硬校验）。
   只改 `service-cidr` 会直接 fatal。→ 本方案 Phase 2 必须**三个一起改**，`node-ip` 也必须在
   `kubelet-arg` 里显式给出（因为 `disable-cloud-controller: true` 时 k3s 不把 `node-ip` 传给 kubelet，
   实测 Node 的 InternalIP 仍只有 IPv4）。
2. **每个节点的 IPv6 必须是真实可用的地址**（双栈 `cluster-cidr` 下 k3s 期望节点有 IPv6；
   实验里 flannel 就因此让 k3s 自杀）。生产 4 台节点均已有 GUA，满足。

### 1.3.3 修正后的推荐：**路线 A′**（原地、两阶段、顺序可调）

| 阶段 | 内容 | 实测风险 |
| --- | --- | --- |
| **A′-1 控制面双栈** | k3s 三个 flag 一起改（IPv4 在前）→ 滚动或全停重启 | 🟡 已被实测量化：fail-fast，既有 Service 只动 kube-dns；唯一不可逆点是 `cluster-dns` 自动双栈（可用显式固定 `cluster-dns` 规避） |
| **A′-2 Pod 双栈** | Cilium `ipam.mode` 由 `kubernetes` 改为 **`cluster-pool`**（IPv4 列表对齐现有映射 + 新增 IPv6 列表）并同一次 helm 打开 `ipv6.enabled=true` | 🟡 见 research §7.5：**原"用 Node 注解"方案已被实测证伪**（E10/E11/E12/E14） |

> ⚠️ **2026-10-03 第二次实验后修订**：A′-2 的做法已改。
> v1 计划"保持 `ipam.mode=kubernetes`、用 `network.cilium.io/ipv6-pod-cidr` 注解补 IPv6"**不成立**——
> 实测该注解无效，且缺 IPv6 PodCIDR 时 Cilium agent 会 **panic + CrashLoopBackOff**（全集群 Pod 网络中断）。
> **完整可执行步骤见 [runbook.md](./runbook.md)**；本文件保留作为评估与推理记录。
| **A′-3 可选** | 逐个小步把需要的 Service 标 `PreferDualStack`（新建的已自动可用） | 🟢 既有对象不动 |

**仍建议先在本机 k3d/同构演练集群跑完 A′-1 与 A′-2 的完整闭环**（现在成本很低，§7.4 的脚本可直接复用），
再决定生产窗口。

> ⚠️ **不要在 A′-1 之后停下就以为"service 双栈已完成"**：IPv6 ClusterIP 只有在 **pod 也有 IPv6 之后**
> 才有意义 —— EndpointSlice 的地址族来自 endpoint 自身，pod 没有 IPv6 时 IPv6 ClusterIP 是个**没有后端的悬空 VIP**。
> 所以 **A′-1 + A′-2 是一组**：node 双栈在 A′-1 落地，service 双栈**结构上**在 A′-1 落地、
> **功能上**要等 A′-2 之后才可用，pod 双栈则由 A′-2 提供。

---

## 2. 与"重建集群"路线的对比（含为何不推荐）

| | **A. 原地增量（推荐）** | **B. 推倒重建为双栈集群** | **C. 只做节点+tailnet 双栈** |
| --- | --- | --- | --- |
| 满足"k3s 双栈" | 是（文档不背书，需演练） | 是（官方背书） | 否 |
| 满足"cilium 双栈" | 是 | 是 | 部分（pod 有 IPv6，Service 无 IPv6 ClusterIP） |
| 满足"tailscale 双栈" | 是（现状已达成） | 是 | 是 |
| 停机 | 控制面 3–10 分钟（一个窗口） | **数小时~数天** | 近零 |
| 数据风险 | 低（不动 etcd 数据、不动 Ceph） | **高**：48 个 Ceph RBD PVC 的 PV/PVC 绑定、CephX key、fsid 全在 etcd 里，需导出+重新收养；OSD 在裸分区 `nvme0n1p3` 上 | 无 |
| 回退 | 还原 Cilium values（保 chart 版本）+ 还原 config.yaml + 重启 k3s，§7 全部实跑过 | 数据恢复流程，RTO 数小时+ | 不回退也无害 |
| 主要不确定性 | k3s flag 变更的启动行为（可在演练环境消除） | Rook 重新收养的成功率 | — |

**推荐 A，并把 C 当作 A 的 Phase 1–3（天然分阶段、每阶段可独立回退）。**
**明确不推荐 B**：Ceph 数据虽在 k8s 之外，但 48 个 RBD image 与 PVC 的绑定关系、CephX key、fsid 只存在于 etcd；
重建路线的风险**大于**原地路线那一个"需演练确认的启动行为"。RPO 也只有 12h（etcd 快照间隔），
对一个承载 Gitea / Kanidm / Paperless / Prometheus 的实例来说代价过高。

---

## 3. 目标地址规划

站点 ULA（RFC 4193，随机 40-bit global ID，本次生成）：`fdb5:92d0:b067::/48`

| 用途 | 现值 | 目标值 | 说明 |
| --- | --- | --- | --- |
| Pod CIDR | `10.42.0.0/16` | `10.42.0.0/16` + `fdb5:92d0:b067:4200::/56` | /56 与 /64 掩码是 k3s 文档推荐值；`4200`/`4300` 呼应现有的 `10.42`/`10.43` |
| 每节点 Pod /64 | 见下 | 见下 | 与现有 IPv4 节点分配 **1:1 对齐** |
| Service CIDR | `10.43.0.0/16` | `10.43.0.0/16` + `fdb5:92d0:b067:4300::/112` | /112 是 IPv6 Service 段最大掩码 |
| 节点 IPv6 | SLAAC GUA | 保持 SLAAC GUA（**不新增 ULA**） | 见 §5 R4 的取舍说明 |
| LB IP 池 | `192.168.3.32/27` | **暂不加 IPv6 段** | 当前 0 个 LB Service；L2 宣告的 NDP 行为未实测 |

每节点 IPv6 Pod /64（镜像 IPv4 分配）：

| 节点 | IPv4 PodCIDR | IPv6 Pod /64 |
| --- | --- | --- |
| n100-jumper-0 | `10.42.0.0/24` | `fdb5:92d0:b067:4200::/64` |
| n100-cheshi-0 | `10.42.1.0/24` | `fdb5:92d0:b067:4201::/64` |
| n100-jumper-2 | `10.42.2.0/24` | `fdb5:92d0:b067:4202::/64` |
| n100-jumper-1 | `10.42.3.0/24` | `fdb5:92d0:b067:4203::/64` |

**为什么 pod 用 ULA 而不是从 ISP PD 里再切一个 /64**：LAN 的 `/64` 是 PPPoE/`dhcpv6` PD 派生的
（`reqprefix=60`，`extendprefix=1`），**会随重播变化**。把 pod 地址绑到 ISP 前缀上，
等于让整个集群的内网编址随运营商抖动，属于自找麻烦。ULA 全局唯一、与运营商无关。

**IPv6 出网模型（关键设计选择）**：路由器**没有 NAT66**（research §3）。所以：

- Pod → 集群外：由 **Cilium 在节点侧做 NAT66**（masquerade 到节点 GUA，`enable-ipv6-masquerade` 已是 `true`）。
  → **不需要改路由器**，也不需要给 pod 全球可路由地址。
- Pod ↔ Pod（跨节点）：设 `ipv6NativeRoutingCIDR = fdb5:92d0:b067:4200::/56`（= pod 段），
  使 pod 段内流量**不被 masquerade**，保留真实源地址（与 IPv4 的语义一致）。
- LAN → Pod（入向）：**默认不做**。若将来需要，再给路由器加
  `fd…:4200::/64 via <节点链路本地地址> dev br-lan`（**下一跳用 link-local**，与 ISP 前缀无关），
  并同步把 LAN `/64` 加进 `ipv6NativeRoutingCIDR`。放在 Phase 6，可选。

---

## 4. 风险登记册

| ID | 风险 | 级别 | 触发/后果 | 缓解 | 检测 |
| --- | --- | --- | --- | --- | --- |
| **R1** | k3s 不背书原地双栈；apiserver 可能因 `--service-cluster-ip-range` 与 `kubernetes` ServiceCIDR 对象不匹配而**拒绝启动** | 🟡 中（**实测已下调**，原 🔴 高） | **实测不成立**（research §7 E3）：三个 flag 一起改双栈后 API ~15s 就绪、无 fatal，`kubernetes` ServiceCIDR 被原地更新。失败模式是**确定性 fail-fast**，且**不损坏 etcd** | ①三个 flag 必须同时改（E2 硬校验）②窗口前手动 etcd 快照 ③一次只改一个变量 ④保留 config.yaml 原件 | 启动后 `kubectl get --raw /readyz`、`kubectl get servicecidr` |
| **R2** | Cilium `ipv6.enabled=true` 而某节点无 IPv6 PodCIDR | 🔴 **高（实测确认，且比预想更糟）** | **实测（research §7.5 E10）**：不是"优雅阻塞"而是 **panic + CrashLoopBackOff**（`error="required IPv6 PodCIDR not available"` → `panic: Start or stop failed to finish on time`，exitCode=2）→ **全集群 Pod 网络中断**。此前设想的"混合来源(注解)"已证伪（E11） | **唯一安全做法**：`ipam.mode` 改为 `cluster-pool`，与 `ipv6.enabled=true` 在**同一次 helm upgrade** 内完成，绝不先开 IPv6 再补 CIDR。详见 [runbook.md](./runbook.md) §7 P2 与 §10.1 | `kubectl -n kube-system get pods -l k8s-app=cilium`（CrashLoop = 命中）、`cilium-dbg status` 的 IPAM 行、`kubectl get ciliumnode -o jsonpath=...` |
| **R3** | Cilium **IPv6 BPF masquerade 是 beta** | 🟡 中 | pod→IPv6 出网异常/丢包 | 先在演练环境压测 pod→internet IPv6；出问题可 `ipv6NativeRoutingCIDR` 调整或整体关闭 IPv6 | pod 内 `ping -6` / `curl -6`，`cilium-dbg status` 的 Masquerading 行 |
| **R4** | ISP PD 前缀变化 → 节点 GUA 变化 → **Node 的 IPv6 InternalIP 失效**（kubelet 的 nodeIP 在启动时确定，运行期不重新探测）+ 路由器 IPv6 pod 路由失效 | 🟡 中 | IPv6 集群内路由断裂（IPv4 不受影响） | ①路由器 IPv6 路由下一跳用 **link-local**（前缀无关）②监测节点 InternalIP vs 实际 GUA ③runbook：把新 GUA 写回 `config.yaml` **再**重启该节点 k3s 重新注册 + 更新路由器路由 ④**Phase 1 专项演练**；若前缀确实不稳，退到"节点加 ULA + netplan `ipv6-address-label`"方案 | 定时比对 Node 的 IPv6 InternalIP 与 `ip -6 addr`（用 `-o custom-columns`，**不要用 `-o wide`**——它只渲染一个 InternalIP） |
| **R5** | 开启双栈后既有对象被意外改动 | 🟢 低（**实测已下调**，原 🟡 中） | **实测爆炸半径 = 1 个对象**：`kubernetes`/`dstest`/**`metrics-server`** 的 ClusterIP 与 policy **全部未变**；唯一变化是 `kube-dns` 被 k3s 自动改成 `RequireDualStack` 并新增 IPv6 ClusterIP `fdb5:...:4300::a`（research §7 E4/E6） | 变更前记录全部 Service 快照，变更后逐字节 diff；**预先决定 `cluster-dns` 策略**（显式固定 `cluster-dns: 10.43.0.10` 可让 CoreDNS 保持单栈） | `kubectl get svc -A -o json` 前后 diff；`kubectl -n kube-system get svc kube-dns -o jsonpath='{.spec.clusterIPs}{.spec.ipFamilyPolicy}'` |
| **R6** | 路由器 `passwall` 透明代理（`dns_redirect=1`、`dns_mode=xray`、`filter_proxy_ipv6=1`）干扰 pod 的 AAAA 解析 / IPv6 出网 | 🟡 中 | IPv6 出网间歇失败、DNS 结果异常 | 变更前先在 pod 内验证 `getent ahostsv6` + `curl -6`；必要时为集群网段加 passwall 直连规则 | pod 内 DNS/连通性探针 |
| **R7** | 三台 server flag 不一致的窗口期内行为未知 | 🟡 中 | 该窗口内创建 Service 可能异常 | 采用"快照 → 全停 → 改 3 台 → 全启"，把窗口压到 3–10 分钟，避免长时间混合状态 | 窗口内不创建 Service |
| **R8** | n100 资源紧张（jumper 节点 14Gi，已用 45–49%），重建 pod 期间峰值 | 🟢 低 | 偶发 OOM / Pending | 变更安排在低峰；变更前确认 `kubectl top nodes` 有余量；只改 Cilium 不动工作负载 | `kubectl top nodes`、`kubectl get pods -A --field-selector=status.phase!=Running` |
| **R9** | kube-vip v0.6.4 仅 ARP/IPv4 | 🟢 低 | 无（API 入口保持 IPv4） | **不改 kube-vip**；明确 IPv6 不做 API VIP | — |
| **R10** | L2 宣告的 IPv6/NDP 行为未实测 | 🟢 低 | 无（当前 0 个 LB Service） | 本次不给 LB IP 池加 IPv6 段；要做时先收紧 `interfaces` 并单独演练 | — |
| **R11** | Cilium DSR + `devices: "e+"` + netkit-l2 与 IPv6 的组合未在生产验证 | 🟡 中 | NodePort/DSR 在 IPv6 下异常 | IPv6 下不新建 LB/NodePort 服务（本集群 LoadBalancer 0 个、NodePort 2 个、ExternalName 8 个）；Cilium 版本 1.20.2 官方 e2e 覆盖 k8s 1.36 | `cilium status`、`cilium-dbg bpf lb list` |
| **R12** | Cilium 版本下限：需 ≥ **1.20.2** | 🟢 低（现状已满足） | 1.20.2 release notes 修复了"BPF masquerade 地址是链路本地时丢弃 IPv6 RS/RA"（issue #48093；**v1.19.4 / v1.19.6 / v1.20.0 均受影响**）。本集群节点正是"BPF masquerade + 链路本地 IPv6"的组合，降到 1.20.0/1.20.1 会主动干扰节点 IPv6 | **迁移窗口内冻结 Cilium 1.20.2**；不要 `helm rollback`（rev 13 = 1.20.1，见 §7 R-cilium） | `helm -n kube-system history cilium` |
| **R13** | Cilium 1.20 相关 **open** issue，仅走路线 A 时生效 | 🟡 中 | ①**#42017** hubble-relay 在 IPv6 agent pod IP 下 CrashLoop（**open**）—— 本集群跑着 hubble-relay ②**#16080** Service 的 IPv6 path-MTU discovery（**open**） | ①G3 必须显式检查 `hubble-relay` 是否稳定 ②G3 增加大包（>1280B）的 IPv6 连通测试 | `kubectl -n kube-system get pods -l k8s-app=hubble-relay`、`ping -6 -s 1400` |
| **R14** | 迁移窗口内顺手升级 k3s | 🟡 中 | k3s issue #14712（kube-proxy 观察到 IPv6 NodeIP 时 k3s 进程退出）**只影响 v1.37**；其验证矩阵明确 `v1.36.5-rc1+k3s1 → Passed`。窗口内升级会引入无关变量 | **窗口内冻结 k3s 版本**，不做 1.36.5 → 1.37 升级；也不要为了"修"这个已知问题而升级 | `kubectl get nodes` 的 VERSION 与基线一致 |

---

## 5. 备份方案

**原则：任何回退动作都不得依赖"正在被回退的那套东西"。** 备份落点必须在集群之外。

### 5.1 变更前必做（T-1 天 + 窗口前各一次）

```bash
# 1) etcd 快照（同时落本地与 S3，S3 目标是集群外的 NAS 192.168.3.216:8010）
ssh casey@192.168.3.226 'sudo k3s etcd-snapshot save --name pre-dualstack'
ssh casey@192.168.3.226 'sudo k3s etcd-snapshot list' | tail -5   # 必须能看到刚生成的快照（本地 + s3:// 两条）

# 2) 全量对象快照（进 NAS，不进集群）
kubectl get svc,endpoints,servicecidr,node,pv,pvc,sc,ciliumloadbalancerippool,ciliuml2announcementpolicy \
  -A -o yaml > ~/dualstack-backup/objects-$(date +%F-%H%M).yaml
kubectl get svc -A -o json | jq -S . > ~/dualstack-backup/services-before.json   # 用于逐字节 diff
kubectl get cep -A -o wide > ~/dualstack-backup/cep-before.txt
kubectl get pods -A -o wide > ~/dualstack-backup/pods-before.txt

# 3) 节点配置存档
for h in 226 174 158 154; do ssh casey@192.168.3.$h \
  'sudo cat /etc/rancher/k3s/config.yaml; echo ---; ip -6 addr; echo ---; ip -6 route; echo ---;
   sudo cat /etc/netplan/*.yaml; echo ---; sudo cat /etc/sysctl.d/90-homelab-prerequisites.conf' \
  > ~/dualstack-backup/node-$h-$(date +%F).txt; done

# 4) Helm release 值存档（回退要用的确切版本）
helm -n kube-system get values cilium -o yaml > ~/dualstack-backup/cilium-values-before.yaml
helm -n kube-system get metadata cilium -o yaml > ~/dualstack-backup/cilium-meta-before.yaml
```

### 5.2 Ceph 关键材料导出（**仅路线 B（重建）需要**；走 A/C 时不必执行）

```bash
# fsid + CephX keys（重建路线的命根子；路线 A 用不到但必须提前有）
kubectl -n rook-ceph get secret rook-ceph-mon -o yaml            > ~/dualstack-backup/ceph-mon-secret.yaml
kubectl -n rook-ceph get secret rook-ceph-admin-keyring -o yaml  > ~/dualstack-backup/ceph-admin-keyring.yaml
kubectl -n rook-ceph get secret -l app.kubernetes.io/part-of=rook-ceph-cluster -o yaml \
                                                                 > ~/dualstack-backup/ceph-secrets-all.yaml
kubectl -n rook-ceph exec deploy/rook-ceph-tools -- ceph status   > ~/dualstack-backup/ceph-status.txt
kubectl -n rook-ceph exec deploy/rook-ceph-tools -- ceph osd tree > ~/dualstack-backup/ceph-osd-tree.txt
kubectl -n rook-ceph exec deploy/rook-ceph-tools -- ceph osd getcrushmap -o /tmp/cm && \
kubectl -n rook-ceph exec deploy/rook-ceph-tools -- crushtool -d /tmp/cm \
                                                                 > ~/dualstack-backup/ceph-crushmap.txt
# 备份落点必须是集群外
scp ~/dualstack-backup/* nas:/volume1/backups/dualstack-$(date +%F)/
```

### 5.3 局域网侧

```bash
ssh root@192.168.3.1 -i ~/.ssh/id_ed25519 'uci export' > ~/dualstack-backup/openwrt-uci-export-$(date +%F).txt
ssh root@192.168.3.1 -i ~/.ssh/id_ed25519 'sysupgrade -b /tmp/owrt-backup.tar.gz && cat /tmp/owrt-backup.tar.gz' \
  > ~/dualstack-backup/openwrt-sysupgrade-$(date +%F).tar.gz
# 记录当前 PD 前缀（用于判断后续是否发生前缀漂移）
ssh root@192.168.3.1 -i ~/.ssh/id_ed25519 'ip -6 route show | grep -E "^240e" '
```

### 5.4 备份的**可恢复性**验证（不可跳过）

- **在 Phase 1 的演练集群上**实际执行一次 `k3s etcd-snapshot` 恢复，确认流程与耗时。
- **绝不要**把生产的 etcd 快照恢复到演练集群（会带出生产的 Secret）。
- Rook 重新收养演练同样只在演练环境做。
- 记录实测 RTO：控制面恢复 ≈ ? 分钟；整集群从 etcd 快照恢复 ≈ ? 分钟。
- **当前 RPO 基线**：etcd 快照每 12h 一次 → 最坏丢 12h。窗口前手动快照可把该次变更的 RPO 压到 ≈0。

---

## 6. 分阶段实施步骤（每阶段独立可回退，含验证门）

> **路线 C 下本次只执行 Phase 0**（= §1.2 的 C-4 演练），Phase 1–7 是**路线 A 的预案**，
> 待 Phase 0 的 D1 组出结论后再决定是否启用。阶段划分刻意做成"每步一个验证门、每门都独立可回退"，
> 就是为了让"决定要不要走到 A"这件事本身也有数据支撑。

> 总原则：**一次只改一个变量；每个验证门不过就停在上一步，不进入下一步。**

### Phase 0 — 演练环境（**未完成前不得动生产**）

1. 用 `metal/inventories/stag.yml` 的 dev 集群，或 `metal/k3d-dev.yaml` + 一台闲置机起 k3d，
   建一个**同构**演练集群：k3s 1.36.5、Cilium 1.20.2、`flannel-backend=none`、`disable-kube-proxy`。
2. 在演练集群上把 research §6 的 9 个未验证项逐条跑掉，特别是：
   - **R1**：`service-cidr` 加 IPv6 后 apiserver 能否启动；"全停→改→全启" vs "滚动"哪个可行。
   - **R2**：混合来源（IPv4 取 `spec.podCIDRs`、IPv6 取 Node 注解）Cilium 是否接受。
   - **R3**：IPv6 BPF masquerade 在本内核的实际表现。
   - **R4**：模拟前缀变化，确认节点 IPv6 InternalIP 的恢复动作。
3. 演练**回退**：`helm rollback` + 还原 config.yaml，确认回到单栈。
4. 产出：演练记录 + 修订后的 runbook + 实测 RTO。
   **验证门 G0：9 个未验证项全部有明确结论；回退流程实跑通过。**

### Phase 1 — 生产准备（零变更）

1. 执行 §5.1 / §5.2 / §5.3 全部备份，确认 etcd 快照在 S3 与本地都存在且可列出。
2. 记录基线：`services-before.json`、`pods-before.txt`、`cep-before.txt`、当前 RA/PD 前缀。
3. 确认 `kubectl top nodes` 余量；确认无进行中的滚动升级（`system-upgrade` / `kured` / ArgoCD sync 已暂停）。
4. **暂停 ArgoCD 自动同步**（否则 GitOps 会把 config 改回去或提前应用）。
   **验证门 G1：备份齐全且可列出；ArgoCD 已挂起；基线快照已存。**

### Phase 2 — k3s 控制面双栈（**唯一有 API 中断的阶段**，维护窗口内）

> ⚠️ **实验确立的硬约束（research §7 E2）**：k3s 强制 `cluster-cidr`、`service-cidr`、`node-ip`
> **三者的地址族形状必须一致**，且必须**同时**改。只改 `service-cidr` 会直接 fatal：
> `cluster-cidr: [...] and service-cidr: [...], must share the same IP version`。
> 所以本阶段不是"改 service-cidr"，而是"三处一起改成双栈、IPv4 在前"。

1. 窗口开始，再打一次 etcd 快照：`k3s etcd-snapshot save --name pre-dualstack-window`。
2. 三台 server 的 `/etc/rancher/k3s/config.yaml` 增加（**三台必须完全一致**）：

   ```yaml
   cluster-cidr: 10.42.0.0/16,fdb5:92d0:b067:4200::/56
   service-cidr: 10.43.0.0/16,fdb5:92d0:b067:4300::/112
   ```
   `[源码核实]` **逗号后不能有空格**：k3s 用 `util.SplitStringSlice` 按 `,` 切分且**不做 trim**，
   `"10.42.0.0/16, 2001:db8::/56"` 会因 CIDR 解析失败而启动失败。**顺序即主族**：两处都保持 IPv4 在前
   （etcd 与 apiserver **不支持双栈**，只用主族；primary 由 `node-ip` / `cluster-cidr` / `service-cidr` 的顺序共同决定，三处必须同序）。

   `[源码核实]` `node-cidr-mask-*` 默认即 IPv4 /24、IPv6 /64，**无需显式设置**。
   `[文档]` `--advertise-address` 要求"primary `service-cidr` 必须与 advertised address 同族" → 本集群
   `advertise-address=192.168.3.100`（IPv4）与 IPv4-primary 一致 ✅。
   `[k3s 文档]` `--cluster-cidr` / `--service-cidr` / `--cluster-dns` 属于 **Critical Configuration Values**，
   各 server 不一致会导致新 server 加入时报 `failed to validate server configuration: critical configuration value mismatch`
   —— 这正是必须"三台一起改"的原因。
   `[源码核实]` k3s 还会在"首个 node-ip 的族与 primary `cluster-cidr` 的族不一致且有 ≥2 个 node-ip"时
   **静默交换前两个 node-ip**，所以顺序要刻意对齐，不能随手写。

   同步更新仓库 `metal/roles/k3s/defaults/main.yml` 的 `k3s_server_config`（保持 GitOps 单一事实源）。

3. **按 Phase 0 演练确认的顺序**重启三台 server（预期为"全停 → 改 → 全启"，窗口 3–10 分钟）。
   `[文档]` 普通重启**不会**重新签发 apiserver 证书（客户端/服务端证书 365 天、到期前 90 天内才自动续期）；
   若需要把新的 IPv6 写进 SAN，必须走 `systemctl stop k3s` → `k3s certificate rotate` → `systemctl start k3s`。
   本次不新增 IPv6 VIP，故**不需要**轮换证书。
4. 每台 agent 显式设置双栈 node-ip。
   `[源码核实]` ⚠️ **本集群必须用 kubelet-arg，不能只写 `node-ip`**：因为
   `disable-cloud-controller: true`（research §1.2），k3s 在 node-ip 为双栈时**刻意不把 node-ip 传给 kubelet**
   （源码注释："If the embedded CCM is disabled, don't assume that dual-stack node IPs are safe"）。
   因此需要显式加：

   ```yaml
   kubelet-arg:
     - "node-ip=192.168.3.154,240e:3a3:20ba:ae43:2f0:4dff:fe00:c7d"
   ```
   （**不要**同时使用 k3s 文档里 `--kubelet-arg="node-ip=0.0.0.0"` 那个片段——它会覆盖掉显式的一对地址。）
   **注意**：GUA 由 SLAAC 派生，写进配置后若前缀变化会失效 —— runbook 必须包含
   "把新 GUA 写回 config.yaml **再**重启 k3s"（kubelet 的 nodeIP 在启动时确定，
   运行期不会重新探测，只重启而不改配置仍会报旧地址）。见 R4。

   **验证门 G2**
   - `kubectl get --raw /readyz` = ok；三台 server 均 Ready
   - `kubectl get servicecidr` 出现 IPv4 + IPv6 两个范围
   - 各节点 InternalIP 有 IPv4 + IPv6，用 `kubectl get nodes -o custom-columns='NAME:.metadata.name,INTERNAL-IPs:.status.addresses[?(@.type=="InternalIP")].address'`（⚠️ **不要用 `-o wide`**：2026-10-07 生产实测它只渲染一个 InternalIP，即便节点确有两个）
   - `services-after.json` 与 `services-before.json` diff：**只允许** `metrics-server` 出现差异
   - 起一个 `PreferDualStack` 的测试 Service，确认拿到双 ClusterIP，随后删除
   - 既有 Pod **不得**出现非预期重启（`kubectl get pods -A` 与基线比对）

   **回退 → R-k3s**（见 §7）

### Phase 3 — Cilium 双栈

> ⛔ **本节原做法（Node 注解）已被实测证伪，不要执行。**
> 实测结论（research §7.5）：
> - **E11**：`network.cilium.io/ipv6-pod-cidr` 注解**在 agent 启动前就在位也不生效**，
>   日志 `Retrieved node information from kubernetes node` 后立刻
>   `error="required IPv6 PodCIDR not available"`，且**根本不创建 CiliumNode**。
> - **E10**：失败模式不是"优雅阻塞"而是 **panic + CrashLoopBackOff**
>   （`panic: Start or stop failed to finish on time`，exitCode=2）→ **全集群 Pod 网络中断**。
>   即使 `cilium-config` 里 `k8s-require-ipv6-pod-cidr=false` 也一样阻塞。
> - **E12**：`Node.spec.podCIDRs` 不可改（`Forbidden: node updates may not change podCIDR except from "" to valid`）。
> - **E14**：删 Node 让它重新注册也不行 —— 控制面节点带 k3s finalizer
>   `wrangler.cattle.io/managed-etcd-controller`，`kubectl delete node` 只卡在 Terminating。
> - **E13**：**新加入**双栈集群的节点会自动拿到双栈 podCIDR，Cilium 双栈 IPAM 工作正常
>   （Pod 实测 `[10.42.0.223, fdb5:…::99b5]`）。
>
> ⇒ **Pod 双栈必须改用 Cilium 自己的 IPAM（`ipam.mode=cluster-pool`）**，
> 因为它自行管理每节点 PodCIDR，**不依赖 `Node.spec.podCIDRs`**。
> **改用 `cluster-pool` 的完整步骤、IPv4 映射风险处置、回退与应急预案：
> 见 [runbook.md](./runbook.md) §7 P2。**

*（以下为 v1 原始步骤，仅作历史记录，**请勿执行**）*

1. **先**给 4 个节点打注解（此时 Cilium 尚未要求 IPv6，注解无副作用）：

   ```bash
   kubectl annotate node n100-jumper-0 network.cilium.io/ipv6-pod-cidr=fdb5:92d0:b067:4200::/64
   kubectl annotate node n100-cheshi-0 network.cilium.io/ipv6-pod-cidr=fdb5:92d0:b067:4201::/64
   kubectl annotate node n100-jumper-2 network.cilium.io/ipv6-pod-cidr=fdb5:92d0:b067:4202::/64
   kubectl annotate node n100-jumper-1 network.cilium.io/ipv6-pod-cidr=fdb5:92d0:b067:4203::/64
   ```
   （长期应由 Ansible/ArgoCD 管理，避免手工漂移。）

2. `helm upgrade cilium` 增加（其余 values 不变）：

   ```yaml
   ipv6:
     enabled: true
   ipv6NativeRoutingCIDR: "fdb5:92d0:b067:4200::/56"   # = pod 段：段内不 masquerade，段外 NAT66
   ```
   `enable-ipv6-masquerade` / `bpf.masquerade` 已是 true，无需再动。
   **不要**同时改 `distributedLRU`、`bpf-lb-mode`、`datapathMode` 或任何无关参数。

   **备选（避免 Node 注解）**：改用 Cilium **`ipam.mode=cluster-pool`** —— 官方文档明确该模式
   "does not depend on Kubernetes being configured to hand out per-node PodCIDRs"，且
   `clusterPoolIPv6PodCIDRList` 属于**新增**列表（文档允许"add a new element"，只禁止改动既有 IPv4 列表）。
   代价：`ipam.mode` 变更会把 IPv4 pod 地址来源也切走，需要严格保持 `clusterPoolIPv4PodCIDRList=10.42.0.0/16`
   + `clusterPoolIPv4MaskSize=24` 才能与现有编址和路由器静态路由一致，**风险高于注解方案**。
   → **优先注解方案；cluster-pool 仅作退路**，且必须在 D1 里实测。

3. **逐节点**确认 `cilium` agent Ready 后再看下一个（4 个节点，顺序：cheshi-0 先，master 后）。
   **验证门 G3**（命令尽量用 Cilium **文档列出**的，而非自造）
   - `kubectl -n kube-system get ds cilium` 4/4，无反复重启
   - `cilium-dbg status --all-addresses`：IPAM 行**同时**出现 IPv4 / IPv6 计数（文档化的双栈检查点）
   - `kubectl get cn <node> -o yaml` → `spec.ipam.podCIDRs` **列出两个族**；`kubectl get ciliumnodes` 查 operator 分配错误
   - `cilium-dbg status | grep Masquerading`：确认 BPF 与排除 CIDR 符合预期
   - `kubectl get cep -A -o wide`：新建 Pod 同时有 IPv4 + IPv6（既有 Pod 不会获得 IPv6 —— Cilium 无法改动已创建的 Pod）
   - pod → pod 跨节点 IPv6 通；pod → internet IPv6 通（经节点 NAT66）
   - **R13 专项**：①`kubectl -n kube-system get pods -l k8s-app=hubble-relay` 必须稳定（#42017 open）
     ②大包测试 `ping -6 -s 1400`（#16080 IPv6 Service PMTU open）
   - `cilium connectivity test`（文档只有裸调用；**不存在** `--test dual-stack` 这种选项）
   - `cilium status` 全 OK

   **回退 → R-cilium**（见 §7）

### Phase 4 — Service 双栈（**opt-in，逐个来**）

1. 明确需要 IPv6 ClusterIP 的 Service 清单（**默认什么都不改**）。
2. 一次一个：把目标 Service 改为 `ipFamilyPolicy: PreferDualStack`，确认
   `.spec.clusterIPs` 变成两个；验证从 pod 用 IPv6 访问该 Service 成功；记录到变更清单。
   `[k8s 文档]` 已有 Service 的 **primary family 不可变**，可以增删 secondary family —— 因此保持 IPv4 为 primary 时，
   既有 Service 的 IPv4 ClusterIP 不会被破坏。
3. ⚠️ **修订（源码核实，此前判断有误）**：CoreDNS 双栈**不是可选项，而是会自动发生**。
   k3s 在 `cluster-dns` **未显式设置**时，会**按每个 service-cidr 各派生一个 DNS IP**
   （`GetIndexedIP(svcCIDR, 10)` → `10.43.0.10` 与 `fdb5:92d0:b067:4300::a`），
   并在数量 >1 时把 CoreDNS 的 `ipFamilyPolicy` 置为 **`RequireDualStack`**。
   本仓库当前**没有**设置 `cluster-dns`（research §1.2），所以 Phase 2 一改 `service-cidr`，
   CoreDNS 就会变双栈、**每个 Pod 的 `/etc/resolv.conf` 随之改变**（需 Pod 重启才生效）。

   → **若想避免这个扩散**：显式固定 `cluster-dns: 10.43.0.10`（单值）即可让 CoreDNS 保持单栈。
   IPv4 DNS 同样能解析 AAAA，功能上没有损失，代价是失去"集群内 DNS 走 IPv6"这一点。
   ✅ **已由实验证实（research §7 E6）**：改完 `service-cidr` 后 `kube-dns` 确实自动变成
   `clusterIPs=["10.43.0.10","fdb5:92d0:b067:4300::a"] policy=RequireDualStack`，
   IPv6 DNS 恰为 `::a`（即 `GetIndexedIP(svcCIDR, 10)`）；其余既有 Service 全部未变（E4）。
   **注意**：`cluster-dns` 也属 k3s Critical Configuration Values，且受 E2 的族一致性校验约束，
   所以它必须在 Phase 2 与另三个 flag **同一个窗口内**一起定，不能事后单独补。
   **验证门 G4**：每个被改的 Service 都有记录且可独立还原；未列入清单的 Service 与基线一致；
   CoreDNS 的 `ipFamilies` / Pod `resolv.conf` 变化符合所选方案。

### Phase 5 — （可选，延后）LAN 入向 / LB IPv6

- 若要 LAN → Pod 的 IPv6 入向：路由器加 `fdb5:92d0:b067:420X::/64 via <节点 link-local> dev br-lan`，
  并把 LAN `/64` 加进 `ipv6NativeRoutingCIDR`。
- 若要 IPv6 LoadBalancer：先给 `CiliumL2AnnouncementPolicy` 收紧 `interfaces`，
  再给 LB 池加 IPv6 段，并**实测 NDP 宣告**（当前 0 个 LB Service，必要性低）。
- 两者都**不属于本次需求**，默认不做。

### Phase 6 — Tailscale 验证（无需改造）

1. `kubectl -n tailscale get pods`：operator / nameserver / ingress-proxies / egress-proxies 全 Ready。
2. `tailscale status --json`：节点仍双栈（`100.x` + `fd7a:…`）。
3. 逐个 `ts-*` ingress：从 tailnet 访问一次，确认 200。
4. 检查 9 个 headless `ts-*` Service 的 EndpointSlice 新增 IPv6 端点后，operator 行为正常（R5）。
5. 确认 `DNSConfig/ts-dns` 的 nameserver ClusterIP（`10.43.65.250`）仍有效；
   若 Phase 4 改了它，需同步验证 CoreDNS 转发。
6. 提醒（官方文档）：**Pod 不能用裸 Tailscale IP（CGNAT/ULA）访问 tailnet 设备**，
   必须走 ClusterIP / MagicDNS。当前仓库无此类依赖（已核查）。

### Phase 7 — 收尾

1. 把实际采用的配置回写仓库（`metal/roles/k3s/defaults/main.yml`、`metal/roles/cilium/defaults/main.yml`），
   恢复 ArgoCD 自动同步，确认无 drift。
2. 落地监控：节点 IPv6 InternalIP vs 实际 GUA（R4）、pod IPv6 可用性、Cilium agent 重启计数。
3. 更新本文档的"实测结论"与 runbook（前缀漂移恢复、回退演练结果）。

---

## 7. 回退方案

**回退顺序与实施顺序相反；每一步的判据是"验证门未通过或出现非预期现象"。**

| 触发 | 动作 | 预期恢复时间 | 备注 |
| --- | --- | --- | --- |
| **R-cilium**：G3 失败 / agent 卡住 / pod IPv6 异常 | **不要用 `helm rollback`**：上一 revision（13）是 Cilium **1.20.1**，回滚会顺带降级版本。正确做法是保留 chart `1.20.2`、用 `helm upgrade cilium --version 1.20.2` 去掉 `ipv6.enabled` / `ipv6NativeRoutingCIDR` 两项（即 §5.1 存档的 `cilium-values-before.yaml`）→ 等 4 个 agent Ready | ≈2–5 分钟 | 最可能用到的一条；**先回 Cilium 再考虑回 k3s**。回退后移除 4 个节点的 `ipv6-pod-cidr` 注解（Cilium 单栈时它们无副作用，但清掉更干净） |
| **R-svc**：某个 Service 的 IPv6 ClusterIP 造成问题 | 删除并重建该 Service（`ipFamilyPolicy` 回 `SingleStack`） | ≈1 分钟 | 仅影响 Phase 4 显式改过的 Service；这也是 Phase 4 必须逐个做、逐个记录的原因 |
| **R-k3s**：G2 失败 / API 起不来 / 控制面异常 | 用备份的 config.yaml 覆盖三台 server → 按同样顺序重启 → `kubectl get --raw /readyz` | ≈3–10 分钟 | 若已有 Service 拿到 IPv6 ClusterIP，回退后需删除重建这些 Service；`kubernetes` ServiceCIDR 对象如需回到单栈，按 k8s 文档处理（`kubectl get servicecidr` / 删除多余对象） |
| **R-hosts**：节点 `node-ip` 写错导致节点 NotReady | 还原 agent config.yaml → 重启该节点 k3s | ≈2 分钟 | agent 单独滚动，不影响其他节点 |
| **R-full**：控制面无法恢复 | 从窗口前的手动 etcd 快照恢复：`k3s server --cluster-reset --cluster-reset-restore-path=<快照>` | ≈15–60 分钟（**待演练实测**） | RPO：窗口前手动快照 → ≈0；否则最坏 12h。会丢弃窗口内的所有变更 |
| **R-disaster**：etcd 快照不可用 | 重建集群 + 用 §5.2 的 Ceph 材料重新收养 Ceph + 按 PV/PVC 清单重建绑定 | 数小时~数天 | 这是路线 B 的日常成本，仅在极端情况使用。⚠️ **`[k3s 文档]` 拆集群前必须先手工删除 `cilium_host` / `cilium_net` / `cilium_vxlan` 三个接口**，否则跑 `k3s-killall.sh` / `k3s-uninstall.sh` 会**丢失宿主机网络连通性**（Cilium 的 k3s 安装页明确警告，并要求把 iptables / ip6tables 规则里的 cilium 条目过滤掉后再恢复） |

> 版本相关的风险（窗口内不要升级 k3s / Cilium）见 §4 的 **R14** 与 **R12**，不属回退动作。

**全局停止条件（任一命中即整体回退到 Phase 1 状态）**：
- 三台 server 中任一台 15 分钟内无法 Ready
- Cilium agent 在任一节点反复重启 > 3 次
- 任一既有工作负载出现非预期重启或 Pending
- 出现数据面丢包（Hubble / 业务探针）
- 无法解释的 etcd leader 抖动

---

## 8. 验收标准

- [ ] 节点双栈：`kubectl get nodes -o custom-columns='NAME:.metadata.name,INTERNAL-IPs:.status.addresses[?(@.type=="InternalIP")].address'` 显示 4 台均有 IPv4 + IPv6（**不用 `-o wide`**，它只渲染一个 InternalIP）
- [ ] `kubectl get servicecidr`：同时存在 IPv4 与 IPv6 范围
- [ ] 新建 `PreferDualStack` Service 获得双 ClusterIP；从 Pod 用 **IPv6** 访问该 Service 成功
- [ ] Pod 同时持有 IPv4 + IPv6（`kubectl get cep -A -o wide`）
- [ ] 跨节点 pod↔pod IPv6 通；pod→internet IPv6 通（经节点 NAT66）
- [ ] **既有 124 个 Service 的 `clusterIP` / `ipFamilies` 与变更前逐字节一致**（除已知的 `metrics-server`）
- [ ] 既有工作负载无额外重启、无 Pending/Evicted
- [ ] `cilium status` 全 OK；Cilium agent 无重启循环；Hubble 正常
- [ ] Tailscale：operator/nameserver/ingress/egress 全 Ready；`ts-*` 入口从 tailnet 可访问；节点仍双栈
- [ ] `k3s etcd-snapshot list` 能看到窗口前后的快照；备份文件已落在 NAS
- [ ] 仓库内配置与实际集群状态一致，ArgoCD 无 drift

---

## 9. 决策记录与剩余待决项

### 9.1 已决定（2026-10-03）

| # | 议题 | 决定 |
| --- | --- | --- |
| 1 | 路线 | ✅ **路线 C** —— 只做节点 + tailnet 双栈，本次不动 k3s，**不执行 Phase 1–7** |
| 2 | 范围（是否需要 IPv6 ClusterIP） | ⏸ **暂不决定**，以 Phase 0 的 D1 组演练结论为准 |

### 9.2 剩余待决项

1. **C-2.2 是否要做 tailnet → 局域网 IPv6 的 subnet router？**
   当前无 subnet router（`AdvertiseRoutes: None`）。若要做，需先回答 C-2.3：
   广告 ISP 的 GUA `/64`（随 PD 漂移）还是引入 LAN ULA？两者都要先跑 §1.2 的 D0 演练
   （`--snat-subnet-routes` 的 IPv6 语义官方**未文档化**）。
2. **C-1.2 监控落地范围**：是否加"节点 IPv6 InternalIP vs 实际 GUA"与"RA 刷新"探针？（建议做）
3. **演练环境**：`stag` dev 集群（172.21.112.x）能用吗？还是某台机器起 k3d 做同构演练？
   D1 组 6 项需要它才能出结论，进而回答待决项 4。
4. **D1 结论 → 是否升级到路线 A**：若要通过，还需要你确认两个前置条件：
   - **维护窗口**：可接受的 API 中断时长？建议 ≤10 分钟（Phase 2 是全流程唯一中断点）。
   - **`cluster-dns` 策略**（见 §6 Phase 4 修订）：接受 CoreDNS 自动变双栈（Pod 需重启以更新 `resolv.conf`），
     还是显式固定 `cluster-dns: 10.43.0.10` 保持单栈？
5. **ISP 前缀稳定性**：是否有历史记录/DDNS 日志可判断 `240e:3a3:20ba:ae43::/64` 的漂移频率？
   这决定 R4 是按"监控 + runbook"处理，还是直接上"节点 ULA + `ipv6-address-label`"方案。
   （路线 C 下影响面较小：路由器的 4 条 pod 路由走节点 IPv4，不受 IPv6 前缀影响。）

