# Implementation Plan: Disk SMART 监控

**Branch**: `005-smartctl-monitoring` | **Date**: 2026-08-30 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/005-smartctl-monitoring/spec.md`

## Summary

为 homelab2 的 4 台 node 增加磁盘 SMART 监控：通过 Ansible 安装 `smartmontools`，将 `prometheus-community/prometheus-smartctl-exporter` Helm chart 作为 subchart 加入 `system/monitoring-system/`，启用 ServiceMonitor 与内置 PrometheusRule，并通过 Grafana sidecar 加载官方 SMART dashboard。

## Technical Context

**Language/Version**: YAML / Helm / Ansible

**Primary Dependencies**: `prometheus-smartctl-exporter` Helm chart `0.17.1`（exporter `v0.14.0`），`smartmontools`

**Storage**: N/A

**Testing**: `helm template` 渲染校验、`pre-commit` / `yamllint` / `helmlint`、集群部署后人工验证

**Target Platform**: K3s / Ubuntu 24.04，4 节点（3 master + 1 worker）

**Project Type**: GitOps 基础设施变更

**Performance Goals**: exporter 资源占用极小（requests 5m/32Mi，limits 64Mi）

**Constraints**: 必须使用官方 subchart；所有资源通过 ArgoCD 管理；不额外增加 exporter down 告警

**Scale/Scope**: 4 节点、单集群

## Constitution Check

| Principle | Status | Notes |
|-----------|--------|-------|
| I. 代码质量 | ✅ PASS | YAML/Helm/Ansible 改动，通过 pre-commit 校验 |
| II. 测试标准 | ✅ PASS | 通过 helm template 和部署后验证清单确认 |
| III. 用户体验一致性 | ✅ PASS | 沿用现有 monitoring-system 与 Grafana sidecar 模式 |
| IV. 性能要求 | ✅ PASS | DaemonSet 资源限制 64Mi |
| V. 中文优先 | ✅ PASS | 文档、注释、提交信息使用中文 |
| 安全与合规 - Secret | ✅ PASS | 不涉及 secret |
| 开发与部署工作流 - GitOps | ✅ PASS | 所有 K8s 资源通过 ArgoCD 同步 |

## Project Structure

### Documentation (this feature)

```text
specs/005-smartctl-monitoring/
├── spec.md              # Feature spec
├── plan.md              # This file
├── research.md          # 调研结论
├── quickstart.md        # 部署验证指南
├── checklists/
│   └── requirements.md  # Spec 质量检查
└── tasks.md             # 实施任务
```

### Source Code (repository root)

```text
metal/roles/prerequisites/tasks/main.yml                 # 安装 smartmontools
system/monitoring-system/Chart.yaml                      # 添加 subchart 依赖
system/monitoring-system/values.yaml                     # smartctl-exporter 配置
system/monitoring-system/files/dashboards/
└── smartctl-exporter-dashboard.json                     # 官方 dashboard 22604
system/monitoring-system/templates/dashboard-smartctl.yaml # Grafana ConfigMap
system/monitoring-system/templates/smartctl-wrapper.yaml   # smartctl wrapper ConfigMap
system/monitoring-system/charts/prometheus-smartctl-exporter/  # 本地化 subchart（扩展 extraVolumes/extraVolumeMounts）
```

**Structure Decision**: 将 exporter 作为 `system/monitoring-system` 的 subchart，与现有 kube-prometheus-stack 同 namespace，复用 Prometheus、Alertmanager、Grafana sidecar 和 ArgoCD 自动发现。

## Complexity Tracking

无违规项。
