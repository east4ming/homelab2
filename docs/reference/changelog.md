# Changelog

版本号格式与发布流程见 [版本管理](versioning.md)。新条目置顶，标题即 git 标签名。

## v2026.10.07

集群从 IPv4-only 转为 IPv4/IPv6 双栈。这是本仓库历史上第一个**需要停机**的变更：
k3s 官方明确双栈必须在集群创建时配置，无法在已运行的 IPv4-only 集群上直接启用，
且 k8s 禁止给既有 Node 增加 `podCIDR`（`node updates may not change podCIDR except
from "" to valid`），删节点重注册又被 k3s 的 `wrangler.cattle.io/managed-etcd-controller`
finalizer 挡住——因此走的是「停 etcd → 改三处 k3s 配置 → 原地更新 ServiceCIDR →
换 Cilium IPAM 模式」这条路，全流程先在本地用同版本容器复现验证后才上生产。

地址规划用站点 ULA `fdb5:92d0:b067::/48`：Pod `10.42.0.0/16` +
`fdb5:92d0:b067:4200::/56`（每节点 /64），Service `10.43.0.0/16` +
`fdb5:92d0:b067:4300::/112`。

### 新增

- `feat(k3s)`：`cluster-cidr` / `service-cidr` 增加 IPv6 段，`node-ip` 与
  `kubelet-arg: node-ip=` 传双族地址。三条硬约束都写进了注释：逗号后**不能有空格**
  （k3s 用 `SplitStringSlice` 切分且不 trim）、三个 flag 必须**同时改且地址族形状一致**
  （只改其一会 fatal）、IPv4 必须在前（etcd 与 apiserver 只用主族）。
  `node-ip` 之外还要 `kubelet-arg`，是因为本集群 `disable-cloud-controller: true` 时
  k3s 不会把 node-ip 传给 kubelet（上游注释 "don't assume that dual-stack node IPs are
  safe"），不显式传则 Node 的 `InternalIP` 里没有 IPv6。
  刻意**不设 `cluster-dns`**，保持 k3s 按每个 service-cidr 各派生一个 DNS IP 并把
  CoreDNS 置为 `RequireDualStack` 的默认行为。
- `feat(k3s)`：新增导出 `tailscale_ipv6` 与 `node_ipv6` 的 task；`node-external-ip`
  补上 Tailscale IPv6。`node_ipv6` 的取法要排除 `fe80:` 与 `fd7a:115c:a1e0:`
  ——Tailscale 自己的 ULA 也会以 global scope 出现在 `tailscale0` 上。
- `feat(cilium)`：`ipam.mode` 由 `kubernetes` 改为 `cluster-pool`，并声明双族池
  （IPv4 逐条列出那 4 个 /24、mask 24；IPv6 一个 /56、mask 64）；新增
  `ipv6.enabled` 与 `ipv6NativeRoutingCIDR`。**必须改 IPAM 模式而不是只开
  `ipv6.enabled`**：`kubernetes`(host-scope) 模式下 agent 要求每个启用的地址族都有
  `Node.spec.podCIDRs` 条目，而如上一段所述既有节点拿不到 IPv6 PodCIDR，结果是
  agent 报 `required IPv6 PodCIDR not available` → panic + CrashLoopBackOff →
  全集群 Pod 网络中断。`cluster-pool` 由 operator 自行分配，不依赖该字段。
- 12 个 app-template 系 chart 声明 `app-template.service.<name>.ipFamilyPolicy:
  PreferDualStack`（`excalidraw`、`jellyfin`、`ollama`、`pairdrop`、`paperless`、
  `searxng`、`speedtest`、`styleferry`、`upsnap`、`kanidm`、`kube-explorer`、
  `semaphore`）。这些 Service 在集群侧已是双栈，本次是把它写进 Git 以获得可复现性
  ——否则如「线上数据修复」一节所述，Declarative 与线上会静默分叉。

### 文档

- `docs(009)`：新增 `specs/009-dual-stack-network/`，含方案（`plan.md`）、调研
  （`research.md`）与实施手册（`runbook.md`）。手册覆盖备份、分阶段步骤与决策点、
  逐项验收门、回退方案 R1–R6 与应急预案，并完整记录了 P1/P2 与收尾阶段的实测结果。

### 线上数据修复（不在 Git 内）

> 本节记录集群侧**无法由 Git 表达**的状态，它们不随 tag 回滚，重建集群时需重放。

- **`CiliumNode.spec.ipam.podCIDRs` 需手工补 IPv6**：从 `kubernetes` 切到
  `cluster-pool` 时，节点上残留的该字段（仅 IPv4）会让 operator **静默跳过**分配
  ——没有日志、没有报错，新 agent 永远等不到 IPv6 PodCIDR，DaemonSet 卡在 2/4。
  给 4 个 `CiliumNode` 各补上 IPv6 /64 后 30 秒内恢复 4/4。**副作用是好的**：手工补
  而不是删 `CiliumNode` 让 operator 重分配，使既有 IPv4 映射逐字节保留，路由器上那
  4 条静态路由一条都不用改。
- **Service 双栈是 opt-in**：改 `ipFamilyPolicy` 不会给既有 Service 追溯补发第二个
  ClusterIP。本次转换了 28 个 Tailscale Ingress 后端 + `kube-dns`（它由 k3s 自动置为
  `RequireDualStack`），共 29 个 Service 具备 IPv6 ClusterIP；剩余 16 个属上游 chart，
  字段路径各异，集群侧已是双栈但尚未写入 Git。
- **ArgoCD 对 Service 的 `ipFamilyPolicy`/`clusterIPs` 做了归一化**，视为可忽略差异。
  两面影响：恢复 selfHeal 不会回退它们；但改动对 GitOps 是"隐形"的，故必须如上写进
  chart values 才不会被重建时丢失。

### 验证

4 节点均有 IPv6 `InternalIP`；`ServiceCIDR kubernetes` 原地更新为
`10.43.0.0/16,fdb5:92d0:b067:4300::/112`；**Pod 双栈覆盖 168/168**；
29 个 Service 有 IPv6 ClusterIP；PVC 50/50 Bound；Ceph `HEALTH_OK`（81 GiB 数据、
4 OSD up/in、81 pgs active+clean，与改造前基线逐项一致）；36/36 ArgoCD Application
`Synced`；无 Pending/异常 Pod。

过程中三个值得记的坑：**① 不要用 `ping -6` 测 ClusterIP**——Cilium LB 不转发 ICMP
到 ClusterIP，100% 丢包是正常的，必须用 TCP/UDP；**② 不要用 `kubectl get nodes -o wide`
判断节点双栈**——它只渲染一个 `InternalIP`，要用
`-o custom-columns` 展开 `status.addresses`；**③ 被 operator 托管的 workload 用
`rollout restart` 可能被静默撤销**（operator 抹掉 `restartedAt` 注解，StatefulSet
只重建了序号最大的那个就停了），判定方法是看
`.spec.template.metadata.annotations`，可靠替代是直接 `delete pod`。

## v2026.10.03.4

Grafana 的内存上限一直贴着稳态用量：新增 dashboard 时 provisioner 的瞬时分配就会把
512Mi 顶穿，26 小时内 OOMKilled 重启 7 次。本轮把上限放宽到 1Gi，顺带认领了一条只在
线上存在的插件 env，并清掉 Grafana 存储里一对重复的 dashboard 记录。

### 修复

- `fix(grafana)`：`platform/grafana` 内存上限 `512Mi -> 1Gi`、request `254Mi -> 512Mi`，
  chart 按 `0.9 × limit` 注入的 `GOMEMLIMIT` 随之 `460MiB -> 921MiB`。判据是线上实测：
  稳态 RSS 已 ~460Mi（`go_memstats_heap_sys_bytes` 335Mi、`heap_released_bytes` 只有
  2Mi），`container_memory_working_set_bytes` 常态 390–440Mi（limit 的 76%–86%）；
  每次 dashboard 增删或 ArgoCD 同步，sidecar 重写 `/tmp/dashboards`、文件 provisioner
  重放全部 dashboard 并重建 unified-storage 的 bleve 搜索索引，working set 一两分钟内
  多出 ~100Mi、冲到 500Mi 以上——重启时刻 11:47 / 13:17 / 16:37 都与 dashboard 变更
  吻合。告警自带的 `Node allocated memory 0.00% out of 31382MB allocatable` 说明这与
  节点无关，打出的是容器 cgroup limit
- `fix(grafana)`：`GF_INSTALL_PLUGINS=performancecopilot-pcp-app` 写进 values.yaml。
  它此前只存在于线上 StatefulSet（out-of-band 添加），而 ArgoCD 用 server-side apply，
  按 name 合并的列表项多出来的条目不会被 prune，所以应用一直显示 Synced、这条 env 无人
  认领。刻意不用 chart 的 `plugins:` 键——chart 13.2.5 把它渲染成
  `GF_PLUGINS_PREINSTALL_SYNC`（另一个变量），写 `env` 映射才能与线上逐字一致：
  渲染后的 env 与线上 13 == 13 项相同，剩余差异只有本次调整带来的 `GOMEMLIMIT`

### 线上数据修复（不在 Git 内）

`prometheus.json`（kube-prometheus-stack 的 Prometheus / Overview）在 Grafana 存储里
存在两份记录，同为 `sourcePath=/tmp/dashboards/prometheus.json`、同带 legacy id
`777586274930688`。文件 provisioner 的保存路径是「按 legacy id 查、且必须恰好 1 条」，
因此每 30s 失败一次：

```
unexpected number of dashboards for id 777586274930688. found: 2. desired: 1
```

该面板自 2025-07 起就无法更新（version 停在 1）。`/tmp/dashboards/` 目录本身只有一份
文件，重复发生在 Grafana 的存储里。

根因：kube-prometheus-stack **75.12.0 -> 75.13.0** 给这个 dashboard 的 JSON 补了写死的
`"uid":"9fa0d141-…"`（75.12.0 的 `prometheus.yaml` 里没有 uid 字段）。provisioner 按
uid 识别 dashboard，于是 2025-07-23 新建了一条记录，而 2025-07-18 生成随机 uid
`644d6b21-…` 的那条留了下来。两条记录的创建时间正好落在两次 chart 发布之后：
75.12.0 发布 2025-07-18T15:00Z -> 记录 2025-07-18T22:13Z；75.13.0 发布
2025-07-22T17:55Z -> 记录 2025-07-23T01:09Z。

处理：删除孤儿记录。Grafana 会拦 `provisioned dashboard cannot be deleted`，所以先经
dashboard apiserver（`/apis/dashboard.grafana.app/v2beta1`）清掉它的
`grafana.app/managedBy` 标记，再 DELETE。删除后下一个 provisioning 周期即保存成功
（面板 version 1 -> 2、`updated=2026-10-03T08:50:19Z`），报错从 45 分钟 33 次归零，
带该 legacy id 的记录只剩 1 条，dashboard 总数 109 -> 108。PVC 每天由 VolSync 备份
（`replicationsource/storage-grafana-0`），可回滚。

两点遗留：同名面板还有第三份来自 Git Sync 仓库
（[east4ming/homelab-grafana-gitsync](https://github.com/east4ming/homelab-grafana-gitsync)
的 `k8s/prometheus-overview.json`，文件夹 `k8s`），属另一条 provisioning 通道，本轮未动；
另外上游 chart 今后若再次改这个 dashboard 的 uid，同样的重复会重演，识别信号就是上面
那条 `unexpected number of dashboards` 报错。

## v2026.10.03.3

kor 从「装上」变成「能用」：分级脚本与清理 runbook、exporter 的假阳性过滤、4 条告警
规则；并据此清理了 449 个确认无用的对象。未使用资源指标 **925 → 183**，全程只读。

### 新增

- **清理流程**（spec-kit `008-kor-monitoring`）：`scripts/kor-audit` 把 kor 的发现结果
  与集群实况（GitOps 归属、ownerReferences）交叉核对，输出 A/B/C 分级。判级的关键是
  两条分界线：**派生对象（有 owner）只看 owner**，声明式对象才看 GitOps 标记——
  486 个 ReplicaSet 里有 258 个继承了 Deployment 的 ArgoCD 注解，按标签判会全部误判
- **清理 runbook**：`docs/how-to-guides/prune-unused-resources.md`，逐 kind 说明 kor 的
  判定语义与假阳性来源、三级清单、备份/删除/误删恢复三阶段，以及 12–24 小时的 etcd
  快照恢复窗口
- **exporter 假阳性过滤**：`--exclude-labels app.kubernetes.io/managed-by=Helm` 与
  `tailscale.com/managed=true`（实测 secret 发现数 62 → 25）。后者是因为 Tailscale
  operator 会重写 Secret 元数据、把外部打的 `kor/used=true` 冲掉，只能从 exporter 侧过滤
- **保护性标签**：给 48 个高危假阳性打 `kor/used=true`（k3s etcd 快照凭据、21 个 VolSync
  备份仓库口令、6 个 rook CSI 密钥；Tailscale 的 21 张证书被 operator 冲掉）。该标签
  同时保证 `kor --delete` 永不触碰这些对象
- **告警规则**：kor 的 PrometheusRule 4 条（审计指标消失、总量 7 天增长、陈旧
  VolumeAttachment、未挂载 PVC 增长）。刻意不做绝对数量告警——规模受过滤配置、集群历史
  与假阳性三者影响

### 修复

- `fix(kor)`：补齐 RBAC 的 `nodes`/`csidrivers`。上游 chart 默认表里没有这两项，导致
  kor 查节点必然失败、**把全部 25 条 VolumeAttachment 报成「Node does not exist」**，
  而这些 VA 的 PV 与节点都存在、属活跃挂载——照那份报告删会触发卷 detach。修正后
  VA 发现数归零
- `fix(kor-audit)`：指标里有、集群里已不存在的对象不再让脚本崩溃（新增 `?` 级别）

### 文档

- `docs(kor)`：更正 #518 里「集群级 CRD 不受 --exclude-labels 影响」的错误结论。
  `processCrds` 有两个调用者：`pkg/kor/all.go` 的 `getUnusedCrds` 传入真实 filterOpts
  （exporter 走这条，CRD 会被过滤），`pkg/kor/crds.go` 的 `GetUnusedCrds` 丢弃参数
  （独立子命令走这条）。同口径实测 871 → 622

### 集群清理（本轮实际删除的 449 个对象）

| 批次 | 对象 | 数量 | 依据与影响 |
| --- | --- | --- | --- |
| 1 | Woodpecker 孤儿流水线 Service + PVC | 7 + 7 | 无 owner、无 Pod 挂载；PV 57→50、Ceph 镜像 55→48，实测仅回收约 0.5 GiB |
| 2 | `pod-impersonation-shell-*` 6 对 + `loft-cluster-*` 4 个 ClusterRole | 16 | 已卸载的 Rancher/Loft 遗留，集群内无任何相关组件 |
| 3 | Loft 收尾（3 ClusterRole + 3 ClusterRoleBinding） | 6 | vcluster 的 SA 所在 namespace 已不存在，引用本已悬空 |
| 4 | 旧 ReplicaSet + 已完成 Job | 381 + 32 | 独立校验：RS 副本为 0 且无 Pod 引用，Job 全部 Completed |

删除前的 YAML 备份与核对记录在操作机 `tmp/kor-backup-2026-10-03-*/`（该目录不入库）。
刻意未删的 25 条 VolumeAttachment 见上文「修复」。

## v2026.10.03.2

kor 接入集群：以 Prometheus exporter 形式常驻，暴露「无人引用的资源」指标，
配套 Grafana dashboard；全程只读。

### 新增

- **未使用资源审计**（spec-kit `008-kor-monitoring`）：`system/kor/` 包装上游
  [yonahd/kor](https://github.com/yonahd/kor) chart `0.2.16`，`namespace=kor`。
  ApplicationSet 按 `system/*` 自动发现，因此没有新增任何 Application 清单
- **只启用 exporter 模式**：CronJob 模式需要 Slack webhook 或频道上传来投递报告，
  而仓库内没有 Slack 凭据（宪法禁止提交凭据），报告只能落进 Pod 日志，故不启用。
  exporter 每 30 分钟重扫一次（上游默认 10 分钟；每轮是整集群 LIST，对 4 节点
  homelab 无需如此频繁），暴露 `kubernetes_orphaned_resources{kind,namespace,resourceName}`
- **抓取无需人工登记**：chart 自带 ServiceMonitor，且被
  `.Capabilities.APIVersions.Has "monitoring.coreos.com/v1"` 门控。ArgoCD v3.5.3 会把
  目标集群的 API 版本透传给 `helm template --api-versions`
  （`controller/state.go` → `argo.APIResourcesToStrings` → `reposerver/repository.go`），
  因此门控能反映真实集群能力；既有 Prometheus 的
  `serviceMonitorSelectorNilUsesHelmValues=false` 使其无需额外标签即被发现
- **Grafana dashboard**：导入上游 19863 到 `system/monitoring-system`（sidecar 只搜索该
  namespace），改两处：datasource 硬编码 uid `prometheus`；`kind="$kind"` 改正则
  `kind=~"$kind"`（`$kind` 是 multi + includeAll，All 在等值匹配下匹配不到序列）
- **只读边界**：RBAC 仅授予 `get`/`list`/`watch`，kor 的 `--delete` 能力不配置；
  镜像钉 `v0.6.9` + `IfNotPresent`（替代上游默认的 `latest` + `Always`），
  并显式声明 requests/limits（10m/64Mi、500m/256Mi）

### 修复

- `fix(kor)`：dashboard 的命名空间过滤条件曾按 kor 源码的标签名写成 `namespace`，
  实测为错——prometheus-operator 会打上目标标签 `namespace="kor"`，Prometheus 把指标
  自带的同名标签重命名为 `exported_namespace`。改用 `namespace` 后过滤器静默失效
  （取值只剩 1 个），改回 `exported_namespace` 后为 41 个命名空间取值、
  `sum by(exported_namespace)` 返回 42 组。教训与实测数据记入 research.md

### 文档

- `docs(008)`：kor 审计的 spec-kit 文档（spec / plan / research / tasks / quickstart /
  checklist）。research.md 记录了 ServiceMonitor 门控的 ArgoCD 源码取证、
  `namespace` 与 `exported_namespace` 的踩坑实测，以及 Grafana sidecar 的
  `grafana_dashboard_folder` 标签实际失效（面板目录来自另一条 provisioning 通道）这一既有现象

## v2026.10.03

集群外的 QNAP NAS 接入监控：系统指标与磁盘 SMART 采集、告警规则与 Grafana dashboard；
另为桌面机新增 Tailscale 抓取目标。

### 新增

- **桌面机 Tailscale 抓取**：`tailscale-nodes` job 新增 `192.168.3.246:5252`（`node: casey-desktop`）
- **QNAP NAS 监控**（spec-kit `007-nas-monitoring`）：`NAS33657A`（TS-453Bmini，QTS 5.2.10）
  以 Container Station 应用运行两个 collector —— `node-exporter`（9100）与
  `smartctl-exporter`（9633），均走 host 网络，Prometheus 通过新增的 `nas-node` /
  `nas-smartctl` 两个静态 job 抓取并附加 `nas` 标签。NAS 是集群外设备，ArgoCD 无法管理其容器，
  故 compose 入库存放在 `metal/nas/compose.yml` 并由 Container Station 导入
- **磁盘 SMART 采集**：实测发现该 QNAP 控制器会让 `smartctl --scan-open` 把 4 块 SATA 盘
  误判为 `scsi`，温度返回 `0` 且 ATA 属性全缺（exporter 照常有输出，属静默失效）。
  必须使用 `smartctl-exporter:v0.14.0` 并以 `--smartctl.device=/dev/sdX;sat` 强制设备类型。
  修复后 5 块盘返回真实温度 44–49°C、`smart_status` 全为 1；SMART 指标另加 `disk` 盘位标签
  （依据 `qcli_storage -d` 实测映射 sdc→bay1、sdd→bay2、sda→bay3、sdb→bay4）
- **告警与可视化**：新增 6 条告警规则（卷容量两级阈值、卷只读、RAID 失去冗余、SMART 健康失败、
  磁盘高温）与 Grafana `NAS` dashboard（13 面板）；抓取中断复用既有 `TargetDown`。
  规则按实测样本逐条评估，排除 QTS 内部固定布局对象（`md9`/`md13` 固件镜像 32 槽位只用 4 槽、
  `/mnt/ext` 固件 DOM 设计上仅剩 7.69% 可用），否则上线即永久误报

### 依赖与构建

- `chore(deps)`：kube-prometheus-stack `91.5.2` → `91.5.3`、renovate chart `46.321.2` → `46.321.8`、
  `Markdown` `3.10.3` → `3.11`、`platformdirs` `4.11.12` → `4.11.14`
- 新增 `.gitignore` 条目 `.helm_ls_cache/`，避免本地 Helm 语言服务缓存入库

### 文档

- `docs(007)`：QNAP NAS 监控的 spec-kit 文档（spec / plan / research / tasks / quickstart / checklist），
  其中 research.md 记录了 SNMP、Entware、QCLI 等被否决路径的实测依据

## v2026.10.02.4

Tailscale 指标监控上线：4 台节点与 operator ProxyGroup 代理的客户端指标接入 Prometheus，
配套告警规则与 Grafana dashboard；同时消除 KubeVirt CDI CRD 的持续 `OutOfSync`。

### 新增

- **Tailscale 节点指标**（spec-kit `006-tailscale-monitoring`）：4 台节点由新增的
  `tailscale-metrics.service` 以只读方式暴露 `tailscale web --readonly --listen <node-ip>:5252`，
  Prometheus 通过 `additionalScrapeConfigs` 的 `tailscale-nodes` job 采集并附加 `node` 标签
- **operator 代理指标**：新增 `tailscale-metrics` ProxyClass（metrics + ServiceMonitor），
  由 `ingress-proxies` / `egress-proxies` 两个 ProxyGroup 通过 `spec.proxyClass` 引用，共 8 个采集目标。
  实测否决了更省事的 `PROXY_DEFAULT_CLASS` 方案：8 个带
  `experimental-forward-cluster-traffic-via-ingress` 注解的独立 Ingress 代理上游不支持 metrics，
  默认类会为它们建出永远失败的 target 并触发 `TargetDown` 误报
- **告警与可视化**：新增 3 条告警规则（节点健康消息、节点异常丢包、代理健康消息）与
  Grafana `Tailscale` dashboard（14 面板）；抓取中断复用既有 `TargetDown` / `KubePodNotReady`

### 修复

- `fix(kubevirt)`：从 vendored `system/kubevirt/templates/cdi-operator.yaml` 的
  `cdis.cdi.kubevirt.io` CRD 中移除 `v1alpha1` 版本块（2517 行），只保留 operator 认可的 `v1beta1`。
  CDI operator 每次 reconcile 都会删除非最新版本，与 Git 中声明的版本列表来回拉锯，
  导致应用持续 `OutOfSync`；README 排障表补上该条

### 依赖与构建

- `chore(deps)`：kube-prometheus-stack `91.5.1` → `91.5.2`、renovate chart `46.317.2` → `46.321.2`
- `chore`：Cilium pin `1.20.1` → `1.20.2`、Tailscale pin → `1.102.4`
- `chore(lobe-chat)`：lobe-chat 镜像更新到 `2.2.18`
- `chore`：合并上游 khuedoan/homelab master，补上落后的提交（含 `build: containerize docs`
  带来的 `Dockerfile` / `.dockerignore`）

### 文档

- [同时使用 GitHub 和 Gitea](../how-to-guides/use-both-github-and-gitea.md) 新增
  「upstream remote 与从 GitHub 同步上游」章节
- `docs(006)`：Tailscale 监控的 spec-kit 文档（spec / plan / research / tasks / quickstart / checklist）

## v2026.10.02.3

Rook-Ceph CephX 密钥加固，以及 OSD `down/out` 故障的排查文档补全。

### 修复

- `fix(rook-ceph)`：按 Rook CVE-2025-30156 指南，将 CSI 与 RBD mirror peer 密钥轮换到 `aes256k`
  （节点内核均已升级到 7.0+）
- `fix(rook-ceph)`：密钥迁移完成后删除旧 CSI 密钥，并移除临时告警 mute
- `fix(rook-ceph)`：将 CephX allowed ciphers 限制为 `aes256k`

### 文档

- 新增 [Rook-Ceph OSD down/out 修复：mon secret FSID 失配](../how-to-guides/troubleshooting/rook-ceph-osd1-fsid-mismatch-recovery.md)：
  `rook-ceph-osd-1` 在 `n100-cheshi-0` 升级后长期 `down/out` 的完整根因分析。
  根因是 `rook-ceph-mon` Secret 的 `fsid` 过期，operator 据此判定 OSD 磁盘
  「属于另一个 Ceph 集群」而拒绝创建 OSD Deployment —— **磁盘数据自始至终完好**。
  修复只需改回真实 `ceph fsid`，无需 `ceph osd purge` 或重建 OSD
- 修正 [Ubuntu 24.04 → 26.04 升级指南](../how-to-guides/upgrade-ubuntu-24-04-to-26-04.md)
  「检查 7」中错误的 OSD 恢复建议：原文要求 `ceph osd purge` + 抹掉分区，
  会销毁完好副本；现改为指向上述 FSID 修复流程
- 将两份 Rook-Ceph 排障文档从 `system/rook-ceph/docs/` 迁入 `docs/` 并加入 mkdocs 导航
  （此前未发布）

## v2026.10.02.2

修正 `metal/roles/*/defaults/main.yml` 中落后的版本 pin，使仓库与集群实跑版本一致。
修正前 Cilium pin 为 `1.20.0`、k3s pin 为 `v1.35.4+k3s1`，而集群实跑 `1.20.1` / `v1.36.5+k3s1`，
直接执行 `make -C metal cluster` 会把两者一起回退。

### 修复

- `fix(cilium)`：Cilium 版本 pin 由 `1.20.0` 更新为 `1.20.1`，与集群实跑 chart 版本一致
- `fix(k3s)`：k3s 版本 pin 由 `v1.35.4+k3s1` 更新为 `v1.36.5+k3s1`，与节点实跑版本一致

## v2026.10.02

4 台节点由 Ubuntu 24.04 LTS 就地升级到 26.04 LTS（Resolute Raccoon）后的适配与修复。
完整明细见 `git log v2026.09.21..v2026.10.02 --no-merges`。

### 修复

- **内核参数持久化**：`prerequisites` 角色原先把 sysctl 写入 `/etc/sysctl.conf`，而 26.04 的
  `procps` 将其标记为 `remove-on-upgrade` 并在升级时删除，导致 `fs.inotify.max_user_instances`
  从 8192 掉回 128，`fwupd` 每小时失败、KubeVirt `virt-handler` 在 inotify 用量高的节点上
  CrashLoopBackOff。四组 sysctl 全部改写到 `/etc/sysctl.d/90-homelab-prerequisites.conf`
- **PXE/autoinstall 适配 26.04.1**：ISO 与 netboot.xyz squash 资源更新到 26.04.1；
  autoinstall 包列表移除 26.04 已不存在的 `libpcre3`/`libpcre3-dev`，`dnsutils` 换成
  `bind9-dnsutils`（否则全新装机在 `packages:` 阶段失败）；netplan 由 `gateway4` 改为 `routes`
- `fix(lobe-chat)`：`.helmignore` 排除 `AGENTS.md` 而非已不存在的 `CLAUDE.md`
- `fix(docs)`：修复 CLAUDE.md 重命名后遗留的悬空引用

### 文档

- 新增 [Ubuntu 24.04 LTS 升级到 26.04 LTS](../how-to-guides/upgrade-ubuntu-24-04-to-26-04.md)：
  升级流程 + 升级后必查清单（sysctl 丢失、第三方 apt 源被禁用、残留 conffile 导致 logrotate 失败、
  旧内核残留、netplan 弃用、Ceph OSD 未被 Rook 接管）
- 全仓库的 24.04 版本描述更新为 26.04.1：README、PXE 引导、沙箱、路线图、决策记录、固件裁剪说明
- `docs(versioning)`：补上 `gh release create` 必需的 `-R` 参数

### 依赖

- Renovate 持续更新 Helm Chart 与容器镜像，非 major 依赖按周聚合合并（含 rustfs 1.x、renovate 46.310.0、pymdown-extensions 12）

## v2026.09.21

自 `v2025.02.17` 以来的状态快照，覆盖 830 个非合并提交。完整明细见 `git log v2025.02.17..v2026.09.21`。

### 新增应用

- **RustFS**：S3 兼容对象存储，启用 TLS、日志轮转与 Tailscale Ingress；lobe-chat 的对象存储由 MinIO 迁移至此
- **RSSHub**：RSS 聚合服务，含 PostgreSQL
- **Upsnap**：网络唤醒（Wake-on-LAN）管理面板
- **SearXNG**：自建元搜索引擎，并接入 lobe-chat
- **Semaphore**：任务编排面板，配置了 dnsPolicy 与时区
- **Kube Explorer**：Kubernetes 资源浏览器
- **Eraser**：节点镜像清理

### 移除

- **Webtop** 与 **MinIO**：不再使用，已移除部署与相关 egress 配置

### KubeVirt 虚拟机

- 引入 KubeVirt 与 CDI，新增虚拟机测试套件（unit / integration / e2e）
- 用 DataVolume PVC 作为 rootdisk，替换 containerDisk
- 支持从外部 Secret 注入 cloud-init，避免在公开仓库中泄露凭据
- control-plane 副本数降为 1，适配 4 节点规模
- Cilium datapathMode 由 `netkit` 调整为 `netkit-l2`

### 网络与 Tailscale

- Tailscale Operator 接管 Ingress / DNS / 证书 / Funnel，替代 nginx-ingress、external-dns、cert-manager、cloudflared
- 新增出口代理组（proxygroup）、proxyclass 与出口服务配置
- 多个外部服务补齐 HTTPS 端口与 proxy-class 注解
- Cilium 由 1.19.1 升级到 1.19.6，保持 native routing、BPF masquerade、DSR、netkit、Bandwidth Manager
- 因内核与 datapathMode 变更导致带 NetworkPolicy 的 Pod 异常，临时禁用本仓库全部 NetworkPolicy

### 系统与升级

- 新增系统升级流程，配合 kured 完成滚动重启
- csi-driver-nfs 补齐 resources requests/limits
- 适配 k3s 移除 kube-proxy IPVS 模式
- journald 日志接入
- 清理 linux-firmware 中不再需要的厂商子包

### 可观测性

- 4 个节点全部接入磁盘 SMART 监控，含仪表盘与告警规则（展示节点主机名与 IP）
- 新增 VolSync 与 kube-explorer 相关监控
- Grafana 12：启用 git sync、图像渲染器等新特性

### 文档与工程

- 重组 troubleshooting 文档结构，新增节点挂起故障排除指南
- 更新架构文档，移除 Zot Registry 相关内容
- 新增 KubeVirt、SMART 监控等能力的 Spec Kit 规格（`specs/`）

### 依赖

- Renovate 持续更新 Helm Chart 与容器镜像，非 major 依赖按周聚合合并

## v2025.02.17

- 进入 homelab2 目录后自动运行: `nix develop --extra-experimental-features nix-command --extra-experimental-features flakes`

### bash 实现

通过 `bash` 的重载 `cd` 函数来实现。

1. **创建一个脚本文件**：
   创建一个脚本文件（例如 `run_nix_develop.sh`），内容如下：

   ```sh
   #!/bin/sh
   nix develop --extra-experimental-features nix-command --extra-experimental-features flakes
   ```

   确保脚本具有可执行权限：

   ```bash
   chmod +x run_nix_develop.sh
   ```

2. **修改 `~/.bashrc` 文件**：
   在 `~/.bashrc` 文件中添加以下内容，以便在每次进入目录时检查是否在特定目录中，并执行相应的脚本。

   ```sh
   # ~/.bashrc
   function cd() {
       builtin cd "$@" || return
       if [ "$(pwd)" == "~/projects/homelab2" ]; then
           ~/projects/homelab2/run_nix_develop.sh
       fi
   }
   ```

   这个脚本会重写 `cd` 命令，使其在每次切换目录后检查当前目录是否为 `~/projects/homelab2`，如果是，则执行 `run_nix_develop.sh` 脚本。

3. **重新加载 `~/.bashrc` 文件**：
   重新加载 `~/.bashrc` 文件以使更改生效：

   ```bash
   source ~/.bashrc
   ```

### zsh 实现

在 `zsh` 中设置进入当前目录后自动执行 `run_nix_develop.sh` 脚本，可以通过以下方法实现：

**使用 `precmd` 钩子**

`precmd` 钩子会在每次显示命令提示符前触发，但需结合目录检查逻辑。

1. **修改 `~/.zshrc` 文件**：

   ```zsh
   # ~/.zshrc
   autoload -U add-zsh-hook

   # 定义钩子函数
   run_on_prompt() {
       if [[ "$(pwd)" == "~/projects/homelab2" ]]; then
           ~/projects/homelab2/run_nix_develop.sh
       fi
   }

   # 将函数绑定到 precmd 钩子
   add-zsh-hook precmd run_on_prompt
   ```

2. **重新加载 `~/.zshrc` 文件**：
   重新加载 `~/.zshrc` 文件以使更改生效：

   ```bash
   source ~/.zshrc
   ```

## v2025.02.16

- Remove Loki-stack, as Loki-stack is no longer actively maintained.
- Use Grafana Cloud -> grafana/k8s-monitoring to monitor logs and Profiles. See [kubernetes-monitoring/configuration](https://grafana.com/docs/grafana-cloud/monitor-infrastructure/kubernetes-monitoring/configuration/) for more details. Since this involves Grafana Cloud secrets, install directly using helm-dashboard; the helm chart's values.yaml is not maintained in this repo.

## 上游历史（fork 前）

以下条目继承自上游 [khuedoan/homelab](https://github.com/khuedoan/homelab)，正文逐字保留。
其中的版本号与 `-alpha` 后缀属于上游命名，不适用本仓库的 [CalVer 版式](versioning.md)。

### v0.0.8

Notable changes:

- **build:** run post install scripts by default
- **build:** set `KUBECONFIG` from global Makefile
- **feat(external-dns)!:** add cluster name as owner ID
- **feat(tools):** install `yamllint`, `ansible-lint` and `k9s`
- **feat(tools):** set `KUBECONFIG` by default
- **feat:** add pre-commit hooks
- **feat:** add script to setup Gitea tokens and OAuth apps
- **perf(argocd):** turning on selective sync
- **refactor(docs):** migrate to [mkdocs](https://squidfunk.github.io/mkdocs-material)
- **refactor(metal):** migrate to Fedora 36 for newer packages
- **refactor(pxe)!:** combine dhcpd and tftpd to dnsmasq
- Many bug fixes

Please see git log for full change log.

### 0.0.7-alpha

- Replace standard Vault with Vault Operator
- Automatically initialize and unseal Vault
- Declarative secret generation and management
- Declarative Gitea configuration with YAML
- Automatic OS rolling upgrade
- Automatic Kubernetes rolling upgrade
- Automatic application updates using Renovate (still require manual token generation)
- Add script to wait for essential services after deployment
- Add icons and bookmarks to the home page
- Deploy Matrix chat
- Replace Authentik with Dex for SSO (still require manual token generation)
- Switch to Mermaid for diagrams in documentation
- Replace Vagrant with k3d for development environment
- Use nip.io domain for development environment
- Remove Backblaze (S3 Glacier and/or Minio will be added in future version)
- Enable monitor for the majority of applications
- Many code refactorings and bug fixes

### 0.0.6-alpha

- Upgrade to Kubernetes 1.23
- Support external resources:
    - Cloudflare DNS and Tunnel
    - Backblaze for backup
    - Auto inject secrets to required namespaces
- Replace self-signed certificates with Let's Encrypt production (with API token injected from the `external` layer)
- Add DNS records automatically using external-dns
- Easy Cloudflare Tunnel configuration with annotations
- Offsite backup to Backblaze B2 bucket using k8up-operator
- Add private container registry
- Remove Knative to save resources (temporarily)
- Enable encryption at rest for Kubernetes Secrets
- Add more Tekton tasks and pipelines
- Initialize GitOps repository on Gitea automatically after install
- Generate MetalLB address pool automatically (default to the last `/27` subnet)
- Some bug fixes

### 0.0.5-alpha

- Add convenience scripts
- Add Loki for logging
- Add custom health check for Application and ApplicationSet
- Use Vault with dev mode on (temporarily until we hit beta)
- Replace Authelia with Authentik
- Upgrade to Kubernetes 1.22
- Upgrade most services to the latest version
- Set ingress class and storage class explicitly
- Initial Linkerd and Knative setup (not working yet)
- Set up Hajimari for home page with automatic ingress discovery
- Add dev VM for local development or evaluation
- Optimize bare metal provisioning performance
- Replace Syncthing with Seafile (may use both in the feature)
- Enable Gitea SSH cloning via Ingress
- Various code clean up
- Add more documents

### 0.0.4-alpha

- Switch to Rocky Linux
- Some optimization for bare metal provisioning
- Switch to k3s and combine Kubernetes cluster config in `./infra` layer to `./metal` layer (because k3s is also configured using Ansible)
- Split boostrap Helm charts in `./infra` layer to `./bootstrap` layer (with new ArgoCD pattern) and `./system` layer
- Add `./platform` layer for some applications like Gitea, Tekton...
- User only need to provision `./metal` and `bootstrap` layer, the `./bootstrap` layer will deploy the remaining layers
- Provisioning time from empty disk to running services is significantly reduced (thanks to k3s and new bootstrap pattern)
- Use [mdBook](https://rust-lang.github.io/mdBook/) for documents
- Replace Drone CI with Tekton
- Enable TLS on all Ingresses (using [cert-manager](https://cert-manager.io))
- Add some new applications

### 0.0.3-alpha

- Generate Terraform backend config automatically
- Switch to CoreOS
- Better PXE boot setup
- Diagrams as code

### 0.0.2-alpha

- Ensure idempotency for bare metal provisioning
- Extract instead of mounting the OS ISO file
- Easy initial controller setup (with only Docker)
- Switch to Fedora
- Remove LXD
- Move etcd (Terraform state backend) back to Docker

### 0.0.1-alpha

- Bare metal provisioning with PXE
- LXD cluster
- Terraform state backend (etcd)
- RKE cluster
- Core services (Vault, Gitea, ArgoCD,...)
- Public services to the internet (via port forwarding or Cloudflare Tunnel)
