# Tasks: Tailscale 指标监控

**Input**: Design documents from `specs/006-tailscale-monitoring/`

**Prerequisites**: plan.md (required), spec.md (required), research.md, quickstart.md

**Organization**: 按部署链路分组，每个任务可独立验证。

## Phase 1: 节点侧只读 metrics 端点

**Purpose**: 让 4 台 node 暴露 `tailscaled_*` 客户端指标

- [ ] T001 新增 `metal/roles/prerequisites/templates/tailscale-metrics.service.j2`（`tailscale web --readonly --listen <node-ip>:5252`）
- [ ] T002 在 `metal/roles/prerequisites/tasks/main.yml` 增加部署并启用该服务的任务
- [ ] T003 部署后验证：4 台 node `ss -tlnp` 显示 `5252` 且仅绑定 LAN IP；`curl :5252/metrics` 返回 200

## Phase 2: Prometheus 采集

**Purpose**: 抓取节点与代理指标

- [ ] T004 在 `system/monitoring-system/values.yaml` 增加 `additionalScrapeConfigs`（job `tailscale-nodes`，4 个静态 target，附加 `node` 标签）
- [ ] T005 ArgoCD 同步后验证：Prometheus Targets 中 4 个 target `UP`，`up{job="tailscale-nodes"} == 1`

## Phase 3: Operator 代理 metrics

**Purpose**: 让 operator 为 ingress 代理创建 metrics Service 与 ServiceMonitor

- [ ] T006 在 `metal/roles/tailscale/templates/proxyclass.yaml` 增加 `tailscale-metrics` ProxyClass
- [ ] T007 在 `metal/roles/tailscale/defaults/main.yml` 设置 `proxyConfig.defaultProxyClass`
- [ ] T008 为 `metal/cluster.yml` / role 任务打 tag，使 CR 可单独 apply（不触发 helm upgrade）
- [ ] T009 部署后验证：`tailscale` namespace 出现 `<proxy>-metrics` Service 与 ServiceMonitor；targets `UP`

## Phase 4: 告警规则

**Purpose**: 把指标变成可执行信号

- [ ] T010 新增 `system/monitoring-system/templates/prometheusrule-tailscale.yaml`（抓取中断 + 健康消息 + 代理中断）
- [ ] T011 ArgoCD 同步后验证：Prometheus rules API 中能查到对应告警名

## Phase 5: Grafana dashboard

**Purpose**: 节点与代理两个维度的可视化

- [ ] T012 新增 `system/monitoring-system/files/dashboards/tailscale.json`
- [ ] T013 新增 `system/monitoring-system/templates/dashboard-tailscale.yaml`（sidecar ConfigMap）
- [ ] T014 验证：Grafana 中出现 `Tailscale` dashboard，面板查询有数据

## Phase 6: 文档与流程

**Purpose**: 按 spec-kit 完成 feature 文档

- [ ] T015 创建 `specs/006-tailscale-monitoring/spec.md`
- [ ] T016 创建 `specs/006-tailscale-monitoring/plan.md`
- [ ] T017 创建 `specs/006-tailscale-monitoring/research.md`
- [ ] T018 创建 `specs/006-tailscale-monitoring/tasks.md`
- [ ] T019 创建 `specs/006-tailscale-monitoring/quickstart.md`
- [ ] T020 创建 `specs/006-tailscale-monitoring/checklists/requirements.md`
- [ ] T021 更新 `.specify/feature.json` 与 `AGENTS.md` 指向 006

## Phase 7: 校验与交付

**Purpose**: 确保改动可渲染、可部署、可验证

- [ ] T022 运行 `helm template system/monitoring-system` 验证渲染（含 dashboard JSON 与 PrometheusRule）
- [ ] T023 运行静态检查（`yamllint` / `pre-commit`）
- [ ] T024 端到端验证（见 quickstart.md）
- [ ] T025 提交 feature branch
