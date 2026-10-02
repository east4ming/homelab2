# Tasks: Tailscale 指标监控

**Input**: Design documents from `specs/006-tailscale-monitoring/`

**Prerequisites**: plan.md (required), spec.md (required), research.md, quickstart.md

**Organization**: 按部署链路分组，每个任务可独立验证。

## Phase 1: 节点侧只读 metrics 端点

**Purpose**: 让 4 台 node 暴露 `tailscaled_*` 客户端指标

- [x] T001 新增 `metal/roles/prerequisites/templates/tailscale-metrics.service.j2`（`tailscale web --readonly --listen <node-ip>:5252`）
- [x] T002 在 `metal/roles/prerequisites/tasks/main.yml` 增加部署并启用该服务的任务（tag `tailscale`）
- [x] T003 部署后验证：4 台 node 均 `active`、`ss -tln` 仅绑定 LAN IP、`GET :5252/metrics` 返回 200（27 条 `tailscaled_*`）

## Phase 2: Prometheus 采集

**Purpose**: 抓取节点与代理指标

- [x] T004 在 `system/monitoring-system/values.yaml` 增加 `additionalScrapeConfigs`（job `tailscale-nodes`，4 个静态 target，附加 `node` 标签）
- [x] T005 ArgoCD 同步后验证：`up{job="tailscale-nodes"}` 4 个 target 全为 1

## Phase 3: Operator 代理 metrics

**Purpose**: 让 operator 为 ProxyGroup 代理创建 metrics Service 与 ServiceMonitor

- [x] T006 在 `metal/roles/tailscale/templates/proxyclass.yaml` 增加 `tailscale-metrics` ProxyClass
- [x] T007 在 `metal/roles/tailscale/templates/proxygroup.yaml` 为 ingress/egress ProxyGroup 设置 `spec.proxyClass`
- [x] T008 为 `metal/roles/tailscale/tasks/main.yml` 的 CR 任务加 `tailscale-cr` tag，使 CR 可单独 apply（不触发 helm upgrade）
- [x] T009 部署后验证：8 个 `ts_proxygroup_*` target 全为 1；8 个不支持 metrics 的独立 Ingress 代理没有 target
- [x] T009a 否决默认 ProxyClass 方案（会产生 8 个永久失败 target 与误报 `TargetDown`），并在 research.md 记录取证

## Phase 4: 告警规则

**Purpose**: 把指标变成可执行信号

- [x] T010 新增 `system/monitoring-system/templates/prometheusrule-tailscale.yaml`（健康消息、异常丢包、代理健康消息）
- [x] T011 ArgoCD 同步后验证：3 条规则 `inactive`，无持续 pending/firing

## Phase 5: Grafana dashboard

**Purpose**: 节点与代理两个维度的可视化

- [x] T012 新增 `system/monitoring-system/files/dashboards/tailscale.json`（14 个面板：节点与代理的状态、吞吐、丢包、健康、路由、DERP）
- [x] T013 新增 `system/monitoring-system/templates/dashboard-tailscale.yaml`（sidecar ConfigMap，folder `Tailscale`）
- [x] T014 验证：Grafana 中出现 `Tailscale` dashboard（uid `tailscale`），面板查询均返回数据

## Phase 6: 文档与流程

**Purpose**: 按 spec-kit 完成 feature 文档

- [x] T015 创建 `specs/006-tailscale-monitoring/spec.md`
- [x] T016 创建 `specs/006-tailscale-monitoring/plan.md`
- [x] T017 创建 `specs/006-tailscale-monitoring/research.md`
- [x] T018 创建 `specs/006-tailscale-monitoring/tasks.md`
- [x] T019 创建 `specs/006-tailscale-monitoring/quickstart.md`
- [x] T020 创建 `specs/006-tailscale-monitoring/checklists/requirements.md`
- [x] T021 更新 `.specify/feature.json` 与 `AGENTS.md` 指向 006

## Phase 7: 校验与交付

**Purpose**: 确保改动可渲染、可部署、可验证

- [x] T022 `helm template system/monitoring-system` 渲染通过（ConfigMap / PrometheusRule / additionalScrapeConfigs Secret）
- [x] T023 静态检查：`yamllint -c .yamllint.yaml` 通过
- [x] T024 端到端验证（见 quickstart.md）：4+8 个 target UP、3 条规则加载、dashboard 可见、5252 只读且不对 tailnet 暴露
- [x] T025 提交并推送 feature branch，创建 PR
