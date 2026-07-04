# Implementation Plan: KubeVirt GitOps 部署与虚拟机管理

**Branch**: `003-kubevirt-gitops` | **Date**: 2026-07-04 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/003-kubevirt-gitops/spec.md`

## Summary

在 homelab2 k3s 集群上通过 ArgoCD GitOps 方式安装 KubeVirt 虚拟化平台，并创建带持久化磁盘的虚拟机。由于 KubeVirt 官方不提供 Helm Chart（仅提供原始 YAML 清单），采用自建 wrapper Helm Chart 方案，将 KubeVirt Operator + CR + CDI 打包为符合项目 ApplicationSet 规范的 Helm Chart，部署于 `system/kubevirt/`。VM 清单同样通过 GitOps 管理。

## Technical Context

**Language/Version**: YAML（Kubernetes 清单 / Helm Chart 模板）

**Primary Dependencies**: KubeVirt（Operator + CR）、CDI（Containerized Data Importer，DataVolume 支持的前置依赖）、KubeVirt virtctl CLI

**Storage**: 集群已有 Rook-Ceph（`standard-rwo` / `standard-rwx` StorageClass），VM 数据磁盘通过 PVC 动态供给

**Testing**: 手动验证（`kubectl get kv -n kubevirt`、`kubectl get vmi`、`virtctl console`），冒烟测试扩展到 KubeVirt 组件

**Target Platform**: k3s（containerd 运行时，4 × N100 mini-host）

**Project Type**: 基础设施即代码（IaC）— Helm Chart + Kubernetes CRDs

**Performance Goals**: KubeVirt 部署 < 5 分钟，VM 启动 < 60 秒（不含镜像拉取）

**Constraints**: 4 节点集群总资源约 64-128GB RAM，VM 需合理申请资源；部署前需验证所有节点 `/dev/kvm` 可用（已确认 N100 节点支持硬件虚拟化 VT-x，KVM 模块已加载）

**Scale/Scope**: MVP 单虚拟机场景

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原则 | 状态 | 说明 |
|------|------|------|
| I. 代码质量 | ✅ PASS | Helm Chart 通过 `helmlint`，YAML 通过 `yamllint` |
| II. 测试标准 | ✅ PASS | 手动验证 + 冒烟测试覆盖 KubeVirt 组件；无代码变更，无需单元测试 |
| III. 用户体验一致性 | ✅ PASS | VM 不暴露 HTTP 端点，不需要 Ingress/Homepage/SSO |
| IV. 性能要求 | ✅ PASS | KubeVirt 组件和 VM 均需显式设置 `resources.requests/limits` |
| V. 优先使用中文 | ✅ PASS | 所有文档、注释使用中文 |
| 安全与合规 | ✅ PASS | 无新增 Secret，无敏感信息 |
| 开发与部署工作流 | ✅ PASS | 通过 ArgoCD ApplicationSet 部署，遵循 GitOps 流程 |

**Gate Result**: ✅ ALL PASS — 无违规，无需 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/003-kubevirt-gitops/
├── plan.md              # This file
├── research.md          # Phase 0: 技术调研
├── data-model.md        # Phase 1: 数据模型
├── quickstart.md        # Phase 1: 快速上手
└── tasks.md             # Phase 2 (by /speckit-tasks)
```

### Source Code (repository root)

```text
system/kubevirt/          # KubeVirt + CDI Helm Chart
├── Chart.yaml            # Umbrella chart: depends on upstream manifests
├── values.yaml           # 配置: kubevirt version, resources, nodeSelector
└── templates/
    ├── cdi-operator.yaml          # CDI Operator 清单
    ├── cdi-cr.yaml                # CDI CR 清单
    ├── kubevirt-operator.yaml     # KubeVirt Operator 清单
    └── kubevirt-cr.yaml           # KubeVirt CR 清单

system/kubevirt/vm/       # VM 清单（不作为独立 Helm Chart — 由父 Chart 管理或独立管理）
└── demo-vm.yaml           # 示例 VM 定义

system/kubevirt/templates/ # 端口: 直接嵌入上游发布清单并参数化
```

**Structure Decision**: 采用项目现有的 `system/<name>/` + Helm Chart 模式。由于 KubeVirt 无官方 Helm Chart，创建 wrapper chart 将上游 YAML 清单封装为 Helm 模板，通过 `values.yaml` 参数化关键配置项。

## Complexity Tracking

> 无 Constitution 违规，此节为空。
