<!--
  Sync Impact Report
  ==================
  Version change: [unversioned template] → 1.0.0
  Bump rationale: MAJOR - Initial ratification of project constitution with 5 core
    principles, 2 additional sections, and governance rules.

  Modified principles (from template placeholders):
    [PRINCIPLE_1_NAME] → I. 代码质量 (Code Quality)
    [PRINCIPLE_2_NAME] → II. 测试标准 (Testing Standards)
    [PRINCIPLE_3_NAME] → III. 用户体验一致性 (User Experience Consistency)
    [PRINCIPLE_4_NAME] → IV. 性能要求 (Performance Requirements)
    [PRINCIPLE_5_NAME] → V. 优先使用中文 (Chinese First)

  Added sections:
    - 安全与合规约束 (Security & Compliance Constraints)
    - 开发与部署工作流 (Development & Deployment Workflow)
    - Governance (filled from template placeholder)

  Removed sections: None (all template sections retained and filled)

  Templates requiring updates:
    - .specify/templates/plan-template.md      ✅ No changes needed (generic Constitution Check section)
    - .specify/templates/spec-template.md       ✅ No changes needed (generic placeholders)
    - .specify/templates/tasks-template.md      ✅ No changes needed (generic task structure)
    - .specify/templates/checklist-template.md  ✅ No changes needed (generic checklist)

  Follow-up TODOs: None
-->

# Homelab2 Constitution

## Core Principles

### I. 代码质量 (Code Quality)

所有代码变更在合入前必须通过自动化质量门禁。代码质量是不可协商的底线。

- **所有 YAML 必须通过 `yamllint`** — 由 `.pre-commit-config.yaml` 和 CI `static-checks` 强制执行
- **所有 Helm Chart 必须通过 `helmlint`** — pre-commit hook 自动校验
- **所有 Shell 脚本必须通过 `shellcheck`** — pre-commit hook 强制检查，`#!/bin/bash` shebang 为必选项
- **OpenTofu 代码必须通过 `tofu_fmt`** — pre-commit hook，提交前自动格式化
- **禁止提交大文件、私钥、合并冲突标记** — pre-commit hooks 包括 `check-added-large-files`、`detect-private-key`、`check-merge-conflict`
- **统一行尾与空白** — `end-of-file-fixer` + `trailing-whitespace` + `mixed-line-ending`

### II. 测试标准 (Testing Standards)

测试是合入的硬性门禁，不可跳过。遵循 TDD 流程确保代码质量。

- **冒烟测试是合入的硬性门禁** — `make smoke-test` 必须验证 ArgoCD、Gitea、Grafana、Homepage、Kanidm 均返回 HTTP 200
- **工具版本约束必须满足** — `tools_test.go` 校验 9 个 CLI 工具（ansible、kubectl、helm、tofu 等）的版本
- **Terraform/OpenTofu 必须通过 `validate`** — `external_test.go` 确保 Infrastructure-as-Code 语法正确
- **完整测试套件必须通过** — `make test` 超时 30 分钟，全部通过才能标记任务完成
- **存储变更需配合 benchmark 验证** — 使用 `dbench-rwo.yaml` / `dbench-rwx.yaml` 验证 Ceph 性能
- **TDD 流程** — Explore → Plan → Write test cases → Code → Test → Commit

### III. 用户体验一致性 (User Experience Consistency)

所有面向用户的服务必须遵循统一的接入、认证和入口规范。

- **所有服务统一通过 Tailscale Ingress 暴露** — 不引入其他 Ingress Controller；ingress class 固定为 `tailscale`
- **统一使用 MagicDNS 域名** — 域名模式 `*.west-beta.ts.net`，不硬编码 IP
- **所有应用入口归集到 Homepage 仪表盘** — 每新增一个 app 必须在 `apps/homepage/` 中注册
- **需要认证的服务必须接入 Kanidm SSO / Dex OIDC** — 禁止独立认证系统，统一身份源
- **Helm values 遵循命名一致性** — `ingress.hosts`、`resources.requests/limits`、`persistence.storageClass` 字段名统一
- **Secret 永远不提交到仓库** — 使用 External Secrets Operator、Ansible Vault 或 Terraform 管理

### IV. 性能要求 (Performance Requirements)

集群资源有限，性能调优已经过针对硬件的精细调整，不可随意修改。

- **每个工作负载必须显式设置 `resources.requests` 和 `resources.limits`** — 不允许"无限制"的 Pod；参照现有基线（CSI sidecar 1-5m CPU，Prometheus 160m/4Gi 等）
- **Cilium eBPF 优化必须保持开启** — BPF masquerade、DSR、netkit datapath、no-conntrack — 禁止回退到 iptables 模式
- **BBR 拥塞控制 + Bandwidth Manager 必须保持** — 已在 Cilium 中配置，不得关闭
- **Ceph 副本数维持 2（不增不减）** — 4 节点集群的冗余与容量最佳平衡点
- **etcd 心跳/选举超时等 K3s 参数不可随意修改** — 已针对 N100 硬件调优
- **新服务引入前评估资源影响** — 4 × N100 mini-host 总资源有限（共约 64-128GB RAM），新服务必须合理申请资源
- **优先使用 SQLite / 内嵌存储** — 如 Gitea 使用 SQLite 而非外部 PostgreSQL，减少运维复杂度与资源消耗

### V. 优先使用中文 (Chinese First)

项目文档、代码注释、提交信息和讨论优先使用中文。

- 所有设计文档、spec、plan 使用中文编写
- 代码注释和提交信息使用中文
- 与项目相关的沟通优先使用中文
- 对外接口文档和技术规范可同时提供中英文版本

## 安全与合规约束 (Security & Compliance Constraints)

安全是不可妥协的底线。所有敏感信息必须通过安全的机制管理。

- **Secret 永远不提交到仓库** — 任何形式的密码、API Key、Token、私钥不得以明文形式出现在 Git 历史中
- **敏感信息管理** — 使用 External Secrets Operator 与外部密钥管理系统集成；Ansible Vault 用于 Ansible playbook 中的敏感变量；Terraform/OpenTofu 敏感变量使用 `sensitive = true` 标记
- **预提交安全检查** — `detect-private-key` hook 阻止私钥提交；`check-merge-conflict` hook 阻止未解决的合并冲突进入仓库
- **网络安全** — 所有服务入口统一通过 Tailscale 零信任网络暴露，不对外公开端口
- **身份认证统一** — 所有需要认证的服务必须通过 Kanidm SSO 或 Dex OIDC 接入，禁止各服务独立维护用户系统

## 开发与部署工作流 (Development & Deployment Workflow)

所有变更是声明式的、可审计的、通过 Git 追溯的。

- **通过 ArgoCD ApplicationSet 部署所有资源** — 严禁手动 `kubectl apply`；所有变更必须经过 Git → ArgoCD 的 GitOps 流程
- **每个 `system/`、`platform/`、`apps/` 目录必须包含 `Chart.yaml` + `values.yaml`** — 这是 ApplicationSet 自动发现的基础契约
- **Git 分支策略** — 使用简化的 GitHub Flow（feature branch → PR → master）
- **TDD 流程强制** — 三步以上任务必须先输出计划；Explore → Plan → Write test cases → Code → Test → Commit
- **先读后写** — 修改文件前必须先读取现有代码，理解上下文

## Governance

本 Constitution 是项目开发的最高准则，所有变更、PR 和设计决策必须符合其规定。

- **修订流程** — 修订需通过 PR 提交，注明修订理由和影响范围，经审查后合入
- **版本管理** — 遵循语义化版本：MAJOR（不兼容的原则移除/重新定义）、MINOR（新增原则/章节）、PATCH（措辞澄清、拼写修正）
- **合规审查** — 每次 Code Review 需对照 Constitution 检查合规性；复杂性增加必须在 plan.md 中明确说明理由
- **运行时指引** — 详细开发指引参见项目 `CLAUDE.md` 和各 `apps/*/CLAUDE.md` 文件

**Version**: 1.0.0 | **Ratified**: 2026-05-22 | **Last Amended**: 2026-05-22
