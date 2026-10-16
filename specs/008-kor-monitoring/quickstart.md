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
# yonahdissen/kor:v0.6.9@sha256:1a85158c82bbca16c942426b7ef3faba3f5cb23634b5b66e462716bc8520fc8f

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
# 总量（首次扫描完成后才有；2026-10-03 实测 925，会随集群漂移）
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
    实测：`namespace` 只有 1 个取值（恒为 `kor`），`exported_namespace` 有 30+ 个。

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
| 升级 kor | 改 `system/kor/Chart.yaml` 的 `version`（Renovate 也会提 PR），然后**必须**做 §3.1 的 `rbac.rules` 对照与 digest 更新 |
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

### 3.1 升级 kor（每次 bump chart 必做，少一步就静默丢权限）

`system/kor/values.yaml` 用**整体覆盖**的方式重写上游 chart 的 `rbac.rules`——Helm 对
`rbac.rules` 是覆盖而非追加，上游增删权限项时本地覆盖表不会跟着变。2026-10 那轮
25 条 VolumeAttachment 假阳性就是这么产生的：上游默认没有 `nodes`/`csidrivers`，
kor 逐个查 VA 引用的节点时 Get 失败，于是把每条活跃挂载都报成
`Node ... does not exist`，而 runbook 当时把它当成「CSI 残留」。

升级时按顺序做完这四步：

1. 拉上游默认 values，与本地覆盖表逐项对照：

   ```sh
   helm repo add kor https://yonahd.github.io/kor && helm repo update
   helm show values kor/kor --version <新 chart 版本> > /tmp/kor-upstream-values.yaml
   diff <(yq -o=json '.rbac.rules' /tmp/kor-upstream-values.yaml | jq -S .) \
        <(yq -o=json '.kor.rbac.rules' system/kor/values.yaml | jq -S .)
   ```

   处置规则：上游**新增**的权限要确认 kor 是否用到、用到就补进本地表；上游**删除**的权限
   要确认新版本确实不再使用后从本地表删掉（本地表是覆盖，留着旧权限等于扩大 SA 权限面）；
   本地**多出**的项（当前是 `nodes`、`csidrivers`）要确认仍然必要。

2. 对齐版本与 digest。`image.tag` 是 `vX.Y.Z@sha256:...` 形式，只改 tag 不改 digest 会
   拉取失败，两者必须来自同一次查询：

   ```sh
   docker buildx imagetools inspect yonahdissen/kor:<新 appVersion> | head -5
   ```

3. 复核线上实际权限（只读）：

   ```sh
   kubectl auth can-i --list --as=system:serviceaccount:kor:kor | head
   ```

4. 确认覆盖表与 digest 都进了 Deployment（本机首次渲染需先 `helm dependency build system/kor`）：

   ```sh
   helm template kor system/kor | grep -E 'image:|csidrivers|nodes'
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
