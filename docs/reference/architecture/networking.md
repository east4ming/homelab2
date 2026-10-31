# Networking

## 地址规划

站点 ULA 为 `fdb5:92d0:b067::/48`（RFC 4193，随机 40-bit global ID）。所有集群内部
地址都从中派生，**唯一出处**是 [metal/inventories/prod.yml](https://git.west-beta.ts.net/ops/homelab2/src/branch/master/metal/inventories/prod.yml)
的 `all.vars`。

| 用途 | 网段 | 定义位置 |
| --- | --- | --- |
| 站点 ULA | `fdb5:92d0:b067::/48` | 约定（文档） |
| 节点主接口 | `fdb5:92d0:b067:1::/64` | `dualstack_ipv6_node_cidr` + 各 host 的 `node_ipv6` |
| Pod | `fdb5:92d0:b067:4200::/56` | `dualstack_ipv6_pod_cidr`（k3s `cluster-cidr` / Cilium `clusterPoolIPv6PodCIDRList`） |
| Service | `fdb5:92d0:b067:4300::/112` | `dualstack_ipv6_service_cidr`（k3s `service-cidr`） |

节点 IPv6 是**固定值**，不是运行时探测的 ISP GUA：

| 节点 | IPv4 | IPv6（node-ip） |
| --- | --- | --- |
| n100-jumper-0 | 192.168.3.226 | `fdb5:92d0:b067:1::11` |
| n100-jumper-1 | 192.168.3.174 | `fdb5:92d0:b067:1::12` |
| n100-jumper-2 | 192.168.3.158 | `fdb5:92d0:b067:1::13` |
| n100-cheshi-0 | 192.168.3.154 | `fdb5:92d0:b067:1::14` |

## 为什么节点身份不用 ISP 下发的 GUA

ISP 的 `240e:` 委派前缀会随 PPPoE 重拨/重启漂移（2026-10-29 就从
`240e:3a3:20ba:ae43::/64` 变成 `240e:3a3:2002:6440::/64`）。而 k3s 的 `node-ip`
是**字面量**，不能动态解析。一旦用它做身份：

- kubelet 每 10 秒报 `failed to validate secondaryNodeIP`，Node 的 IPv6 InternalIP 停旧；
- Cilium agent 把旧地址写进 `CiliumNode`，`auto-direct-node-routes` 装不出跨节点
  IPv6 直连路由 → **跨节点 IPv6 pod 通信静默失效**；
- hostNetwork pod 的 IPv6 EndpointSlice 指向不存在的地址；
- 每次漂移都要改 4 台 `config.yaml` 并滚动重启 k3s + cilium agent。

所以节点身份锚定在站点 ULA 上；GUA 保留在接口上，只承担出站/NAT。
细节与回退见 [specs/012-stable-node-ula-ipv6](https://github.com/east4ming/homelab2/blob/master/specs/012-stable-node-ula-ipv6/plan.md)。

## 地址如何落地

- **已装机器的持久化**：`metal/roles/prerequisites` 渲染
  `/etc/netplan/60-homelab-ula.yaml`（只写 ULA 一条；netplan 的 `addresses`
  是追加语义，cloud-init 的 IPv4 与 `dhcp6: yes` 不受影响）并 `netplan apply`。
- **新装机器**：`metal/roles/pxe_server/templates/user-data.j2` 的 netplan
  `addresses` 直接包含 ULA。
- **k3s**：`node-ip` 与 `kubelet-arg: node-ip=` 引用 inventory 的 `node_ipv6`；
  k3s role 会先断言该地址确实在接口上，缺地址直接失败（不静默降级）。

## 路由器

节点间 IPv6 走 LAN 的二层转发（`br-lan` 桥），路由器不参与该 `/64` 的路由，
**不需要**为 ULA 做任何配置：不需要静态路由、不需要 RA 下发、不需要防火墙放行。
外部访问走 Tailscale（`node-external-ip` 仍是 Tailscale 的 `100.x` / `fd7a:`）。

## 流量路径

```mermaid
flowchart TD

  laptop/desktop/phone <-- Tailscale VPN Over Internet/Intranet --> Tailscale Ingress Pod

  subgraph LAN
    subgraph k8s[Kubernetes cluster]
      Pod --> Service
      Service --> Ingress

      Tailscale Ingress Pod

      Tailscale Funnel Ingress Pod
      Tailscale Funnel Ingress Pod <--> Ingress
    end
    Tailscale Ingress Pod <--> Ingress
  end

  Tailscale Funnel Ingress Pod -- outbound --> ts.net
  Internet -- inbound --> ts.net
```

- Pod↔Pod（跨节点）：Cilium native routing，`auto-direct-node-routes` 按对方**节点 ULA** 装
  `fdb5:…420N::/64 via fdb5:…1::N` 的直连路由，下一跳是本 LAN 的二层邻居。
- 节点→外网：GUA（SLAAC）经路由器。
- 集群外访问：Tailscale Ingress / Funnel。
