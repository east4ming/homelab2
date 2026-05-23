# Data Model: StyleFerry Helm Chart

**Feature**: 001-add-styleferry-app
**Date**: 2026-05-22

## Entity: StyleFerry Helm Values

app-template values 结构，定义 StyleFerry 部署的完整配置。

### 字段定义

| 路径 | 类型 | 必填 | 说明 | 值/示例 |
|------|------|------|------|---------|
| `app-template.defaultPodOptions.enableServiceLinks` | bool | 是 | 禁用 Service 环境变量注入 | `false` |
| `app-template.controllers.main.containers.main.image.repository` | string | 是 | 容器镜像地址 | `registry.cn-hangzhou.aliyuncs.com/caseycui/styleferry` |
| `app-template.controllers.main.containers.main.image.tag` | string | 是 | 镜像标签 | `1.0.0` |
| `app-template.controllers.main.containers.main.env` | list | 是 | 非敏感环境变量列表 | 见环境变量表 |
| `app-template.controllers.main.containers.main.envFrom` | list | 是 | 敏感环境变量来源（Secret 引用） | `secret: "{{ .Release.Name }}-secret"` |
| `app-template.controllers.main.containers.main.probes` | object | 是 | 探针配置 | liveness/readiness/startup 全部启用 |
| `app-template.service.main.controller` | string | 是 | 关联的控制器名 | `main` |
| `app-template.service.main.ports.http.port` | int | 是 | 服务端口 | `8000` |
| `app-template.ingress.main.enabled` | bool | 是 | 启用 Ingress | `true` |
| `app-template.ingress.main.className` | string | 是 | Ingress Class | `tailscale` |
| `app-template.ingress.main.hosts` | list | 是 | 域名列表 | `styleferry.west-beta.ts.net` |
| `app-template.persistence.data.accessMode` | string | 是 | 存储访问模式 | `ReadWriteOnce` |
| `app-template.persistence.data.size` | string | 是 | 存储容量 | `10Gi` |
| `app-template.persistence.data.advancedMounts` | object | 是 | 挂载路径配置 | `/data` |
| `app-template.resources.requests` | object | 是 | 资源请求 | CPU 50m / Memory 128Mi |
| `app-template.resources.limits` | object | 是 | 资源限制 | CPU 500m / Memory 512Mi |

### 环境变量（非敏感）

| 变量名 | 值 | 说明 |
|--------|-----|------|
| `BLOG_LLM_PROVIDER` | `deepseek` | LLM 提供商 |
| `BLOG_LLM_BASE_URL` | `https://api.deepseek.com` | LLM API 端点 |
| `BLOG_LLM_MODEL` | `deepseek-v4-flash` | LLM 模型 |
| `BLOG_SEARCH_PROVIDER` | `searxng` | 搜索引擎 |
| `BLOG_SEARXNG_URL` | `http://searxng-caddy.searxng` | SearXNG 服务地址 |
| `BLOG_MONTHLY_COST_LIMIT` | `100.0` | 月度费用上限（美元） |
| `BLOG_LOG_LEVEL` | `DEBUG` | 日志级别 |
| `BLOG_TRACING_PROVIDER` | `langsmith` | 追踪提供商 |
| `BLOG_RECALL_BASE_URL` | `https://backend.getrecall.ai/api/v1` | Recall API 端点 |
| `BLOG_SQLITE_PATH` | `/data/blog_system.db` | SQLite 数据库路径 |
| `BLOG_CACHE_DIR` | `/data/cache` | 缓存目录 |

### 环境变量（敏感，来自 Secret）

| 变量名 | Secret Key | 说明 |
|--------|------------|------|
| `BLOG_LLM_API_KEY` | `styleferry` → `BLOG_LLM_API_KEY` | DeepSeek API Key |
| `BLOG_BRAVE_API_KEY` | `styleferry` → `BLOG_BRAVE_API_KEY` | Brave Search API Key |
| `BLOG_LANGSMITH_API_KEY` | `styleferry` → `BLOG_LANGSMITH_API_KEY` | LangSmith API Key |
| `BLOG_LANGFUSE_PUBLIC_KEY` | `styleferry` → `BLOG_LANGFUSE_PUBLIC_KEY` | LangFuse 公钥 |
| `BLOG_LANGFUSE_SECRET_KEY` | `styleferry` → `BLOG_LANGFUSE_SECRET_KEY` | LangFuse 密钥 |
| `BLOG_RECALL_API_KEY` | `styleferry` → `BLOG_RECALL_API_KEY` | Recall API Key |

## Entity: ExternalSecret

`templates/secret.yaml` 通过 External Secrets Operator 从 global-secrets ClusterSecretStore 提取 key `styleferry`，生成 Kubernetes Secret `styleferry-secret`（`{{ .Release.Name }}-secret`）。

| 字段 | 值 | 说明 |
|------|-----|------|
| `apiVersion` | `external-secrets.io/v1` | External Secrets Operator API |
| `kind` | `ExternalSecret` | 资源类型 |
| `metadata.name` | `{{ .Release.Name }}-secret` | Secret 名称 |
| `spec.secretStoreRef.kind` | `ClusterSecretStore` | 引用集群级 Secret Store |
| `spec.secretStoreRef.name` | `global-secrets` | 全局 Secret Store 名称 |
| `spec.dataFrom[0].extract.key` | `styleferry` | 要提取的 key |
