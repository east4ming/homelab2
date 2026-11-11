# Specification Quality Checklist: 以 Helm Chart 在 homelab2 安装 DeepSeek Harness

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-11-11
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

- 本文档按 homelab2 既有 spec 风格编写（参见 013/014）：平台与工具是用户明确施加的运维约束（Helm、
  Tailscale、PVC、镜像 tag），因此「无实现细节」按「不预设内部代码结构」理解，而不是删除这些约束。
- 高影响默认选择已记录在 Assumptions，供规划前确认：Web/桌面 Ingress 主机名、API Key 路由、市场镜像版本
  策略、skills 通过本机→PVC 同步而非 GitOps、配置通过本机 `gh`/`~/.dsh` + `kubectl cp` 手动同步、noVNC
  无认证仅 tailnet 暴露、四种 PVC 备份由用户后续手动配置。任何一项改变都不影响其余需求，但会影响实施细节。
- 验证过的关键事实：上游 Chart 无 Ingress/额外卷；上游 Service 是 Headless，Tailscale L7 Ingress 要求
  ClusterIP 后端；`networkPolicy.ingress: []` 为 deny-all；Tailscale 代理位于 `tailscale` 命名空间且标签为
  `parent-resource-type=proxygroup` / `parent-resource=ingress-proxies`；镜像
  `0.2.2-rc.1-r1-market.1` 存在；mise registry 提供 atuin，且 mise 的 token 优先级原生包含
  `GITHUB_API_TOKEN`；pnpm 10.15.1 忽略 `allowBuilds` 但支持 `onlyBuiltDependencies`。
- `east4ming/dsh-config` 是私有仓库，但同步在维护者本机完成（`gh` 已认证或直接读 `~/.dsh`），集群内不需要
  配置仓库凭据；homelab2 是 public 仓库，skills 内容与配置凭据都不得提交。
- 四块 PVC 是后续手动备份对象；本特性不配置 VolSync/备份策略，也不得在 `scripts/backup-coverage` 中添加豁免。
- noVNC 无认证是显式接受的：仅通过 Tailscale Ingress 暴露，公网不可达，且 tailnet 只有维护者一人使用；
  Tailscale ACL 是唯一网络边界。
- 当前 shell 中 `DEEPSEEK_API_KEY`、`GITHUB_API_TOKEN` 未设置；部署时需在具备这两个变量的 shell 中执行
  bootstrap，否则脚本应按 FR-005 失败而不是创建空 Secret。
