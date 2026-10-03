# Quickstart: 集群未使用资源审计（kor）

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

kor 以常驻 exporter 形式运行在 `kor` namespace，`/metrics` 由既有 Prometheus 抓取，面板在 Grafana 的 `Kor Dashboard`（uid `Zrue32P7Ik`）。

## 1. 上线

不需要任何额外步骤：`system/kor/` 被 ApplicationSet 的 git generator 覆盖（`system/*`），合入 `master` 即创建 `kor` Application 并同步。

```sh
kubectl get application kor -n argocd
kubectl -n kor get deploy,svc,servicemonitor
```

!!! note "需要等一会儿"

    ApplicationSet 的 git generator 轮询间隔是 `requeueAfterSeconds: 600`，且仓库未配置 webhook。实测从合入到 `kor` Application 出现约 4 分钟，到 `Synced/Healthy` 约 5 分钟。期间 `kubectl get application kor` 会返回 NotFound，属正常。

## 2. 验证

### 2.1 ArgoCD 与工作负载

```sh
kubectl get application kor -n argocd \
  -o jsonpath='{.status.sync.status} {.status.health.status}{"\n"}'
# Synced Healthy

kubectl -n kor get deploy kor-exporter \
  -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
# yonahdissen/kor:v0.6.9

kubectl -n kor get servicemonitor kor-exporter
```

### 2.2 Prometheus 抓取

```promql
up{job="kor-exporter"}
# 1
```

不通时先看 target 是否被 Prometheus 发现：

```sh
kubectl -n monitoring-system get servicemonitor -A | grep kor
kubectl -n kor logs deploy/kor-exporter --tail=20
# Server listening on :8080
# collecting unused resources
```

### 2.3 指标

```promql
# 总量（首次扫描完成后才有，实测 925）
count(kubernetes_orphaned_resources)

# 按命名空间汇总：必须用 exported_namespace
sum by(exported_namespace) (kubernetes_orphaned_resources{kind=~".*"})

# 某个命名空间里的未使用资源
kubernetes_orphaned_resources{exported_namespace="paperless"}
```

!!! danger "过滤一定要用 exported_namespace"

    kor 源码里的标签叫 `namespace`，但 prometheus-operator 会打上目标标签 `namespace="kor"`，
    Prometheus 把冲突的指标标签重命名为 `exported_namespace`。
    用 `namespace` 过滤**不会报错**，但结果恒为空或恒为 `kor`——属于静默失效。
    实测：`namespace` 只有 1 个取值，`exported_namespace` 有 41 个。

### 2.4 Dashboard

Grafana → Dashboards → 搜索 `Kor Dashboard`。4 个内容面板：总量（stat）、按 namespace 汇总（timeseries）、按 kind 分布（piechart / barchart）。

首次打开若为空，先确认 2.3 的 `count(...)` 已非零（首扫约 3 分钟）。

### 2.5 只读性核对

```sh
kubectl get clusterrole kor-read-resources-clusterrole \
  -o jsonpath='{.rules[*].verbs}' | tr ' ' '\n' | sort -u
# get list watch —— 不应出现 delete / update / patch
```

## 3. 日常运维

| 场景 | 操作 |
| --- | --- |
| 升级 kor | 改 `system/kor/Chart.yaml` 的 `version`（Renovate 也会提 PR），同时把 `values.yaml` 的 `image.tag` 对齐新的 appVersion |
| 调整扫描频率 | 改 `system/kor/values.yaml` 的 `prometheusExporter.exporterInterval`（单位**分钟**） |
| 调整资源 | 改同一文件的 `resources`；实测常驻约 10MiB |
| 让某个资源不再被报 | 给它打 `kor/used=true` |
| 强制把某个资源列为待清理 | 打 `kor/used=false` |
| 实际删除资源 | **人工决策后手工执行**。本特性只读，RBAC 无写权限，不提供自动清理 |

清理候选的查看方式（只读）：

```sh
# 从集群外直接问 Prometheus，避免为了看一眼而建临时 Pod
curl -s --get --data-urlencode \
  'query=kubernetes_orphaned_resources{exported_namespace="paperless"}' \
  https://prometheus.west-beta.ts.net/api/v1/query | jq -r '.data.result[].metric.resourceName'
```

## 4. 排障

| 症状 | 原因与处理 |
| --- | --- |
| 集群里没有 ServiceMonitor | 集群缺少 `monitoring.coreos.com/v1` CRD，chart 的门控会静默跳过。确认 CRD 存在后重新同步 |
| 有 ServiceMonitor 但 `up` 为 0 | 看 `kubectl -n kor describe servicemonitor` 与 Pod 状态；确认 Service 的 8080 端口有 endpoints |
| 面板全部 No data，但 `count(...)` 有值 | 查询里被改成了 `namespace`，应改回 `exported_namespace`（见 2.3 的 danger 块） |
| stat 面板「Unused $kind」单独没数据 | 该面板必须用正则 `kind=~"$kind"`；`$kind` 是 multi + includeAll，All 在等值匹配下会被插值成逗号列表 |
| 指标长时间不更新 | `EXPORTER_INTERVAL` 未生效或 values 被改回默认；`kubectl -n kor get deploy kor-exporter -o jsonpath='{.spec.template.spec.containers[0].env}'` |
| 首扫很慢（分钟级） | 正常：kor 要对 25 类资源做全集群 LIST。这也是把间隔放宽到 30 分钟的原因 |
| dashboard 没有出现在 `Kor` 目录里 | 既有现象：sidecar 只按 `monitoring-system` namespace 平铺加载，`grafana_dashboard_folder` 标签对该通道无效；`NAS`/`SMART`/`Tailscale` 同理，见 [research.md](./research.md) 第 7 节 |
