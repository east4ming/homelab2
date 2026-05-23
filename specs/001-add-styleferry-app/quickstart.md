# Quickstart: 部署 StyleFerry

**Feature**: 001-add-styleferry-app
**Date**: 2026-05-22

## 前置条件

1. K3s 集群已部署 ArgoCD + ApplicationSet
2. External Secrets Operator 已安装
3. `global-secrets` ClusterSecretStore 已配置
4. Tailscale Operator 已安装
5. 已在 `global-secrets` 后端存储中添加 `styleferry` key（包含所有敏感环境变量）

## 部署步骤

### 1. 准备 Secret 数据

在 `global-secrets` 对应的 Secret 后端（如 GCP Secret Manager、Vault 等）中添加 key `styleferry`，内容为 JSON：

```json
{
  "BLOG_LLM_API_KEY": "sk-...",
  "BLOG_BRAVE_API_KEY": "...",
  "BLOG_LANGSMITH_API_KEY": "lsv2_pt_c...",
  "BLOG_LANGFUSE_PUBLIC_KEY": "...",
  "BLOG_LANGFUSE_SECRET_KEY": "...",
  "BLOG_RECALL_API_KEY": "sk_..."
}
```

### 2. 推送 Chart 到 Git

```bash
git add apps/styleferry/
git commit -m "feat: add styleferry helm chart"
git push origin 001-add-styleferry-app
```

### 3. ArgoCD 自动同步

ArgoCD ApplicationSet 扫描 `apps/styleferry/`，自动创建 Application 并同步。同步完成后 Pod 启动。

### 4. 验证部署

```bash
# 检查 Pod 状态
kubectl get pods -l app.kubernetes.io/instance=styleferry

# 检查 ExternalSecret 状态
kubectl get externalsecret styleferry-secret

# 冒烟测试
curl -I https://styleferry.west-beta.ts.net
```

预期：HTTP 200

### 5. 注册到 Homepage

编辑 `apps/homepage/values.yaml`，在 `config.services` 中新增：

```yaml
- AI Tools:
    - StyleFerry:
        href: https://styleferry.west-beta.ts.net
        description: AI-powered blog generation service
        icon: si-styleferry  # 或自定义图标
```

### 6. 更新冒烟测试

在 `make smoke-test` 中添加对 `https://styleferry.west-beta.ts.net` 的 200 检查。

## 故障排查

| 症状 | 可能原因 | 解决 |
|------|----------|------|
| Pod CrashLoopBackOff | Secret `styleferry-secret` 未创建 | 检查 ExternalSecret 状态，确认 global-secrets 中有 `styleferry` key |
| 502 Bad Gateway | 健康检查端口不匹配 | 确认 `service.ports.http.port` 为 8000 |
| PVC Pending | 存储类不可用 | 确认 Ceph/Rook 集群正常，检查 `persistence.data.storageClass` |
