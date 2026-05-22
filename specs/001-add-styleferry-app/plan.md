# Implementation Plan: 新增 StyleFerry 应用

**Branch**: `001-add-styleferry-app` | **Date**: 2026-05-22 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/001-add-styleferry-app/spec.md`

## Summary

新增 StyleFerry 博客生成服务的 Helm Chart，遵循项目统一的 `bjw-s-labs/app-template` 模式。Chart 位于 `apps/styleferry/`，包含 Chart.yaml、values.yaml（镜像、环境变量、Ingress、持久化、资源限制）和 templates/secret.yaml（ExternalSecret）。

## Technical Context

**Language/Version**: YAML (Helm Chart values) + Go templates (Helm)

**Primary Dependencies**: bjw-s-labs/app-template v5.0.1 Helm Chart

**Storage**: SQLite（内嵌，持久化到 PVC `/data`）

**Testing**: `make smoke-test`（HTTP 200 检查）、`helmlint`、`yamllint`（pre-commit hooks）

**Target Platform**: K3s 集群（4 × N100 mini-host），ArgoCD GitOps 部署

**Project Type**: Helm Chart（infrastructure-as-code）

**Performance Goals**: 单用户博客生成工具，低并发场景，响应时间取决于上游 LLM API

**Constraints**: resources.requests/limits 必填；镜像来自阿里云容器镜像仓库；Secret 通过 ExternalSecret 管理

**Scale/Scope**: 单一 Deployment，1 副本，1 个 PVC

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原则 | 检查项 | 状态 |
|------|--------|------|
| I. 代码质量 | YAML 通过 yamllint、Helm Chart 通过 helmlint、pre-commit hooks 全量配置 | ✅ 通过 |
| II. 测试标准 | `make smoke-test` 需新增 styleferry 端点检查 | ⚠ 需在 tests 中新增 |
| III. 用户体验一致性 | Tailscale Ingress、MagicDNS `styleferry.west-beta.ts.net`、Homepage 注册 | ✅ 通过 |
| IV. 性能要求 | 显式设置 resources、使用 SQLite 内嵌存储、Cilium 配置不变 | ✅ 通过 |
| V. 优先使用中文 | 注释、提交信息使用中文 | ✅ 通过 |
| 安全与合规 | Secret 通过 ExternalSecret 管理、不提交敏感信息到仓库 | ✅ 通过 |
| 开发与部署工作流 | 通过 ArgoCD ApplicationSet 部署、目录包含 Chart.yaml + values.yaml | ✅ 通过 |

**结论**: 全部通过，仅需在 smoke-test 中新增 styleferry 端点检查。

## Project Structure

### Documentation (this feature)

```text
specs/001-add-styleferry-app/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

```text
apps/styleferry/
├── Chart.yaml           # Helm Chart 元数据，依赖 app-template v5.0.1
├── values.yaml          # 镜像、环境变量、Ingress、持久化、资源限制
└── templates/
    └── secret.yaml      # ExternalSecret：从 global-secrets 引用 styleferry key
```

**Structure Decision**: 遵循项目现有的单 Chart 模式（参考 `apps/paperless/`）。每个 app 目录包含 Chart.yaml + values.yaml + templates/。不引入子 Chart 或 library Chart。

## Complexity Tracking

> 无 Constitution 违规，无需记录。
