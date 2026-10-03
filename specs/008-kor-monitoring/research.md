# Research: 集群未使用资源审计（kor）

**Date**: 2026-10-03
**Feature**: [spec.md](./spec.md)

本文件记录方案取舍与实测取证。所有「实测」结论均来自本次对集群（`kubectl`）、ArgoCD（v3.5.3）与线上 Prometheus/Grafana 的直接操作，或上游源码/仓库的直接读取。

## 1. 上游 chart 而不是自制清单

上游提供 GitHub Pages Helm 仓库 `https://yonahd.github.io/kor`，最新 chart 为 `kor-0.2.16`（appVersion `0.6.9`）。chart 覆盖本特性需要的全部对象：ServiceAccount、Role/ClusterRole 及绑定、Service、Deployment、ServiceMonitor，以及一个可选 CronJob。

选它的三个理由：

- **CRD 门控**：ServiceMonitor 模板被 `.Capabilities.APIVersions.Has "monitoring.coreos.com/v1"` 包住，集群没有该 CRD 时不会同步失败。
- **可升级**：`Chart.yaml` 里一行版本号即可升级，且 Renovate 能按既有流程跟踪。
- **RBAC 规则已成表**：25 类资源的只读规则由 chart 维护，抄进仓库只会增加与上游漂移的风险。

**否决**：把 `helm template` 结果直接入库。多出约 300 行需要手工维护的清单，并且丢掉 CRD 门控——在没有 ServiceMonitor CRD 的集群上会同步失败。

## 2. CronJob 还是 exporter

chart 的两种模式相互独立，可单开可同开。默认 `prometheusExporter.enabled=true`、`cronJob.enabled=false`。

本特性只启用 exporter，理由：

- CronJob 的产出是**报告文本**，chart 支持的投递方式是 Slack webhook 或 Slack 频道上传；仓库内没有任何 Slack 凭据（宪法禁止提交凭据），报告只能落进 Pod 日志——没有人会去看。
- exporter 把同一份扫描结果变成指标，天然接入既有 Prometheus，并可由 Grafana 长期观察趋势。

kor 源码确认（`pkg/kor/exporter.go`，v0.6.9）：

```go
orphanedResourcesGauge = prometheus.NewGaugeVec(
    prometheus.GaugeOpts{
        Name: "kubernetes_orphaned_resources",
        Help: "Orphaned resources in Kubernetes",
    },
    []string{"kind", "namespace", "resourceName"},
)
```

`EXPORTER_INTERVAL` 的单位是**分钟**（`time.Duration(exporterIntervalValue) * time.Minute`），默认 `10`。

## 3. ServiceMonitor 能不能下发：ArgoCD 的 `--api-versions`

这是本特性唯一一处「不看源码就会判断错」的地方。

chart 的 ServiceMonitor 模板：

```gotemplate
{{- if and ( .Capabilities.APIVersions.Has "monitoring.coreos.com/v1" ) ( .Values.prometheusExporter.serviceMonitor.enabled ) }}
```

ArgoCD 的 repo-server 本身不访问集群，因此关键问题是：渲染时 `Capabilities.APIVersions` 从哪来。查证链路（argo-cd v3.5.3 源码）：

1. `controller/state.go`：从目标集群取 API 资源列表，转成字符串数组后放进 `ManifestRequest.ApiVersions`
   （`m.liveStateCache.GetVersionsInfo(destCluster)` → `argo.APIResourcesToStrings(apiResources, true)`）。
2. `reposerver/repository/repository.go`：`APIVersions: q.ApplicationSource.GetAPIVersionsOrDefault(q.ApiVersions)`。
3. `util/helm/cmd.go`：对每个元素追加 `--api-versions <v>`。

即：**ArgoCD 把目标集群的真实 API 版本透传给 `helm template`**，所以该门控在集群上为真。实测双向确认：

```sh
# 带参数：ServiceMonitor 出现
helm template --namespace kor --api-versions monitoring.coreos.com/v1 kor system/kor | grep -c "kind: ServiceMonitor"
# => 1

# 不带参数（等价于集群没有该 CRD）：不出现
helm template --namespace kor kor system/kor | grep -c "kind: ServiceMonitor"
# => 0
```

上线后集群中确实存在 `servicemonitor.monitoring.coreos.com/kor-exporter`，门控判断得到实证。

## 4. Prometheus 为什么不需要额外标签

既有 `system/monitoring-system/values.yaml`：

```yaml
prometheus:
  prometheusSpec:
    serviceMonitorSelectorNilUsesHelmValues: false
```

该项为 `false` 时，prometheus-operator 不再用 Helm release 标签筛选 ServiceMonitor，而是发现集群内全部 ServiceMonitor（无 namespace 限制）。既有 `rook-ceph`、`argocd` 的 exporter 正是这样接入的。因此 kor 的 ServiceMonitor **不需要** `release: kube-prometheus-stack` 之类的标签，实测部署后 `up{job="kor-exporter"}` 立即为 `1`。

## 5. 踩坑：`namespace` 与 `exported_namespace`（已修复）

**事故经过**：上游 dashboard 19863 的查询使用 `exported_namespace`。我在适配时依据 `pkg/kor/exporter.go` 的 `[]string{"kind","namespace","resourceName"}` 判断上游写错了，把过滤条件改成了 `namespace`。上线后实测发现改错了。

**根因**：prometheus-operator 抓取时会为所有 series 附加目标标签 `namespace=<exporter 所在 namespace>`；指标自带同名标签时，Prometheus 按标签冲突规则把**指标原有的**标签重命名为 `exported_` 前缀。

**实测证据**（上线后直接查询线上 Prometheus）：

```promql
kubernetes_orphaned_resources{... kind="ClusterRole", namespace="kor", resourceName="cdi.kubevirt.io:admin"}
```

| 查询 | 修改前（`namespace`） | 修改后（`exported_namespace`） |
| --- | --- | --- |
| 该标签的取值个数 | 1（恒为 `kor`） | 41（argocd、rook-ceph、monitoring-system…） |
| `sum by(<label>) (…)` | 单桶，全部落在一起 | 42 组（41 个命名空间 + 无标签的非命名空间资源） |
| `$namespace` 变量 | 只能取到 `kor` | 41 个真实命名空间 |

**修复**：改回 `exported_namespace`，并在 `templates/dashboard-kor.yaml` 的注释里写明原因，避免以后又被「修」回去（commit `8dc8223f`，PR #515）。

**教训**：kor 源码里的标签名 ≠ 落到 Prometheus 后的标签名。凡是面板查询，必须拿线上实际序列验证标签取值分布，不能只看 exporter 源码或文档。

## 6. dashboard 相对上游的两处改动

| 改动 | 原因 |
| --- | --- |
| datasource 由 `${datasource}` 变量改为硬编码 uid `prometheus` | 与仓库内既有 dashboard 一致（`monitoring-system-kube-pro-grafana-datasource` 里 Prometheus 的 uid 就是 `prometheus`） |
| `kind="$kind"` → `kind=~"$kind"` | `$kind` 是 multi + includeAll；All 在非正则上下文会被插值成逗号列表，`kind="{a,b,…}"` 匹配不到任何 series，stat 面板恒为 No data |

保留的字段：`uid`（`Zrue32P7Ik`）、`description`、`time`、`refresh`，面板结构未动，只改查询与 datasource。

## 7. sidecar 的 folder 标签实际上不生效（既有现象，未改动）

实测 Grafana 的 dashboard sidecar 日志，**所有** dashboard 一律平铺写入：

```
Writing /tmp/dashboards/nas-dashboard.json (ascii)
Writing /tmp/dashboards/tailscale-dashboard.json (ascii)
Writing /tmp/dashboards/kor-dashboard.json (ascii)
```

路径中没有以 folder 命名的子目录，因此 `grafana_dashboard_folder` 标签对这条通道无效。Grafana API 的搜索结果印证了这一点：同名的 dashboard 出现两份——

| 来源 | folderTitle |
| --- | --- |
| ConfigMap + sidecar（本仓库，含 `nas-qnap`、`tailscale`、`ce8j0dmrrej9cc`、`Zrue32P7Ik`） | `None` |
| 另一条 provisioning 通道 | `NAS` / `SMART` / `tailscale` |

`/api/folders` 只列出 `east4ming/homelab-grafana-gitsync`，说明带目录的那一份来自另一个 provisioning 连接，与本仓库的 ConfigMap 无关。

处理方式：**沿用既有标签、不造特例**。kor 的 ConfigMap 与其他三个保持同样的 `grafana_dashboard: "1"` + `grafana_dashboard_folder: "Kor"`，行为与它们完全一致（都落在默认目录）。要让 folder 生效需要改 provisioning 通道，属于既有行为的调整，不在本特性范围内。

## 8. 取值依据

| 项 | 取值 | 依据 |
| --- | --- | --- |
| 镜像 tag | `v0.6.9` | chart `0.2.16` 的 appVersion；上游默认 `latest` + `Always`，不可追溯 |
| `imagePullPolicy` | `IfNotPresent` | 与钉版本配套；实测拉取耗时 55.7s、镜像 10.5MB，缓存命中可省 |
| `exporterInterval` | `30`（分钟） | 上游默认 10 分钟；每轮是整集群 LIST，4 节点 homelab 无需如此频繁 |
| `requests` | `10m` / `64Mi` | 实测常驻 10MiB、24m CPU，留出首扫余量 |
| `limits` | `500m` / `256Mi` | 允许扫描瞬间突发；内存上限约为实测峰值的数倍，避免 OOMKilled |
| 扫描覆盖 | chart 默认（namespaced 与 non-namespaced 全扫） | 只读，无需收敛范围 |

实测时间线与开销：

```
13:01:39  Pod ready（此前 55.7s 用于拉镜像）
13:04:33  kubernetes_orphaned_resources 出现 925 条序列（首扫约 3 分钟）
常驻      10MiB / 24m CPU
```

## 9. 被否决的方案

| 方案 | 结论 |
| --- | --- |
| CronJob 模式（每周报告） | 无 Slack 凭据，报告只能进 Pod 日志。否决 |
| 用 kor 的 `--delete --no-interactive` 自动清理 | 需要写权限，且 kor 的判定存在上游已知假阳性（被 CRD/动态配置引用的 Secret 等）。清理必须是人工决策。否决 |
| krew/本地二进制安装 kor | 无法持续暴露指标，也不进入 GitOps 链路。否决 |
| 自研 exporter 或 recording rule 复刻 kor | 重新实现 25 类资源的「是否被引用」判定，收益为零。否决 |
| 让 dashboard 跟随 kor 目录（放宽 sidecar 的 searchNamespace 或新建 provisioning 通道） | 为 1 个面板改动既有 Grafana 行为。否决，见第 7 节 |
| 手工 `kubectl apply` 验证后再补 Git | 违反宪法「严禁手动 `kubectl apply`」。否决；验证一律用 `helm template` 与只读查询完成 |

## 10. 实测记录汇总

| 项目 | 结果 |
| --- | --- |
| 上游 chart | `kor 0.2.16`（appVersion `0.6.9`），仓库 `https://yonahd.github.io/kor` |
| 集群 ArgoCD | v3.5.3；ApplicationSet 轮询 `requeueAfterSeconds: 600` |
| 渲染对象数 | 8 个（SA、Role、RoleBinding、ClusterRole、ClusterRoleBinding、Service、Deployment、ServiceMonitor） |
| ServiceMonitor 门控 | 带 `--api-versions` 渲染出，不带则不渲染（两者实测） |
| 上线耗时 | 12:56:37 合入 → 13:00:39 Application 出现 → 13:01:39 `Synced/Healthy` |
| 抓取 | `up{job="kor-exporter"}=1`，无需任何 Prometheus 配置改动 |
| 指标 | 925 条 `kubernetes_orphaned_resources`；`exported_namespace` 41 个取值 |
| RBAC 动词 | 仅 `get`/`list`/`watch` |
| RBAC 对象 | Role + ClusterRole 各一（chart 默认 `rbac.create: true` 同时创建两者） |
| 常驻开销 | 10MiB / 24m CPU，镜像 10.5MB |
| dashboard | `Kor Dashboard`（uid `Zrue32P7Ik`）5 个面板（1 row + 4 内容面板），sidecar reload 返回 200 |
