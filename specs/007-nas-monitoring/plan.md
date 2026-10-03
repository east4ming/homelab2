# Implementation Plan: QNAP NAS 指标监控

**Branch**: `007-nas-monitoring` | **Date**: 2026-10-03 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/007-nas-monitoring/spec.md`

## Summary

为 homelab2 的 QNAP NAS（NAS33657A，TS-453Bmini，QTS 5.2.10，`192.168.3.216`）补齐指标监控：

1. **NAS 侧**：`metal/nas/compose.yml` 定义一个 Container Station 应用，含 `nas-node-exporter`（9100，主机指标）与 `nas-smartctl-exporter`（9633，磁盘 SMART）。两个 exporter 均走 host 网络，因此集群可直接抓取。
2. **采集**：`system/monitoring-system/values.yaml` 的 `additionalScrapeConfigs` 增加 `nas-node` 与 `nas-smartctl` 两个静态 job，附加 `nas` 标签，并为 SMART 指标做 `device`→`disk` 盘位重标记。
3. **告警**：`system/monitoring-system/templates/prometheusrule-nas.yaml` 提供 6 条规则；抓取中断复用既有 `TargetDown`。
4. **可视化**：`system/monitoring-system/files/dashboards/nas.json` + `templates/dashboard-nas.yaml` 的 sidecar ConfigMap。

NAS 是集群外的设备，ArgoCD 只能管理集群侧对象（采集配置、规则、dashboard）。NAS 上的容器由入库的 compose 文件定义，通过 Container Station 导入——这是 K8s 之外不可避免的一条通道，见 research.md 的方案对比。

## Technical Context

**Language/Version**: YAML / Helm / Docker Compose / PromQL

**Primary Dependencies**: node_exporter v1.8.2，smartctl-exporter v0.14.0（`smartmontools` 7.4），kube-prometheus-stack 91.5.2，Grafana sidecar，Container Station（Docker 27.1.2-qnap8 / Compose v2.29.1-qnap2）

**Storage**: 无新增持久化；指标进既有 Prometheus 30Gi PVC

**Testing**: compose 语法校验（`docker compose config`）、`yamllint`、`helm template` 渲染、`promtool check rules` / `check config`、部署后按实测样本评估 6 条告警表达式、Prometheus Targets 与 Grafana 面板人工验证

**Target Platform**: NAS 侧 QTS 5.2.10（kernel 5.10.60-qnap，x86_64，16GB RAM）；集群侧 K3s v1.36.5，4 节点

**Project Type**: GitOps 基础设施变更 + 集群外设备的一次性应用导入

**Performance Goals**: NAS 侧新增 2 个常驻容器（实测 node-exporter ~20MiB、smartctl-exporter ~6.4MiB）；Prometheus 新增 2 个 target，抓取间隔 60s

**Constraints**: 只读采集；不提交任何凭据；不修改 QTS 系统配置；smartctl 必须以 `-d sat` 强制设备类型

**Scale/Scope**: 1 台 NAS、4 个盘位 + 1 个 USB 外接盘、5 个存储卷、2 个 exporter

## Constitution Check

| Principle | Status | Notes |
|-----------|--------|-------|
| I. 代码质量 | ✅ PASS | YAML/JSON 改动，通过 `yamllint`、`docker compose config`、`helm template`、`promtool` |
| II. 测试标准 | ✅ PASS | 规则表达式按实测样本逐条评估；采集链路在集群网络命名空间内验证可达性 |
| III. 用户体验一致性 | ✅ PASS | 沿用 monitoring-system + Grafana sidecar 模式；NAS 应用走 Container Station 既有入口 |
| IV. 性能要求 | ✅ PASS | NAS 侧合计 <30MiB 常驻；Prometheus 仅新增 2 target |
| V. 中文优先 | ✅ PASS | 文档、注释、提交信息使用中文 |
| 安全与合规 - 网络 | ✅ PASS | exporter 仅监听 NAS LAN IP 的既有端口，不新增公网/tailnet 入口；容器只读挂载 `/` |
| 安全与合规 - Secret | ✅ PASS | compose 与 values 中无凭据；sudo 口令不落盘、不入库 |
| 开发与部署工作流 - GitOps | ✅ PASS（有说明） | 集群侧全部走 ArgoCD；NAS 侧容器无法由 ArgoCD 管理，改为入库 compose + Container Station 导入，见 Complexity Tracking |

## Project Structure

### Documentation (this feature)

```text
specs/007-nas-monitoring/
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
metal/nas/compose.yml                                          # NAS 侧 Container Station 应用定义
system/monitoring-system/values.yaml                           # additionalScrapeConfigs（nas-node / nas-smartctl）
system/monitoring-system/templates/prometheusrule-nas.yaml     # 6 条告警规则
system/monitoring-system/templates/dashboard-nas.yaml          # Grafana ConfigMap
system/monitoring-system/files/dashboards/nas.json             # dashboard 定义
```

**Structure Decision**: NAS 不是集群节点，不能进 `metal/inventories/prod.yml`：该 inventory 由 `boot.yml`/`cluster.yml` 驱动，会对其执行 Wake-on-LAN 与 K3s 初始化。因此 NAS 的采集定义单独放 `metal/nas/`（仍是「物理机侧」的归属），集群侧监控资源沿用 `system/monitoring-system`，复用既有 ArgoCD 自动发现与 Grafana sidecar。

## Complexity Tracking

一处刻意取舍，无原则违规：

- **NAS 侧容器不由 ArgoCD 管理**。ArgoCD 的同步单元是 K8s 对象，NAS 上的 Docker 容器不在其管辖范围内。可选路径已在 research.md 逐条否决（在 NAS 上装 K8s/k3s、用 Flux 的通用控制器、用 ArgoCD 的 `ConfigManagementPlugin` 都无法在 QTS 上落地），最终选择「compose 入库 + Container Station 导入」：配置仍可追溯到 Git，NAS 重装后可复现，代价是导入这一步是人工的。
- **告警范围排除 QTS 内部对象**。`md9`/`md13` 是 32 槽位的固件 DOM 镜像，实际只用 4 槽，`active < required` 永久成立；`/mnt/ext` 是 436MB 固件 DOM，设计上就只剩约 8%。若不做范围限制，规则上线即持续误报（已实测确认）。这属于必要的领域约束，不是可配置项，因此硬编码在规则中并注释说明。
