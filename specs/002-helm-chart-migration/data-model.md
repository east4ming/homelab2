# Data Model: Raw Manifests to Helm Chart Migration

**Feature**: 002-helm-chart-migration
**Date**: 2026-05-24

## 关键实体

### Helm Chart

| 属性 | 说明 |
|------|------|
| `Chart.yaml: apiVersion` | `v2` — Helm 3 标准 |
| `Chart.yaml: name` | 与目录名一致（`rsshub` / `lobe-chat`） |
| `Chart.yaml: version` | `0.1.0` — 初始版本 |
| `Chart.yaml: appVersion` | `1.0.0` — 占位值（无实际意义） |
| `dependencies` | 空（不依赖任何第三方 chart） |

### Helm Chart 资源清单

#### rsshub (namespace: rsshub)

| 文件 | Kind | Name |
|------|------|------|
| `ns.yaml` | Namespace | rsshub |
| `deploy-rsshub.yaml` | Deployment | rsshub |
| `deploy-browserless.yaml` | Deployment | browserless |
| `deploy-database-postgres.yaml` | Deployment | database-postgres |
| `deploy-redis.yaml` | Deployment | redis |
| `deploy-service-mercury.yaml` | Deployment | service-mercury |
| `deploy-service-opencc.yaml` | Deployment | service-opencc |
| `deploy-service-rss.yaml` | Deployment | service-rss |
| `service-rsshub.yaml` | Service | rsshub |
| `service-browserless.yaml` | Service | browserless |
| `service-database-postgres.yaml` | Service | database-postgres |
| `service-database-postgres-np.yaml` | Service | database-postgres-np (NodePort) |
| `service-redis.yaml` | Service | redis |
| `service-external-rsshub.yaml` | Service | egress-rss (ExternalName) |
| `service-service-mercury.yaml` | Service | service-mercury |
| `service-service-opencc.yaml` | Service | service-opencc |
| `service-service-rss.yaml` | Service | service-rss |
| `ingress-rsshub.yaml` | Ingress | rsshub |
| `ingress-ttrss.yaml` | Ingress | ttrss |
| `pvc-database-postgres-claim0.yaml` | PersistentVolumeClaim | database-postgres-claim0 (2Gi) |
| `pvc-feed-icons.yaml` | PersistentVolumeClaim | feed-icons (10Mi) |
| `pvc-redis-data.yaml` | PersistentVolumeClaim | redis-data (100Mi) |

#### lobe-chat (namespace: lobe-chat)

| 文件 | Kind | Name |
|------|------|------|
| `deploy-lobe.yaml` | Deployment | lobe |
| `deploy-casdoor.yaml` | Deployment | casdoor |
| `deploy-postgresql.yaml` | Deployment | postgresql |
| `deploy-redis.yaml` | Deployment | lobe-redis |
| `svc-lobe.yaml` | Service | lobe |
| `svc-casdoor.yaml` | Service | casdoor |
| `svc-postgresql.yaml` | Service | postgresql |
| `svc-redis.yaml` | Service | redis |
| `svc-egress-lobe.yaml` | Service | egress-lobe (ExternalName) |
| `svc-egress-casdoor.yaml` | Service | egress-casdoor (ExternalName) |
| `svc-egress-rustfs.yaml` | Service | egress-rustfs (ExternalName) |
| `ingress-lobe.yaml` | Ingress | lobe |
| `ingress-casdoor.yaml` | Ingress | casdoor |
| `pvc-postgresql-claim1.yaml` | PersistentVolumeClaim | postgresql-claim1 (10Gi, standard-rwo) |
| `pvc-redis.yaml` | PersistentVolumeClaim | redis-data-pvc (1Gi) |

### 外部依赖（不在 chart 内管理）

| 资源 | 引用方式 | 说明 |
|------|----------|------|
| `rsshub-secret` | `secretKeyRef` | RSSHub ACCESS_KEY |
| `postgres-secret` | `secretKeyRef` | PostgreSQL 密码 |
| `lobe-auth` | `secretKeyRef` | Casdoor OAuth 配置 |
| `lobe-db-secrets` | `secretKeyRef` | PostgreSQL 连接字符串 |
| `lobe-s3-secrets` | `secretKeyRef` | S3 存储凭证 |
| `lobe-ai-api-keys` | `secretKeyRef` | AI API keys |
| `casdoor-cm0` | ConfigMap `configMapKeyRef` | Casdoor 初始化数据（已存在于集群中） |

## 状态转换

不适用。此次变更不引入新的状态管理，仅改变打包格式。

## 验证约束

- `helm lint <chart-path>` 通过（无 error、无 warning）
- `helm template --namespace <ns> <name> <chart-path>` 正常渲染，退出码 0
- `dyff between` 原始 renders 与 Helm template 输出仅显示 label 差异
