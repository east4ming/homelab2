# Feature Specification: 集群未使用资源审计（kor）

**Feature Branch**: `008-kor-monitoring`

**Created**: 2026-10-03

**Status**: Draft

**Input**: User description: 使用 GitOps/ArgoCD 方式安装 https://github.com/yonahd/kor，要求 follow AGENTS.md 与 docs/reference/versioning.md 的要求和约束。

## User Scenarios & Testing

### User Story 1 - 未使用资源以 Prometheus 指标暴露 (Priority: P1)

作为 homelab2 运维者，我希望集群里「没有任何工作负载引用」的资源（ConfigMap、Secret、Service、PVC、ClusterRole、CRD 等）被持续扫描并暴露成指标，以便在资源紧张的 4 节点 N100 集群上发现可以清理的对象，而不是逐个 namespace 翻阅。

**Why this priority**: 采集是所有后续价值（可视化、清理决策）的前提；集群已连续运行 678 天，历史遗留对象只会越积越多。

**Independent Test**: 部署后查询 `kubernetes_orphaned_resources` 返回非空序列集，且每条序列带 `kind` 与资源所在命名空间。

**Acceptance Scenarios**:

1. **Given** exporter 已部署并完成首次扫描，**When** 查询 `kubernetes_orphaned_resources`，**Then** 返回数百条序列，覆盖多个 `kind`（实测 925 条）。
2. **Given** exporter 常驻运行，**When** 等待一个扫描周期，**Then** 指标按周期刷新，不需要人工触发。
3. **Given** 有人给某个资源打上 `kor/used=true`，**When** 下一个扫描周期结束，**Then** 该资源从指标中消失（视作已使用）。
4. **Given** exporter 只有只读权限，**When** 查询其 RBAC，**Then** 动词只有 `get`/`list`/`watch`，**不含** `delete`/`update`/`patch`——本特性不自动删除任何资源。

---

### User Story 2 - Prometheus 自动抓取，无需人工登记 (Priority: P1)

作为 homelab2 运维者，我希望新部署的 exporter 被既有 Prometheus 自动发现并抓取，不需要在 Prometheus 配置里逐条登记 target 或加标签。

**Why this priority**: 否则每次新增 exporter 都要改 central 配置，违背本仓库「ApplicationSet 自动发现」的既有契约。

**Independent Test**: 部署后 Prometheus 中出现 `up{job="kor-exporter"} = 1`，且无需修改任何 Prometheus 配置。

**Acceptance Scenarios**:

1. **Given** 集群内已存在 `monitoring.coreos.com/v1` CRD，**When** ArgoCD 渲染并同步本特性，**Then** 集群中出现 `ServiceMonitor/kor-exporter`。
2. **Given** ServiceMonitor 已下发，**When** 查询 `up{job="kor-exporter"}`，**Then** 其值为 `1`（实测上线后即成立）。
3. **Given** 目标集群不存在 ServiceMonitor CRD，**When** 渲染同一份 chart，**Then** 不产出该对象且同步不报错（门控生效）。

---

### User Story 3 - Grafana 一屏总览并可筛选 (Priority: P2)

作为 homelab2 运维者，我希望在 Grafana 里一眼看到未使用资源的总量、按 namespace 与按 kind 的分布，并能按 namespace/类型筛选。

**Why this priority**: 可视化让「哪些 namespace 该清理」变成可执行的判断；依赖 P1 的指标。

**Independent Test**: Grafana 中出现 `Kor Dashboard`，面板有数据，且 namespace 变量能列出多个真实命名空间。

**Acceptance Scenarios**:

1. **Given** dashboard ConfigMap 已部署，**When** 打开 Grafana，**Then** 能搜索到 `Kor Dashboard`。
2. **Given** dashboard 已打开，**When** 查看面板，**Then** 总量、按 namespace 汇总、按 kind 分布均有数据。
3. **Given** namespace 筛选变量，**When** 展开其取值列表，**Then** 列出的是**被审计资源所在的**命名空间（实测 41 个），而不是 exporter 自己所在的 `kor`。
4. **Given** 面板查询里出现 `namespace` 与 `exported_namespace` 两个标签，**When** 需要按资源所属命名空间过滤，**Then** 必须使用 `exported_namespace`（见 research.md 第 5 节）。

### Edge Cases

- **首次扫描耗时**：kor 需要对集群做全量 LIST，首次扫描实测约 3 分钟；在此之前 `/metrics` 只有 Go 运行时指标，面板显示「No data」属正常。
- **命名空间标签冲突**：prometheus-operator 会给所有 series 加目标标签 `namespace`，导致指标自带的同名标签被重命名为 `exported_namespace`。任何按命名空间过滤的查询若用 `namespace`，结果恒等于 `kor`（静默失效，不报错）。
- **只有只读权限**：kor 的 `--delete` / `--no-interactive` 能力在本特性中**不可用也不应启用**；清理动作由人确认后手工执行。
- **已知假阳性**：上游 README 明确列出秘密/ConfigMap 被 CRD、动态加载配置引用时会被误判为未使用。本特性定位是「提供线索」，不做自动处置。
- **无通知通道**：仓库内没有 Slack 凭据，因此 CronJob 模式（把报告发到 Slack/频道）不具备条件，只启用 exporter 模式。
- **资源开销**：每轮扫描是整集群 LIST，间隔过短会给 apiserver 带来无谓压力；间隔在 values 中显式指定。
- **dashboard 归属**：Grafana sidecar 只搜索 `monitoring-system` namespace，dashboard ConfigMap 必须放在那里，不能跟随 kor 自己的目录。

## Requirements

### Functional Requirements

- **FR-001**: 系统 MUST 在集群内以常驻工作负载运行 kor exporter，监听 `8080` 暴露 `/metrics`。
- **FR-002**: exporter MUST NOT 使用 `latest` 镜像标签；MUST 钉住与所依赖 chart 的 `appVersion` 对应的明确版本。
- **FR-003**: exporter 工作负载 MUST 显式声明 `resources.requests` 与 `resources.limits`。
- **FR-004**: 系统 MUST 通过 `ServiceMonitor` 接入既有 Prometheus，MUST NOT 需要额外的标签约定或人工登记 target。
- **FR-005**: 系统 MUST NOT 依赖集群上不存在的 CRD；当 `monitoring.coreos.com/v1` 缺失时 MUST 静默跳过 ServiceMonitor 而不是同步失败。
- **FR-006**: 扫描间隔 MUST 可通过 values 配置，且取值 MUST 与整集群 LIST 的开销相称。
- **FR-007**: 指标 MUST 至少包含资源类型（`kind`）与资源名（`resourceName`），并可区分被审计资源所属的命名空间。
- **FR-008**: 系统 MUST 提供 Grafana dashboard，覆盖未使用资源总量、按 namespace 汇总、按 kind 分布。
- **FR-009**: dashboard 中按命名空间过滤的查询 MUST 使用线上实际存在的标签名，面板 MUST NOT 依赖「看起来对但恒为单值」的标签。
- **FR-010**: 所有集群侧资源（Deployment、Service、ServiceMonitor、RBAC、dashboard）MUST 通过 Git 管理并由 ArgoCD 交付；MUST NOT 手工 `kubectl apply`。
- **FR-011**: exporter 的 RBAC MUST 只授予只读动词（`get`/`list`/`watch`），MUST NOT 授予任何写动词。
- **FR-012**: 仓库中 MUST NOT 提交任何凭据（Slack token、webhook URL 等）；依赖凭据的通知能力 MUST 保持关闭。

### Key Entities

- **`system/kor`（Helm chart 包装）**: 依赖上游 `kor` chart 的本地 chart，`Chart.yaml` + `values.yaml` 两个文件，由 ApplicationSet 从 `system/*` 自动发现。
- **kor Application**: ArgoCD Application，namespace `kor`（由 ApplicationSet 的 `path.basename` 决定）。
- **`kor-exporter` Deployment / Service / ServiceMonitor**: exporter 本体与抓取入口。
- **`kor-read-resources-*` Role/ClusterRole 及绑定**: 只读 RBAC，由 chart 生成。
- **Grafana dashboard `Kor Dashboard`**: `monitoring-system` 中的 ConfigMap，由 sidecar 加载。

## Success Criteria

### Measurable Outcomes

- **SC-001**: ArgoCD 中 `kor` Application 为 `Synced`/`Healthy`，其全部资源均为 `Synced`。
- **SC-002**: `up{job="kor-exporter"} = 1`，且不需要任何 Prometheus 配置改动。
- **SC-003**: `kubernetes_orphaned_resources` 返回非空序列集（实测首次扫描后 925 条）。
- **SC-004**: `sum by(exported_namespace) (kubernetes_orphaned_resources{...})` 返回 >1 个分组（实测 42 组：41 个命名空间 + 无命名空间标签的非命名空间资源）。
- **SC-005**: Grafana 中存在 `Kor Dashboard`（uid `Zrue32P7Ik`），4 个内容面板均有数据。
- **SC-006**: `kor-read-resources-*` 的 verbs 集合 ⊆ {get, list, watch}。
- **SC-007**: 从 `master` 合入到 exporter 就绪全程无需人工介入（实测约 5 分钟；ApplicationSet 轮询间隔 600s）。

## Assumptions

- 上游提供可用的 Helm 仓库（`https://yonahd.github.io/kor`）与容器镜像（`yonahdissen/kor`）；本特性不构建自有镜像。
- 集群已安装 `monitoring.coreos.com/v1`（kube-prometheus-stack 自带），因此 ServiceMonitor 可用。
- 既有 Prometheus 的 `serviceMonitorSelectorNilUsesHelmValues=false`，即按 ns 无关的方式发现所有 ServiceMonitor——这正是 `rook-ceph`、`argocd` 等既有 exporter 的接入方式。
- Grafana 的 dashboard sidecar 作用域是 `monitoring-system`，且以 `grafana_dashboard: "1"` 标签识别 ConfigMap。
- ArgoCD 会把目标集群的 API 版本透传给 Helm 渲染，因此 chart 内的 `.Capabilities.APIVersions.Has` 门控能反映真实集群能力。
- kor 的资源判定存在上游已知的假阳性；本特性只提供只读信号，清理动作由人工决策。
- 扫描周期内允许指标短暂陈旧（默认 30 分钟），这是用 apiserver 压力换取新鲜度的取舍。
- 仓库无 Slack 凭据，故不启用 CronJob 通知模式。
