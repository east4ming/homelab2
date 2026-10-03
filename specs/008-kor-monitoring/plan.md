# Implementation Plan: 集群未使用资源审计（kor）

**Branch**: `008-kor-monitoring` | **Date**: 2026-10-03 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/008-kor-monitoring/spec.md`

## Summary

以本仓库既有的 GitOps 契约引入上游 [yonahd/kor](https://github.com/yonahd/kor)，把「集群里没人引用的资源」变成可查询、可可视化的信号：

1. **exporter**：`system/kor/` 新增一个包装 chart，依赖上游 `kor` chart `0.2.16`，只启用 `prometheusExporter`（常驻 Deployment），镜像钉 `v0.6.9`，显式声明 requests/limits，扫描间隔 30 分钟。
2. **抓取**：由 chart 自带的 `ServiceMonitor` 接入既有 Prometheus；既有 `serviceMonitorSelectorNilUsesHelmValues=false` 使其无需额外标签即可被发现。
3. **可视化**：`system/monitoring-system/` 新增 dashboard ConfigMap（`templates/dashboard-kor.yaml` + `files/dashboards/kor.json`），沿用该目录既有的 sidecar 模式。
4. **交付**：不新增任何 ArgoCD Application 清单——ApplicationSet 按 `system/*` 自动发现，新增目录即新增应用（namespace 取目录名 `kor`）。

全程只读：RBAC 只授予 `get`/`list`/`watch`，kor 的删除能力不启用。

## Technical Context

**Language/Version**: YAML / Helm（chart apiVersion v2）/ PromQL / JSON（Grafana dashboard schema v38）

**Primary Dependencies**: 上游 chart `kor 0.2.16`（appVersion `0.6.9`，镜像 `yonahdissen/kor:v0.6.9`）；kube-prometheus-stack（`monitoring.coreos.com/v1`、Prometheus）；Grafana 13.2.2 + k8s-sidecar 2.11.2；ArgoCD v3.5.3

**Storage**: 无新增持久化。指标进既有 Prometheus 30Gi PVC

**Testing**: `helm dependency update` + `helm lint`；`helm template`（带与不带 `--api-versions monitoring.coreos.com/v1` 两种情形）；渲染产物内嵌 JSON 解析；`yamllint`；上线后对线上 Prometheus 直接执行面板中的 PromQL，核对返回数据与标签

**Target Platform**: K3s v1.36.5，4 节点 N100；ArgoCD ApplicationSet（`refs/heads/master`，automated + selfHeal + prune）

**Project Type**: GitOps 基础设施变更（纯声明式 YAML/JSON，无自研代码）

**Performance Goals**: 常驻 exporter 实测 10MiB 内存、24m CPU；每 30 分钟一次整集群 LIST；首扫约 3 分钟。请求 10m/64Mi、上限 500m/256Mi

**Constraints**: 只读（不含 `--delete`）；不提交凭据；不新增公网/tailnet 入口（无 Ingress）；不修改既有 Prometheus/Grafana 配置

**Scale/Scope**: 1 个 Deployment、1 个 Service、1 个 ServiceMonitor、5 个 RBAC 对象、1 个 dashboard、约 925 条指标序列

## Constitution Check

| Principle | Status | Notes |
|-----------|--------|-------|
| I. 代码质量 | ✅ PASS | `helmlint`（`helm lint`）通过；YAML 通过 `yamllint`；Chart.lock/`.tgz` 由既有 `.gitignore` 排除 |
| II. 测试标准 | ✅ PASS | 渲染两条路径（有/无 CRD）均实测；面板 PromQL 对线上 Prometheus 逐条执行核对；不新增单元测试（无自研代码） |
| III. 用户体验一致性 | ✅ PASS | 无 Ingress、无 UI，因此不涉及 Tailscale 入口与 Kanidm SSO，也无需登记 Homepage（kor 不是面向用户的服务）；dashboard 走既有 sidecar |
| IV. 性能要求 | ✅ PASS | 显式 requests/limits；扫描间隔由默认 10 分钟放宽到 30 分钟；实测常驻 10MiB |
| V. 中文优先 | ✅ PASS | 文档、注释、提交信息使用中文 |
| 安全与合规 - 网络 | ✅ PASS | 只有 ClusterIP Service，无新增入口 |
| 安全与合规 - Secret | ✅ PASS | 未配置任何凭据；Slack 相关 values 全部留空，chart 因此不生成 Secret |
| 开发与部署工作流 - GitOps | ✅ PASS | 全部资源经 ApplicationSet/ArgoCD 交付，无手工 `kubectl apply`；新增 `system/kor/{Chart.yaml,values.yaml}` 符合目录契约 |

## Project Structure

### Documentation (this feature)

```text
specs/008-kor-monitoring/
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
system/kor/Chart.yaml                                          # 包装 chart（依赖上游 kor）
system/kor/values.yaml                                         # exporter 模式、镜像钉版、资源、扫描间隔
system/monitoring-system/templates/dashboard-kor.yaml          # Grafana sidecar ConfigMap
system/monitoring-system/files/dashboards/kor.json             # dashboard 定义（上游 19863 改两处）
AGENTS.md                                                      # SPECKIT 区块指向本 plan
```

**Structure Decision**:

- kor 是集群级审计工具（要对整个集群做 LIST，需要 ClusterRole），与 `kured`、`eraser`、`rook-ceph` 同类，因此放 `system/` 而不是放面向用户的 `apps/`。ApplicationSet 取目录名作为 namespace，于是应用与 namespace 都是 `kor`。
- **dashboard 的归属刻意与 kor 不同目录**：Grafana sidecar 的 `searchNamespace` 是 `monitoring-system`，dashboard ConfigMap 只有放在那里才会被加载，`NAS`/`SMART`/`Tailscale` 三个 dashboard 也是这样处理的。代价是一次变更跨两个 stack 目录，换来的是零改动既有 Grafana 行为——比放宽 sidecar 作用域或给 kor 单开一条 provisioning 通道都更小。
- 不新增 Application 清单：ApplicationSet 的 git generator 已经覆盖 `system/*`，这是仓库既有的自动发现契约（宪法「每个 `system/`、`platform/`、`apps/` 目录必须包含 `Chart.yaml` + `values.yaml`」）。

## Complexity Tracking

两处刻意取舍，均无原则违规：

| 取舍 | 为什么 | 被否决的更简单方案 |
|------|--------|--------------------|
| 用上游 chart 包装（Chart.yaml 依赖）而不是把渲染后的清单直接入库 | 上游 chart 已提供 Deployment/Service/ServiceMonitor/RBAC 五种对象与 CRD 门控；包装方式让 Renovate 能跟踪版本，升级只需改一行 | 直接抄渲染结果入库：多出约 300 行需要手工维护，且丢失 `Capabilities` 门控与后续升级路径 |
| dashboard 放在 `monitoring-system` 而非 `system/kor` | sidecar 只搜 `monitoring-system` | 放宽 sidecar 的 `searchNamespace`（会影响既有 Grafana 行为）、或让 kor 目录自带一套 provisioning（为 1 个面板引入新通道） |
