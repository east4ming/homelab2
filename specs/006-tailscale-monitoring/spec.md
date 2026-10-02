# Feature Specification: Tailscale 指标监控

**Feature Branch**: `006-tailscale-monitoring`

**Created**: 2026-10-02

**Status**: Draft

**Input**: User description: 基于 Tailscale 官方《client metrics》与《Kubernetes Operator》文档，为 homelab 4 台 node（标准 Linux 安装的 tailscaled）与 K8s 集群上由 tailscale-operator 管理的 pod 配置 metrics、Prometheus 采集、Grafana dashboard 与 Prometheus 告警规则。

## User Scenarios & Testing

### User Story 1 - 4 台 node 的 Tailscale 客户端指标被采集 (Priority: P1)

作为 homelab2 运维者，我希望 4 台 node 上原生安装的 `tailscaled` 客户端指标被 Prometheus 自动采集，以便集中查看每台节点的连通性、流量与丢弃包情况。

**Why this priority**: 指标采集是所有告警与可视化的基础；4 台 node 是 tailnet 的骨干（subnet router / 节点自身入口）。

**Independent Test**: Prometheus Targets 页面出现 `tailscale-nodes` job 的 4 个 target 且均为 `UP`，查询 `tailscaled_health_messages` 能返回 4 台 node 的数据。

**Acceptance Scenarios**:

1. **Given** 4 台 node 已安装 Tailscale v1.78+，**When** 部署只读 metrics 端点并配置抓取，**Then** Prometheus 中 4 个 target 全部 `UP`。
2. **Given** 采集已生效，**When** 在 Prometheus 查询 `tailscaled_inbound_bytes_total`，**Then** 每条时间序列带有可读的 `node` 标签（节点名）而不是裸 IP。
3. **Given** metrics 端点仅以只读模式暴露，**When** 访问该端点，**Then** 只能读取指标，不能通过它修改 Tailscale 配置。

---

### User Story 2 - Kubernetes Operator 代理指标被采集 (Priority: P1)

作为 homelab2 运维者，我希望由 tailscale-operator 创建的 ingress 代理 pod 的客户端指标被 Prometheus 采集，以便观察每个 Ingress 背后的 Tailscale 代理状态。

**Why this priority**: 集群内所有对外服务的入口都经由这些代理；没有它们的指标，集群侧 Tailscale 监控就是空白。

**Independent Test**: `tailscale` namespace 中出现 `<proxy>-metrics` Service 与对应 ServiceMonitor，Prometheus Targets 中对应 job 为 `UP`，且指标带 `ts_proxy_type` / `ts_proxy_parent_name` 标签。

**Acceptance Scenarios**:

1. **Given** operator 已安装且支持 ProxyClass metrics，**When** 为 ProxyGroup 指定启用 metrics 的 ProxyClass，**Then** 该 ProxyGroup 的每个代理都有对应 metrics Service / ServiceMonitor。
2. **Given** 采集生效，**When** 查询 `tailscaled_health_messages{ts_proxy_type="proxygroup"}`，**Then** 能按代理组维度查看代理健康状况。
3. **Given** 带 `experimental-forward-cluster-traffic-via-ingress` 注解的 Ingress 代理不支持 metrics（上游限制），**When** 不为其指定 ProxyClass，**Then** 不会产生永远失败的抓取目标与误报 `TargetDown`。

---

### User Story 3 - 告警规则 (Priority: P2)

作为 homelab2 运维者，我希望 Tailscale 抓取中断或客户端报告健康告警时能收到通知，而不是等到用户报障。

**Why this priority**: 告警把采集数据变成可执行信号。

**Independent Test**: Prometheus 中能查询到 Tailscale 相关告警规则；人为停止某节点 metrics 端点后，对应告警在 `for` 时长后进入 `firing`。

**Acceptance Scenarios**:

1. **Given** 告警规则已加载，**When** 某台 node 的 metrics 端点不可用超过阈值时间，**Then** 触发 `TailscaleNodeMetricsDown`。
2. **Given** 客户端上报 `type="warning"` 的健康信息持续存在，**When** 规则评估，**Then** 触发 `TailscaleNodeHealthMessages`。
3. **Given** 告警恢复，**When** 规则重新评估，**Then** 告警自动 `resolved`。

---

### User Story 4 - Grafana dashboard (Priority: P3)

作为 homelab2 运维者，我希望在 Grafana 中一屏看到节点与代理的 Tailscale 健康与流量。

**Why this priority**: 可视化用于快速定位与日常巡检，依赖 P1 的采集。

**Independent Test**: Grafana 中出现 `Tailscale` dashboard，节点变量可选 4 台 node 且面板有数据。

**Acceptance Scenarios**:

1. **Given** dashboard ConfigMap 已部署，**When** 打开 Grafana，**Then** 能在 `Tailscale` 目录下看到 dashboard。
2. **Given** dashboard 已打开，**When** 选择节点，**Then** 展示健康消息、上下行流量、丢弃包与路由数量。
3. **Given** 代理指标已采集，**When** 切换到代理面板，**Then** 按 `ts_proxy_parent_name` 展示代理健康与流量。

### Edge Cases

- 某台 node 关机或 `tailscale-metrics.service` 停止：target 变为 `DOWN`，由既有 `TargetDown` 规则告警；历史指标按 Prometheus 保留策略过期。
- 节点 LAN IP 变更：需要同步更新 inventory 与 Prometheus 抓取目标（两者都在 Git 中）。
- 节点上 Tailscale 版本低于 v1.78：端点不存在，target `DOWN`；本环境 4 台均为 1.102.4。
- 指定 ProxyClass 后：相关代理滚动重启，入口有秒级中断。
- 新增使用 `ingress-proxies` ProxyGroup 的 Ingress：自动继承该 ProxyGroup 的 ProxyClass，无需额外配置即可被采集。
- 新增带 `experimental-forward-cluster-traffic-via-ingress` 注解的独立 Ingress：其代理不支持 metrics，不会被采集（上游限制）。

## Requirements

### Functional Requirements

- **FR-001**: 系统 MUST 在 4 台 node 上以 systemd 服务方式暴露 Tailscale 客户端指标，且 MUST 为只读模式（`tailscale web --readonly`），不得暴露可写控制界面。
- **FR-002**: 系统 MUST 只监听在节点 LAN IP 的 5252 端口，不监听 `0.0.0.0`。
- **FR-003**: Prometheus MUST 抓取 4 台 node 的客户端指标，并为每条序列附加 `node` 标签（节点名）。
- **FR-004**: 系统 MUST 通过 ProxyClass 启用 Kubernetes Operator 代理的 metrics 与 Prometheus ServiceMonitor 创建。
- **FR-005**: 系统 MUST 通过 ProxyGroup 的 `spec.proxyClass` 把启用 metrics 的 ProxyClass 应用到 ingress 与 egress ProxyGroup；对于上游不支持 metrics 的代理（独立 egress 代理、带 `experimental-forward-cluster-traffic-via-ingress` 注解的 Ingress 代理），MUST NOT 产生抓取目标。
- **FR-006**: 系统 MUST 提供 PrometheusRule，覆盖客户端健康消息与异常丢包；抓取中断 MUST 复用既有 `TargetDown` / `KubePodNotReady` 规则而不重复定义。
- **FR-007**: 系统 MUST 通过 Grafana sidecar 提供 Tailscale dashboard，覆盖节点与代理两个维度。
- **FR-008**: 所有新增 K8s 资源 MUST 通过 Git 管理：`system/monitoring-system` 走 ArgoCD，tailscale namespace 下的 CR 走 `metal/roles/tailscale`（沿用 operator 现有 Ansible 管理方式）。
- **FR-009**: 系统 MUST NOT 修改 egress 代理行为（上游不支持其 metrics）。

### Key Entities

- **tailscale-metrics.service**: 节点侧 systemd 服务，运行 `tailscale web --readonly --listen <node-ip>:5252`。
- **tailscale-nodes scrape job**: Prometheus 附加抓取配置，静态目标为 4 台 node 的 LAN IP。
- **ProxyClass `tailscale-metrics`**: 启用 `spec.metrics.enable` 与 `spec.metrics.serviceMonitor.enable` 的 ProxyClass，由两个 ProxyGroup 通过 `spec.proxyClass` 引用。
- **metrics Service / ServiceMonitor**: operator 为每个使用该 ProxyClass 的代理创建（`<sts>-metrics`，端口 9002）。
- **PrometheusRule `tailscale`**: 告警规则集合。
- **Grafana dashboard `tailscale`**: sidecar 加载的 dashboard ConfigMap。

## Success Criteria

### Measurable Outcomes

- **SC-001**: Prometheus Targets 中 tailscale 相关 job 全部 `UP`：4 个节点 target + 8 个 ProxyGroup 代理 target（ingress 与 egress 各 4），且没有 `up == 0` 的 Tailscale target。
- **SC-002**: Prometheus 中至少加载 3 条 Tailscale 告警规则，且不产生持续 pending/firing 的误报。
- **SC-003**: Grafana 中出现 `Tailscale` dashboard，节点与代理面板均能查询到数据。
- **SC-004**: 节点 5252 端口只读：写操作不可用，且端口未监听 `0.0.0.0`。
- **SC-005**: Git 之外的任何手工 `kubectl apply` 都不是必需的：重新同步 ArgoCD 与重跑 Ansible 即可复现全部配置。

## Assumptions

- 4 台 node 的 Tailscale 版本 ≥ 1.78（实测 1.102.4），`tailscale web --readonly` 可用。
- 集群内 Prometheus 能直连节点 LAN IP（node-exporter 已按同样方式采集，实测 pod 可访问 `192.168.3.226:5252`）。
- tailscale-operator v1.102.4（Helm chart `tailscale-operator` 1.102.4）已安装，CRD 支持 ProxyClass `metrics`。
- 8 个带 `experimental-forward-cluster-traffic-via-ingress` 注解的独立 Ingress 代理不支持 metrics（上游限制），因此不纳入采集范围。
- Grafana.com 上没有基于 `tailscaled_*` 客户端指标、可直接导入的 dashboard（现有 Tailscale dashboard 24177/24178 依赖 API 型 `tailscale-exporter` 指标），因此 dashboard 在本仓库内维护。
- Ansible inventory 中 tailscale OAuth 凭据为占位值，因此本次部署不覆盖 operator release 的现有凭据（见 research.md）。
