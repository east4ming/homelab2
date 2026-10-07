# 调研与取证：k3s / Cilium / Tailscale 双栈（IPv4+IPv6）

**Date**: 2026-10-03 | **方法**: 线上只读实测（ssh / kubectl / openwrt uci / tcpdump）+ 上游文档原文核对

本文件只记录**可复现的事实**：要么来自命令输出，要么来自带链接的官方文档原文。
推断一律标注 `[推断]`，未验证项见文末。

---

## 1. 集群与组件快照（实测）

| 项 | 值 | 来源 |
| --- | --- | --- |
| k3s | `v1.36.5+k3s1`（Kubernetes 1.36.5） | `kubectl get nodes` / `metal/roles/k3s/defaults/main.yml` |
| 节点 | 4 台：`n100-jumper-0/1/2`（control-plane,etcd,master）+ `n100-cheshi-0`（agent） | `kubectl get nodes -o wide` |
| OS / 内核 | Ubuntu 26.04.1 LTS / `7.0.0-38-generic` | 同上 |
| 容器运行时 | `containerd://2.3.4-k3s1.36` | 同上 |
| Cilium | `1.20.2`（Helm release rev 14，chart `cilium-1.20.2`） | `helm list -A` |
| Tailscale Operator | `v1.102.4`（Helm rev 18）；`k8s-nameserver:unstable` | 同上 |
| Tailscale 节点 | `1.102.4`，每节点 `100.x` + `fd7a:115c:a1e0::/128` | `tailscale ip` / `tailscale status --json` |
| 工作负载规模 | 49 namespace / 124 Service / 50 PVC / 4 节点 | `kubectl get` |

### 1.1 CNI / 网络关键参数（`kubectl -n kube-system get cm cilium-config`）

```
enable-ipv4=true                enable-ipv6=false          ← 本次要打开
enable-bpf-masquerade=true      enable-ipv6-masquerade=true ← 注：已是 true，IPv6 一开即生效
routing-mode=native             auto-direct-node-routes=true
enable-l2-announcements=true    enable-lb-ipam=true        kube-proxy-replacement=True
enable-host-firewall=false      enable-l2-neigh-discovery=false
```

Helm values（`metal/roles/cilium/defaults/main.yml`）：

```yaml
kubeProxyReplacement: true
routingMode: native
autoDirectNodeRoutes: true
ipv4NativeRoutingCIDR: "192.168.3.0/24"   # = ansible_default_ipv4.network/prefix
bpf: { masquerade: true, datapathMode: netkit-l2 }
ipam: { mode: kubernetes }
loadBalancer: { mode: dsr }
devices: "e+"                              # 只挂 ethernet，排除 tailscale0
installNoConntrackIptablesRules: true
bandwidthManager: { enabled: true, bbr: true }
l2announcements: { enabled: true }
```

`CiliumLoadBalancerIPPool/default` = `192.168.3.32/27`；
`CiliumL2AnnouncementPolicy/default` = `externalIPs:false, loadBalancerIPs:true`（**未指定 interfaces**）。
**当前 `type=LoadBalancer` 的 Service 数量 = 0**（该 IP 池实际未被使用）。

### 1.2 CIDR 现状：k3s 全部走默认值

`/etc/rancher/k3s/config.yaml`（n100-jumper-0 实读）**没有** `cluster-cidr` / `service-cidr` / `node-ip`：

```yaml
cluster-init: true
advertise-address: 192.168.3.100
tls-san: [192.168.3.100]
disable: [local-storage, servicelb, traefik]
disable-helm-controller: true
disable-kube-proxy: true
disable-network-policy: true
disable-cloud-controller: true
flannel-backend: none
secrets-encryption: true
embedded-registry: true
etcd-expose-metrics: true
etcd-s3: true
etcd-arg: ["heartbeat-interval=200", "election-timeout=2000"]
kube-controller-manager-arg: ["bind-address=0.0.0.0"]
kube-scheduler-arg: ["bind-address=0.0.0.0"]
snapshotter: stargz
# agent 段：
node-external-ip: 100.67.231.9     # = tailscale ip --4
```

由此得到：

```
ServiceCIDR 对象:  kubernetes = 10.43.0.0/16        （kubectl get servicecidr）
kubernetes svc:    clusterIP 10.43.0.1, ipFamilies [IPv4], ipFamilyPolicy SingleStack
Node podCIDR:      jumper-0 10.42.0.0/24   cheshi-0 10.42.1.0/24
                   jumper-2 10.42.2.0/24   jumper-1 10.42.3.0/24
```

> 关键含义：`--service-cluster-ip-range` 决定了**可用的 Service 地址族**，当前只声明了 IPv4，
> 所以集群无法分配 IPv6 ClusterIP。这是"k3s 双栈"必须触碰控制面配置的根本原因。

### 1.3 控制面入口

- **kube-vip v0.6.4** 以 static pod 形式跑在 3 台 master 上（`kube-vip-n100-jumper-{0,1,2}`），
  `vip_arp=true`，持有 `192.168.3.100`（当前在 jumper-0，MAC `00:e0:4c:72:37:9f`）。
  **纯 ARP/IPv4**，不含 NDP。`curl https://192.168.3.100:6443/livez` 正常。
- `advertise-address` / `tls-san` 都是该 VIP → **API 入口保持 IPv4 即可，本次不需要动 kube-vip**。

### 1.4 已存在的 Service 地址族分布（爆炸半径取证）

```
type:            ClusterIP => 114     ExternalName => 8      NodePort => 2      LoadBalancer => 0
ipFamilies:      [IPv4] => 115        [] => 8               [IPv4, IPv6] => 1
ipFamilyPolicy:  SingleStack => 106   <unset> => 8
                 PreferDualStack => 9  RequireDualStack => 1
headless: 23 / 124
```

> `ipFamilies` / `ipFamilyPolicy` 为空的 8 个 = 8 个 `ExternalName` Service（无 ClusterIP，天然与地址族无关）。

逐条核对后，唯一"有真实 ClusterIP 且非 SingleStack"的 Service 是 **1 个**：

| Service | policy | families | clusterIPs |
| --- | --- | --- | --- |
| `kube-system/metrics-server` | PreferDualStack | `[IPv4]` | `10.43.154.180` |
| `kube-system/monitoring-system-kube-pro-kubelet` | RequireDualStack | `[IPv4, IPv6]` | `None`（headless） |
| `tailscale/ts-{casdoor,dex,gitea,kanidm,lobe,rsshub,rustfs,woodpecker-server}-*` | PreferDualStack | `[IPv4]` | `None`（headless） |

> `[推断]` 打开双栈后：`metrics-server` 可能被控制面补发一个 IPv6 ClusterIP；
> 9 个 headless 的 `ts-*` Service 的 EndpointSlice 会开始包含 IPv6 pod 地址。
> 这两点是**仅有的既有对象行为变化**，必须逐个验证。其余 114 个 Service 不受影响
> —— 见 §4 的 k8s 官方"已存在 Service 保持 SingleStack"原文。

---

## 2. 节点 IPv6 实测：**已经是活的、自愈的**

四台节点都已有全局 IPv6（SLAAC，EUI-64 接口标识），默认路由经 br-lan 的链路本地地址：

```
n100-jumper-0  enp3s0  240e:3a3:20ba:ae43:2e0:4cff:fe72:379f/64
n100-jumper-1  enp3s0  240e:3a3:20ba:ae43:2e0:4cff:fe72:376b/64
n100-jumper-2  enp3s0  240e:3a3:20ba:ae43:2e0:4cff:fe72:375b/64
n100-cheshi-0  enp2s0  240e:3a3:20ba:ae43:2f0:4dff:fe00:c7d/64
default via fe80::2476:3ff:fe05:bdb6 dev <if> proto ra metric 100 expires <N>sec
四台均可 ping6 2400:3200::1 与 2001:4860:4860::8888
```

`net.ipv6.conf.all.forwarding = 1`，`net.ipv6.conf.all.accept_ra = 2`
（由 `metal/roles/prerequisites` 写入 `/etc/sysctl.d/90-homelab-prerequisites.conf`）。

### 2.1 `accept_ra=0` 的疑点 —— 已用时间序列排除

实测 `enp3s0.accept_ra = 0`（`all=2`、`default=1`），与 k3s 文档"必须设 `all.accept_ra=2`，
否则默认路由过期后会被丢弃"的说法表面上冲突。**对 n100-jumper-0 连续采样 8 次（每 45s）**：

```
18:55:20 expires=2582   18:56:05 expires=2536   18:56:50 expires=2491   ← 两次 RA 之间的自然衰减
18:57:36 expires=2445   18:58:21 expires=2656  ← 重置    18:59:07 expires=2610
18:59:52 expires=2660  ← 重置              19:00:38 expires=2614
```

同时在路由器 `br-lan` 抓包（`icmp6 and ip6[40]==134`）：

```
router lifetime 2700s, Flags [other stateful]
  prefix info option: 240e:3a3:20ba:ae43::/64, Flags [onlink, auto], valid 5400s, pref 2700s
  rdnss option: lifetime 5400s, addr 240e:3a3:20ba:ae43::1
```

**第二组独立取证（更长窗口，20 次采样、每 ~51s，跨约 16 分钟）**——同时统计路由器 30s 内的 RA 数量、
节点默认路由剩余寿命、以及节点 IPv6 到公网可达性：

```
19:00:51 expires=2601 ping6=OK | ras_in_30s=2     19:08:29 expires=2680 ping6=OK | ras_in_30s=2
19:01:42 expires=2680 ping6=OK | ras_in_30s=2     19:11:53 expires=2680 ping6=OK | ras_in_30s=3
19:02:33 … 19:07:39 全部 expires=2680 ping6=OK     19:12:44 … 19:16:59 全部 expires=2680 ping6=OK
```

**结论（实测，比第一组更强）**：

1. 路由器以**稳定节奏持续发送 RA**（`ras_in_30s` 恒为 2，偶发 3 ≈ 每 15s 一次），
   而 RA 的 router lifetime 是 2700s —— **刷新频率相对寿命有约 180× 的余量**，
   偶发丢一两个 RA 完全无害。
2. 节点默认路由的剩余寿命在 16 分钟里**钉在 2680s**（2700s 的 99.3%），**不随时间衰减**；
   ping6 20/20 全 OK。→ **不是"勉强刷新"，而是被持续顶在最大值附近。**
   ⚠️ 前提是**路由器持续发 RA**：RA 一旦停止（路由器重启、WAN6 PD 丢失等），
   节点默认路由会在 router lifetime 内（最多 45 分钟）过期并消失。
   这正是 §1.2 C-1.2 要把"RA 是否持续刷新"做成探针的原因。
3. 第一组 45s 间隔采样看到的下降—重置锯齿，是因为采样间隔恰好在两次 RA 之间；
   两组数据共同证明 **RA 被处理并不断刷新**，且 router lifetime 与 prefix valid
   与节点观测值（5400/2700）精确吻合。
4. 四台节点的剩余寿命彼此相差 ≤2s（同一次 RA）。→ **节点 IPv6 健康、稳定。**

`accept_ra=0` 不代表 RA 被丢弃，原因（`[推断]`，有旁证）：

- 默认路由带 `nhid 1002475959`，是 **nexthop 对象**：`ip -6 nexthop show` 输出
  `id 1002475959 via fe80::2476:3ff:fe05:bdb6 dev enp3s0 scope link proto ra`；
- `/run/systemd/network/10-netplan-enp3s0.network` 由 netplan 渲染（`dhcp6: true` →
  `DHCP=ipv6`），**没有 `IPv6AcceptRA=` 行**；
- 即：**RA 由 systemd-networkd 的用户态 RA 客户端接管**，内核 per-interface `accept_ra`
  被置 0 属预期，不是故障。

> **不要"顺手修"这个 `accept_ra=0`。** 节点 IPv6 配置由 netplan/cloud-init 管理
> （`/etc/netplan/50-cloud-init.yaml` 明确写着改动不会跨重启保留），
> 任何 IPv6 静态配置必须走 netplan/Ansible，不能用裸 `ip` 命令。

---

## 3. 局域网 / OpenWrt（iStoreOS 24.10.8，kernel 6.6.144）

| 项 | 值 |
| --- | --- |
| br-lan | `192.168.3.1/24` + `240e:3a3:20ba:ae43::1/64` |
| WAN（IPv4） | `eth1` proto `pppoe`，`pppoe-wan = 100.72.194.84` |
| WAN6 | `eth1` proto `dhcpv6`，`reqprefix=60` `extendprefix=1` `norelease=1` `ip6class=wan6` |
| LAN IPv6 | `ip6assign=64` `ip6class=wan6` |
| IPv6 上游 | **两条并存**：`eth1` 上游 `fe80::1`（PD `240e:3a3:20ba:ae40::/60`）与 PPPoE（PD `240e:3a3:20bb:9670::/60`） |
| RA | `dhcp.lan.ra=server` `ra_default=2`；实测 router lifetime 2700s / prefix valid 5400s / RDNSS = `240e:3a3:20ba:ae43::1` |
| 转发 | `net.ipv6.conf.all.forwarding=1`、`br-lan.forwarding=1` |
| **NAT66** | **不存在**。`nft list ruleset` 只有 `meta nfproto ipv4 masquerade fullcone`（wan zone `masq=1`，但未启用 `masq6`） |
| 路由器 IPv4 到 pod 的静态路由 | `10.42.0.0/24→192.168.3.226`、`10.42.3.0/24→.174`、`10.42.2.0/24→.158`、`10.42.1.0/24→.154` |
| 路由器 IPv6 到 pod 的静态路由 | **无** |
| 透明代理 | `passwall` 已启用：`dns_shunt=chinadns-ng`、`dns_mode=xray`、`dns_redirect=1`、`filter_proxy_ipv6=1`、`@global_forwarding[0].ipv6_tproxy=0` |
| DDNS | `myddns_ipv4/ipv6` 均 `enabled=0`（未启用） |
| 路由器 uptime | 1 天 21 小时（前缀在该窗口内未变；`norelease=1` 有助于保持租约） |

**三个直接影响方案的结论：**

1. **LAN /64 是 ISP PD 派生的，会变**（`240e:3a3:20ba:ae43::/64` 取自 `ae40::/60` 的第 4 个 /64）。
   节点 GUA 是 EUI-64（接口标识稳定），**只有前缀可能变**。
2. **IPv6 是纯路由模型**：路由器不做 NAT66。因此任何使用非公网可达源地址（ULA）
   的 pod 流量，若要在 LAN→WAN 方向工作，**必须由节点侧做 NAT66**（Cilium masquerade），
   或者路由器加回程路由 + pod 使用 GUA。
3. **passwall 在链路上**（DNS 重定向 + xray 透明代理）。pod 的 AAAA 解析与 IPv6 出网
   路径要单独验证，必要时为 `10.42.0.0/16` / 集群 ULA 加直连（bypass）规则。

---

## 4. 上游文档原文（带出处）

### 4.1 k3s：**不支持在既有集群上原地开启双栈**

<https://docs.k3s.io/networking/basic-network-options>（Dual-stack 小节）原文：

> Dual-stack networking must be configured when the cluster is first created.
> **It cannot be enabled on an existing cluster once it has been started as IPv4-only.**

同页其他要求：

> To enable dual-stack in K3s, you must provide valid dual-stack `cluster-cidr` and `service-cidr`
> on all server nodes.
> `--cluster-cidr=10.42.0.0/16,2001:db8:42::/56 --service-cidr=10.43.0.0/16,2001:db8:43::/112`
> …the above masks are recommended. If you change the `cluster-cidr` mask, you should also change
> the `node-cidr-mask-size-ipv4` and `node-cidr-mask-size-ipv6` values to match…
> The largest supported `service-cidr` mask is /12 for IPv4, and /112 for IPv6.
> …you might want to add the `--flannel-ipv6-masq` option…（本集群 `flannel-backend: none`，不适用）
> **Known Issue**: When defining cluster-cidr and service-cidr with IPv6 as the primary family,
> the node-ip of all cluster members should be explicitly set…

同页 IPv6 单栈小节（与 §2.1 的 `accept_ra` 取证相关）：

> If your IPv6 default route is set by a router advertisement (RA), you will need to set the sysctl
> `net.ipv6.conf.all.accept_ra=2`; otherwise, the node will drop the default route once it expires.

### 4.2 Kubernetes：**"保留主族的单栈→双栈转换"是官方认可的操作类目**

<https://kubernetes.io/docs/tasks/network/reconfigure-default-service-ip-ranges/>
（`min-kubernetes-server-version: v1.33`，feature gate `MultiCIDRServiceAllocator`）：

> The IP families available for Service ClusterIPs are determined by the
> `--service-cluster-ip-range` flag to kube-apiserver.
> …all kube-apiserver instances must be configured with the same `--service-cluster-ip-range`
> values, **which must match the default `kubernetes` ServiceCIDR object**.

> **Single-to-dual-stack conversion preserving the primary ServiceCIDR:** This involves introducing
> a secondary IP family (IPv6 to an IPv4-only cluster…) while keeping the original IP family as
> primary. This requires an update to the kube-apiserver configuration and a corresponding
> modification of various cluster components that need to handle this additional IP family. These
> components include, but are not limited to, **kube-proxy, the CNI or network plugin, service mesh
> implementations, and DNS services.**

> **Extending the existing ServiceCIDRs:** This can be done dynamically by adding new ServiceCIDR
> objects **without the need for reconfiguring the kube-apiserver**.

> 本集群实测 `kubectl get servicecidr` 已存在 `kubernetes = 10.43.0.0/16` 对象 → 该机制已生效。

### 4.3 Kubernetes：已存在 Service **不受影响**（爆炸半径≈0）

<https://kubernetes.io/docs/concepts/services-networking/dual-stack/>：

> **Dual-stack defaults on existing Services** … When dual-stack is enabled on a cluster,
> **existing Services (whether `IPv4` or `IPv6`) are configured by the control plane to set
> `.spec.ipFamilyPolicy` to `SingleStack`** and set `.spec.ipFamilies` to the address family of the
> existing Service. The existing Service cluster IP will be stored in `.spec.clusterIPs`.

> **Dual-stack options on new Services** … This Service specification does not explicitly define
> `.spec.ipFamilyPolicy`. When you create this Service, Kubernetes assigns a cluster IP … from the
> first configured `service-cluster-ip-range` and **sets the `.spec.ipFamilyPolicy` to `SingleStack`**.

> `PreferDualStack`: Allocates both IPv4 and IPv6 cluster IPs for the Service **when dual-stack is enabled**.

**含义**：开启双栈后，既有 Service 的 ClusterIP 不变、新 Service 默认仍是单栈；
IPv6 ClusterIP 只出现在**显式声明** `PreferDualStack`/`RequireDualStack` 的 Service 上（opt-in）。
这正是把本次迁移做成"低风险增量"的根据。

### 4.4 Cilium：`ipam.mode=kubernetes` 要求**每个启用的地址族**都有 PodCIDR

<https://docs.cilium.io/en/stable/network/concepts/ipam/kubernetes/>

> In this mode, the Cilium agent will **wait on startup until the `PodCIDR` range is made available
> via the Kubernetes `v1.Node` object for all enabled address families** via one of the following methods:

| 来源 | 字段 |
| --- | --- |
| v1.Node 资源 | `spec.podCIDRs`（IPv4 和/或 IPv6）、`spec.podCIDR` |
| v1.Node 注解 | `network.cilium.io/ipv4-pod-cidr`、**`network.cilium.io/ipv6-pod-cidr`** |

> `ipam: kubernetes`: Enabling this option will automatically enable `k8s-require-ipv4-pod-cidr` if
> `enable-ipv4` is `true` and **`k8s-require-ipv6-pod-cidr` if `enable-ipv6` is `true`**.

> ⚠️ **这是本次最大的单点风险**：先打开 `ipv6.enabled=true` 而节点没有 IPv6 PodCIDR，
> Cilium agent 会**卡在启动等待**，等于全集群网络中断。必须先给节点 IPv6 PodCIDR，再升级 Cilium。

**但本集群的实测值给这条风险加了重要限定 —— 必须实测确认，不能照搬文档结论：**

```
[实测] kubectl -n kube-system get cm cilium-config
  ipam                        = kubernetes      ← 确认不是 cluster-pool（cluster-pool-ipv4-cidr 为空）
  k8s-require-ipv4-pod-cidr   = false           ← 与文档"会自动启用"的说法相反
  k8s-require-ipv6-pod-cidr   = false
  enable-ipv6                 = false
[实测] kubectl get ciliumnode n100-jumper-0 -o jsonpath='{.spec.ipam}'
  {"podCIDRs":["10.42.0.0/24"],"pools":{}}      ← 确认走 host-scope，pod CIDR 来自 Node 对象
```

文档说 `ipam: kubernetes` 会把 `k8s-require-ipv4-pod-cidr` 自动置 true，**但本集群 CM 里是显式 `false`**
（Helm values 的 `k8s.requireIPv4PodCIDR` 默认 false，被渲染进了 CM）。
→ 两种可能，**结论相反，必须实测**：

| 可能 | 若 `enable-ipv6=true` 后的行为 | 后果 |
| --- | --- | --- |
| (a) CM 的显式 `false` 压过文档的"自动启用" | agent **不阻塞**，但没有 IPv6 PodCIDR → 只是**分配不出 IPv6 pod IP** | 降级为功能不生效，**不会断网** |
| (b) 文档的自动启用生效 | agent **阻塞等待** IPv6 PodCIDR | **全集群网络中断** |

**不管哪种可能，正确的操作顺序都一样：先给节点 IPv6 PodCIDR（注解），再开 `ipv6.enabled`。**
这样无论落到 (a) 还是 (b) 都安全 —— 这正是把它列为 D1 演练项（plan §1.2）的原因。

### 4.5 Cilium：IPv6 masquerade 是 **beta**

<https://docs.cilium.io/en/stable/network/concepts/masquerading/>

> **IPv6** BPF masquerading is a beta feature. Please provide feedback and file a GitHub issue if you
> experience any problems. **IPv4 BPF masquerading is production-ready.**

> The default behavior is to exclude any destination within the IP allocation CIDR of the local node.
> If the pod IPs are routable across a wider network, that network can be specified with the option:
> `ipv4-native-routing-cidr: 10.0.0.0/8` (or **`ipv6-native-routing-cidr: fd00::/100`** for IPv6
> addresses) in which case all destinations within that CIDR will **not** be masqueraded.

> Masquerading can take place only on those devices which run the eBPF masquerading program…
> automatically attached to the devices selected by the BPF NodePort device detection mechanism…
> use the `devices` helm option.

> The eBPF-based masquerading can masquerade packets of the following L4 protocols: TCP / UDP / ICMP

本集群 `bpf.masquerade=true` + `devices="e+"`（已匹配 `enp2s0/enp3s0`）→ 机制已就位；
`enable-ipv6-masquerade` 也**已经是 `true`**，打开 IPv6 后立即走这条 beta 路径。

### 4.6 Cilium：版本兼容与 L2 宣告

- <https://docs.cilium.io/en/stable/network/kubernetes/requirements/>：e2e 兼容 **1.33 / 1.34 / 1.35 / 1.36**（本集群 1.36.5 ✅）
- <https://docs.cilium.io/en/stable/network/l2-announcements/>：功能描述通篇使用
  "ARP/**NDP** queries"、"Gratuitous ARP replies / **NDP Advertisements**"；
  唯一明确"无 IPv6 支持"的是**较新的 `l2podAnnouncements` 子功能**：
  > Since this feature has no IPv6 support yet, only ARP messages are sent,
  > no Unsolicited Neighbor Advertisements are sent.
  `[推断]` 主 L2 宣告（LoadBalancer IP）支持 IPv6/NDP，但**需在演练环境实测确认**；
  本集群当前 0 个 LoadBalancer Service，故此项风险很低、可延后。
  注意 `CiliumL2AnnouncementPolicy/default` **未指定 `interfaces`**，加 IPv6 LB 段前应先收紧。

### 4.7 Tailscale Operator：官方 IPv6 支持矩阵

<https://tailscale.com/docs/kubernetes-operator/reference/ipv6>

| 模式 | 功能 | IPv6 支持 | 集群要求 |
| --- | --- | --- | --- |
| Singleton proxy / ProxyGroup | Ingress | 支持 | **Dual-stack cluster required to expose Kubernetes `Service`s over both IPv4 and IPv6 ClusterIPs** |
| 同上 | Egress | 支持 | The cluster must support IPv6 networking if a tailnet target is reachable only over IPv6 |
| 同上 | API Server Proxy | 支持 | 无 |

> **Note:** Pods cannot reach tailnet devices by raw Tailscale IP address (CGNAT/ULA).
> Use the Cluster IP address (IPv4 or IPv6 if dualstack cluster) or MagicDNS name if `DNSConfig` is configured.

`[实测]` 本集群 Tailscale 侧现状：节点已双栈（`100.x` + `fd7a:...`），36 个 peer 全部带 IPv6 地址；
`ProxyGroup` ingress/egress 各 4 副本，`DNSConfig/ts-dns` 的 nameserver `status.ip = 10.43.65.250`（IPv4 ClusterIP）；
仓库内不存在对裸 Tailscale IP（100.64/10）的业务依赖
（仅 `specs/006-tailscale-monitoring/research.md` 提到节点本机 `100.100.100.100` 指标端点，
且该出处在 git 中只是文档描述，不是配置）。

**补充（专项深挖：operator 源码 + changelog 逐条核对）**

- `[文档]` **Operator 侧不需要任何配置**：operator 的 Helm chart、deployment 模板，
  以及 `operator.go`/`sts.go` 里的 env 全集（`OPERATOR_*` / `PROXY_*` / `CLIENT_*` / `TS_*`）
  **都不存在** IPv6/dual-stack 相关的 value 或环境变量 → 双栈是自动行为。
- `[文档]` 版本时间线（operator 有独立于客户端版本的 changelog 条目）：
  v1.66.3 修 init 容器在无 IPv6 模块主机上的失败 · v1.72.0 FQDN egress 支持 IPv6-only ·
  v1.72.1 修 DNSConfig 在双栈集群的 reconcile · **v1.90.5 DNSConfig nameserver 支持 IPv6 Pod 并返回 AAAA** ·
  v1.96.5 `TS_LOCAL_ADDR_PORT` 接受无方括号 IPv6 · v1.98.3 ProxyGroup egress 在双栈下同时拿到 IPv4 ·
  **v1.102.2 "IPv6 is supported in Egress ProxyGroups" + 4via6 支持**。
  → v1.102.4 已包含全部 1.102 IPv6 工作。
- `[源码]` `DNSConfig` 的 `status.nameserver.ip` 取自 `svc.Spec.ClusterIP`（**单个、主族地址**），
  即使集群双栈也只报一个 → 本集群的 `10.43.65.250` 在双栈下仍是 IPv4，CoreDNS stub 转发不受影响。
- `[源码]` ProxyGroup 的 L3 ingress 路径遍历 `svc.Spec.ClusterIPs`，为 IPv4/IPv6 各建一条映射；
  而**非 ProxyGroup 的独立 proxy 路径只取 `svc.Spec.ClusterIP`（主族）**，
  且 LoadBalancer ingress IP 按 `addr.Is4() == clusterIPAddr.Is4()` 过滤。
- `[文档]` 若集群 primary family 变成 IPv6，未显式 `PreferDualStack` 的 Service 会变 IPv6-only；
  官方缓解手段是 tailnet 侧 `disable-ipv4` node attribute
  （写在 CGNAT 冲突文档中，**operator 文档未提**，关联只在 issue #18680）。
  → **保持 IPv4 为 primary 可完全绕开该问题。**
- `[文档]` **已知缺陷 #21077（v1.102.4 受影响）**：ProxyGroup egress 的就绪判定可能只验证一个地址族就置 Ready；
  修复 PR #21572 截至 2026-09-30 仍未合并。当前单栈不受影响。
- `[文档]` Subnet router：`--advertise-routes` 接受 IPv4/IPv6 CIDR（除 Apple TV 外全平台），
  Linux 需同时有 `net.ipv4.ip_forward=1` 与 `net.ipv6.conf.all.forwarding=1`（本集群节点已满足）；
  exit node"完全支持 IPv6"；MagicDNS 返回 AAAA。
  **未文档化**：`--snat-subnet-routes` 在 IPv6 下的语义；关 SNAT 时 `fd7a:115c:a1e0::/48` 的回程路由
  （文档只给了 IPv4 的 `100.64.0.0/10`）；广告公网 IPv6 前缀是否有特殊限制。
- `[源码]` `containerboot` 对 IPv6 egress 目标有前置条件 `ea.Is6() && nfr.HasIPV6NAT()`，
  否则报 `no forwarding rules for egress addresses %v, host supports IPv6: %v`
  → IPv6 egress 依赖**宿主机可编程 IPv6 NAT**，双栈集群本身不保证。

### 4.8 k3s 源码级事实（v1.36.5+k3s1 tag 实读，用于修正方案细节）

| 事实 | 内容 | 影响 |
| --- | --- | --- |
| flag 切分 | `util.SplitStringSlice` 按 `,` 切分且**不 trim 空白** | `cluster-cidr`/`service-cidr` **逗号后不能有空格**，否则 CIDR 解析失败 |
| 主族由顺序决定 | `ClusterIPRange = ClusterIPRanges[0]`、`ServiceIPRange = ServiceIPRanges[0]`；**etcd 与 apiserver 不支持双栈**，只用主族 | 三处顺序必须一致且 IPv4 在前 |
| `--cluster-dns` | **StringSliceFlag**；未设置时 k3s 按**每个 service-cidr 各派生一个** DNS IP（`GetIndexedIP(svcCIDR, 10)`），并在数量 >1 时把 CoreDNS 的 `ipFamilyPolicy` 置为 `RequireDualStack` | ⚠️ **CoreDNS 双栈是自动的，不是可选项**；要避免必须显式固定 `cluster-dns: 10.43.0.10` |
| 族一致性校验 | 硬校验并给出明确错误：`cluster-cidr: %v and service-cidr: %v, must share the same IP version` / `cluster-cidr: %v and node-ip: %v, ...` | 配错 fail-fast，不会静默跑歪 |
| node-ip 自动调整 | 若"首个 node-ip 的族 ≠ primary cluster-cidr 的族"且 node-ip ≥2 个，k3s **静默交换前两个** | 顺序要刻意写，不能依赖自动 |
| **CCM 与 node-ip** | 启用内置 CCM 时把完整 node-ip 列表传给 kubelet；**`disable-cloud-controller` 时对双栈 node-ip 刻意不传**（源码注释 "don't assume that dual-stack node IPs are safe"） | ⚠️ **本集群 `disable-cloud-controller: true`，必须显式设 `kubelet-arg: node-ip=<v4>,<v6>`** |
| Critical Configuration Values | `--cluster-cidr` / `--cluster-dns` / `--service-cidr` / `--flannel-backend` / `--flannel-ipv6-masq` / `--disable-cloud-controller` / `--disable=servicelb` 各 server 必须一致，否则报 `failed to validate server configuration: critical configuration value mismatch` | 必须三台一起改，不能只改半套 |
| 证书 | 普通重启**不会**重新签发 apiserver 证书（服务端/客户端 365 天，到期前 90 天内才自动续期）；要改 SAN 需 `k3s certificate rotate` | 不新增 IPv6 VIP 就不需要轮换 |
| pod CIDR 分配 | k8s `AllocateOrOccupyCIDR`：节点已有任何 podCIDR 就直接 `occupyCIDRs` 返回，**只按索引占用、不会补发另一个族**；若既有 podCIDR 落在新 `cluster-cidr` 之外 → 控制器 "This error will keep crashing controller-manager" | 必须**保留 10.42.0.0/16 为 primary 且只做新增**，绝不能收窄 |
| 卸载危险 | Cilium 的 k3s 安装页明确：拆集群前必须手工删除 `cilium_host` / `cilium_net` / `cilium_vxlan`，否则 `k3s-killall.sh` / `k3s-uninstall.sh` 会**丢失宿主机网络连通性** | 仅重建路线踩得到；已写入 plan §7 R-disaster |
| 版本陷阱 | k3s issue #14712（kube-proxy 观察到 IPv6 NodeIP 时进程退出）**只影响 v1.37**；其矩阵明确 `v1.36.5-rc1+k3s1 → Passed` | 迁移窗口内**冻结 k3s 版本**，不要升到 1.37 |
| Cilium cluster-pool 备选 | 官方：该模式 "does not depend on Kubernetes being configured to hand out per-node PodCIDRs"；`clusterPoolIPv6PodCIDRList` 属**新增**列表（文档允许 add，禁止改既有 IPv4 列表） | 可作"不改 Node podCIDR"的备选，但会连 IPv4 来源一起切换，风险高于注解方案 |

### 4.9 Cilium kube-proxy-replacement × Tailscale：socketLB 要求（已实测排除）

<https://tailscale.com/docs/kubernetes-operator/reference/compatibility> 原文：

> If running Cilium in kube-proxy replacement mode with socket load balancing enabled, connections from
> `Pod`s to `ClusterIP`s bypass Tailscale firewall rules attached to netfilter hooks.
> You must enable **bypassing socket load balancer in Pods' namespaces** if you intend to:
> * Expose a Kubernetes `Service` as a Tailscale LoadBalancer `Service`.
> * Expose a Kubernetes `Service` using the `tailscale.com/expose` annotation.
> * Expose a `Service` CIDR range using `Connector`.

`[实测]` **本集群不触发**：`kubectl get connectors,recorders,peerrelays -A` 均为空；
无 `tailscale.com/expose` 注解；`type=LoadBalancer` 的 Service 数量 = 0；
29 个 Tailscale 入口**全部是 Ingress**（`ingressClassName: tailscale`），而 Ingress **不在**上述清单内。
→ `metal/roles/cilium/defaults/main.yml` 中注释掉的 `socketLB.hostNamespaceOnly: true` **继续保持注释**；
若日后引入 Connector 或改用 `tailscale.com/expose`，再打开。

### 4.10 Cilium 1.20 双栈细则与限制（专项深挖）

**先说一个与 §2 节点 IPv6 结论直接互证的事实：**

> 1.20.2 release notes：*"Fix IPv6 Router Solicitations and Router Advertisements being dropped with
> 'Unsupported protocol for NAT masquerade' on nodes whose BPF masquerade address is a link-local address."*
> （backport #48418 / upstream #48094，修 issue #48093；**受影响版本含 v1.19.4 / v1.19.6 / v1.20.0**）

`[实测]` 本集群节点正是"BPF masquerade + 链路本地 IPv6 地址"的组合（`devices: "e+"`、`bpf.masquerade=true`、
节点有 `fe80::` 地址），而 Cilium 是 **1.20.2**（已含该修复）。→ 这既解释了 §2 里"节点 RA 一切正常"，
也给出一个**硬性版本下限：不要降到 1.20.2 以下**（1.20.0 会主动干扰 IPv6 RS/RA）。

**Helm values（1.20.2 `values.yaml` 默认值）**

```yaml
ipv4: {enabled: true}
ipv6: {enabled: false}                 # 本次要打开
ipam:
  mode: "cluster-pool"                 # 本集群实际用的是 kubernetes（research §1.1）
  operator:
    clusterPoolIPv4PodCIDRList: ["10.0.0.0/8"]
    clusterPoolIPv4MaskSize: 24
    clusterPoolIPv6PodCIDRList: ["fd00::/104"]
    clusterPoolIPv6MaskSize: 120
ipv4NativeRoutingCIDR: ""
ipv6NativeRoutingCIDR: ""
nativeRoutingCIDRFromClusterPool: false
enableIPv6Masquerade: true             # 已是 true
preferIpv6: false                      # 1.20.0 新增：health probe / Hubble peer 通信优先用 IPv6
```

- `[文档]` **`nativeRoutingCIDRFromClusterPool`（1.20 新增）**：仅 `ipam.mode=cluster-pool` 且每族恰好一个 CIDR 时，
  自动派生两个 native routing CIDR。**本集群 `ipam.mode=kubernetes`，不适用**（记录备查）。
- `[文档]` `ipv6NativeRoutingCIDR` 语义："When specified, Cilium assumes networking for this CIDR is preconfigured
  and hands traffic destined for that range to the Linux network stack without applying any SNAT"。
- `[文档]` `autoDirectNodeRoutes` 是 **node↔node only**，不会动 LAN 路由器。
  `[源码]` 该选项**与地址族无关**：`pkg/datapath/linux/node.go` 的 `updateDirectRoutes(...)` /
  `createDirectRouteSpec` 同时构建 `FAMILY_V4` 与 `FAMILY_V6` → 现有配置在 IPv6 下会自动装节点间 pod 路由。
- `[文档]` agent flag `--ipv6-service-range` 默认 **`auto`**，即 Cilium 自行探测 IPv6 service CIDR。
  → **改完 apiserver 的 service-cidr 后必须让 Cilium agent 滚动重启**才能纳入新范围。
  本方案 Phase 2 先改 k3s、Phase 3 再 `helm upgrade` 触发 agent 滚动，顺序天然满足。
  （探测机制本身**未文档化**，"必须重启"属推断。）

**1.20 文档化的 IPv6 缺口（逐条对照本集群）**

| 缺口 | 原文 | 对本集群的影响 |
| --- | --- | --- |
| BPF masquerade IPv6 = **beta** | "**IPv6** BPF masquerading is a beta feature… IPv4 BPF masquerading is production-ready." | 走 A 时踩到，已列 R3 |
| L2 **Pod** Announcements 无 IPv6 | "Since this feature has no IPv6 support yet, only ARP messages are sent…" | 不用该子功能 → 无影响（主 L2 宣告走 NDP，§4.6） |
| 加密 strict mode egress 仅 IPv4 | "The pod CIDR and therefore the encryption strict mode egress CIDR must be IPv4. IPv6 traffic is not protected by the strict mode and can be leaked." | `cilium-config` 无 `enable-encryption` → **未启用加密，无影响** |
| Tunnel underlay 双栈下优先 IPv4 | `underlay-protocol` 默认 `auto`，双栈时 "prioritizing IPv4" | `tunnel-protocol=vxlan` 但 `routing-mode=native` → **不走隧道，无影响** |

**Cilium 1.20 侧同样没有"单栈→双栈"迁移文档**：全量扫 308 个 `Documentation/**/*.rst`，
只有 4 个文件提到 `dual-stack`（BGP×2、LB IPAM、ENI），**没有任何双栈指南或迁移页**。
唯一的在线 IPAM 迁移是 cluster-pool → multi-pool，且明确 *"In case of failure, no rollback is available."*
→ 与 k3s 的禁令叠加，**结论一致：原地双栈无任何厂商文档背书，只能按"需自证"处理。**

**1.20 相关 open issues（仅走路线 A 时需要关注）**

| Issue | 状态 | 与本集群的关系 |
| --- | --- | --- |
| #42017 hubble-relay 在 IPv6 agent pod IP 下 CrashLoop | **open** | ⚠️ 本集群跑着 hubble-relay → **走 A 必须复验**，已列 R13 |
| #16080 IPv6 path-MTU discovery for Service | **open** | ⚠️ Service 的 IPv6 PMTU 未解决 → 走 A 的 G3 要加大包测试 |
| #43280 XDP nodeport 加速不支持 IPv6 underlay | open | `loadBalancer.acceleration` 未启用（仓库注释说明 enp3s0 驱动不支持 XDP）→ 无影响 |
| #48660 双栈 `destinationCIDRs` 破坏 IPv4 egressIP | open（1.20.x 回归） | 仅 Egress Gateway；本集群无 EgressGateway 资源 → 无影响 |
| #47645 pod SLAAC 链路本地 ICMPv6 MLD/RS 被丢 | open | 仅当 pod 用 SLAAC 链路本地；本方案 pod 用 ULA → 无影响 |
| #43774 IPv6 L2 宣告不响应 NDP | closed | 已修 → 与 §4.6 的推断一致 |

**文档化的验证命令（走 A 时用于 G3，比自造命令更权威）**

```
cilium-dbg status --all-addresses                 # IPAM 行应同时出现 IPv4 / IPv6 计数
cilium-dbg status | grep Masquerading             # 应显示 BPF 与排除 CIDR
kubectl get cn <node> -o yaml                     # spec.ipam.podCIDRs 需含两族
kubectl get ciliumnodes -o jsonpath='{...}'       # 查 operator 分配错误
cilium connectivity test                          # 仅裸调用有文档；**不存在** --test dual-stack 选项
```
`[文档]` `cilium-dbg bpf ipcache list` 是合法命令，但**未被文档列为双栈验证步骤**（勿当成验收依据）。

**额外确认**：Cilium 1.20 官方"推荐性能档"本身就包含 `ipv6.enabled=true` + `routingMode=native` +
`bpf.datapathMode=netkit` + `bpf.masquerade=true` + `kubeProxyReplacement=true` + `bandwidthManager.bbr=true`
—— 即本集群现有形态的 IPv6 版本正是 Cilium 自己推荐的组合，**不是冷门路径**。

---

## 5. 备份与存储现状（"重建路线"成本取证）

| 项 | 事实 |
| --- | --- |
| etcd 快照 | 已配置 S3：`s3://k3s-etcd-snapshot` @ `192.168.3.216:8010`（`etcd-s3-insecure=true`），**每 12h**（00:00 / 12:00）+ 本地副本；`k3s etcd-snapshot list` 可列出 |
| 备份落点 | `192.168.3.216` = `NAS33657A.lan`，**在集群之外**（不是 k8s 节点、不在 LB 池内）→ 备份不循环依赖集群 |
| Rook Ceph | `useAllNodes: true`、`useAllDevices: true`、`dataDirHostPath: /var/lib/rook` |
| OSD 承载 | **裸分区**：`nvme0n1p3`（889.4G，`FSTYPE=ceph_bluestore`）；另有 `nvme0n1p1=/boot/efi`、`nvme0n1p2=64G /` |
| mon 数据 | `/var/lib/rook/mon-a`、`/var/lib/rook/mon-g`（hostPath，**在集群状态之外**） |
| PV/PVC | 50 PVC：**48 个 `standard-rwo`（Ceph RBD，RWO）** + 2 个 `nfs-csi-*`（RWX，外部 NFS）；`standard-rwx`（CephFS）当前 0 个 PVC |
| 节点余量 | jumper-0/1/2：4C / 14Gi（已用 45–49%）；cheshi-0：4C / 30Gi（已用 34%）；根分区剩余 20–32G |

**对"重建集群"路线的影响**：Ceph 的**数据**（OSD 裸分区 + mon 目录）在 k8s 之外，
理论上可在重建后由 Rook 重新收养；但 **48 个 RBD image / CephFS subvolume 与 PVC/PV 的绑定关系、
CephX key、fsid 全部只存在于 etcd**，必须提前导出到 NAS 才能重建。
→ 这是"重建"路线的主要风险来源，也是它比"原地增量"更危险的原因（见 plan.md §3）。

---

## 6. 未验证项（按用途分组；未验证前不得上生产）

**分组依据见 plan.md §1.2 的 C-4。D0 对"路线 C"本身就有用，D1 只用于决定是否升级到路线 A。**

### D0 —— 路线 C 需要（本次执行）

| # | 项目 | 状态 |
| --- | --- | --- |
| D0-1 | passwall（`dns_redirect=1` + `filter_proxy_ipv6=1` + xray）对 pod / 节点 AAAA 解析与 IPv6 出网的实际影响 | **未验证** |
| D0-2 | Tailscale subnet router 的 IPv6 广告：`--snat-subnet-routes` 的 IPv6 语义、关 SNAT 时 `fd7a:115c:a1e0::/48` 的回程路由（**官方未文档化**，§4.7） | **未验证**（仅在做 C-2.2 时需要） |
| D0-3 | 广告哪个前缀：ISP GUA `/64`（随 PD 漂移）vs 引入 LAN ULA | **待决策** |
| D0-4 | operator 在双栈 tailnet 下的实际行为；#21077 是否影响本集群 | 单栈下**不受影响**；若日后走双栈需复验 |

### D1 —— 仅为决定"是否升级到路线 A"（需要同构演练集群）

| # | 项目 | 已由文档/源码回答的部分 |
| --- | --- | --- |
| D1-1 | k3s 改 `service-cidr` 后 apiserver 能否启动（`--service-cluster-ip-range` 与 `kubernetes` ServiceCIDR 对象是否强校验） | 文档只说"must match"，**未说明不匹配的后果** → 必须实测 |
| D1-2 | **滚动重启 vs 一次性全停**：flag 不一致窗口期内 apiserver 是否可用 | §4.8 已确认三者属 Critical Configuration Values；滚动半套会被新 server 拒绝，但**已在运行**的旧 server 行为仍未验证 |
| D1-3 | Cilium `ipam.mode=kubernetes` 下 IPv4 取 `spec.podCIDRs` + IPv6 取 Node 注解的**混合来源**是否被接受 | 注解机制**有文档**（§4.4），混合使用**未文档化** |
| D1-4 | `cluster-dns` 自动派生导致 CoreDNS 变 `RequireDualStack`、Pod `resolv.conf` 改变的实际影响 | §4.8 已从源码确认**会自动发生**；要避免须显式固定 `cluster-dns: 10.43.0.10` |
| D1-5 | `metrics-server`（PreferDualStack + 真实 ClusterIP）是否被自动补发 IPv6 ClusterIP | §4.3 文档只覆盖"未显式声明 policy"的情形 → 需实测 |
| D1-6 | Cilium IPv6 BPF masquerade（**beta**，§4.5）在本内核 7.0.0 上 pod→internet 的表现 | 明确标注 beta → 必须实测 |
| D1-7 | 主 L2 宣告功能的 IPv6/NDP 行为 | §4.6：仅 `l2podAnnouncements` 明确无 IPv6 → 主功能需实测（当前 0 个 LB Service，优先级低） |
| D1-8 | 9 个 headless `ts-*` Service 的 EndpointSlice 出现 IPv6 端点后 operator 是否正常 | §4.7 有源码依据但无文档结论 |
| D1-9 | **ISP PD 前缀变更后的恢复动作**：节点 GUA 变化 → Node 的 IPv6 InternalIP 是否随 kubelet 重启刷新 | §4.8：kubelet 的 nodeIP 在启动时确定 → 必须"改 config 再重启"；**恢复时长需实测** |

---

## 7. 本地实验取证（真实 k3s v1.36.5+k3s1 + 嵌入式 etcd）

> **方法**：在工作站用 Docker 跑 `rancher/k3s:v1.36.5-k3s1`（与生产**完全同版本**），
> `--cluster-init`（嵌入式 etcd）+ `--flannel-backend=none --disable-kube-proxy
> --disable-network-policy --disable-cloud-controller`（**复刻生产 k3s 配置**），
> 持久化数据卷。**全程未触碰 homelab 生产集群**（仅本机 Docker）。
>
> 复现脚本见本文件末尾。容器/卷名：`k3s-ds4`、`k3s-ds5`、卷 `k3s-dsx-data`。

### 7.1 实验结论汇总

| # | 结论 | 证据 |
| --- | --- | --- |
| **E1** | **Service 双栈无法从 Cilium / ServiceCIDR 侧实现**，必须改 apiserver 的 `--service-cluster-ip-range` | 单栈集群上新建 IPv6 `ServiceCIDR fd00:43::/112` 后：对象创建成功且 `Ready=True`，但 `PreferDualStack` Service **只拿到 IPv4**（`["10.43.107.68"]`）；`RequireDualStack` 被 apiserver 直接拒绝：**`this cluster is not configured for dual-stack services`** |
| **E2** | **k3s 强制 `cluster-cidr` ≡ `service-cidr` ≡ `node-ip` 三者的地址族形状一致**（硬校验，fail-fast） | 两次 fatal：<br>① `cluster-cidr: [10.42.0.0/16] and service-cidr: [10.43.0.0/16 fdb5:...:4300::/112], must share the same IP version`<br>② `cluster-cidr: [10.42.0.0/16 fdb5:...:4200::/56] and node-ip: [172.17.0.3], must share the same IP version` |
| **E3** | **既有单栈集群可以原地转双栈**：三个 flag 一起改（IPv4 在前、逗号无空格）即可，apiserver 正常启动 | `--cluster-cidr=10.42.0.0/16,fdb5:...:4200::/56 --service-cidr=10.43.0.0/16,fdb5:...:4300::/112 --node-ip=<v4>,<v6>` → API ready ~15s，**无 fatal**，且 `kubectl get servicecidr` 的 `kubernetes` 对象被**原地更新**为 `10.43.0.0/16,fdb5:...:4300::/112` |
| **E4** | **既有 Service 几乎不受影响** —— 唯一变化是 kube-dns | 重启前 → 后：`kubernetes` `[10.43.0.1]` SingleStack **未变**；`dstest`（PreferDualStack 且有真实 ClusterIP）`[10.43.107.68]` **未变**；**`metrics-server`（PreferDualStack）`[10.43.142.140]` 未变**；仅 `kube-dns` 变为双栈 |
| **E5** | **★ 新建 `PreferDualStack` Service 能拿到 IPv6 ClusterIP**（IPv4 仍为 primary） | `realdual: clusterIPs=["10.43.14.152","fdb5:92d0:b067:4300::7d4"] families=["IPv4","IPv6"]` |
| **E6** | **k3s 自动派生第二个 cluster-dns，并把 CoreDNS 改成 `RequireDualStack`**（证实了 §4.8 的源码结论） | `kube-dns: clusterIPs=["10.43.0.10","fdb5:92d0:b067:4300::a"] policy=RequireDualStack`；IPv6 DNS 恰为 `::a`，即 `GetIndexedIP(svcCIDR, 10)` |
| **E7** | **既有 Node 不会拿到 IPv6 podCIDR** | `podCIDRs=["10.42.0.0/24"]`（重启后仍未变） |
| **E8** | **`disable-cloud-controller: true` 时 `--node-ip` 不会传给 kubelet** —— Node 的 InternalIP 仍只有 IPv4 | `addresses=[{172.17.0.3, InternalIP}, {k3s-dsx, Hostname}]`，尽管 `--node-ip=172.17.0.3,fd00:3::1`。→ 生产必须显式加 `kubelet-arg: node-ip=<v4>,<v6>`（证实 §4.8 的源码推断） |
| **E9** | 附带发现：`cluster-cidr` 双栈时 **flannel 要求节点接口上真实存在 IPv6 地址**，否则 k3s 自我关闭 | 容器内 `ip -6 addr add` 失败（Docker 默认桥未启 IPv6）→ `Shutdown request received: "flannel exited: failed to find the interface: failed to find IPv6 address for interface eth0"`。生产 `flannel-backend=none`，**不受此限**，但说明"节点必须有可用 IPv6"是硬前提 |

### 7.2 这三个结论对方案的影响

1. **用户设想的"Cilium IPAM 方案"无法覆盖 service 双栈**（E1）。Service 地址族由 apiserver flag 决定，
   `ServiceCIDR` 对象只能**扩展已启用族内的范围**，不能引入新族。Cilium 只编程 apiserver 分配出来的
   ClusterIP，自己没有分配权。
2. **但 k3s 侧的风险远低于文档给人的印象**（E2/E3/E4）：
   - 校验是**确定性的、fail-fast 的**，配错只会启动失败并留下清晰错误，**不损坏 etcd**
     （本次同一份 etcd 数据经历了一次 fatal 退出后仍能正常启动，即为证据）；
   - 三个 flag 必须同时改，这是 k3s 的显式约束，不是模糊地带；
   - **既有 Service 的爆炸半径实测 = 1 个对象（kube-dns）**，此前担心的 metrics-server 补发 IPv6
     **实测不成立**（E4）→ 原 R5 风险可下调。
3. **pod 侧的 IPAM 模式不需要动**。E7 证明既有节点永远拿不到 IPv6 podCIDR，所以要靠
   `network.cilium.io/ipv6-pod-cidr` 注解；这样可**保持 `ipam.mode=kubernetes` 不变**，
   从而避开"切换 IPAM 模式"这个 Cilium 明确警告的操作。

### 7.3 对用户提议的两个文档的判决

| 提议 | 判决 | 依据 |
| --- | --- | --- |
| `ipam-crd`（CRD-backed IPAM） | ❌ **不可用** | 官方原文：*"At the moment only single IP addresses are allowed. **CIDR's are not supported.**"* —— 连 CIDR 块都不支持，无法为每个节点分配 IPv6 /64，也没有任何 IPv6/双栈说明 |
| `ipam-cluster-pool` | ⚠️ **能做 pod 双栈，但不该选** | ①它**完全不碰 service**，对 E1 的结论无帮助 ②从本集群现用的 `ipam.mode=kubernetes` 切过去属**无文档支持的 IPAM 模式变更**，Cilium 原文：*"Don't change the IPAM mode of an existing cluster except when following a documented migration procedure… The safest path to change IPAM mode is to install a fresh Kubernetes cluster"*，而唯一有文档的在线迁移是 cluster-pool → multi-pool ③operator 会**重新分配**各节点 IPv4 /24，极可能与现有映射（jumper-0=10.42.0.0/24、cheshi-0=10.42.1.0/24、jumper-2=10.42.2.0/24、jumper-1=10.42.3.0/24）不一致，从而**打断路由器上那 4 条静态路由**，而既有 pod 仍持有旧 IP |

### 7.4 复现脚本（本机 Docker，不触碰生产）

```bash
# 启动：与生产同版本、同 k3s 配置，但三个 flag 已是双栈
docker run -d --name k3s-ds5 --privileged --hostname k3s-dsx \
  --sysctl net.ipv6.conf.all.disable_ipv6=0 \
  -v k3s-dsx-data:/var/lib/rancher/k3s rancher/k3s:v1.36.5-k3s1 server --cluster-init \
  --flannel-backend=none --disable-kube-proxy --disable-network-policy \
  --disable-cloud-controller --disable=traefik --disable=servicelb --disable=local-storage \
  --cluster-cidr=10.42.0.0/16,fdb5:92d0:b067:4200::/56 \
  --service-cidr=10.43.0.0/16,fdb5:92d0:b067:4300::/112 \
  --node-ip=172.17.0.3,fd00:3::1

# 验证
docker exec k3s-ds5 kubectl get servicecidr
docker exec k3s-ds5 kubectl get svc -A -o custom-columns=\
'NS:.metadata.namespace,NAME:.metadata.name,IPS:.spec.clusterIPs,POLICY:.spec.ipFamilyPolicy'
```

> 注：`docker exec` 传 heredoc 必须加 `-i`（`docker exec -i ... kubectl apply -f -`），否则
> stdin 未分配、`apply` 报 "no objects passed to apply"。

### 7.5 Cilium 侧实验（E10–E14）：注解方案被证伪

> 在 §7.4 的容器基础上装 Cilium 1.20.2（`helm install`，values 与生产对齐 + `ipv6.enabled=true`）。
> 容器需 `--privileged`，且**进入 k3s 前必须 `mount --make-rshared /`**，否则 Cilium init 容器报
> `path "/sys/fs/bpf" is mounted on "/sys" but it is not a shared mount` 而 `CreateContainerError`。

| # | 结论 | 关键输出 |
| --- | --- | --- |
| **E10** | **`ipv6.enabled=true` + `ipam.mode=kubernetes` + 节点无 IPv6 PodCIDR → agent 不是"优雅阻塞"，而是 panic + CrashLoopBackOff** | `level=warn msg="Waiting for k8s node information" module=agent.controlplane.local-node-sync error="required IPv6 PodCIDR not available"` → `panic: Start or stop failed to finish on time, aborting forcefully.`，`exitCode=2`，`CrashLoopBackOff`。<br>⚠️ **注意**：`cilium-config` 里 `k8s-require-ipv6-pod-cidr=false` 也**照样阻塞** —— 该 CM 键不能关掉这个要求（文档说 `ipam=kubernetes` 会自动启用它，实测是 agent 内部逻辑强制） |
| **E11** | **`network.cilium.io/ipv6-pod-cidr` Node 注解不满足该要求**（启动前就在位也不行） | 注解 `fd-b5…:4200::/64` 已在 Node 上，重启 agent 后仍 `required IPv6 PodCIDR not available`；日志显示 `Retrieved node information from kubernetes node nodeName=ds-sim3` 后即失败；**CiliumNode 对象根本没被创建** → 注解路径无效 |
| **E12** | **`Node.spec.podCIDRs` 不可修改** | `The Node "k3s-cil2" is invalid: spec.podCIDRs: Forbidden: node updates may not change podCIDR except from "" to valid` → 既有节点无法补 IPv6 段 |
| **E13** | **新加入**双栈集群的节点会自动拿到双栈 podCIDR，Cilium 双栈 IPAM 完全正常 | `podCIDRs=["10.42.0.0/24","fdb5:92d0:b067:4200::/64"]`；`cilium-dbg status`：`IPAM: IPv4: 5/254 from 10.42.0.0/24, IPv6: 5/… from fdb5:92d0:b067:4200::/64`，`Masquerading: BPF [eth0] … [IPv4: Enabled, IPv6: Enabled]`；Pod 实测双栈：coredns `[10.42.0.223, fdb5:…::99b5]`、metrics-server `[10.42.0.66, fdb5:…::3dcd]` |
| **E14** | **控制面节点的 Node 对象删不掉**：k3s finalizer 使其卡在 Terminating | `finalizers=["wrangler.cattle.io/managed-etcd-controller"]`、`deletionTimestamp` 已设置但对象未消失，`podCIDRs` 保持 `["10.42.0.0/24"]` → "删节点让它重新注册"这条路在 CP 节点上走不通 |

**E10+E11+E12+E14 四条叠加的结论**：`ipam.mode=kubernetes` 下，**既有节点无法获得 IPv6 PodCIDR**，
因此 **Pod 双栈必须改用 Cilium 自己的 IPAM（`cluster-pool`）**。E13 证明该模式在双栈集群上工作正常。

**复现要点（供 P0 演练复用）**：

```bash
# 1) 专用网络：固定 IPv4 + 真实 IPv6（节点必须有真实 IPv6，见 E9）
docker network create ds-net --driver bridge \
  --subnet 172.30.9.0/24 --gateway 172.30.9.1 \
  --subnet fd00:3::/64 --gateway fd00:3::1 --ipv6
# 2) k3s：固定 IP + Cilium 友好挂载 + make-rshared
docker run -d --name k3s-cil --privileged --hostname k3s-cil \
  --network ds-net --ip 172.30.9.2 --ip6 fd00:3::2 -p 127.0.0.1:16443:6443 \
  --cgroupns=host --tmpfs /run --tmpfs /var/run -v /lib/modules:/lib/modules:ro \
  -v k3s-cil-data:/var/lib/rancher/k3s \
  --sysctl net.ipv4.ip_forward=1 --sysctl net.ipv6.conf.all.forwarding=1 \
  --sysctl net.ipv4.conf.all.rp_filter=0 \
  --entrypoint /bin/sh rancher/k3s:v1.36.5-k3s1 -c 'mount --make-rshared /; exec k3s server \
    --cluster-init --flannel-backend=none --disable-kube-proxy --disable-network-policy \
    --disable-cloud-controller --disable=traefik --disable=servicelb --disable=local-storage \
    --cluster-cidr=10.42.0.0/16,fdb5:92d0:b067:4200::/56 \
    --service-cidr=10.43.0.0/16,fdb5:92d0:b067:4300::/112 \
    --node-ip=172.30.9.2,fd00:3::2'
# 3) 复刻"节点先以单栈身份注册"再切双栈，才能得到 IPv4-only podCIDR 的生产前置状态
# 4) helm 需把 cache/config/data 指到可写目录（沙箱下 ~/.cache 只读）：
export HELM_CACHE_HOME=$PWD/tmp/helm/cache HELM_CONFIG_HOME=$PWD/tmp/helm/config HELM_DATA_HOME=$PWD/tmp/helm/data
# 5) docker exec 传 heredoc 必须加 -i
```
