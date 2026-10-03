# Specification Quality Checklist: 集群未使用资源审计（kor）

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-10-03
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details leaked into user stories
- [x] Focused on user value and operational needs
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

- 已与用户确认两点范围：（1）只启用 Prometheus exporter 模式，不启用 CronJob；（2）chart 放 `system/kor`，不放 `apps/`。
- 不启用 CronJob 的原因是硬约束而非偏好：仓库内没有 Slack 凭据，CronJob 的报告只能落在 Pod 日志里。这一点写入 FR-012 与假设。
- 「只读」是本特性的安全边界：FR-011 要求 RBAC 只有 `get`/`list`/`watch`。kor 自身的 `--delete` 能力不配置、不启用，清理始终由人决策。
- 规划阶段的关键不确定项是 ServiceMonitor 能否下发（chart 用 `.Capabilities.APIVersions.Has` 门控）。已通过 ArgoCD 源码 + 双向渲染实测确认，见 research.md 第 3 节。
- 实现阶段出现一次判断错误：曾依据 kor 源码的标签名把 dashboard 的 `exported_namespace` 改成 `namespace`，上线后实测发现 `namespace` 恒为 `kor`。已修正并复验（tasks.md T025/T026），原因见 research.md 第 5 节。
