# Implementation Plan: Raw Manifests to Helm Chart Migration

**Branch**: `002-helm-chart-migration` | **Date**: 2026-05-24 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-helm-chart-migration/spec.md`

## Summary

将 `apps/rsshub/`（22 个 Kubernetes 资源文件）和 `apps/lobe-chat/`（15 个资源文件）从原始 YAML manifests 转换为最简 Helm chart。每个应用目录新增 `Chart.yaml`、`values.yaml`、`.helmignore`，并将所有现有 YAML manifest 移入 `templates/` 子目录，内容保持不变。不引入 app-template 依赖，不改变资源 spec（Deployment selector、Service port、PVC storage、Ingress rule 等全部原样保留）。唯一允许的变更是新增标准 Helm 标签和注解。

## Technical Context

**Language/Version**: YAML / Helm Chart `apiVersion: v2`

**Primary Dependencies**: Helm 3.x CLI（CI 中已安装）；无 chart 依赖（不使用 app-template 等第三方 chart）

**Storage**: N/A（不涉及新的存储需求）

**Testing**: `helm lint` 做语法校验；`helm template` 渲染后与原始 manifests 做 `dyff between` 对比

**Target Platform**: Kubernetes (K3s on homelab)，ArgoCD 部署

**Project Type**: Helm chart 打包（基础设施即代码）

**Performance Goals**: `helm template` 渲染时间 < 1s（最小化模板，无复杂逻辑）

**Constraints**: 
- 渲染输出必须与原始 manifests 在 spec 层面完全一致（仅允许新增 label/annotation）
- 不引入任何 chart 依赖以避免 CI `helm dependency update` 下载失败
- 保持现有 kompose 标签和注解不变

**Scale/Scope**: 2 个 app 目录，共 37 个 Kubernetes 资源文件

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原则 | 状态 | 说明 |
|------|------|------|
| I. 代码质量 | ✅ PASS | 转换后每个 chart 执行 `helm lint`；YAML 文件通过 `yamllint`（pre-commit hook 已配置） |
| II. 测试标准 | ✅ PASS | `helm template` 渲染成功 → 输出与原始 manifests 无 spec 差异 |
| III. UX 一致性 | ✅ PASS | 不改变 Ingress、Service、域名、认证方式；所有资源 spec 保持不变 |
| IV. 性能要求 | ✅ PASS | 不改变任何 `resources.requests/limits`；不修改 Cilium/Ceph 配置 |
| V. 中文优先 | ✅ PASS | 本计划及所有文档使用中文编写 |
| 安全与合规 | ✅ PASS | 不提交 Secret；使用 SecretKeyRef 引用外部管理的 Secret |
| 开发与部署工作流 | ✅ PASS | 满足 `apps/` 目录必须包含 `Chart.yaml` + `values.yaml` 的契约要求 |

## Project Structure

### Documentation (this feature)

```text
specs/002-helm-chart-migration/
├── plan.md              # 本文件
├── research.md          # Phase 0 输出
├── data-model.md        # Phase 1 输出
├── quickstart.md        # Phase 1 输出
└── tasks.md             # Phase 2 输出（/speckit-tasks 命令生成）
```

### Source Code (repository root)

```text
apps/
├── rsshub/
│   ├── Chart.yaml           # 新增：Helm chart 元数据
│   ├── values.yaml          # 新增：空 values（保留扩展点）
│   ├── .helmignore          # 新增：排除非模板文件
│   ├── templates/           # 新增：所有 K8s 资源模板
│   │   ├── ns.yaml
│   │   ├── deploy-rsshub.yaml
│   │   ├── deploy-browserless.yaml
│   │   ├── deploy-database-postgres.yaml
│   │   ├── deploy-redis.yaml
│   │   ├── deploy-service-mercury.yaml
│   │   ├── deploy-service-opencc.yaml
│   │   ├── deploy-service-rss.yaml
│   │   ├── service-rsshub.yaml
│   │   ├── service-browserless.yaml
│   │   ├── service-database-postgres.yaml
│   │   ├── service-database-postgres-np.yaml
│   │   ├── service-redis.yaml
│   │   ├── service-external-rsshub.yaml
│   │   ├── service-service-mercury.yaml
│   │   ├── service-service-opencc.yaml
│   │   ├── service-service-rss.yaml
│   │   ├── ingress-rsshub.yaml
│   │   ├── ingress-ttrss.yaml
│   │   ├── pvc-database-postgres-claim0.yaml
│   │   ├── pvc-feed-icons.yaml
│   │   └── pvc-redis-data.yaml
│   ├── .gitignore            # 保持不变
│   ├── README.md             # 保持不变
│   ├── README.zh-CN.md       # 保持不变
│   ├── kubectl-neat.sh       # 保持不变
│   └── move_and_rename.sh    # 保持不变
│
└── lobe-chat/
    ├── Chart.yaml            # 新增
    ├── values.yaml           # 新增
    ├── .helmignore           # 新增
    ├── templates/            # 新增：所有 K8s 资源模板
    │   ├── deploy-lobe.yaml
    │   ├── deploy-casdoor.yaml
    │   ├── deploy-postgresql.yaml
    │   ├── deploy-redis.yaml
    │   ├── svc-lobe.yaml
    │   ├── svc-casdoor.yaml
    │   ├── svc-postgresql.yaml
    │   ├── svc-redis.yaml
    │   ├── svc-egress-lobe.yaml
    │   ├── svc-egress-casdoor.yaml
    │   ├── svc-egress-rustfs.yaml
    │   ├── ingress-lobe.yaml
    │   ├── ingress-casdoor.yaml
    │   ├── pvc-postgresql-claim1.yaml
    │   └── pvc-redis.yaml
    ├── README.md             # 保持不变
    ├── README.zh-CN.md       # 保持不变
    ├── CLAUDE.md             # 保持不变
    ├── casdoor-cm0-configmap.yaml.example  # 保持原位（示例文件，不入 templates）
    ├── docs/                 # 保持不变
    └── examples/             # 保持不变
```

**Structure Decision**: 采用最简 Helm chart 结构 — `Chart.yaml` + `values.yaml` + `templates/` 目录，无任何依赖。templates 中的文件直接使用原始 YAML 内容（raw template），不引入 Go template 逻辑（除非需要 `{{ .Release.Namespace }}` 等标准化处理）。

## Complexity Tracking

> 无 Constitution 违规需要申辩。此次变更是修复性工作——将不符合契约（缺少 Chart.yaml）的 app 目录转换为符合 Constitution 要求的标准 Helm chart。
