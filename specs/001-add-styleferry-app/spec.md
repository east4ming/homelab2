# Feature Specification: 新增 StyleFerry 应用

**Feature Branch**: `001-add-styleferry-app`

**Created**: 2026-05-22

**Status**: Draft

**Input**: User description: "参考 paperless 新增 Helm Chart 应用 styleferry，镜像 registry.cn-hangzhou.aliyuncs.com/caseycui/styleferry:1.0.0，端口 8000，通过环境变量配置 LLM/搜索/可观测性等参数，敏感信息通过 ExternalSecret 引用，启用 ingress 和 persistence。"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 部署 StyleFerry Helm Chart (Priority: P1)

运维人员通过 ArgoCD GitOps 流程部署 StyleFerry 应用到 Kubernetes 集群。Helm Chart 遵循项目统一的 app-template 模式，包含 Chart.yaml、values.yaml 和 templates/ 目录结构。

**Why this priority**: 这是应用存在的基础——没有 Chart 就无法部署。

**Independent Test**: 将 Chart 放入 `apps/styleferry/` 后，ArgoCD ApplicationSet 自动发现并创建 Application，Pod 成功启动且探活通过。

**Acceptance Scenarios**:

1. **Given** `apps/styleferry/` 目录包含 `Chart.yaml` + `values.yaml`，**When** ArgoCD ApplicationSet 扫描 apps 目录，**Then** Application 被自动创建
2. **Given** Application 已创建，**When** ArgoCD 同步资源，**Then** Pod 拉取 `registry.cn-hangzhou.aliyuncs.com/caseycui/styleferry:1.0.0` 镜像并启动成功
3. **Given** Pod 已运行，**When** 检查容器端口，**Then** 容器监听 8000 端口

---

### User Story 2 - 通过 Tailscale Ingress 访问 StyleFerry (Priority: P2)

最终用户通过 Tailscale MagicDNS 域名访问 StyleFerry 博客生成服务，流量经由 Tailscale Ingress 代理转发到 Pod。

**Why this priority**: 无 Ingress 则服务无法从外部访问。

**Independent Test**: 在已加入 Tailscale 网络的设备上通过 `https://styleferry.west-beta.ts.net` 访问服务，返回 StyleFerry 界面。

**Acceptance Scenarios**:

1. **Given** StyleFerry Pod 正在运行，**When** 访问 `https://styleferry.west-beta.ts.net`，**Then** 服务返回 HTTP 200
2. **Given** Ingress 配置了 `tailscale.com/proxy-group: ingress-proxies` 注解，**When** Tailscale Operator 处理 Ingress，**Then** 自动申请 TLS 证书并启用 HTTPS

---

### User Story 3 - 数据持久化 (Priority: P3)

StyleFerry 的 SQLite 数据库和缓存文件存储在持久卷上，Pod 重启后数据不丢失。

**Why this priority**: 没有持久化则重启后丢失所有数据（博客文章、缓存等），影响可用性。

**Independent Test**: 写入测试数据后删除 Pod，新 Pod 启动后读取到的数据与写入一致。

**Acceptance Scenarios**:

1. **Given** Persistence 已配置，**When** Pod 首次启动，**Then** `/data` 目录挂载到 PVC
2. **Given** 已通过 StyleFerry 生成博客内容，**When** Pod 重启（滚动更新或手动删除），**Then** 之前的博客数据仍然存在
3. **Given** PVC 配置了 `accessMode: ReadWriteOnce`，**When** 检查 PVC 状态，**Then** 已 Bound 且容量满足需求

---

### Edge Cases

- 如果 ExternalSecret `styleferry` 不存在，Pod 启动时会因为缺少 `envFrom` 引用的 Secret 而失败（用户声明后续手动创建，此为预期行为）
- 如果 PVC 容量耗尽（SQLite DB + 缓存增大），写入操作会失败——需要监控磁盘使用率
- 如果 DeepSeek API / SearXNG / Recall 上游服务不可用，StyleFerry 应能正常启动但在调用对应功能时返回错误

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 系统 MUST 在 `apps/styleferry/` 目录提供 Helm Chart，遵循 `bjw-s-labs/app-template` 图表模式
- **FR-002**: 系统 MUST 使用镜像 `registry.cn-hangzhou.aliyuncs.com/caseycui/styleferry:1.0.0`，监听端口 8000
- **FR-003**: 系统 MUST 通过环境变量注入所有非敏感配置（LLM provider/model、搜索 provider/URL、日志级别、费用上限、数据库路径、缓存路径、Recall URL）
- **FR-004**: 系统 MUST 通过 `envFrom.secret` 从名为 `styleferry` 的 Secret 注入敏感配置（BLOG_LLM_API_KEY、BLOG_BRAVE_API_KEY、BLOG_LANGSMITH_API_KEY、BLOG_LANGFUSE_PUBLIC_KEY、BLOG_LANGFUSE_SECRET_KEY、BLOG_RECALL_API_KEY）
- **FR-005**: 系统 MUST 启用 Tailscale Ingress，域名固定为 `styleferry.west-beta.ts.net`
- **FR-006**: 系统 MUST 配置 persistence 将 `/data` 路径挂载到 PVC（accessMode: ReadWriteOnce）
- **FR-007**: 系统 MUST 配置 startup/liveness/readiness 探针以确保 Pod 健康状态可观测
- **FR-008**: 系统 MUST 在 `apps/homepage/` 中注册 StyleFerry 入口，归集到 Homepage 仪表盘
- **FR-009**: 系统 MUST 在 values.yaml 中显式设置 `resources.requests` 和 `resources.limits`

### Key Entities

- **StyleFerry App**: Helm Chart 应用，代表博客生成服务，包含容器镜像、环境变量、端口、持久化配置
- **StlyeFerry Secret**: External Secret Operator 管理的 Secret，类型为 `ExternalSecret`，从 `global-secrets` ClusterSecretStore 引用 `styleferry` key

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `make smoke-test` 中 styleferry 端点返回 HTTP 200
- **SC-002**: ArgoCD ApplicationSet 在 Chart 推送到 Git 后 3 分钟内自动创建并同步 Application
- **SC-003**: Pod 删除后重建，原有数据完整可读
- **SC-004**: 在 Tailscale 网络内的设备上可以正常打开 `https://styleferry.west-beta.ts.net`

## Assumptions

- StyleFerry 镜像已在 `registry.cn-hangzhou.aliyuncs.com/caseycui/styleferry:1.0.0` 就绪且可公开拉取
- Secret `styleferry` 将在部署前由运维人员手动创建（通过 External Secret 或其他方式）
- 项目遵循统一的 app-template Helm Chart 模式，不需要自定义 Helm 模板（除 ExternalSecret 外）
- Service 端口使用 `http` 名称和 HTTP 协议
- 持久化容量暂时不确定，可比照类似应用设定初始值（建议 10Gi）
- 不需要独立的 Redis 或 PostgreSQL——StyleFerry 使用内嵌 SQLite
- 域名 `styleferry.west-beta.ts.net` 遵循项目命名约定
