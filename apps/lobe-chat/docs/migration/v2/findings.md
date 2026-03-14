# Findings & Decisions
<!--
  WHAT: Your knowledge base for the task. Stores everything you discover and decide.
  WHY: Context windows are limited. This file is your "external memory" - persistent and unlimited.
  WHEN: Update after ANY discovery, especially after 2 view/browser/search operations (2-Action Rule).
-->

## Requirements
<!--
  WHAT: What the user asked for, broken down into specific requirements.
  WHY: Keeps requirements visible so you don't forget what you're building.
  WHEN: Fill this in during Phase 1 (Requirements & Discovery).
  EXAMPLE:
    - Command-line interface
    - Add tasks
    - List all tasks
    - Delete tasks
    - Python implementation
-->
<!-- Captured from user request -->
- 将 Lobe Chat v1 迁移到 v2（生产环境）
- 认证系统变更：从 NextAuth + Casdoor 迁移到 Better Auth
- PostgreSQL 升级：从 pg16 升级到 pg17（推荐版本）
- 环境变量变更：移除 NextAuth 相关变量，添加 Better Auth 必需变量
- 数据库模式变更：v2 仅支持 Server DB 模式（当前已使用此模式）
- 关键约束：生产环境，数据安全第一，零数据丢失
- 域名：west-beta.ts.net
- 当前使用 Tailscale Ingress 和 ExternalServices 进行网络配置
- 所有用户需要重新登录，SSO 连接数据可能会丢失
- 用户确认信息：用户数量≤10，所有用户都有邮箱，继续使用 Casdoor

## Research Findings
<!--
  WHAT: Key discoveries from web searches, documentation reading, or exploration.
  WHY: Multimodal content (images, browser results) doesn't persist. Write it down immediately.
  WHEN: After EVERY 2 view/browser/search operations, update this section (2-Action Rule).
  EXAMPLE:
    - Python's argparse module supports subcommands for clean CLI design
    - JSON module handles file persistence easily
    - Standard pattern: python script.py <command> [args]
-->
<!-- Key discoveries during exploration -->
### v2 迁移要求总结：
1. **认证系统变更**：
   - NextAuth → Better Auth
   - 移除的环境变量：`NEXT_AUTH_SECRET`, `NEXT_AUTH_SSO_PROVIDERS`, `NEXTAUTH_URL`, `NEXT_PUBLIC_ENABLE_NEXT_AUTH`, `AUTH_URL` 等
   - 新增必需变量：`AUTH_SECRET`, `JWKS_KEY`
   - SSO 提供商变量变更：Microsoft Entra ID → microsoft（变量前缀：`AUTH_MICROSOFT_ENTRA_ID_` → `AUTH_MICROSOFT_`）

2. **Casdoor 注意事项**：
   - Better Auth 强依赖用户邮箱，但 Casdoor 不要求用户配置邮箱（用户确认所有用户都有邮箱）
   - 需要确认 Better Auth 是否原生支持 Casdoor 作为 SSO 提供商
   - 如不支持，可能需要使用 OIDC 通用配置或迁移到其他 SSO 提供商

3. **PostgreSQL 升级**：
   - 当前：`pgvector/pgvector:pg16` (PostgreSQL 16)
   - 目标：PostgreSQL 17（推荐 `paradedb/paradedb:latest-pg17`）
   - 原因：v2 使用 `pg_search` 插件提供全文搜索，仅在 PostgreSQL 17 可用

4. **迁移方式**：
   - 简单迁移（≤10用户）：只迁移 `users` 表
   - 用户需要重新登录
   - SSO 连接数据会丢失（可重新绑定）
   - 若用户没有邮箱，可能遇到 `email_not_found` 错误

### 重要发现（用户确认）：
5. **Better Auth 对 Casdoor 的支持**：
   - **原生支持**：Better Auth 原生支持 Casdoor 作为 SSO 提供商
   - **环境变量**：`AUTH_CASDOOR_ID`, `AUTH_CASDOOR_SECRET`, `AUTH_CASDOOR_ISSUER` 无需改变
   - **配置简化**：迁移时可以直接保留现有 Casdoor SSO 配置

### 当前 v1 配置发现（通过读取部署文件）：
1. **PostgreSQL 部署** (`deploy-postgresql.yaml`)：
   - 镜像：`pgvector/pgvector:pg16`
   - 数据库名：`lobechat`
   - 密码通过 Secret `lobe-db-secrets` 的 `PGVECTOR_POSTGRES_PASSWORD` 管理
   - 使用 PVC `postgresql-claim0`

2. **Lobe Chat 部署** (`deploy-lobe.yaml`)：
   - 镜像：`docker.io/lobehub/lobe-chat-database:latest`
   - 端口：3210
   - 认证相关 Secrets：`lobe-auth`
   - 环境变量：
     - `APP_URL`: `https://lobe.west-beta.ts.net`
     - `NEXTAUTH_URL`: `https://lobe.west-beta.ts.net/api/auth`
     - `NEXT_AUTH_SECRET`: 从 Secret 获取
     - `NEXT_AUTH_SSO_PROVIDERS`: `casdoor`
     - `AUTH_CASDOOR_ID`, `AUTH_CASDOOR_SECRET`: 从 Secret 获取
     - `AUTH_CASDOOR_ISSUER`: `https://casdoor.west-beta.ts.net`
   - 其他 Secrets：`lobe-db-secrets`, `lobe-s3-secrets`, `lobe-ai-api-keys`

3. **存储配置**：
   - S3 端点：`https://rustfs.west-beta.ts.net`
   - 存储桶：`lobe`
   - 路径风格：启用

### Phase 1 发现（数据库检查）：
1. **用户数量确认**：
   - 数据库查询结果：2个用户（符合≤10用户的确认）
   - 用户ID和邮箱：
     - `33ca6dfc-15db-4383-895c-49f90539fdbe` | `admin@example.com`
     - `8bc588db-9c23-4d17-a395-b853247e54b7` | `cuikaidong@foxmail.com`

2. **邮箱配置验证**：
   - 所有用户都有邮箱配置（无空邮箱或NULL值）
   - 邮箱格式正常，符合Better Auth要求

3. **Casdoor 配置状态**：
   - Casdoor版本：`casbin/casdoor:v1.840.0`
   - 使用ConfigMap `casdoor-cm0` 进行初始化
   - 数据库连接通过Secret `lobe-db-secrets` 的 `CASDOOR_dataSourceName` 管理
   - 需要进一步验证Casdoor中的用户邮箱验证状态

## Technical Decisions
<!--
  WHAT: Architecture and implementation choices you've made, with reasoning.
  WHY: You'll forget why you made choices. This table preserves that knowledge.
  WHEN: Update whenever you make a significant technical choice.
  EXAMPLE:
    | Use JSON for storage | Simple, human-readable, built-in Python support |
    | argparse with subcommands | Clean CLI: python todo.py add "task" |
-->
<!-- Decisions made with rationale -->
| Decision | Rationale |
|----------|-----------|
| 采用简单迁移方案（只迁移 `users` 表） | 用户确认用户数量≤10，简单迁移方案风险最低，SSO 连接数据可重新绑定 |
| PostgreSQL 升级到 17 并使用 paradedb/paradedb:latest-pg17 | v2 依赖 `pg_search` 插件提供全文搜索功能，该插件仅在 PostgreSQL 17 可用 |
| 保持现有 Casdoor SSO 配置 | 用户确认继续使用 Casdoor，迁移后用户需要重新登录绑定 |
| 分阶段迁移策略 | 降低风险，便于问题定位和回滚 |
| 创建全新的认证 Secrets (lobe-auth-v2) | 隔离新旧认证系统，便于管理和回滚 |
| 保留原有配置备份 | 紧急情况下可快速回滚到 v1 版本 |

## Issues Encountered
<!--
  WHAT: Problems you ran into and how you solved them.
  WHY: Similar to errors in task_plan.md, but focused on broader issues (not just code errors).
  WHEN: Document when you encounter blockers or unexpected challenges.
  EXAMPLE:
    | Empty file causes JSONDecodeError | Added explicit empty file check before json.load() |
-->
<!-- Errors and how they were resolved -->
| Issue | Resolution |
|-------|------------|
| Better Auth 对 Casdoor 支持情况未知 | **已解决**：用户确认 Better Auth 原生支持 Casdoor 作为 SSO 提供商，CASDOOR 相关环境变量无需改变 |
| Casdoor 用户邮箱验证状态未知 | 需要检查 Casdoor 管理界面确认用户邮箱配置和验证状态 |
| 迁移过程中服务中断时间 | 计划在低流量时段执行，分阶段缩短单次中断时间 |

## 备份信息（Phase 1 完成）
<!--
  WHAT: 记录Phase 1完成的备份任务详情和验证计划
  WHY: 备份是迁移的关键步骤，需要详细记录备份内容和验证方法
-->
### 备份文件清单
1. **数据库完整备份**：
   - 文件：`lobechat_v1_backup_20260314_182103.dump`
   - 大小：13M
   - 格式：PostgreSQL custom format (pg_dump -Fc)
   - 内容：完整的lobechat数据库

2. **用户表备份**：
   - 文件：`users_backup_20260314_182200.sql`
   - 大小：2.8K
   - 格式：SQL with INSERTs
   - 内容：仅users表数据，用于简单迁移方案

3. **Kubernetes Secrets备份**：
   - 文件：`secrets_backup_20260314_182304.yaml`
   - 大小：5.7K
   - 内容：lobe-chat命名空间中的所有Secrets

4. **配置文件备份**：
   - `deploy-postgresql.yaml.backup_20260314_182348`
   - `deploy-lobe.yaml.backup_20260314_182348`
   - `deploy-casdoor.yaml.backup_20260314_182348`

### 备份验证计划
1. **数据库备份验证**：
   - **方法**：在测试环境中使用pg_restore恢复备份
   - **验证点**：检查表结构完整性、用户数据存在性
   - **备用方案**：如无法完全恢复，使用用户表SQL文件手动恢复

2. **用户表备份验证**：
   - **已验证**：文件包含2个用户的INSERT语句
   - **注意**：第二个INSERT语句被注释（可能需手动处理）

3. **Secrets备份验证**：
   - **方法**：检查YAML文件结构，确认包含关键Secrets（lobe-auth, lobe-db-secrets等）
   - **验证点**：Secret名称和数量匹配预期

4. **配置备份验证**：
   - **方法**：diff比较备份文件与原始文件
   - **验证点**：配置内容一致，无意外变更

### 恢复测试建议
1. **测试环境准备**：在独立Kubernetes集群或命名空间测试恢复
2. **分阶段测试**：先测试数据库恢复，再测试应用配置
3. **验证时间**：迁移前24小时完成恢复测试
4. **回滚准备**：基于备份文件准备快速回滚脚本

## Resources
<!--
  WHAT: URLs, file paths, API references, documentation links you've found useful.
  WHY: Easy reference for later. Don't lose important links in context.
  WHEN: Add as you discover useful resources.
  EXAMPLE:
    - Python argparse docs: https://docs.python.org/3/library/argparse.html
    - Project structure: src/main.py, src/utils.py
-->
<!-- URLs, file paths, API references -->
- 项目目录：`/home/casey/projects/homelab2/apps/lobe-chat/`
- 关键文件：
  - `deploy-postgresql.yaml` - PostgreSQL 部署配置
  - `deploy-lobe.yaml` - Lobe Chat v1 部署配置
  - `deploy-casdoor.yaml` - Casdoor 部署配置
  - `svc-*.yaml` - 服务配置
  - `ingress-*.yaml` - Ingress 配置
- CLAUDE.md 项目文档：包含项目概述、常用命令、架构说明

## Visual/Browser Findings
<!--
  WHAT: Information you learned from viewing images, PDFs, or browser results.
  WHY: CRITICAL - Visual/multimodal content doesn't persist in context. Must be captured as text.
  WHEN: IMMEDIATELY after viewing images or browser results. Don't wait!
  EXAMPLE:
    - Screenshot shows login form has email and password fields
    - Browser shows API returns JSON with "status" and "data" keys
-->
<!-- CRITICAL: Update after every 2 view/browser operations -->
<!-- Multimodal content must be captured as text immediately -->
- 无视觉内容需要记录

---
<!--
  REMINDER: The 2-Action Rule
  After every 2 view/browser/search operations, you MUST update this file.
  This prevents visual information from being lost when context resets.
-->
*Update this file after every 2 view/browser/search operations*
*This prevents visual information from being lost*