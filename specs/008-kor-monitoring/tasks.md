# Tasks: 集群未使用资源审计（kor）

**Input**: Design documents from `specs/008-kor-monitoring/`

**Prerequisites**: plan.md (required), spec.md (required), research.md, quickstart.md

**Organization**: 按交付链路分组，每个任务可独立验证。

## Phase 1: 选型与取证

**Purpose**: 确认上游 chart 的形态与集群侧的前提条件

- [x] T001 读取上游仓库：确认 Helm 仓库 `https://yonahd.github.io/kor`、最新 chart `0.2.16`（appVersion `0.6.9`）
- [x] T002 展开 chart 模板：确认 exporter 与 CronJob 两种模式相互独立，默认只开 exporter；ServiceMonitor 被 `.Capabilities.APIVersions.Has "monitoring.coreos.com/v1"` 门控
- [x] T003 读上游源码 `pkg/kor/exporter.go`：确认指标名 `kubernetes_orphaned_resources`、标签 `kind/namespace/resourceName`、`EXPORTER_INTERVAL` 单位为分钟（默认 10）
- [x] T004 查证 ArgoCD 是否把集群 API 版本透传给 Helm：`controller/state.go` → `argo.APIResourcesToStrings` → `reposerver/repository.go` → `util/helm/cmd.go` 的 `--api-versions`
- [x] T005 确认既有 Prometheus 的发现方式：`serviceMonitorSelectorNilUsesHelmValues: false`，即无需额外标签（对照既有 `rook-ceph`、`argocd`）
- [x] T006 确认 dashboard 落点：Grafana sidecar 的 `searchNamespace` 为 `monitoring-system`

## Phase 2: kor chart

**Purpose**: 让 exporter 在集群内常驻并暴露指标

- [x] T007 新增 `system/kor/Chart.yaml`（依赖上游 `kor 0.2.16`）
- [x] T008 新增 `system/kor/values.yaml`：只启用 `prometheusExporter`，显式关闭 `cronJob`（仓库无 Slack 凭据）
- [x] T009 镜像钉 `v0.6.9` + `imagePullPolicy: IfNotPresent`，替代上游默认的 `latest` + `Always`
- [x] T010 显式声明 `resources.requests/limits`（10m/64Mi、500m/256Mi）
- [x] T011 `exporterInterval` 由默认 10 分钟放宽到 30 分钟（每轮为整集群 LIST）

## Phase 3: Grafana dashboard

**Purpose**: 一屏查看未使用资源的分布

- [x] T012 拉取上游 dashboard 19863，改 datasource 为硬编码 uid `prometheus`，去掉 `${datasource}` 变量
- [x] T013 修正 `kind="$kind"` 为 `kind=~"$kind"`（multi + includeAll 在 All 下的插值问题）
- [x] T014 新增 `system/monitoring-system/files/dashboards/kor.json` 与 `templates/dashboard-kor.yaml`（sidecar ConfigMap，沿用既有标签约定）

## Phase 4: 校验与交付

- [x] T015 `helm dependency update` + `helm lint system/kor` 通过
- [x] T016 `helm template --api-versions monitoring.coreos.com/v1` 渲染出 8 个对象，且**不带**该参数时 ServiceMonitor 消失（双向确认门控）
- [x] T017 `helm template` 渲染 monitoring-system，内嵌 dashboard JSON 可被 `json.loads` 解析
- [x] T018 `yamllint` 通过；确认 `Chart.lock`/`*.tgz` 由既有 `.gitignore` 排除，不误入库
- [x] T019 新增 `specs/008-kor-monitoring/`（spec、plan、research、quickstart、checklist、tasks）并在 `AGENTS.md` 更新当前 Plan
- [x] T020 主题分支 `008-kor-monitoring` + PR 合入 `master`（ApplicationSet 自动发现，无需新增 Application 清单）

## Phase 5: 上线验证与修正

- [x] T021 合并后验证：`kor` Application `Synced/Healthy`，8 个资源全部 Synced，Pod 运行 `yonahdissen/kor:v0.6.9`
- [x] T022 验证 `up{job="kor-exporter"}=1`，且未改动任何 Prometheus 配置
- [x] T023 首扫完成后确认 `kubernetes_orphaned_resources` 为 925 条序列
- [x] T024 验证 Grafana 中 `Kor Dashboard` 已加载（sidecar 写入并 reload 200）
- [x] T025 **发现并修正**：T013 之外，适配时误将上游的 `exported_namespace` 改为 `namespace`。实测 `namespace` 恒为 `kor`（prometheus-operator 目标标签），资源真实命名空间在 `exported_namespace`（41 个取值），遂改回并在模板注释中写明原因
- [x] T026 修正后复验：`sum by(exported_namespace)` 返回 42 组；Grafana 中 dashboard 的 4 条查询均命中线上数据
- [x] T027 按 [quickstart.md](./quickstart.md) 全流程复核：Application、Pod、ServiceMonitor、指标、dashboard、只读 RBAC 六项全部通过
