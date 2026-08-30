# Feature Specification: Disk SMART 监控

**Feature Branch**: `005-smartctl-monitoring`

**Created**: 2026-08-30

**Status**: Approved

**Input**: User description: 为 homelab2 k8s 集群的 4 台 node 增加 disk SMART 监控。

## User Scenarios & Testing

### User Story 1 - 4 节点 SMART 指标采集 (Priority: P1)

作为 homelab2 运维者，我希望 4 台 node 的 SMART 指标被 Prometheus 自动采集，以便集中查看磁盘健康状态。

**Why this priority**: 指标采集是所有监控、告警和可视化的基础。

**Independent Test**: 在 `monitoring-system` namespace 中部署 DaemonSet 后，4 个节点都有 exporter Pod 运行，且 Prometheus Target 中对应 job 为 `UP`。

**Acceptance Scenarios**:

1. **Given** 集群有 4 台 node，**When** `prometheus-smartctl-exporter` DaemonSet 部署完成，**Then** 4 个节点各有一个 exporter Pod 处于 `Running`。
2. **Given** exporter 已运行，**When** Prometheus 抓取 `/metrics`，**Then** 能看到 `smartctl_device`、`smartctl_device_temperature`、`smartctl_device_smart_status` 等指标。
3. **Given** 监控系统使用 ArgoCD 管理，**When** 配置提交到 Git，**Then** 所有监控资源通过 GitOps 自动同步，无需手工 `kubectl apply`。

---

### User Story 2 - SMART 告警规则 (Priority: P2)

作为 homelab2 运维者，我希望磁盘出现健康异常、温度过高或控制器警告时能收到告警。

**Why this priority**: 告警是主动发现磁盘故障的关键。

**Independent Test**: 启用 `prometheus-smartctl-exporter` 内置 PrometheusRule 后，Prometheus 中能看到 SmartCTL 告警规则，且 Alertmanager 能接收触发事件。

**Acceptance Scenarios**:

1. **Given** PrometheusRule 已加载，**When** 磁盘 SMART 状态异常或温度超过阈值，**Then** 对应 Alertmanager 告警被触发。
2. **Given** 磁盘状态恢复正常，**When** 规则重新评估，**Then** 告警自动恢复。

---

### User Story 3 - Grafana Dashboard (Priority: P3)

作为 homelab2 运维者，我希望在 Grafana 中直接查看 4 台 node 的磁盘 SMART 概览。

**Why this priority**: 可视化能帮助快速定位磁盘异常。

**Independent Test**: Grafana sidecar 自动加载 `smartctl-exporter-dashboard` ConfigMap 后，仪表盘出现在 Grafana 中并展示 SMART 数据。

**Acceptance Scenarios**:

1. **Given** dashboard ConfigMap 已部署到 `monitoring-system`，**When** 打开 Grafana，**Then** 能看到 `SMARTctl Exporter Dashboard`。
2. **Given** dashboard 已打开，**When** 选择节点/磁盘，**Then** 能展示温度、SMART 状态、介质错误、寿命等指标。

### Edge Cases

- 某台 node 临时不可达时，DaemonSet Pod 会处于 `Pending`/`NotReady`，Prometheus target 会变为 `DOWN`，已有 SMART 指标会过期；依赖 `up` 和告警规则观察。
- 节点磁盘被替换后，旧 `device` 指标会消失，新磁盘自动被 exporter 扫描。
- 若集群没有 `unrestricted-psp` ClusterRole，关闭 chart 默认 RBAC 可避免同步失败。

## Requirements

### Functional Requirements

- **FR-001**: 系统 MUST 在 4 台 node 上运行 `prometheus-smartctl-exporter` 特权 DaemonSet。
- **FR-002**: 系统 MUST 通过 ServiceMonitor 让 Prometheus 自动抓取 exporter 指标。
- **FR-003**: 系统 MUST 包含 SMART 健康、温度、介质错误、控制器警告等告警规则。
- **FR-004**: 系统 MUST 通过 Grafana sidecar 提供 SMART dashboard。
- **FR-005**: 所有新增 Kubernetes 资源 MUST 通过 ArgoCD/GitOps 管理。

### Key Entities

- **smartctl-exporter DaemonSet**: 每节点一个 exporter Pod，以 privileged 容器读取宿主 `/dev`。
- **ServiceMonitor**: 定义 Prometheus 抓取 smartctl-exporter 的端口、路径和频率。
- **PrometheusRule**: 定义 SMART 相关告警。
- **Grafana Dashboard ConfigMap**: 由 Grafana sidecar 自动加载。

## Success Criteria

### Measurable Outcomes

- **SC-001**: 4 台 node 的 smartctl-exporter Pod 全部 `Running`。
- **SC-002**: Prometheus 中 smartctl-exporter 抓取目标为 `UP`。
- **SC-003**: Prometheus 中至少加载 6 条 SmartCTL 告警规则。
- **SC-004**: Grafana 中出现 `SMARTctl Exporter Dashboard`，并能查询到 `smartctl_device` 指标。

## Assumptions

- 集群为当前 homelab2 单集群，共 4 台 node，均可通过 SSH 访问。
- 使用官方 Helm chart `prometheus-community/prometheus-smartctl-exporter` 作为 `system/monitoring-system` 的 subchart。
- 使用 Grafana dashboard 22604（`SMARTctl Exporter Dashboard`）。
- 告警阈值采用 chart 内置默认值。
