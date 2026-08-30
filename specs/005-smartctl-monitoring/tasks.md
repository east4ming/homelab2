# Tasks: Disk SMART 监控

**Input**: Design documents from `specs/005-smartctl-monitoring/`

**Prerequisites**: plan.md (required), spec.md (required), research.md, quickstart.md

**Organization**: 按部署链路分组，每个任务可独立验证。

## Phase 1: 宿主机准备

**Purpose**: 确保 4 台 node 有 `smartctl` 命令

- [x] T001 在 `metal/roles/prerequisites/tasks/main.yml` 的 Ubuntu 依赖包中加入 `smartmontools`

## Phase 2: Helm subchart 接入

**Purpose**: 将官方 smartctl-exporter chart 接入现有监控栈

- [x] T002 在 `system/monitoring-system/Chart.yaml` 添加 `prometheus-smartctl-exporter` 0.17.1 依赖
- [x] T003 在 `system/monitoring-system/values.yaml` 添加 subchart values：启用 ServiceMonitor、PrometheusRules、关闭多余 RBAC、设置端口/容忍/资源

## Phase 3: Grafana Dashboard

**Purpose**: 提供可视化界面

- [x] T004 下载并规范化官方 dashboard 22604 到 `system/monitoring-system/files/dashboards/smartctl-exporter-dashboard.json`
- [x] T005 创建 `system/monitoring-system/templates/dashboard-smartctl.yaml` ConfigMap，供 Grafana sidecar 加载

## Phase 4: 文档与流程

**Purpose**: 按 spec-kit 完成 feature 文档

- [x] T006 创建 `specs/005-smartctl-monitoring/spec.md`
- [x] T007 创建 `specs/005-smartctl-monitoring/plan.md`
- [x] T008 创建 `specs/005-smartctl-monitoring/tasks.md`
- [x] T009 创建 `specs/005-smartctl-monitoring/research.md`
- [x] T010 创建 `specs/005-smartctl-monitoring/quickstart.md`
- [x] T011 创建 `specs/005-smartctl-monitoring/checklists/requirements.md`

## Phase 5: 校验与交付

**Purpose**: 确保改动可渲染、可部署、可验证

- [x] T012 运行 `helm template` 验证 subchart 与 dashboard 渲染
- [x] T013 运行可用的静态检查（`yamllint` / `helm lint` / `helm template`）
- [x] T014 更新 `.specify/feature.json` 与 `CLAUDE.md` 指向 005
- [ ] T015 提交并推送 feature branch
