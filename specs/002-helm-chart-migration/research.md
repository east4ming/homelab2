# Research: Raw Manifests to Helm Chart Migration

**Feature**: 002-helm-chart-migration
**Date**: 2026-05-24

## 1. CI Helm-Diff 失败根因

**Decision**: 确认失败原因是 `apps/rsshub/` 和 `apps/lobe-chat/` 缺少 `Chart.yaml`，导致 `helm dependency update` 和 `helm template` 报错。

**Rationale**: 
- `scripts/helm-diff` 对 `apps/` 下每个子目录执行 `helm dependency update` → `helm template`
- 当目录不包含 `Chart.yaml` 时，Helm CLI 返回错误并退出
- 代码注释声称"should not raise error"但与实际实现不符（使用 `check=True`）

**Alternatives Considered**:
- 修改 `scripts/helm-diff` 脚本跳过非 Helm chart 目录 → 拒绝，治标不治本，且项目 Constitution 要求 `apps/` 目录必须有 `Chart.yaml`
- 仅添加空 `Chart.yaml` 不做其他变更 → 拒绝，`helm template` 仍需 `templates/` 目录才能渲染

## 2. 最简 Helm Chart 结构

**Decision**: 采用 `Chart.yaml` + `values.yaml`（空）+ `.helmignore` + `templates/` 目录结构，不使用任何 chart 依赖（包括 app-template）。

**Rationale**:
- styleferry 使用 app-template 依赖是因为其配置比较简单
- rsshub 和 lobe-chat 的 manifests 结构复杂（多个 Deployment、多种 Service 类型、PVC、Ingress 等），强行映射到 app-template 的 values 结构会导致大量模板定制
- 用户明确要求"最简封装"和"与实际环境保持一致"
- 直接 raw template 方案可以保证零 spec 变更

**Alternatives Considered**:
- 使用 app-template（如 styleferry）→ 拒绝，rsshub 有 7 个 Deployment、3 个 PVC、多种 Service（ClusterIP/NodePort/ExternalName），app-template 的 opinionated 结构无法覆盖
- 自定义 Go template 将所有变量 values 化 → 拒绝，复杂度过高，且用户强调"最小变更"

## 3. Namespace 处理策略

**Decision**: 保持现有行为不变。rsshub 资源中硬编码的 `namespace: rsshub` 保留在 template 中；lobe-chat 资源不添加 namespace 字段（保持原样）。

**Rationale**:
- rsshub 所有资源都硬编码了 `namespace: rsshub`，`helm template --namespace rsshub` 的输出与原名一致
- lobe-chat 所有资源都没有 namespace 字段，由 ArgoCD Application destination.namespace 统一注入
- 保持现有行为避免了 ArgoCD 的 namespace 管理冲突

**Alternatives Considered**:
- 将所有 namespace 替换为 `{{ .Release.Namespace }}` → 拒绝，对 lobe-chat 而言是新增字段，可能导致 ArgoCD 行为变化

## 4. 标签与注解新增策略

**Decision**: 在所有资源的 `metadata.labels` 中新增 `app.kubernetes.io/managed-by: {{ .Release.Service }}` 标签。不添加 `helm.sh/chart` 标签（避免 version 硬编码导致 diff 噪音）。

**Rationale**:
- `app.kubernetes.io/managed-by` 是 Kubernetes recommended labels 之一，用于标识资源的管理者
- `{{ .Release.Service }}` 在 `helm template` 渲染时始终输出 `Helm`
- 不添加含版本号的标签以避免每次升级版本时产生不必要的 diff
- 用户允许新增 labels 和 annotations

**Alternatives Considered**:
- 完全不添加任何标签 → 可行，但失去了标记 Helm 管理的优势
- 添加完整的 recommended labels set → 拒绝，部分标签（如 `app.kubernetes.io/version`）需要每应用定义，增加复杂度

## 5. helm-diff 脚本过渡期处理

**Decision**: 同时修复 `scripts/helm-diff` 使其真正优雅处理非 Helm chart 目录（当 `Chart.yaml` 不存在时跳过该目录）。

**Rationale**:
- 当前 PR 的 CI 会比较 source branch（Helm chart）与 target branch（raw manifests）
- 如不修复脚本，target branch 的 `helm template` 仍会失败
- 代码注释中已有此意图，只是实现不完整

**Alternatives Considered**:
- 仅在合并后生效（不修复脚本）→ 拒绝，当前 PR 的 CI 会失败，不符合"通过 CI 验证"的目标
