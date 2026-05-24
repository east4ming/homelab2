# Quickstart: Helm Chart 迁移验证

**Feature**: 002-helm-chart-migration

## 验证步骤

### 1. Helm Lint

```bash
helm lint apps/rsshub
helm lint apps/lobe-chat
```

期望输出：`0 chart(s) linted, 0 chart(s) failed`

### 2. Helm Template 渲染

```bash
helm template --namespace rsshub rsshub apps/rsshub > /tmp/rsshub-rendered.yaml
helm template --namespace lobe-chat lobe-chat apps/lobe-chat > /tmp/lobe-chat-rendered.yaml
```

期望：退出码 0，输出包含所有预期的 Kubernetes 资源

### 3. 与原始 Manifests 对比

```bash
# 原始 manifests（通过 cat 拼接为单个 YAML）
cat apps/rsshub/*.yaml > /tmp/rsshub-original.yaml
cat apps/lobe-chat/*.yaml > /tmp/lobe-chat-original.yaml

# 对比（期望：仅 label/annotation 差异）
dyff between /tmp/rsshub-original.yaml /tmp/rsshub-rendered.yaml
dyff between /tmp/lobe-chat-original.yaml /tmp/lobe-chat-rendered.yaml
```

### 4. 资源计数验证

```bash
# rsshub: 应有 22 个 resource
grep -c '^kind:' /tmp/rsshub-rendered.yaml   # → 22
# lobe-chat: 应有 15 个 resource
grep -c '^kind:' /tmp/lobe-chat-rendered.yaml # → 15
```

### 5. CI 模拟验证

```bash
./scripts/helm-diff --repository <repo-url> --source 002-helm-chart-migration --target master --subpath apps
```

期望：仅对 rsshub 和 lobe-chat 显示 label 差异，无 error。

## 回滚方式

如果迁移后出现问题，直接 revert commit 即可恢复原始 manifests 结构。由于渲染输出在 spec 层面一致，ArgoCD 不会产生额外同步操作。
