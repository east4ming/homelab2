# Implementation Plan: Tailscale 指标监控

**Branch**: `006-tailscale-monitoring` | **Date**: 2026-10-02 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/006-tailscale-monitoring/spec.md`

## Summary

为 homelab2 的 4 台 node 与 tailscale-operator 的 ProxyGroup 代理补齐指标监控：

1. 节点侧：Ansible 部署 `tailscale-metrics.service`（`tailscale web --readonly --listen <node-ip>:5252`），Prometheus 通过 `additionalScrapeConfigs` 静态抓取 4 台节点，并附加 `node` 标签。
2. 集群侧：新增 `tailscale-metrics` ProxyClass（metrics + ServiceMonitor），由 `ingress-proxies` / `egress-proxies` 两个 ProxyGroup 通过 `spec.proxyClass` 引用，共 8 个 target。
3. 告警：`system/monitoring-system/templates/prometheusrule-tailscale.yaml` 提供 3 条规则；抓取中断复用既有 `TargetDown` / `KubePodNotReady`。
4. 可视化：`system/monitoring-system/files/dashboards/tailscale.json` + sidecar ConfigMap。

## Technical Context

**Language/Version**: YAML / Helm / Ansible / systemd / PromQL

**Primary Dependencies**: tailscale 1.102.4（客户端与 operator），kube-prometheus-stack 91.5.2，Grafana sidecar

**Storage**: Prometheus 30Gi PVC（既有）

**Testing**: `helm template` 渲染校验、`ansible-playbook --check`、部署后 Prometheus/Grafana API 验证

**Target Platform**: K3s v1.36.5，4 节点（3 master + 1 worker），Ubuntu 26.04.1

**Project Type**: GitOps 基础设施变更

**Performance Goals**: 节点侧新增 4 个只读 HTTP 进程（`tailscale web --readonly`，内存占用极小）；Prometheus 新增 16 个 target，抓取间隔 60s

**Constraints**: 只读暴露；不覆盖 operator release 现有 OAuth 凭据；不修改 egress 代理

**Scale/Scope**: 4 节点、12 个 ingress 代理、单集群

## Constitution Check

| Principle | Status | Notes |
|-----------|--------|-------|
| I. 代码质量 | ✅ PASS | YAML/JSON/Ansible 改动，通过 pre-commit（yamllint 等） |
| II. 测试标准 | ✅ PASS | `helm template` + Prometheus/Grafana API 端到端验证（见 quickstart） |
| III. 用户体验一致性 | ✅ PASS | 沿用 monitoring-system + Grafana sidecar 模式；不新增对外入口 |
| IV. 性能要求 | ✅ PASS | 无新增 K8s 工作负载；Prometheus 额外 16 target，节点侧进程极轻 |
| V. 中文优先 | ✅ PASS | 文档、注释、提交信息使用中文 |
| 安全与合规 - 网络 | ✅ PASS | 只读端点，仅监听节点 LAN IP；不新增公网/tailnet 入口 |
| 安全与合规 - Secret | ✅ PASS | 不提交任何凭据；部署时复用现有 release 凭据 |
| 开发与部署工作流 - GitOps | ✅ PASS | `system/monitoring-system` 走 ArgoCD；tailscale CR 沿用既有 Ansible 管理 |

## Project Structure

### Documentation (this feature)

```text
specs/006-tailscale-monitoring/
├── spec.md              # Feature spec
├── plan.md              # This file
├── research.md          # 调研与实测取证
├── quickstart.md        # 部署与验证指南
├── checklists/
│   └── requirements.md  # Spec 质量检查
└── tasks.md             # 实施任务
```

### Source Code (repository root)

```text
metal/roles/prerequisites/tasks/main.yml              # 新增 tailscale metrics systemd 服务任务
metal/roles/prerequisites/templates/tailscale-metrics.service.j2   # 只读 metrics 服务单元
metal/roles/tailscale/templates/proxyclass.yaml        # 新增 tailscale-metrics ProxyClass
metal/roles/tailscale/templates/proxygroup.yaml        # 两个 ProxyGroup 引用该 ProxyClass
metal/roles/tailscale/tasks/main.yml                   # CR 任务加 tailscale-cr tag，便于单独 apply
system/monitoring-system/values.yaml                   # additionalScrapeConfigs（tailscale-nodes）
system/monitoring-system/templates/prometheusrule-tailscale.yaml  # 告警规则
system/monitoring-system/templates/dashboard-tailscale.yaml       # Grafana ConfigMap
system/monitoring-system/files/dashboards/tailscale.json          # dashboard 定义
```

**Structure Decision**: 节点侧沿用 `prerequisites`（唯一的 node 级收敛 role，且 UFW 例外也在其中）；集群侧 Tailscale CR 沿用 `metal/roles/tailscale`（operator 本身就是 Ansible 管理，不在 ArgoCD 内）；监控资源统一放 `system/monitoring-system`，复用既有 Prometheus / Grafana sidecar / ArgoCD 自动发现。

## Complexity Tracking

无违规项。两处刻意取舍：

- dashboard 在本仓库维护而非引用 grafana.com：站上无匹配客户端指标的 dashboard（见 research.md）。
- 节点 metrics 走独立 scrape job 而非 node-exporter textfile collector：避免改动 node-exporter 参数/挂载，也避免文件写入的 staleness。
