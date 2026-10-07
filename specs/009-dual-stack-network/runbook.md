# 实施手册（Runbook）：homelab k3s 集群 IPv4/IPv6 双栈改造

**版本**: v2（实验校正版） | **Date**: 2026-10-03
**适用集群**: k3s `v1.36.5+k3s1` / Cilium `1.20.2` / Tailscale Operator `1.102.4` / 4 节点
**证据出处**: [research.md](./research.md) §7（本地对照实验 E1–E14）、§4.4/§4.8/§4.10（上游文档与源码）
**前置阅读**: [plan.md](./plan.md) §1.3（路线重估）

> ⚠️ **本手册 v2 推翻了 v1 的一个关键做法**：v1 计划用
> `network.cilium.io/ipv6-pod-cidr` Node 注解给既有节点补 IPv6 PodCIDR。
> **实测证明该注解在 Cilium 1.20.2 + `ipam.mode=kubernetes` 下无效**（E11），
> 且缺失 IPv6 PodCIDR 时 agent 会 **panic 并 CrashLoopBackOff**（E10）。
> v2 改为：**控制面走 k3s 三 flag，Pod 侧走 Cilium IPAM 模式切换**。

---

## 0. 一句话结论与三层判定

| 层 | 能否原地达成 | 手段 | 风险 |
| --- | --- | --- | --- |
| **node 双栈** | ✅ 能 | k3s 三个 flag（`cluster-cidr`/`service-cidr`/`node-ip`）**一起**改双栈，另加 `kubelet-arg: node-ip=<v4>,<v6>` | 🟡 已实测量化（fail-fast，etcd 不损坏） |
| **service 双栈** | ✅ 能（**必须**改 apiserver flag，Cilium 侧无解） | 同上；新 Service 用 `PreferDualStack` 即得双 ClusterIP | 🟢 既有 Service 实测只动 `kube-dns` |
| **pod 双栈** | ⚠️ 能，但**必须切 Cilium IPAM 模式** | `ipam.mode` 由 `kubernetes` 改为 `cluster-pool`，IPv4 列表对齐现有映射 + 新增 IPv6 列表 | 🟡 IPv4 每节点映射可能变化 → 需同步改路由器静态路由并滚动重启工作负载 |

**为什么 pod 侧必须切 IPAM 模式**（三条实测事实叠加，无解）：
1. `ipam.mode=kubernetes` 要求**每个节点**在 `Node.spec.podCIDRs` 里有 IPv6 段，否则 agent 报
   `required IPv6 PodCIDR not available` → **panic → CrashLoopBackOff**（E10）。
2. `Node.spec.podCIDRs` **不可修改**：`spec.podCIDRs: Forbidden: node updates may not change podCIDR except from "" to valid`（E12）。
3. 删除 Node 让它重新注册也走不通：控制面节点带 k3s finalizer
   `wrangler.cattle.io/managed-etcd-controller`，`kubectl delete node` 只会卡在 Terminating（E14）。
   而 `network.cilium.io/ipv6-pod-cidr` 注解**在启动前就在位也不生效**（E11）。

---

## 1. 实测证据索引（写本手册的依据）

| # | 结论 | 关键输出 |
| --- | --- | --- |
| E1 | Service 地址族只由 apiserver flag 决定，`ServiceCIDR` 无法引入新族 | 建 IPv6 `ServiceCIDR` 后 `RequireDualStack` 被拒：`this cluster is not configured for dual-stack services` |
| E2 | k3s 硬校验三个 flag 族人一致且必须同改 | `cluster-cidr: [...] and service-cidr: [...], must share the same IP version`；`cluster-cidr: [...] and node-ip: [...], must share the same IP version` |
| E3 | 三个 flag 同改后**原地**成功，ServiceCIDR 被原地更新 | API ready ~15s，无 fatal，`kubernetes` → `10.43.0.0/16,fdb5:92d0:b067:4300::/112` |
| E4 | 既有 Service 几乎不动 | `kubernetes`/`dstest`/`metrics-server` 的 ClusterIP 与 policy **全部未变**；仅 `kube-dns` 变双栈 |
| E5 | 新建 `PreferDualStack` Service 拿到双 ClusterIP | `["10.43.14.152","fdb5:92d0:b067:4300::7d4"] families=["IPv4","IPv6"]` |
| E6 | k3s 自动派生第二个 cluster-dns 并把 CoreDNS 置 `RequireDualStack` | `kube-dns: ["10.43.0.10","fdb5:92d0:b067:4300::a"]`（IPv6 = `::a`，即 index 10） |
| E7 | 已注册过的节点**不会**补发 IPv6 podCIDR | 迁移后 `podCIDRs=["10.42.0.0/24"]` |
| E8 | `disable-cloud-controller: true` 时 `node-ip` 不传给 kubelet | Node InternalIP 仍只有 IPv4 → 必须 `kubelet-arg: node-ip=` |
| E9 | 双栈 `cluster-cidr` 下 k3s 期望节点有真实 IPv6（flannel 会因此自杀） | `flannel exited: ... failed to find IPv6 address for interface eth0`（生产 flannel 关闭，不受此限） |
| **E10** | **`ipv6.enabled=true` + `ipam=kubernetes` + 节点无 IPv6 podCIDR → agent panic/CrashLoop** | `error="required IPv6 PodCIDR not available"` → `panic: Start or stop failed to finish on time` |
| **E11** | **`network.cilium.io/ipv6-pod-cidr` 注解不满足该要求**（启动前在位也不行） | 注解在位后重启 agent，仍 `required IPv6 PodCIDR not available`，且不生成 CiliumNode |
| E12 | `Node.spec.podCIDRs` 不可改 | `Forbidden: node updates may not change podCIDR except from "" to valid` |
| E13 | **新加入**双栈集群的节点会自动拿到双栈 podCIDR，Cilium 双栈 IPAM 正常工作 | `podCIDRs=["10.42.0.0/24","fdb5:92d0:b067:4200::/64"]`；Pod 实测 `[10.42.0.223, fdb5:...::99b5]` |
| E14 | 控制面节点删除被 k3s finalizer 阻塞 | `finalizers=["wrangler.cattle.io/managed-etcd-controller"]`，卡 Terminating |

---

## 2. 目标地址规划（已定稿）

| 用途 | 现值 | 目标值 |
| --- | --- | --- |
| Pod IPv4 | `10.42.0.0/16`（每节点 /24） | **不变** |
| Pod IPv6 | — | `fdb5:92d0:b067:4200::/56`（每节点 /64） |
| Service IPv4 | `10.43.0.0/16` | **不变** |
| Service IPv6 | — | `fdb5:92d0:b067:4300::/112` |
| 节点 IPv6 | SLAAC GUA `240e:3a3:20ba:ae43::/64` 内 | **不变**（不做静态化） |
| Cluster DNS | `10.43.0.10` | `10.43.0.10`（**§4.2 决策点**） |

每节点 Pod 段（沿用现有 IPv4 与节点的对应关系，v4/v6 下标对齐）：

| 节点 | IPv4 PodCIDR | 目标 IPv6 Pod /64 |
| --- | --- | --- |
| n100-jumper-0 | `10.42.0.0/24` | `fdb5:92d0:b067:4200::/64` |
| n100-cheshi-0 | `10.42.1.0/24` | `fdb5:92d0:b067:4201::/64` |
| n100-jumper-2 | `10.42.2.0/24` | `fdb5:92d0:b067:4202::/64` |
| n100-jumper-1 | `10.42.3.0/24` | `fdb5:92d0:b067:4203::/64` |

---

## 3. 实施前置条件检查清单（全部必须通过）

```bash
# 3.1 集群健康
kubectl get nodes -o wide                     # 4/4 Ready，版本 v1.36.5+k3s1
kubectl -n kube-system get ds cilium          # 4/4
kubectl get pods -A --field-selector=status.phase!=Running   # 必须为空（或已知的 Completed）
kubectl -n rook-ceph exec deploy/rook-ceph-tools -- ceph status   # HEALTH_OK
kubectl -n rook-ceph exec deploy/rook-ceph-tools -- ceph osd tree # 4 个 OSD 全 up/in

# 3.2 节点 IPv6 健康（前置硬条件，E9）
for h in 226 174 158 154; do ssh casey@192.168.3.$h \
  'hostname; ip -6 route show default; ping -6 -c1 -W3 2400:3200::1 >/dev/null && echo v6-OK || echo v6-FAIL'; done
#   四台必须都有 GUA、有 default via fe80:: 且 ping6 OK

# 3.3 关键版本冻结（R12/R14）
helm -n kube-system history cilium | tail -2      # 必须 deployed 1.20.2（不要回滚到 1.20.1）
kubectl get nodes -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.status.nodeInfo.kubeletVersion}{"\n"}{end}'

# 3.4 GitOps 暂停（实测细化，2026-10-07）
#    [实测] 36 个 ArgoCD Application 全部 automated+selfHeal，但【没有任何一个管理 Cilium 或 k3s】
#      （Cilium/k3s 由 Ansible metal/roles 管理）→ 因此 P1（k3s config）与 P2（helm upgrade cilium）
#      本身【不会】被 ArgoCD 回退，这两步不强制暂停。
#    ⚠️ 但 P2.5/§9 的「重建工作负载」这一步【必须先暂停 selfHeal】：
#      `kubectl rollout restart` 会往 Pod 模板加 kubectl.kubernetes.io/restartedAt 注解
#      → 相对 git 产生 drift → selfHeal 会把它改回去 → 又触发一轮 rollout
#      → 每个工作负载会被滚动重启【两遍】。不是故障，但会很乱、窗口被拉长。
#    做法：`kubectl -n argocd patch applications <所有> --type merge -p '{"spec":{"syncPolicy":{"automated":null}}}'`
#          或直接在 UI 关掉 auto-sync；重启完工作负载后再恢复。

# 3.5 备份达标（§5 全部完成且验证可列出）

# 3.6 窗口与人力
#    - 维护窗口：控制面中断 3–10 分钟 + Cilium 切换后工作负载滚动重启
#    - 有人在现场可物理接触节点（应急硬重启）
```

**任一不通过 → 不进入实施。**

---

## 4. 方案总览与两个决策点

### 4.1 阶段划分

```
P0  演练（k3d / stag，不碰生产）           ← 必做
P1  控制面双栈（k3s 三 flag）              ← 有 API 中断（3–10 分钟）
P2  Cilium IPAM 切换（kubernetes→cluster-pool）+ 双栈   ← 有 Pod IP 变动
P3  验证 / 收尾 / GitOps 回写
```

**P1 与 P2 之间存在一个安全中间态**：P1 完成后集群是"node + service 双栈、pod 仍单栈"。
此时**不要**急着开 `ipv6.enabled=true`（E10 会 panic）。P2 必须与 Cilium 的 IPAM 切换**同一次 helm 操作**完成。

### 4.2 决策点 1：`cluster-dns` 策略（P1 之前必须定）

E6 证明：`cluster-dns` 未显式设置时，k3s 会**自动**按每个 service-cidr 各派生一个 DNS IP，
并把 CoreDNS 置为 `RequireDualStack` → **每个 Pod 的 `/etc/resolv.conf` 改变**（需 Pod 重启生效）。

| 选项 | 效果 | 代价 |
| --- | --- | --- |
| **A（默认，不设 `cluster-dns`）** | CoreDNS 自动双栈，`kube-dns` 拿到 `[10.43.0.10, fdb5:...:4300::a]` | Pod 需重启才能用上双 DNS；`resolv.conf` 变化面广 |
| **B（显式 `cluster-dns: 10.43.0.10`）** | CoreDNS 保持单栈，`resolv.conf` 不变 | 集群内 DNS 查询走 IPv4（AAAA 解析不受影响） |

> **推荐 B**：本次目标是网络双栈，不是 DNS 双栈；B 把 `resolv.conf` 这个面广的变更面直接消除。
> **注意**：`cluster-dns` 属 k3s Critical Configuration Values，必须在 P1 与另三个 flag **同窗口**写入。

### 4.3 决策点 2：P2 的 IPv4 映射处理

切到 `cluster-pool` 后，operator 会**自己**给每个节点分配 IPv4 `/24`，顺序不受现有映射约束（E13 已证新节点会拿到新分配的段）。
现有 pod 保留旧 IP，而路由器上那 4 条静态路由按旧映射指向节点 → **可能造成既有 Pod 跨网段失联**。

**处置（按优先级）**：
1. **首选**：`clusterPoolIPv4PodCIDRList` 按"期望映射顺序"排列，切换后**立即核对**每节点实际拿到的段；
   若与旧映射一致，无需改路由器。
2. **兜底（必然可用）**：核对后**按实际映射更新路由器 4 条静态路由**，并**滚动重启全部工作负载**，
   让 Pod 全部换到新映射下的地址。
3. 无论走哪条，**P2 都必须与"滚动重启工作负载"绑定在同一个窗口**，否则会长时间处于新旧 IP 混用状态。

---

## 5. 备份方案（P1 之前必须完成并验证）

> 原则：**任何回退动作都不得依赖正在被回退的东西**；备份落点必须在集群之外。
> 已验证的集群外落点：`192.168.3.216:8010` = `NAS33657A.lan`（S3，非 k8s 节点、不在 LB 池）。

### 5.1 etcd 快照（RPO 的兜底）

```bash
# k3s 已配置 S3 快照（每 12h）。窗口前必须手动再打一次：
ssh casey@192.168.3.226 'sudo k3s etcd-snapshot save --name pre-dualstack'
ssh casey@192.168.3.226 'sudo k3s etcd-snapshot list' | tail -8
#   验收：能看到刚生成的快照，且同时有 file:// 与 s3:// 两条记录
#   记录快照文件名与大小到变更单
```

### 5.2 集群对象快照（用于 diff 与回退比对）

```bash
mkdir -p dualstack-backup
kubectl get svc -A -o json | jq -S . > dualstack-backup/services-before.json
kubectl get svc -A -o custom-columns=\
'NS:.metadata.namespace,NAME:.metadata.name,IPS:.spec.clusterIPs,POLICY:.spec.ipFamilyPolicy' \
  > dualstack-backup/services-before.txt
kubectl get svc,endpoints,servicecidr,node,pv,pvc,sc -A -o yaml > dualstack-backup/objects-before.yaml
kubectl get pods -A -o wide > dualstack-backup/pods-before.txt
kubectl get cep -A -o wide  > dualstack-backup/cep-before.txt
kubectl -n kube-system get cm cilium-config -o yaml > dualstack-backup/cilium-config-before.yaml
```

### 5.3 Helm 版本与 values（回退的精确依据）

```bash
helm -n kube-system history cilium            > dualstack-backup/cilium-history.txt
helm -n kube-system get values cilium -o yaml > dualstack-backup/cilium-values-before.yaml
helm -n kube-system get metadata cilium -o yaml > dualstack-backup/cilium-meta-before.yaml
```

### 5.4 节点配置存档（4 台全做）

```bash
for h in 226 174 158 154; do ssh casey@192.168.3.$h '
  echo "### hostname"; hostname
  echo "### k3s config"; sudo cat /etc/rancher/k3s/config.yaml
  echo "### k3s service"; sudo systemctl cat k3s
  echo "### netplan"; sudo cat /etc/netplan/*.yaml
  echo "### sysctl.d"; sudo cat /etc/sysctl.d/90-homelab-prerequisites.conf
  echo "### ipv6 addr/route"; ip -6 addr show scope global; ip -6 route show default
' > dualstack-backup/node-$h-before.txt; done
```

### 5.5 路由器配置（改静态路由前必须备份）

```bash
ssh root@192.168.3.1 -i ~/.ssh/id_ed25519 'uci export' > dualstack-backup/openwrt-uci-before.txt
ssh root@192.168.3.1 -i ~/.ssh/id_ed25519 'sysupgrade -b /tmp/owrt-backup.tar.gz && base64 /tmp/owrt-backup.tar.gz' \
  > dualstack-backup/openwrt-sysupgrade-before.b64
ssh root@192.168.3.1 -i ~/.ssh/id_ed25519 'ip -4 route show; ip -6 route show' \
  > dualstack-backup/openwrt-routes-before.txt
```

### 5.6 备份落盘到集群外并**验证可读**

```bash
scp dualstack-backup/* nas:/volume1/backups/dualstack-$(date +%F)/
ssh nas 'ls -l /volume1/backups/dualstack-*/ | head -20'   # 确认文件在、大小非 0
```

### 5.7 可恢复性验证（**不可跳过**）

- 在 **P0 演练环境**上实际执行一次 `k3s etcd-snapshot` 恢复，记录实测 RTO。
- **绝不**把生产的 etcd 快照恢复到演练集群（会带出生产 Secret）。
- 记录：控制面恢复 ≈ ? 分钟；整集群从快照恢复 ≈ ? 分钟。

---

## 6. P0：演练（必做，不碰生产）

**目标**：把 §8 应急预案里的每条处置都实跑一遍，把"未知"清零。

1. 用工作站的 Docker 起一个同构集群（**已验证可用**，脚本见 research §7.4）：
   k3s `v1.36.5+k3s1`、`--cluster-init`、`--flannel-backend=none --disable-kube-proxy
   --disable-network-policy --disable-cloud-controller`。
   **注意**：容器需 `--privileged`，且**进入 k3s 前必须 `mount --make-rshared /`**，
   否则 Cilium 的 init 容器会失败：`path "/sys/fs/bpf" is mounted on "/sys" but it is not a shared mount`。
2. 演练顺序（每一步都记录命令/输出/耗时）：
   - a) 单栈集群起来 → 记录基线
   - b) 三 flag 改双栈重启 → 验证 E3/E4（既有 Service 只动 kube-dns）
   - c) 触发一次**故意配错**（只改 service-cidr）→ 确认 fail-fast 且 etcd 无损
   - d) 安装 Cilium（`ipam.mode=kubernetes` + `ipv6.enabled=true`）→ **复现 E10 的 panic**
   - e) 改为 `ipam.mode=cluster-pool` + 双列表 → 确认 agent Ready、Pod 拿到双栈 IP
   - f) 演练 §8 的**回退**（回到单栈 Cilium、回到单栈 k3s）
3. **验证门 G0**：以上 a–f 全部跑通且记录完整；否则不得进入生产。

---

## 7. P1/P2/P3：生产实施步骤

### P1 — 控制面双栈（唯一有 API 中断的阶段）

**P1.1** 窗口开始，重打快照：
```bash
ssh casey@192.168.3.226 'sudo k3s etcd-snapshot save --name pre-dualstack-window'
```

**P1.2** 修改仓库 `metal/roles/k3s/defaults/main.yml` 的 `k3s_server_config`（保持 GitOps 单一事实源），
然后同步写入三台 server 的 `/etc/rancher/k3s/config.yaml`。**三台内容必须完全一致**：

```yaml
# ⚠️ 逗号后不能有空格（k3s 用 SplitStringSlice 切分且不 trim）
# ⚠️ 四个键必须同窗口一起改（E2 硬校验）
cluster-cidr: 10.42.0.0/16,fdb5:92d0:b067:4200::/56
service-cidr: 10.43.0.0/16,fdb5:92d0:b067:4300::/112
cluster-dns: 10.43.0.10            # 决策点 1 选 B；选 A 则删掉本行
node-ip: <本节点IPv4>,<本节点GUA>    # 例如 192.168.3.226,240e:3a3:20ba:ae43:2e0:4cff:fe72:379f
```

并给**每个节点**（含 agent `n100-cheshi-0`）加 kubelet 参数 —— 因为 `disable-cloud-controller: true`
时 k3s **不会**把 `node-ip` 传给 kubelet（E8），不加则 Node 的 InternalIP 仍只有 IPv4：

```yaml
kubelet-arg:
  - "node-ip=<本节点IPv4>,<本节点GUA>"
```

> ⚠️ 不要使用 k3s 文档里 `--kubelet-arg="node-ip=0.0.0.0"` 那种写法，它会覆盖掉显式的一对地址。

**P1.3** 按 P0 演练确定的顺序重启。**预期为"三台一起停 → 改 → 一起启"**（避免 flag 不一致的混合态）：

```bash
# 停止（stop 会正常返回，不受影响）
for h in 226 174 158; do ssh casey@192.168.3.$h 'sudo systemctl stop k3s'; done

# 写入配置（P1.2），然后启动
# ⛔ 2026-10-07 生产实测踩坑修正：绝不能用 `systemctl start k3s`（不带 --no-block）串行启动！
#    原因：etcd 3 成员需要 2 票才选主。第 1 台启动后会一直停在 activating，
#    systemctl start 因此永不返回 → ssh 不返回 → for 循环卡死在第 1 台，
#    第 2/3 台根本没被执行 → 形成死锁：
#      第 1 台 active ⟸ 需要 quorum ⟸ 需要另外两台起来 ⟸ 需要第 1 台的 start 返回
#    症状：第 1 台 `systemctl list-jobs` 显示 `k3s.service start running`，
#          另两台 `Active: inactive (dead)` 且 journalctl 里没有任何启动痕迹。
# ✅ 正确做法：必须加 --no-block，并且并行启动
for h in 226 174 158; do
  ssh casey@192.168.3.$h 'sudo systemctl start --no-block k3s' &
done
wait

# 等待 etcd 形成 quorum + API 就绪（通常 30–90 秒）
until kubectl get --raw /readyz >/dev/null 2>&1; do sleep 5; done; echo API-OK

# agent 单独滚动即可
ssh casey@192.168.3.154 'sudo systemctl restart k3s'
```

> **救援速查**：若已卡在死锁里，**不需要动第 1 台**（它的 start 作业会在 quorum 形成后自行完成），
> 只需并行启动其余节点：
>
> ```bash
> for h in 174 158; do ssh casey@192.168.3.$h 'sudo systemctl start --no-block k3s' & done; wait
> ```
> 诊断用：`systemctl list-jobs`（看有没有卡住的 start 作业）、`systemctl is-active k3s`。

**P1.4 验证门 G1**（任一不过 → 走 §8 回退 R-k3s）
```bash
kubectl get --raw /readyz                                  # ok

# ⛔ 2026-10-07 生产实测修正：绝不要用 `kubectl get nodes -o wide` 判断双栈！
#    实测（kubectl v1.37.1 / server v1.36.5+k3s1）：`-o wide` 的 Node 表格只渲染【一个】InternalIP
#    （取的是 addresses 里排在前面的 IPv4），即使节点确实有两个 InternalIP 也只显示 IPv4。
#    同一份数据用 custom-columns / jsonpath 却能看到两个 → `-o wide` 不能用于双栈校验。
# ✅ 正确做法：显式取 InternalIP 类型的全部地址
kubectl get nodes -o custom-columns='NAME:.metadata.name,INTERNAL-IPs:.status.addresses[?(@.type=="InternalIP")].address'
#   期望：每行形如 192.168.3.226,240e:3a3:20ba:ae43:2e0:4cff:fe72:379f

kubectl get servicecidr                                    # IPv4 + IPv6 两个范围
kubectl -n kube-system get svc kube-dns -o jsonpath='{.spec.clusterIPs}{"\n"}'   # 按决策点 1 预期
diff <(jq -S . dualstack-backup/services-before.json) <(kubectl get svc -A -o json | jq -S .)
#   ↑ 只允许 kube-dns（选 A 时）出现差异；其他任何差异都要停下查清
kubectl -n rook-ceph exec deploy/rook-ceph-tools -- ceph status   # 仍 HEALTH_OK
```
若某节点缺 IPv6 InternalIP → `kubelet-arg` 没生效（E8），停下修正；
**注意 IPv6 可能滞后出现，逐节点确认并留等待时间**（P0 实测：ds-z 立刻有、ds-a 迟迟没有）。
另外**不要**用 `-o wide` 的 EXTERNAL-IP 列判断 `node-external-ip` —— 本集群该列一直是 `<none>`（改造前就是），不是回归。

**⛔ P1 结束后不要开 `ipv6.enabled`**（会 panic，E10）。直接进 P2。

---

### P2 — Cilium IPAM 切换 + 双栈（有 Pod IP 变动）

**P2.1** 记录当前每节点 IPv4 映射（用于切换后比对）：
```bash
kubectl get nodes -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.spec.podCIDRs}{"\n"}{end}' \
  | tee dualstack-backup/podcidr-before.txt
```

**P2.1.5（2026-10-07 生产实测新增，**必须**在 helm upgrade 之前做）—— 清理陈旧的 CiliumNode 分配**

> **这是 P2 最大的坑，P0 演练无法发现**（P0 是全新安装，没有历史 `CiliumNode`）。

```bash
kubectl get ciliumnode -o jsonpath='{range .items[*]}{.metadata.name}: spec.ipam={.spec.ipam}{"\n"}{end}'
```

若任一 `CiliumNode` 的 **`spec.ipam.podCIDRs` 已有值但只有 IPv4**（从 `ipam.mode=kubernetes` 时代残留）：

- cluster-pool 模式下，每节点分配由 **operator 写入 `CiliumNode.spec.ipam.podCIDRs`**；
- 但该字段**已被旧值占住**，operator 视为"已分配"而**静默跳过**（日志无任何 IPAM 动作、无报错）；
- 结果：**IPv6 段永远补不上** → 新 agent 报
  `Waiting for k8s node information … error="required IPv6 PodCIDR not available"` → 卡住 → DS 停在 2/4 →
  相关节点被打上 `node.cilium.io/agent-not-ready` 污点，**新 Pod 无法调度**。

**两种处置（推荐 A）：**

**A. 手工补齐（保留现有 IPv4 映射 → 路由器路由不用改、既有 Pod 不换 IP）**
```bash
# 下标与现有 IPv4 对齐，IPv6 全部落在 clusterPoolIPv6PodCIDRList 池内且互不重叠
kubectl patch ciliumnode n100-jumper-0 --type=merge -p '{"spec":{"ipam":{"podCIDRs":["10.42.0.0/24","fdb5:92d0:b067:4200::/64"]}}}'
kubectl patch ciliumnode n100-cheshi-0 --type=merge -p '{"spec":{"ipam":{"podCIDRs":["10.42.1.0/24","fdb5:92d0:b067:4201::/64"]}}}'
kubectl patch ciliumnode n100-jumper-2 --type=merge -p '{"spec":{"ipam":{"podCIDRs":["10.42.2.0/24","fdb5:92d0:b067:4202::/64"]}}}'
kubectl patch ciliumnode n100-jumper-1 --type=merge -p '{"spec":{"ipam":{"podCIDRs":["10.42.3.0/24","fdb5:92d0:b067:4203::/64"]}}}'
kubectl -n kube-system get pods -l k8s-app=cilium -w      # 观察卡住的 agent 转 Ready
```
> 依据：agent 检查的是 **CiliumNode**（不是 k8s Node）—— P0 里 `ds-z` 的 k8s Node 也只有 IPv4，但 CiliumNode 有两族 → agent Ready。
> 注意该字段名义上归 operator 所有，属管理员越权写入，**写完要观察 operator 是否把它抹掉**；若被抹掉才退到 B。

**B. 删除 CiliumNode 让 operator 重新分配** —— 会**重新洗牌 IPv4 映射**，必须接 §4.3 的兜底流程
（按实际映射改路由器 4 条静态路由 + 重建工作负载）。

**P2.2** 改 `metal/roles/cilium/defaults/main.yml`，**一次 helm upgrade 内同时**改这几项
（分开做会出现 E10 的 panic 中间态）：

```yaml
ipv6:
  enabled: true
ipam:
  mode: cluster-pool                 # ← 由 kubernetes 改为 cluster-pool
  operator:
    clusterPoolIPv4PodCIDRList:      # ← 按"期望映射顺序"排列，尽量命中现有映射
      - "10.42.0.0/24"
      - "10.42.1.0/24"
      - "10.42.2.0/24"
      - "10.42.3.0/24"
    clusterPoolIPv4MaskSize: 24
    clusterPoolIPv6PodCIDRList:
      - "fdb5:92d0:b067:4200::/56"
    clusterPoolIPv6MaskSize: 64
ipv6NativeRoutingCIDR: "fdb5:92d0:b067:4200::/56"
# 其余保持原样：routingMode=native / autoDirectNodeRoutes / bpf.masquerade /
#              devices=e+ / kubeProxyReplacement / loadBalancer.mode=dsr 等
```

> `ipam.mode` 变更在 Cilium 官方属**无文档支持的操作**（原文：最安全的方式是"装一个新集群"）。
> 本方案之所以仍可用，是因为 `cluster-pool` 的 CIDR 由 Cilium 自己管理、
> **不依赖 `Node.spec.podCIDRs`**，因此不受 E7/E12 限制。**风险全部集中在 IPv4 映射上**，见 P2.4。

**P2.3** 执行升级并盯住 agent：
```bash
helm -n kube-system upgrade cilium cilium/cilium --version 1.20.2 \
  -f <渲染后的 values> --wait --timeout 10m
# 若 --wait 超时：立刻看 agent 日志，区分"等 PodCIDR"(E10) 与"环境问题"
```

**P2.4 验证门 G2**（关键：IPv4 映射 + 双栈 IPAM）
```bash
kubectl -n kube-system get ds cilium                       # 4/4，无 CrashLoop
kubectl -n kube-system get pods -l k8s-app=cilium          # 全部 Running/Ready
kubectl -n kube-system exec ds/cilium -c cilium-agent -- cilium-dbg status | head -20
#   ↑ 期望看到：IPAM: IPv4: n/... from 10.42.x.0/24, IPv6: n/... from fdb5:...
#               Masquerading: BPF [eth0] ... [IPv4: Enabled, IPv6: Enabled]
kubectl get ciliumnode -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.spec.ipam.podCIDRs}{"\n"}{end}'
#   ↑ 每节点必须同时有 IPv4 与 IPv6

# ★ IPv4 映射比对
diff dualstack-backup/podcidr-before.txt <(kubectl get nodes -o jsonpath=... )
```

**P2.5** 按 §4.3 处置 IPv4 映射：
- 映射一致 → 跳过。
- 映射变化 → **立即**更新路由器 4 条静态路由到新映射（见 P2.6），然后**滚动重启全部工作负载**：
```bash
kubectl -n <ns> rollout restart deploy,statefulset,daemonset   # 逐 ns 做，观察就绪
```
> 不重启工作负载的后果：旧 Pod 保留旧 IP，而路由器按新映射转发 → 跨节点访问失败。

**P2.6** 路由器静态路由（若需要改）
```bash
ssh root@192.168.3.1 -i ~/.ssh/id_ed25519
# 先看现状，再按实际映射逐条 uci set，最后 uci commit network && /etc/init.d/network reload
uci show network | grep "@route\["
```
> 路由器的 IPv4 pod 路由**不受 IPv6 前缀漂移影响**（它们指向节点 IPv4），这是本方案的一个稳定点。

**P2.7 验证门 G3**
```bash
# Pod 双栈
kubectl run dstest --image=busybox:1.36 --restart=Never -- sleep 300
kubectl get pod dstest -o jsonpath='{.status.podIPs}{"\n"}'      # 必须有 IPv4 + IPv6
# service 双栈
kubectl apply -f - <<'EOF'
apiVersion: v1
kind: Service
metadata: {name: dstest-svc}
spec: {ipFamilyPolicy: PreferDualStack, ports: [{port: 80}], selector: {run: dstest}}
EOF
kubectl get svc dstest-svc -o jsonpath='{.spec.clusterIPs}{"\n"}'   # 两个
# 连通性（在 dstest 内）
kubectl exec dstest -- ping -6 -c2 fdb5:92d0:b067:4300::<其他pod>   # pod→pod 跨节点
kubectl exec dstest -- ping -6 -c2 2400:3200::1                     # pod→internet（经节点 NAT66）
kubectl exec dstest -- ping -6 -s 1400 -c2 <对端>                    # 大包（#16080 PMTU）
kubectl -n kube-system get pods -l k8s-app=hubble-relay             # 必须 Running（#42017）
cilium connectivity test
kubectl delete pod dstest; kubectl delete svc dstest-svc
```

---

### P3 — 收尾

1. 回写仓库：`metal/roles/k3s/defaults/main.yml`、`metal/roles/cilium/defaults/main.yml` 与实际一致。
2. 恢复 ArgoCD 自动同步，确认无 drift（`kubectl diff` 或 ArgoCD UI 全 Synced）。
3. 落地 §8 的常态监控项。
4. 把实测耗时/RTO/异常点回写本手册。

---

## 8. 状态监控

### 8.1 上线前埋点（P1 之前就要有）

| 监控项 | 方法 | 判据 |
| --- | --- | --- |
| 节点 IPv6 默认路由是否被 RA 刷新 | 定时采 `ip -6 route show default` 的 `expires` | 应在 2600–2700s 间反复重置，**不得单调下降到 0** |
| 节点实际 GUA vs Node InternalIP | 比对 `ip -6 addr` 与 `kubectl get nodes -o custom-columns='NAME:.metadata.name,INTERNAL-IPs:.status.addresses[?(@.type=="InternalIP")].address'`（**不要用 `-o wide`**，它只渲染一个 InternalIP） | 必须一致（前缀漂移会让两者分叉 → R4） |
| 节点 IPv6 公网可达 | `ping -6 2400:3200::1` | OK |
| Cilium agent 重启计数 | `kube_pod_container_status_restarts_total` | 不得持续增长 |
| etcd 快照新鲜度 | `k3s etcd-snapshot list` 最新时间 | ≤ 13h |

> 已有的实测基线（research §2.1）：路由器约每 15s 发一次 RA，router lifetime 2700s、
> prefix valid 5400s；节点默认路由寿命在 16 分钟内**钉在 2680s**、ping6 20/20 全 OK。

### 8.2 上线中（每个验证门之间）

```bash
watch -n5 'kubectl get nodes -o custom-columns="NAME:.metadata.name,INTERNAL-IPs:.status.addresses[?(@.type==\"InternalIP\")].address,STATUS:.status.conditions[-1].type"; echo ---; kubectl -n kube-system get pods -l k8s-app=cilium; echo ---; kubectl get svc -A | wc -l'
```

### 8.3 上线后常态

- 每 5 分钟：节点 Ready、Cilium DS Ready、`kubectl get pods -A` 非 Running 数
- 每小时：节点 GUA vs InternalIP 一致性
- 每日：`ceph status`、etcd 快照新鲜度、Pod IPv6 可用性探针（一个常驻 pod 定期 `ping -6` 出网）

---

## 9. 回退方案

**回退顺序与实施顺序相反。** 每一步的判据是"验证门未通过或出现非预期现象"。

| # | 触发 | 动作 | 预期耗时 |
| --- | --- | --- | --- |
| **R1** | G3 失败 / agent CrashLoop / Pod IPv6 异常 | 三步，缺一不可（P0 实测，见 §12.2）：<br>① **不要用 `helm rollback`**（rev 13 = Cilium **1.20.1**，会顺带降级）。改用 `helm upgrade cilium --version 1.20.2` 套用 `dualstack-backup/cilium-values-before.yaml`（即 `ipam.mode=kubernetes`、无 `ipv6`）<br>② **`kubectl -n kube-system rollout restart ds/cilium ds/cilium-envoy`** —— 改 ConfigMap **不会**自动重启 agent，不做这步回退不生效<br>③ **重建工作负载**（`rollout restart deploy,statefulset,daemonset`，逐 ns）—— 否则旧 Pod 保留旧池 IP 会**双双失联** | 2–5 分钟 + 工作负载重启时间 |
| **R2** | R1 后 Pod 仍异常 | 若 P2.5 改过路由器路由，按 `openwrt-routes-before.txt` 还原；滚动重启工作负载 | 5–15 分钟 |
| **R3** | G1 失败 / API 起不来 / 控制面异常 | 用 `node-*-before.txt` 里的 config.yaml 覆盖三台 server → 按同样顺序重启 → `kubectl get --raw /readyz` | 3–10 分钟 |
| **R4** | 单节点 `node-ip` 写错致 NotReady | 还原该节点 config.yaml → 重启该节点 k3s | 2 分钟 |
| **R5** | 控制面无法恢复 | 从窗口前快照恢复：`sudo k3s server --cluster-reset --cluster-reset-restore-path=<快照>` | 15–60 分钟（**待 P0 实测**） |
| **R6** | etcd 快照也不可用 | 重建集群 + 用 §10.4 的 Ceph 材料重新收养 + 按 PV/PVC 清单重建绑定 | 数小时~数天 |

**全局停止条件（任一命中即整体回退）**：
- 三台 server 任一台 15 分钟内无法 Ready
- 任一节点 Cilium agent 重启 > 3 次
- 既有工作负载出现非预期重启或 Pending
- 业务探针丢包
- etcd leader 抖动无法解释
- `ceph status` 非 HEALTH_OK

---

## 10. 应急预案（逐个场景：症状 → 判定 → 处置）

### 10.1 【最高危】Cilium agent panic / CrashLoopBackOff
**症状**：`kubectl -n kube-system get pods -l k8s-app=cilium` 显示 `CrashLoopBackOff`，
`lastState.terminated.exitCode=2`，日志含 `panic: Start or stop failed to finish on time`。
**判定**：往上翻日志，若见 `error="required IPv6 PodCIDR not available"` → 就是 E10。
**根因**：`ipv6.enabled=true` 但某节点没有 IPv6 PodCIDR（`ipam.mode=kubernetes` 时必然发生）。
**处置**：
1. `kubectl get nodes -o jsonpath=...` 找出哪个节点的 `podCIDRs` 缺 IPv6。
2. **不要**尝试用注解补（E11 已证无效），**不要**尝试删节点（E14 会卡 Terminating）。
3. 立即执行 **R1**：`helm upgrade` 回到 `ipam.mode=kubernetes` + `ipv6.enabled=false`，
   **然后必须 `kubectl -n kube-system rollout restart ds/cilium ds/cilium-envoy`**（P0 实测：改 CM 不会自动重启 agent），
   最后**重建工作负载**（P0 实测：不重建则旧 Pod 的 v4/v6 双双失联）。
4. 网络恢复后，改按 §7 P2 的 **cluster-pool 一次性切换**重做。

### 10.1b 【实测已发生】DS 滚动更新停在 2/4 + `required IPv6 PodCIDR not available`
**症状**：`kubectl -n kube-system get ds cilium` 显示 `READY 2`（`CURRENT/UP-TO-DATE` 为 2），
出现 2 个 `AGE` 只有几分钟的 `0/1 Running` 新 pod，同时 2 个 `AGE` 很大的 `1/1` 旧 pod 仍在跑；
`kubectl -n kube-system exec ds/cilium -- cilium-dbg status` 采到的是**旧 pod**（`IPv6: Disabled`），
所以**看起来像 IPAM 没生效，其实配置是对的**——先确认采到的是哪个 pod。
新 pod 日志：`error="required IPv6 PodCIDR not available"`。
**判定**：`kubectl get ciliumnode -o jsonpath='{range .items[*]}{.metadata.name}: {.spec.ipam}{"\n"}{end}'`
→ 若 `spec.ipam.podCIDRs` **只有 IPv4**，即为"陈旧 CiliumNode 挡住 operator 分配"。
**处置**：见 **§7 P2.1.5 方案 A**（手工给 `spec.ipam.podCIDRs` 补 IPv6，保留 IPv4 映射）。
**影响面**：受影响节点带 `node.cilium.io/agent-not-ready` 污点，**新 Pod 无法调度到该节点**；
既有 Pod 不受影响（旧 agent 仍在服务）。**不会自动扩散，可从从容处置。**
**不要**误判为配置错误而去回退或改动 `cluster-pool` 参数——先核对 `ciliumnode` 的 `spec.ipam`。

### 10.2 节点卡在 Terminating（误删 Node 的后果）
**症状**：`kubectl get nodes` 该节点 STATUS 空/Terminating，带 `deletionTimestamp`。
**判定**：`kubectl get node <n> -o jsonpath='{.metadata.finalizers}'` → 见 `wrangler.cattle.io/managed-etcd-controller`。
**处置**：
1. 该节点**仍可正常工作**（kubelet/容器未受影响），不要慌。
2. 用 `kubectl patch node <n> -p '{"metadata":{"finalizers":null}}' --type=merge` 移除 finalizer
   **仅当**确认不再需要 k3s 的 etcd 控制器管理该节点时使用；否则保持现状并接受该状态。
3. 恢复方式：把该节点的 Node 对象重建（kubelet 会重新注册），并核对其 `podCIDRs`。

### 10.3 Pod 换 IP 后跨节点不通
**症状**：P2 后部分 Pod 与 LAN/其他节点不通。**判定**：比对 `podcidr-before.txt` 与实际映射；
路由器路由仍指向旧映射。
**处置**：按 §7 P2.6 更新路由器静态路由 → 滚动重启受影响工作负载。

### 10.4 Ceph 相关应急（仅在 R6 场景需要）
```bash
kubectl -n rook-ceph get secret rook-ceph-mon -o yaml          > ceph-mon-secret.yaml
kubectl -n rook-ceph get secret rook-ceph-admin-keyring -o yaml > ceph-admin-keyring.yaml
kubectl -n rook-ceph exec deploy/rook-ceph-tools -- ceph status
kubectl -n rook-ceph exec deploy/rook-ceph-tools -- ceph osd tree
kubectl -n rook-ceph exec deploy/rook-ceph-tools -- ceph osd getcrushmap -o /tmp/cm
kubectl -n rook-ceph exec deploy/rook-ceph-tools -- crushtool -d /tmp/cm    # CRUSH map
# 关键：OSD 数据在裸分区 nvme0n1p3(ceph_bluestore)，mon 数据在 /var/lib/rook —— 都在 k8s 之外
```
**拆集群前必须先手工删除 `cilium_host` / `cilium_net` / `cilium_vxlan`**，否则 `k3s-killall.sh` /
`k3s-uninstall.sh` 会**丢失宿主机网络连通性**（Cilium 官方 k3s 安装页警告），
并把 iptables/ip6tables 里的 cilium 条目过滤掉后再恢复规则。

### 10.5 ISP 前缀漂移（R4）
**症状**：节点 IPv6 默认路由消失、或 Node InternalIP 的 IPv6 与实际 GUA 分叉。
**处置**：把新 GUA 写回该节点 `config.yaml` 的 `node-ip`/`kubelet-arg` → 重启该节点 k3s 重新注册。
（kubelet 的 nodeIP 在启动时确定，**只重启不改配置仍会报旧地址**。）
若发现前缀频繁漂移 → 改用"节点加 ULA + netplan `ipv6-address-label`"方案，并把
`cluster-cidr` 的 IPv6 段一并迁到 ULA 体系（需重做 P1/P2）。

### 10.6 passwall 干扰 IPv6 出网（R6）
**症状**：Pod 的 AAAA 解析异常或 IPv6 出网间歇失败。
**处置**：先在 Pod 内 `getent ahostsv6` + `curl -6` 定位；必要时在路由器为集群网段加 passwall 直连规则。
（路由器 `passwall` 已启用：`dns_redirect=1`、`dns_mode=xray`、`filter_proxy_ipv6=1`。）

### 10.7 最坏情况：现场完全失控
1. 停止一切变更，保留现场（**不要**在未备份的情况下重装）。
2. 用 §9 R5 从 etcd 快照恢复控制面。
3. 若控制面也起不来 → 按 R6 走重建路径，先保 Ceph 数据（§10.4）。
4. 记录时间线用于复盘。

---

## 11. 验收标准

- [ ] 节点双栈：`kubectl get nodes -o custom-columns='NAME:.metadata.name,INTERNAL-IPs:.status.addresses[?(@.type=="InternalIP")].address'` 显示 **4 台均有 IPv4 + IPv6**（**不用 `-o wide`**，它只渲染一个 InternalIP）
- [ ] `kubectl get servicecidr`：同时存在 IPv4 与 IPv6 范围
- [ ] `kubectl get ciliumnode -o jsonpath=...`：**每节点** `podCIDRs` 同时含两族
- [ ] `cilium-dbg status` 的 IPAM 行同时显示 IPv4/IPv6；Masquerading 行 `[IPv4: Enabled, IPv6: Enabled]`
- [ ] 新建 Pod 同时持有 IPv4 + IPv6
- [ ] 新建 `PreferDualStack` Service 拿到双 ClusterIP；从 Pod 用 IPv6 访问成功
- [ ] 跨节点 pod↔pod IPv6 通；pod→internet IPv6 通；大包（-s 1400）通
- [ ] 既有 Service 的 `clusterIP`/`ipFamilies` 与 `services-before.json` 一致
      （仅 `kube-dns` 按决策点 1 的结果允许差异）
- [ ] 既有工作负载无额外重启、无 Pending/Evicted
- [ ] `hubble-relay` 稳定 Running（#42017）
- [ ] `ceph status` = HEALTH_OK
- [ ] 路由器静态路由与实际 PodCIDR 映射一致
- [ ] 仓库配置与实际一致，ArgoCD 无 drift
- [ ] §8.1 的监控项全部落地

---

## 12. 已确认决策 / P0 实测结论 / 剩余待决项

### 12.1 已决策（2026-10-03）

| # | 议题 | 决定 | P0 实测确认 |
| --- | --- | --- | --- |
| 1 | `cluster-dns` 策略 | ✅ **不设**（决策点 1 选 A） | 实测 `kube-dns` 自动变 `["10.43.0.10","fdb5:92d0:b067:4300::a"] policy=RequireDualStack` —— 即每个 Pod 的 `resolv.conf` 会变，**P2 后必须重启工作负载**（与 P2.5 的工作负载重启合并做即可） |
| 2 | P2 的 IPv4 映射处理 | ✅ **兜底**（改路由器路由 + 滚动重启） | 实测证明兜底是正确选择，见 12.2 |

### 12.2 P0 实测结论（2 节点演练集群，已全部跑通）

| 项 | 实测结果 |
| --- | --- |
| **cluster-pool 的 IPv4 分配规则** | **`clusterPoolIPv4PodCIDRList` 的顺序确实决定映射**：列表被打乱成 `[3,0,2,1]` 后，**最先请求的节点拿到 list[0]**（ds-z → `10.42.3.0/24`）。分配顺序 = 各节点 CiliumNode 的请求顺序，**不可靠地对应节点名或加入顺序** → **"按列表排列精确钉住生产映射"不可行，兜底是唯一稳妥做法**（已被决策 2 覆盖） |
| **P2 方案整体可行性** | ✅ **成功**。`ipam.mode=cluster-pool` + `clusterPoolIPv6PodCIDRList` + `ipv6.enabled=true`，在**节点 podCIDRs 仅 IPv4** 的集群上：agent **1/1 Ready，无 panic**；`IPAM: IPv4: n/254 from 10.42.3.0/24, IPv6: n/… from fdb5:92d0:b067:4200::/64`；`Masquerading … [IPv4: Enabled, IPv6: Enabled]` |
| **Pod 双栈** | ✅ 测试 Pod `p0test` 拿到 `10.42.3.142` + `fdb5:92d0:b067:4200::a769`；coredns / metrics-server 同样双栈 |
| **pod → internet IPv6** | ✅ `ping -6 2400:3200::1` 0% 丢包（13.8ms，经节点 NAT66） |
| **Service 双栈** | ✅ `PreferDualStack` Service 拿到 `["10.43.123.193","fdb5:92d0:b067:4300::6553"]` |
| **hubble-relay（issue #42017）** | ✅ **未复现**。IPv6 agent/pod IP 下 hubble-relay 正常 Running |
| **`kubelet-arg` 的必要性（E8）** | ✅ 确认：只加 `--node-ip` 时 Node InternalIP 仍只有 IPv4；**加上 `--kubelet-arg=node-ip=<v4>,<v6>` 后才出现 IPv6 InternalIP**（ds-z 实测同时有 `172.30.9.10` 与 `fd00:3::10`）→ **G1 必须逐节点检查，且 IPv6 可能滞后出现，需留等待时间** |
| **★ 回退 R1 的两个坑（重要修正）** | ①**改 ConfigMap 不会重启 DaemonSet**：`helm upgrade` 后 CM 已变（`enable-ipv6=false`、`ipam=kubernetes`）但 agent 仍在跑旧配置（`RESTARTS 0`、pod 未重建）→ **必须显式 `kubectl -n kube-system rollout restart ds/cilium ds/cilium-envoy`**。<br>②**回退后既有 Pod 会失联**：旧 Pod 保留旧池 IP（`10.42.3.142` + IPv6），回退后 **IPv4 与 IPv6 双双 ping 失败**；**重建工作负载后 IPv4 恢复**（`p0test3 → 10.42.0.223`，ping4 OK；ping6 按预期失败，因 IPv6 已关）→ **回退流程必须以"重建工作负载"收尾** |
| 演练中遇到的非生产问题 | 反复以同一 hostname 重建 agent 容器会导致 `Node password rejected … try enabling a unique node name`，节点变 NotReady。这是演练环境自造问题（容器重建而 `/etc/rancher/node/password` 与 datastore 失配），生产不会遇到；处理方式是清掉 datastore 中该节点的 password secret 或用 `--with-node-id` |

### 12.3 剩余待决项

1. **维护窗口长度**：P1 控制面中断（3–10 分钟）+ P2 的 Cilium 切换 + **工作负载全量重建**（决策 1 的 `resolv.conf` 变更与兜底的 IP 映射变更都需要它）。按 49 个 namespace 估算，合计建议预留 **60–120 分钟**。
2. **ISP 前缀漂移频率**：是否有 DDNS/日志可判断？决定 R4 走"监控 + runbook"还是"节点 ULA"。
3. **P1.2 的写法**：决策 1 选 A（不设）→ **删掉 `cluster-dns` 那一行**，并把 `kube-dns` 加入 G1 的预期差异清单。
4. **真窗口前 24h 内复跑一次 P0**：用 §6 的脚本再跑一遍，重点复跑 §12.2 的
   "回退 R1 两个坑"与"cluster-pool 切换"，确认无环境漂移。

---

## 13. 生产执行记录（2026-10-07）—— P1 与 P2 实测

### 13.1 时间线

| 时刻 | 事件 |
| --- | --- |
| 09:27 | `k3s etcd-snapshot save --name pre-dualstack`（本地 + S3 双份）✅ |
| 09:45 | 三台 server `systemctl stop k3s` |
| 09:46 | 启动 226 → **卡在 etcd 选举（1/3 票）**；174/158 一直 `inactive` |
| 10:00 | **定位为 `systemctl start` 阻塞导致的死锁**（见 §7 P1.3 修正），并行 `--no-block` 启动 174/158 |
| ~10:05 | etcd 形成 quorum，API 就绪 |
| 10:12 | **P2 执行 helm upgrade**（`cluster-pool` + `ipv6.enabled=true`）→ 新 agent 卡在 `required IPv6 PodCIDR not available`，DS 停在 2/4 |
| 10:20 | **定位为陈旧 `CiliumNode.spec.ipam.podCIDRs`**（见 §7 P2.1.5） |
| 10:22 | 打 4 个 CiliumNode 补丁（补 IPv6 /64，IPv4 原样保留） |
| 10:23 | **30 秒内 DS 4/4 就绪** |

### 13.2 P1 验证门 G1 —— ✅ 通过

| 项 | 结果 |
| --- | --- |
| 节点双栈 | 4/4 均有 IPv4 + IPv6 InternalIP（用 `-o custom-columns` 验，**不是** `-o wide`） |
| `ServiceCIDR` | `10.43.0.0/16,fdb5:92d0:b067:4300::/112`（对象原地更新，AGE 417d） |
| `kube-dns` | `["10.43.0.10","fdb5:92d0:b067:4300::a"] policy=RequireDualStack`（决策 1=A 的预期） |
| 既有 Service | 124 个，**仅 `kube-dns` 真正拿到 IPv6 ClusterIP**；9 个 `PreferDualStack` 的 `ipFamilies` 变 `[IPv4,IPv6]`（8 个 headless `ts-*` + `metrics-server`，后者**未被补发** IPv6 ClusterIP，与 P0 的 E4 一致） |
| 工作负载 | 0 个非 Running；Cilium DS 4/4；`ceph status` = HEALTH_OK |

### 13.3 P2 验证门 G2 —— ✅ 通过

| 项 | 结果 |
| --- | --- |
| DS / agent | 4/4，全部 Ready，4 个节点污点 `node.cilium.io/agent-not-ready` **全部消失** |
| IPAM（逐节点） | 四台**同时**有 `IPv4: n/254 from 10.42.x.0/24` 与 `IPv6: n/… from fdb5:92d0:b067:420x::/64` |
| Masquerading | 四台均 `[IPv4: Enabled, IPv6: Enabled]` |
| **IPv4 映射** | **逐节点与改造前完全一致**（jumper-0=.0、cheshi-0=.1、jumper-2=.2、jumper-1=.3） |
| 路由器静态路由 | 4 条**无需改动**，仍与集群映射一一对应 ✅ |
| operator 是否抹掉补丁 | **没有**，`spec.ipam.podCIDRs` 保持两族 |
| Pod 双栈（新建） | `p2test` → `10.42.2.148` + `fdb5:92d0:b067:4202::4092` ✅ |
| IPv6 连通性 | pod→internet IPv6 0% 丢包；pod→LAN 网关 IPv6 0% 丢包；IPv4 对照正常 ✅ |

### 13.4 关键收获（P0 未能覆盖的两点，均已写回上文）

1. **`systemctl start k3s` 死锁**（§7 P1.3）：串行启动时第一台的 `systemctl start` 永不返回 →
   循环卡死 → 另外两台根本没启动。**必须 `--no-block` + 并行。**
2. **陈旧 `CiliumNode` 挡住 IPAM 升级**（§7 P2.1.5 / §10.1b）：从 `ipam.mode=kubernetes` 升级到
   `cluster-pool` 时，节点上残留的 `CiliumNode.spec.ipam.podCIDRs`（仅 IPv4）会让 operator
   **静默跳过**分配 → IPv6 永远补不上 → 新 agent 卡住 → DS 停在 2/4。
   **P0 是全新安装，没有历史 `CiliumNode`，因此不可能暴露这个问题** —— 这是 P0 设计的缺口。
3. **手工补 `spec.ipam.podCIDRs` 是最优解**：既解除了阻塞，又**完整保留了 IPv4 映射**，
   因此 §4.3 的"兜底"（改路由器路由 + 因 IP 映射重建工作负载）**不需要执行**。

### 13.5 P2 之后仍未完成的事项

- [ ] **既有 Pod 仍是 IPv4-only**（Cilium 无法改写已创建的 Pod）。要让现有工作负载拿到 IPv6，
      必须**重建工作负载**（`rollout restart`）。执行前**先暂停 ArgoCD selfHeal**（见 §3.4），
      否则 `restartedAt` 注解会被回滚并触发第二轮 rollout。
      同时这也是决策 1=A 带来的 `resolv.conf` 变更生效的必要步骤。
- [ ] **Service 双栈是 opt-in**：目前只有 `kube-dns` 有 IPv6 ClusterIP。
      需要 IPv6 的 Service 逐个改 `ipFamilyPolicy: PreferDualStack`（runbook §7 Phase 4）。
- [ ] **Tailscale 验证**（Phase 6）：operator / nameserver / ingress / egress 全 Ready，
      `ts-*` 入口从 tailnet 可访问；注意 9 个 headless `ts-*` Service 之后会出现 IPv6 endpoint。
- [ ] 回写仓库（`metal/roles/k3s/defaults/main.yml`、`metal/roles/cilium/defaults/main.yml`），
      恢复 ArgoCD selfHeal，确认无 drift。
- [ ] 落地 §8.1 的常态监控。

### 13.6 工作负载重建执行记录（2026-10-07，P2 之后）

**前置**：ArgoCD 36 个 Application 的 **selfHeal 已全部关闭**（`automated` 保留）——
已实测确认 `selfHeal=0`，因此 `rollout restart` 加的 `restartedAt` 注解不会被回滚。

**分批策略（有意排除，不做重启）**

| namespace | 排除原因 |
| --- | --- |
| **`tailscale`** | ⚠️ **本集群 kubectl 的 server 是 `https://tailscale-operator.west-beta.ts.net`**（走 Tailscale API 代理）—— 重启它会**切断操作者的控制通道**，必须硬排除 |
| `rook-ceph` / `csi-driver-nfs` / `volsync-system` | 存储风险（Ceph 守护进程 / CSI / 复制任务） |
| `argocd` | 自管理，重启会波及正在使用的交付链路 |
| `kubevirt` / `kubevirt-test` | 实测无 VM 在跑（`virt-launcher` 0 个），无收益 |
| `kured` / `system-upgrade` | **重启可能触发节点重启** |

**执行结果（4 批）**

| 批 | namespace | 结果 |
| --- | --- | --- |
| A 试点 | netshoot, excalidraw, pairdrop, speedtest, homepage | ✅ 5/5 全 IPv6，~140s |
| B 无状态 | searxng, kompose, kor, kube-explorer, helm-dashboard, eraser, dex, ollama, upsnap, styleferry, default | ✅ 10/11 全 IPv6；`default` 的 holmesgpt/robusta 因**拉镜像慢**（robustadev/* 走代理）晚就绪，非故障 |
| C 有状态 | jellyfin, semaphore, paperless, woodpecker, gitea, kanidm, grafana, lobe-chat, rsshub, rustfs, monitoring-system | ✅ **11/11 全就绪且 IPv6 覆盖 100%**（monitoring-system 12/12、rsshub 7/7），~310s |
| D 基础设施 | kube-system（**仅 Deployment**，不动已更新的 cilium DS）、external-secrets、grafana-cloud | ✅ 全就绪，~360s |

**验证结果**

| 项 | 结果 |
| --- | --- |
| 全局 Pod 双栈覆盖 | **92 / 165** 含 IPv6；仅剩 73 个全在有意排除的 namespace 内（rook-ceph 29、tailscale 18、kubevirt 11、argocd 6、kured 4、grafana-cloud 3、system-upgrade 1、volsync-system 1） |
| **`resolv.conf`** | 新 Pod 得到 `nameserver 10.43.0.10` + `nameserver fdb5:92d0:b067:4300::a` → **决策 1=A 生效** |
| kube-dns IPv6 ClusterIP | `nc -z fdb5:92d0:b067:4300::a 53` → **OK** |
| **注意：不要用 ICMP 测 ClusterIP** | `ping -6 <ClusterIP>` 100% 丢包是**正常的**（Cilium LB 不转发 ICMP 到 ClusterIP）；**必须用 TCP/UDP 测**。此坑曾误判为故障 |
| DNS over IPv6 | 用 IPv6 服务器 `nslookup www.taobao.com fdb5:92d0:b067:4300::a` → 正常解析；`kube-dns.kube-system.svc.cluster.local` → **AAAA = fdb5:92d0:b067:4300::a** |
| Pod 双栈 + 出网 | `podIPs=[10.42.0.135, fdb5:92d0:b067:4200::8daf]`；pod→internet IPv4/IPv6 均 0% 丢包 |
| PVC | **50/50 全部 Bound** |
| Cilium DS | 4/4 ready |
| `ceph health` | **HEALTH_OK** |

> 排查小记：`kubectl get pvc -A` 的列序是 `NAMESPACE NAME STATUS ...`，`STATUS` 是**第 3 列**。
> 用 `$2` 判 Bound 会得到"50 个非 Bound"的假告警。

**仍未做（留给后续）**
- [ ] `tailscale` namespace（18 个 Pod，含 ingress/egress proxies 与 8 个 `ts-*`）仍是 IPv4-only。
      **需在能承受短暂 tailnet 中断时单独执行**；若通过 tailnet 访问本集群，重启期间会断连。
- [ ] `grafana-cloud` 仍有 3 个 Pod IPv4-only（Batch D 已重启，建议复查是否 hostNetwork 或未滚动到）。
- [ ] Service 双栈仍是 opt-in：目前只有 `kube-dns` 有 IPv6 ClusterIP。
- [x] **回写仓库（2026-10-07 完成，待审 diff，未提交）**：4 个文件，86 增 / 2 删
      - `metal/inventories/prod.yml`：新增双栈地址规划（`dualstack_ipv6_pod_cidr` / `dualstack_ipv6_service_cidr`），
        只定义一份供 k3s 与 Cilium 两个 role 共用
      - `metal/roles/k3s/defaults/main.yml`：server 加 `cluster-cidr`/`service-cidr`（逗号无空格、IPv4 在前）；
        agent 加 `node-ip` 与 `kubelet-arg: node-ip=`（E8 必需）；`node-external-ip` 补 Tailscale IPv6；
        **明确不设 `cluster-dns`**（附原因注释）
      - `metal/roles/k3s/tasks/main.yml`：新增导出 `tailscale_ipv6` 与 `node_ipv6` 的 task
        （后者排除 `fe80:` 与 `fd7a:115c:a1e0:` 后取第一个 GUA）
      - `metal/roles/cilium/defaults/main.yml`：`ipam.mode` → `cluster-pool` + 双族池列表；
        新增 `ipv6.enabled` 与 `ipv6NativeRoutingCIDR`（附"为什么必须改 IPAM 模式"与陈旧 CiliumNode 的注释）
      - **验证**：`yamllint` 通过；Jinja 渲染 `config.yaml.j2` 的结果与节点实际运行值**逐项一致**
        （master 五项全同；worker 的 `cluster-cidr` 正确缺失，且 diff 修正了它实际遗漏的顶层 `node-ip`）；
        Cilium 的 8 个关键 values 与 `helm get values` **全部一致**
      - `ansible-playbook --syntax-check` 因环境缺 `ansible.posix` collection 无法完成（**既有环境问题，与本次改动无关**）
- [ ] 恢复 ArgoCD selfHeal；确认无 drift
- [ ] 落地 §8.1 常态监控
- [ ] ⚠️ 注意：`node_ipv6` 是运行时从节点探测的。若 ISP 前缀漂移（R4），该值会随之改变，
      需重跑 k3s role 才能把新 GUA 写进 `node-ip` / `kubelet-arg`
      （kubelet 的 nodeIP 在启动时确定，不会自动更新）

---

## 14. 收尾执行记录（2026-10-07）：tailscale / grafana-cloud / Service 双栈

### 14.1 tailscale namespace —— ✅ 18/18 双栈

| 步骤 | 结果 |
| --- | --- |
| 前置：验证 SSH 回退通道 | `ssh casey@192.168.3.226 'sudo k3s kubectl ...'` 可用（用户提供） |
| **关键情报** | namespace 内**没有独立的 API 代理 Pod**：18 个 = operator(1) + nameserver(1) + ingress-proxies(4) + egress-proxies(4) + `ts-*`(8)。`apiServerProxyConfig.mode: true` 的 API 代理**跑在 operator 里**，而 `tailscale-operator.west-beta.ts.net` 解析到 `100.85.2.4` 就是它 |
| Phase 1a：nameserver + 8 个 `ts-*` | `rollout restart` 直接生效，17/18 就绪，**kubectl 未受影响**（证实 API 代理确在 operator） |
| Phase 1b：ingress/egress proxies | ⚠️ `rollout restart` **只重建了每个 StatefulSet 的 `-3`**（StatefulSet 滚动从大序号开始）；原因是 **operator 把 `restartedAt` 注解剥掉了**（`podTemplateAnnotations` 为空 → `updateRevision == currentRevision`）→ **改用直接 `delete pod`**，6 个全部双栈 |
| Phase 2：operator（**会切断控制通道**） | 全程用 SSH 通道触发与轮询：`operator-67857cf589-9rbw6` → `operator-8498dcbd86-njd75`，~20s 就绪 |
| **tailnet 通道恢复** | **~5 秒**（几乎无感） |
| 最终验证 | **18/18 双栈**；`ingress-proxies-0` 与 `ts-gitea`（主机名 `git`）均 `online=True`、`BackendState=Running`、36 个 peer |

### 14.2 grafana-cloud 排查 —— ✅ 无遗留问题，但发现一个值得记的机理

**症状**：`k8s-monitoring-alloy-logs-8jrfb` 与 `k8s-monitoring-alloy-singleton-*` 各 6 次重启，日志：
```
err="... lookup fleet-management-prod-005.grafana.net on [fdb5:92d0:b067:4300::a]:53:
     dial udp [fdb5:92d0:b067:4300::a]:53: connect: no route to host"
```

**结论：滚动窗口撞车造成的瞬时故障，已自愈。** 证据：两个 Pod 于 10:39:5x 启动（正是 `kube-system`/coredns 滚动收尾窗口），10:42:5x 退出；同一 DaemonSet 在 10:46 之后启动的 3 个 Pod **RESTARTS=0**；两个问题 Pod 已稳定 23 分钟不再增长；现在 UDP/TCP 到 IPv6 DNS 均正常，`fleet-management-prod-005.grafana.net` 能解析。

**机理（重要）**：决策 1=A 让 `resolv.conf` 同时列出 IPv4 与 IPv6 两个 DNS。**若 Pod 恰好在一个 DNS 后端短暂不可用的窗口内启动，Go 解析器会把 IPv6 nameserver 的 `no route to host` 抛出来**，表现为"启动即失败"。→ 这解释了两个 Pod 的 6 次重启，未来**重启 coredns 时对并发新建的 Pod 有同类风险**，宜避开或错峰。

### 14.3 ⚠️ 本次发现的最重要风险：**GitOps 客户端必须先双栈，再改 Service**

排查中发现一个会**直接打断交付链**的耦合：

```
argocd 的 repoURL = http://gitea-http.gitea:3000/ops/homelab2   ← 走 gitea 的 ClusterIP
argocd 全部 6 个 Pod 当时仍是 IPv4-only（含真正执行 git clone 的 repo-server）
其 resolv.conf 只有 nameserver 10.43.0.10（未重建过，没有 IPv6 DNS）
```

**若此时把 `gitea/gitea-http` 改成 PreferDualStack**：DNS 同时返回 A 与 AAAA → argocd 的 IPv4-only Pod 解析到 AAAA → `ENETUNREACH` → git clone 失败 → **GitOps 交付中断**。`dex/dex`（argocd 的 OIDC 依赖）同理。

**规则（建议写入任何后续 Service 双栈操作）**：
> **先把该 Service 的客户端 Pod 变成双栈，再改 Service。** 否则 IPv4-only 客户端拿到 AAAA 会直接失败
> （glibc 系可能失败、Go 的 Happy Eyeballs 多数能兜住，但不能赌）。

据此执行的顺序：先 `argocd / kubevirt / kured / system-upgrade / volsync-system`（23 个 Pod）双栈，
**其中 argocd 6/6 且 `resolv.conf` 已含 IPv6 DNS 之后**，才动 Service。

### 14.4 又一次遇到"operator 抹掉注解"（KubeVirt）

`kubevirt` 的 `virt-api` / `virt-controller` / `virt-handler` 用 `rollout restart` **无效** ——
Deployment/DS 上只剩 KubeVirt 自己的 `kubevirt.io/install-strategy-*` 注解，`restartedAt` 被 virt-operator 抹掉。
→ **同样改用直接 `delete pod`**，5 个 Pod 重建后双栈。

**通用教训**：对于"被某个 operator 托管的 workload"，`rollout restart` 可能被静默撤销。
**判定方法**：`kubectl get <obj> -o jsonpath='{.spec.template.metadata.annotations}'` 看注解是否还在；
**可靠替代**是直接 `delete pod`（控制器必然按当前模板重建）。

### 14.5 Service 双栈（opt-in）—— ✅ 已转换 28 个

**范围**：Tailscale Ingress 的 28 个后端 Service（它们的客户端以已双栈的 tailscale 代理为主，风险最低）。

| 项 | 结果 |
| --- | --- |
| 转换方式 | `kubectl patch svc <n> -p '{"spec":{"ipFamilyPolicy":"PreferDualStack"}}'`（**不用重建**） |
| 成功数 | 27/27（+ 先前试点 `excalidraw` = 28） |
| **原 IPv4 ClusterIP** | **完整保留**，只新增 IPv6（实测 `["10.43.147.123","fdb5:92d0:b067:4300::da39"]`） |
| EndpointSlice | 均出现 `addrType=IPv6` 与 `addrType=IPv4` 两条，端口一致 |
| 有 IPv6 ClusterIP 的 Service 总数 | **29** |
| IPv6 连通性抽测 | `gitea-http:3000` OK、`argocd-server:443` OK；`kanidm`/`woodpecker-server` 的"失败"是**我端口猜错**（实际 443/636 与 80/9000/9001），IPv4 同样失败 → **非回归** |
| DNS | 对这些服务同时返回 A 与 AAAA |

**两个不算异常的"声明双栈但无 IPv6 ClusterIP"**：
- 8 个 `tailscale/ts-*` 是 **headless**（`clusterIP: None`），本就没有 ClusterIP
- `kube-system/metrics-server` 是改造前就已存在的 PreferDualStack，**k8s 不会追溯补发**第二个 ClusterIP（与 P0 的 E4 一致）

### 14.6 ArgoCD 与 drift 的实测结论

| 问题 | 实测结论 |
| --- | --- |
| 我改了 27 个 Service，为何 ArgoCD 不报 drift？ | **ArgoCD 对 Service 的 `ipFamilyPolicy` / `clusterIPs` 做了归一化、视为可忽略差异** → `gitea` 等仍报 `Synced`。**含义两面**：①恢复 selfHeal **不会**回退这些 Service ②**改动对 GitOps 是"隐形"的**，仓库不补声明则将来重建会退回单栈 |
| `restartedAt` 注解（69 个 Deployment 上有）会不会造成 drift？ | **不会**。反证：`argocd/argocd-server` 带该注解但 App 为 `Synced` → 恢复 selfHeal **不会**触发第二轮全量滚动 |
| 剩余 OutOfSync | 2 个，**与本次改动无关**：`grafana`（`Secret/grafana-image-renderer`）、`rsshub`（5 个 Deployment）。**恢复 selfHeal 前应先查清这两个**，因为 sync 会把 git 版本应用到集群 |
| 其余 | 23 Synced / 11 Unknown（对比缓存刷新中）/ 2 OutOfSync |

### 14.7 最终状态

| 项 | 值 |
| --- | --- |
| **Pod 双栈覆盖** | **140/169**；仅 `rook-ceph` 29 个仍 IPv4-only（**有意保留**：Ceph 守护进程重启有存储风险，且它与已转换的 28 个 Service 无消费关系） |
| Service 双栈 | 29 个有 IPv6 ClusterIP（`kube-dns` + 28 个 Ingress 后端） |
| Cilium | DS 4/4，四节点 IPAM 均含两族 |
| ceph | HEALTH_OK |
| tailscale | 18/18 双栈，tailnet 连接正常 |

**尚未做（建议后续，非阻塞）**
- [ ] `rook-ceph` 29 个 Pod 双栈：需逐个守护进程滚动 + Ceph 健康门（`ceph health` 每步确认），**不要一次性 rollout**
- [ ] 把 28 个 Service 的 `ipFamilyPolicy: PreferDualStack` 写入仓库（否则如 §14.6 所述是"隐形 drift"，重建即丢失）
- [ ] 恢复 ArgoCD selfHeal **之前**先处理 `grafana` / `rsshub` 两个既有 OutOfSync
- [ ] `kube-system/metrics-server` 若要真正双栈，需删除重建 Service（会短暂影响 metrics API 与 HPA），价值低、建议不动

---

## 15. 终局执行记录（2026-10-07）：rook-ceph 与仓库回写

### 15.1 rook-ceph 29 个 Pod —— ✅ 全部双栈（6 波，逐步健康门）

**方法**：逐个 `delete pod`（**不是** `rollout restart` —— Rook/virt operator 会抹掉 `restartedAt`），
每步之后跑四重门：`health=HEALTH_OK` + `mon: 3 daemons …quorum` + `osd: 4 osds: 4 up …4 in` + `pgs: 81 active+clean`。
**任一门不通过即立刻停止**（脚本内建）。

| 波 | 对象 | 结果 |
| --- | --- | --- |
| 0 | crashcollector(4) / exporter(4) / tools / snapshot-controller / operator | 11 个 ✅ 每步 HEALTH_OK |
| 1 | ceph-csi-controller-manager / 2 ctrlplugin / 2 nodeplugin | ✅ |
| 1b | rook-discover (DS) | ✅ |
| 2 | mgr-b（standby）→ mgr-a（active，触发 failover） | ✅ |
| 3 | mds-standard-rwx-b（standby）→ a（active，CephFS 元数据短暂停顿） | ✅ |
| 4 | **mon-c → mon-e → mon-g**（逐个，quorum 必须保持 3） | ✅ 每步 `quorum c,e,g` 均由 2 恢复为 3 |
| 5 | **osd-0 → 1 → 2 → 3**（逐个，必须 4up/4in + active+clean） | ✅ 每步 `4 osds: 4 up, 4 in`、`81 pgs active+clean` |

**最终 Ceph 状态（数据零损失）**：
```
health: HEALTH_OK
mon: 3 daemons, quorum c,e,g     mgr: a(active), standbys: b     mds: 1/1 up, 1 hot standby
osd: 4 osds: 4 up, 4 in         pools: 4, pgs: 81 active+clean
objects: 22.20k objects, 81 GiB  volumes: 1/1 healthy
```
→ 与改造前基线（§15 开头记录的 22.20k objects / 81 GiB / 81 pgs / 4 pools）**完全一致**。

> ⚠️ **执行中我犯的一个错误（记录以免重犯）**：第一版门函数先对 `ceph -s` 的输出做 `tr -d ' '`，
> 随后却用**带空格**的模式 `"4 osds: 4 up"` 去匹配 → 永远不可能命中 → **误判为 OSD 不健康并中止脚本**。
> 实际当时 Ceph 完全正常（mon-c 已成功归队）。**教训：解析命令输出时，格式化与匹配必须用同一套空白规则。**

### 15.2 仓库回写：28 个 Service 的 `PreferDualStack`

**已完成 12 个**（全部是 `app-template@5.2.1` 系的包装 chart，字段路径 `app-template.service.<name>.ipFamilyPolicy`）：

| 文件 | service 子键 | 对应 k8s Service |
| --- | --- | --- |
| `apps/excalidraw/values.yaml` | main | excalidraw |
| `apps/jellyfin/values.yaml` | main | jellyfin |
| `apps/ollama/values.yaml` | main | ollama |
| `apps/pairdrop/values.yaml` | main | pairdrop |
| `apps/paperless/values.yaml` | main | paperless |
| `apps/searxng/values.yaml` | caddy | searxng-caddy |
| `apps/speedtest/values.yaml` | main | speedtest |
| `apps/styleferry/values.yaml` | main | styleferry |
| `apps/upsnap/values.yaml` | upsnap | upsnap |
| `platform/kanidm/values.yaml` | main | kanidm |
| `system/kube-explorer/values.yaml` | main | kube-explorer |
| `system/semaphore/values.yaml` | semaphore | semaphore |

**验证**（12/12 全通过）：
- `yamllint` 通过
- 用 Python 解析断言 `app-template.service.<key>.ipFamilyPolicy == 'PreferDualStack'` —— **12/12**
- 用 **app-template 官方 `values.schema.json`** 对每个 `app-template:` 块做 jsonschema 校验 —— **12/12 通过**
- `helm template` 无法本地完成：这些 chart 的依赖未 vendor 到 `charts/`（只有 styleferry 有 tgz），
  **属既有环境状况、与本次改动无关**；故改用上面的解析断言 + 官方 schema 校验作为等价验证

**后续处理结果（2026-10-07，随 v2026.10.07.2 发布）：16 个中 9 个已写入仓库，7 个无法声明。**

| Service | 声明位置 | 验证 |
| --- | --- | --- |
| `lobe` / `casdoor` | `apps/lobe-chat/templates/svc-{lobe,casdoor}.yaml`（自研 chart，模板在仓库内） | 渲染 7 个 Service 命中 2 个 |
| `rsshub` / `service-rss` | `apps/rsshub/templates/service-{rsshub,service-rss}.yaml`（自研 chart） | 渲染 9 个 Service 命中 2 个 |
| `argocd-server` | `system/argocd` → `global.dualStack.ipFamilyPolicy`（chart 的 `_helpers.tpl` 用它统一注入） | 渲染 9 处 |
| `gitea-http` | `platform/gitea` → `service.http.ipFamilyPolicy` | ✅ |
| `grafana` | `platform/grafana` → `service.ipFamilyPolicy` | ✅ |
| prometheus / alertmanager | `system/monitoring-system` → `prometheus/alertmanager.service.ipDualStack` | ✅ 2 处 |

> ⚠️ **kube-prometheus-stack 的两个坑**（实测踩到）：
> 1. 模板整块被 `if .Values.<c>.service.ipDualStack.enabled` 门住 —— **只写 `ipFamilyPolicy` 渲染出 0 处**，必须显式 `enabled: true`。
> 2. chart 默认 `ipFamilies: ["IPv6","IPv4"]`，而 **`ipFamilies` 不可变**，本集群这两个 Service
>    是从 IPv4-only 原地转换来的（主族仍是 IPv4）→ 照默认写会被 apiserver 拒绝。
>    必须显式写成 `ipFamilies: ["IPv4","IPv6"]`。

**无法声明的 7 个**（已逐个读取上游 chart 源码确认：其 Service 模板里**完全没有**
`ipFamilyPolicy` 字段，不是路径没找对）：

`dex`(dex@0.24.1)、`helm-dashboard`(helm-dashboard@2.0.7)、`homepage`(homepage@2.1.0)、
`rook-ceph-mgr-dashboard`(rook-ceph-cluster@v1.20.7)、`rustfs-svc`(rustfs@1.0.0)、
`woodpecker-server`(woodpecker@3.7.3)、`hubble-ui`(cilium@1.20.2，`templates/hubble-ui/service.yaml`)。

> 要声明它们只能把这些应用从 Helm source 改成 **Kustomize + `helmCharts` 膨胀 + JSON patch**
> （并给 ArgoCD 开 `--enable-helm`），而**本仓库内并没有 Application/ApplicationSet 清单**
> （只存在于集群侧），需先从集群导入 —— **属架构改动，经决定不做，永久接受现状**。
> 因此这 7 个若被重建（换集群、或删除后由 ArgoCD 重建）会退回单栈，届时的补救命令
> （幂等、可重复执行）：
>
> ```sh
> for s in dex/dex helm-dashboard/helm-dashboard homepage/homepage \
>          rook-ceph/rook-ceph-mgr-dashboard rustfs/rustfs-svc \
>          woodpecker/woodpecker-server kube-system/hubble-ui; do
>   kubectl -n "${s%%/*}" patch svc "${s##*/}" \
>     -p '{"spec":{"ipFamilyPolicy":"PreferDualStack"}}'
> done
> ```

**集群侧这 7 个当前已是双栈**，所以这是"可复现性"缺口而非"功能"缺口。

### 15.3 最终状态

| 项 | 值 |
| --- | --- |
| **Pod 双栈覆盖** | **168/168 —— 集群内已无 IPv4-only Pod** 🎉 |
| 节点 | 4/4 有 IPv4+IPv6 InternalIP |
| Service | 29 个有 IPv6 ClusterIP（`kube-dns` + 28 个 Ingress 后端） |
| Cilium | DS 4/4，四节点 IPAM 均两族 |
| Ceph | HEALTH_OK，81 GiB 数据完整，4 OSD up/in |
| PVC | 50/50 Bound |
| ArgoCD | **36/36 Synced** |
| 非 Running Pod | 0 |
