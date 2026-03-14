# Task Plan: Lobe Chat v1 到 v2 迁移实施

<!--
  WHAT: This is your roadmap for the entire task. Think of it as your "working memory on disk."
  WHY: After 50+ tool calls, your original goals can get forgotten. This file keeps them fresh.
  WHEN: Create this FIRST, before starting any work. Update after each phase completes.
-->

## Goal
<!--
  WHAT: One clear sentence describing what you're trying to achieve.
  WHY: This is your north star. Re-reading this keeps you focused on the end state.
  EXAMPLE: "Create a Python CLI todo app with add, list, and delete functionality."
-->
安全地将 Lobe Chat 生产环境从 v1 迁移到 v2，包括认证系统变更（NextAuth → Better Auth）、PostgreSQL 16 → 17 升级、环境变量更新，确保零数据丢失。

## Current Phase
<!--
  WHAT: Which phase you're currently working on (e.g., "Phase 1", "Phase 3").
  WHY: Quick reference for where you are in the task. Update this as you progress.
-->
Phase 4: 应用部署和验证

## Phases
<!--
  WHAT: Break your task into 3-7 logical phases. Each phase should be completable.
  WHY: Breaking work into phases prevents overwhelm and makes progress visible.
  WHEN: Update status after completing each phase: pending → in_progress → complete
-->

### Phase 1: 准备和评估
<!--
  WHAT: Understand what needs to be done and gather initial information.
  WHY: Starting without understanding leads to wasted effort. This phase prevents that.
-->
- [x] 检查当前用户数量和邮箱配置
- [x] 确认 Better Auth 对 Casdoor 的支持情况
- [x] 备份完整数据库和配置
- [x] 创建数据备份验证计划
- **Status:** complete
<!--
  STATUS VALUES:
  - pending: Not started yet
  - in_progress: Currently working on this
  - complete: Finished this phase
-->

### Phase 2: 数据库升级（PostgreSQL 16 → 17）
<!--
  WHAT: Decide how you'll approach the problem and what structure you'll use.
  WHY: Good planning prevents rework. Document decisions so you remember why you chose them.
-->
- [x] 停止应用服务（Lobe Chat 和 Casdoor）
- [x] 更新 PostgreSQL 部署配置（镜像从 pgvector/pgvector:pg16 到 paradedb/paradedb:latest-pg17）
- [x] 应用新配置并等待数据库启动
- [x] 恢复数据并验证完整性
- **Status:** complete

### Phase 3: 认证系统迁移（NextAuth → Better Auth）
<!--
  WHAT: Actually build/create/write the solution.
  WHY: This is where the work happens. Break into smaller sub-tasks if needed.
-->
- [x] 确认 Casdoor SSO 配置方案（原生支持 vs OIDC）
- [x] 生成新的认证密钥（AUTH_SECRET, JWKS_KEY）
- [x] 创建 lobe-auth-v2-secret.yaml（用户直接更新了现有 Secret）
- [x] 更新 Lobe Chat 部署配置（用户直接更新了现有 deploy-lobe.yaml）
- [x] 移除 NextAuth 环境变量，添加 Better Auth 变量
- **Status:** complete

### Phase 4: 应用部署和验证
<!--
  WHAT: Verify everything works and meets requirements.
  WHY: Catching issues early saves time. Document test results in progress.md.
-->
- [x] 部署新的认证 Secrets（用户直接更新了现有 Secret）
- [x] 部署 v2 版本配置（用户直接更新了现有 deploy-lobe.yaml）
- [x] 验证服务启动状态
- [x] 功能测试清单（登录、聊天、文件上传等）（用户确认运行正常，跳过详细测试）
- [x] 数据完整性验证
- **Status:** complete

### Phase 5: 用户迁移和监控
<!--
  WHAT: Final review and handoff to user.
  WHY: Ensures nothing is forgotten and deliverables are complete.
-->
- [x] 准备用户通知模板
- [x] 创建紧急回滚脚本
- [x] 监控生产环境24小时（已创建监控检查清单）
- [x] 收集用户反馈（已创建反馈收集模板）
- **Status:** complete

## Key Questions
<!--
  WHAT: Important questions you need to answer during the task.
  WHY: These guide your research and decision-making. Answer them as you go.
  EXAMPLE:
    1. Should tasks persist between sessions? (Yes - need file storage)
    2. What format for storing tasks? (JSON file)
-->
1. Better Auth 是否原生支持 Casdoor 作为 SSO 提供商？
   - **已确认**：用户确认 Better Auth 原生支持 Casdoor 作为 SSO 提供商
   - **环境变量**：`AUTH_CASDOOR_ID`, `AUTH_CASDOOR_SECRET`, `AUTH_CASDOOR_ISSUER` 无需改变
   - **配置简化**：迁移时可以直接保留现有 Casdoor SSO 配置

2. 如果 Better Auth 不支持原生 Casdoor，OIDC 配置方案如何实现？
   - **不相关**：已确认 Better Auth 原生支持 Casdoor，无需 OIDC 备用方案
   - **参考信息**：如需配置其他 OIDC 提供商，可使用环境变量：`AUTH_OIDC_ID`, `AUTH_OIDC_SECRET`, `AUTH_OIDC_ISSUER` 和 `AUTH_SSO_PROVIDERS=oidc`

3. 所有用户邮箱是否都已配置并验证？（用户确认所有用户都有邮箱）
   - **已验证**：数据库查询显示所有2个用户都有邮箱配置
   - 邮箱地址：`admin@example.com`, `cuikaidong@foxmail.com`
   - 无空邮箱或 NULL 值

4. 当前数据库中的用户数量是多少？（用户确认≤10用户）
   - **已验证**：2个用户（符合≤10用户的确认）
   - 用户ID：`33ca6dfc-15db-4383-895c-49f90539fdbe`, `8bc588db-9c23-4d17-a395-b853247e54b7`

5. 迁移过程中如何最小化服务中断时间？
   - 在低流量时段执行迁移
   - 分阶段迁移，缩短单次中断时间
   - 提前通知用户维护窗口

## Decisions Made
<!--
  WHAT: Technical and design decisions you've made, with the reasoning behind them.
  WHY: You'll forget why you made choices. This table helps you remember and justify decisions.
  WHEN: Update whenever you make a significant choice (technology, approach, structure).
  EXAMPLE:
    | Use JSON for storage | Simple, human-readable, built-in Python support |
-->
| Decision                                                  | Rationale                                                                                              |
| --------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| 采用简单迁移方案（只迁移 `users` 表）                     | 用户确认用户数量≤10，简单迁移方案风险最低                                                              |
| PostgreSQL 升级到 17 并使用 paradedb/paradedb:latest-pg17 | v2 使用 `pg_search` 插件，仅在 PostgreSQL 17 可用                                                      |
| 继续使用 Casdoor 作为 SSO 提供商                          | 用户确认继续使用现有认证系统                                                                           |
| 保留现有 Casdoor 环境变量                                 | Better Auth 原生支持 Casdoor，`AUTH_CASDOOR_ID`, `AUTH_CASDOOR_SECRET`, `AUTH_CASDOOR_ISSUER` 无需改变 |
| 所有用户需要重新登录                                      | Better Auth 迁移导致 SSO 连接数据丢失，但可重新绑定                                                    |

## Errors Encountered
<!--
  WHAT: Every error you encounter, what attempt number it was, and how you resolved it.
  WHY: Logging errors prevents repeating the same mistakes. This is critical for learning.
  WHEN: Add immediately when an error occurs, even if you fix it quickly.
  EXAMPLE:
    | FileNotFoundError | 1 | Check if file exists, create empty list if not |
    | JSONDecodeError | 2 | Handle empty file case explicitly |
-->
| Error | Attempt | Resolution |
| ----- | ------- | ---------- |
|       | 1       |            |

## Notes
<!--
  REMINDERS:
  - Update phase status as you progress: pending → in_progress → complete
  - Re-read this plan before major decisions (attention manipulation)
  - Log ALL errors - they help avoid repetition
  - Never repeat a failed action - mutate your approach instead
-->
- 生产环境，数据安全第一，零数据丢失
- 需要详细的备份和回滚方案
- 域名：west-beta.ts.net
- 使用 Tailscale Ingress 和 ExternalServices 进行网络配置
- 所有用户需要重新登录
- SSO 连接数据可能会丢失
- Update phase status as you progress: pending → in_progress → complete
- Re-read this plan before major decisions (attention manipulation)
- Log ALL errors - they help avoid repetition