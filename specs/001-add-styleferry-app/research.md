# Research: StyleFerry Helm Chart

**Feature**: 001-add-styleferry-app
**Date**: 2026-05-22

## 1. 基础 Chart 模式

**Decision**: 使用 `bjw-s-labs/app-template` v5.0.1 作为 Helm Chart 依赖

**Rationale**:
- 项目已有 12 个 app 使用相同模式（paperless、searxng、upsnap 等）
- 提供标准化的 Deployment、Service、Ingress、Persistence 模板
- 减少样板代码，只需提供 values.yaml 即可

**Alternatives considered**:
- 手写原生 Kubernetes YAML — 与项目现有模式不一致，维护成本高
- 使用 bitnami/common 库 — 不如 app-template 简洁

## 2. Secret 管理模式

**Decision**: 使用 ExternalSecret（external-secrets.io/v1）从 `global-secrets` ClusterSecretStore 引用 key `styleferry`

**Rationale**:
- 遵循 paperless 的模式（`templates/secret.yaml`）
- Secret 不提交到 Git 仓库
- 与现有 External Secrets Operator 基础设施集成

**Alternatives considered**:
- 原生 Kubernetes Secret（手动创建）— 不符合 GitOps 理念
- Sealed Secrets — 项目未采用此方案

## 3. 持久化策略

**Decision**: PVC（ReadWriteOnce），初始容量 10Gi，挂载到 `/data`

**Rationale**:
- StyleFerry 使用 SQLite（`/data/blog_system.db`）+ 文件缓存（`/data/cache`）
- SQLite 只需要 ReadWriteOnce（单副本 Deployment）
- 10Gi 参照 paperless 的配置，足以容纳博客内容和缓存

## 4. 资源限制

**Decision**: requests: CPU 50m / Memory 128Mi；limits: CPU 500m / Memory 512Mi

**Rationale**:
- StyleFerry 是博客生成工具，主要等待上游 LLM API 响应，自身计算开销低
- 参照同类应用：homepage 32m/157Mi、upsnap 无显式限制但 Pod 轻量
- 512Mi 内存上限为 SQLite 缓存 + Python 运行时留足余量
- 不设 GPU 资源——StyleFerry 调用外部 LLM API，不需要本地 GPU

## 5. Homepage 注册

**Decision**: 在 `apps/homepage/values.yaml` 的 `config.services` 下新增 StyleFerry 条目

**Rationale**:
- 项目 Constitution 要求所有应用入口归集到 Homepage
- StyleFerry 属于 "Utilities" 或可新增 "AI Tools" 分类
- 图标：暂用默认图标或 styleferry 自定义图标

## 6. Smoke Test 更新

**Decision**: 在 `make smoke-test` 中新增 `https://styleferry.west-beta.ts.net` 的 HTTP 200 检查

**Rationale**:
- Constitution 规定冒烟测试覆盖核心服务
- StyleFerry 作为面向用户的服务，需纳入冒烟测试
