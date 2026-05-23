# StyleFerry Helm Chart Contract

**Feature**: 001-add-styleferry-app
**Version**: 1.0.0

## Values Interface

StyleFerry Helm Chart 基于 `bjw-s-labs/app-template` v5.0.1，遵循其 values schema。以下是 StyleFerry 特定的约定：

### 必填值

```yaml
app-template:
  controllers:
    main:
      containers:
        main:
          image:
            repository: registry.cn-hangzhou.aliyuncs.com/caseycui/styleferry
            tag: 1.0.0
          envFrom:
            - secret: "{{ .Release.Name }}-secret"
  service:
    main:
      controller: main
      ports:
        http:
          port: 8000
  ingress:
    main:
      enabled: true
      className: tailscale
  persistence:
    data:
      accessMode: ReadWriteOnce
      advancedMounts:
        main:
          main:
            - path: /data
```

### Secret Contract

ExternalSecret 期望从 `global-secrets` ClusterSecretStore 提取 key `styleferry`，输出的 Kubernetes Secret 必须包含以下 key：

| Key | 说明 |
|-----|------|
| `BLOG_LLM_API_KEY` | DeepSeek API Key |
| `BLOG_BRAVE_API_KEY` | Brave Search API Key |
| `BLOG_LANGSMITH_API_KEY` | LangSmith API Key |
| `BLOG_LANGFUSE_PUBLIC_KEY` | LangFuse 公钥 |
| `BLOG_LANGFUSE_SECRET_KEY` | LangFuse 密钥 |
| `BLOG_RECALL_API_KEY` | Recall API Key |

### Ingress Contract

- Class: `tailscale`
- Annotation: `tailscale.com/proxy-group: ingress-proxies`
- Host: `styleferry.west-beta.ts.net`
- TLS: 自动（Tailscale Operator 管理证书）

### Persistence Contract

- `/data` → PVC（ReadWriteOnce）
- SQLite DB: `/data/blog_system.db`
- Cache dir: `/data/cache`
