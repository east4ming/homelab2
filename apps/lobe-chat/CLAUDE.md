# Lobe Chat Kubernetes Deployment

K8s manifests for self-hosting Lobe Chat (AI chatbot) with Casdoor auth, PostgreSQL + pgvector, and S3-compatible storage.

## 技术栈

- Kubernetes (homelab + Tailscale)
- PostgreSQL + pgvector
- Casdoor (SSO/OIDC)

## 常用命令

| 用途 | 命令 |
| :--- | :--- |
| 部署全部 | 通过 ArgoCD 自动部署 |
| 查看状态 | `kubectl get pods -n lobe-chat -w` |
| 重启服务 | `kubectl rollout restart deployment/lobe -n lobe-chat` |

## 目录架构

| 路径 | 职责 |
| :--- | :--- |
| `deploy-*.yaml` | 各组件 Deployment |
| `svc-*.yaml` | 内部 Service |
| `svc-egress-*.yaml` | Tailscale 外部访问 |
| `ingress-*.yaml` | Tailscale Ingress |

## 行动原则

- **强制规划**：3步以上任务必须先输出计划。
- **强制验证**：必须通过测试证明代码能运行，才能标记完成。
- **先读后写**：修改前必须先阅读现有代码。
- **及时止损**：多次失败或上下文逼近极限时，主动停止并请求人类介入。

## 关键注意事项

- Secrets 不提交仓库，需外部管理
- S3 存储需桶匿名读权限（前端文件展示用）
- PostgreSQL PVC 大小可在 `pvc-postgresql.yaml` 调整
