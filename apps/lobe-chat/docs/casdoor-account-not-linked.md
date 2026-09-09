# Casdoor 登录报 account_not_linked 修复记录

**日期**: 2026-09-09
**影响版本**: `lobehub/lobehub:2.2.9`（内置 better-auth 1.6.15）
**受影响账号**: `admin@example.com`（`users.id = 33ca6dfc-15db-4383-895c-49f90539fdbe`）

## 现象

Casdoor 自身登录正常，但经 Casdoor 回跳到 LobeChat 后落在：

```
https://lobe.west-beta.ts.net/auth-error?error=account_not_linked
```

页面显示「登录遇到问题 … ErrorCode: account_not_linked」。Lobe 容器日志：

```
ERROR [Better Auth]: account_not_linked
```

## 根因

三个条件同时成立才会触发，缺一不可：

1. **better-auth 升级引入了新的门禁**。LobeChat 2.2.6 内置 better-auth **1.4.6**，2.2.9 升到 **1.6.15**。1.6.x 在「按邮箱隐式关联账号」（implicit account linking）时多了一道本地邮箱验证检查：

   ```js
   const requireLocalEmailVerified = accountLinking?.requireLocalEmailVerified ?? true;
   if (
     (!isTrustedProvider && !userInfo.emailVerified) ||
     (requireLocalEmailVerified && !dbUser.user.emailVerified) || // ← 2.2.9 新增
     accountLinking?.enabled === false ||
     accountLinking?.disableImplicitLinking === true
   ) {
     return { error: "account not linked" }; // → redirectOnError(...) 转成 account_not_linked
   }
   ```

   LobeChat 只设置了 `allowDifferentEmails / enabled / trustedProviders`，**没有**设置 `requireLocalEmailVerified`，因此取默认值 `true`。1.4.6 的门禁只有 `(!isTrustedProvider && !userInfo.emailVerified) || enabled === false`，而 `casdoor` 在 `trustedProviders` 里，所以 2.2.6 及以前可以正常登录——这就是「升级到 2.2.9 之后才开始报错」的原因。

2. **本地用户行没有邮箱验证标记**。`users.email_verified = false`、`email_verified_at = NULL`（NextAuth 时代迁移过来一直如此），所以第 1 条的门禁必然命中。

3. **Casdoor 账号链接失效，被迫走邮箱隐式关联**。`accounts` 表里 `casdoor` 的 9 条历史链接的 `account_id` 都是旧值，而 Casdoor 数据库在 2026-09-05 重建后 `admin` 的 id 变成 `176e931f-a71e-4e7d-bb13-0a09d8d9c71a`，没有任何一条链接能匹配。只有当没有匹配链接时，better-auth 才会退化为「按邮箱找用户 + 隐式关联」，于是撞上第 1 条的门禁。

> 环境变量无法绕过：LobeChat 未暴露 `requireLocalEmailVerified`，构建产物里 `accountLinking` 只有 `allowDifferentEmails:true, enabled:true, trustedProviders`（可用 `grep -o "accountLinking:{[^}]*}" /app/.next/server/chunks/*.js` 确认）。

## 诊断命令

```bash
# 1. 确认日志里的错误码
kubectl -n lobe-chat logs deploy/lobe --tail=50 | grep -i better

# 2. 本地用户行
kubectl -n lobe-chat exec deploy/postgresql -- psql -U postgres -d lobechat -c \
  "select id, email, email_verified, email_verified_at from users;"

# 3. 已有的 casdoor 链接
kubectl -n lobe-chat exec deploy/postgresql -- psql -U postgres -d lobechat -c \
  "select account_id, user_id, created_at from accounts where provider_id = 'casdoor' order by created_at;"

# 4. Casdoor 当前用户 id（与第 3 步对比，不一致即为链接失效）
kubectl -n lobe-chat exec deploy/postgresql -- psql -U postgres -d casdoor -c \
  "select name, id, email, email_verified from \"user\";"
```

## 修复

把本地用户行标记为邮箱已验证，让 better-auth 恢复「按邮箱隐式关联」：

```sql
UPDATE users
SET email_verified    = true,
    email_verified_at = COALESCE(email_verified_at, now())
WHERE id = '33ca6dfc-15db-4383-895c-49f90539fdbe';
```

```bash
kubectl -n lobe-chat exec deploy/postgresql -- psql -U postgres -d lobechat -c \
  "UPDATE users SET email_verified = true, email_verified_at = COALESCE(email_verified_at, now()) WHERE id = '33ca6dfc-15db-4383-895c-49f90539fdbe';"
```

不需要重启 Pod，改完直接重新登录即可。

**为什么改本地用户行，而不是手工插 `accounts` 行**：改 `email_verified` 后，首次登录会由 better-auth 自动补写当前 Casdoor 用户 id 的 `accounts` 行；即使 Casdoor 将来再次重建、id 再次变化，也仍然能按邮箱重新关联。手工插 `accounts` 行只是补上这一次的 id，Casdoor id 再变就会复发。

**副作用评估**：该用户 `accounts` 表里没有任何 `password` 行（只能走 Casdoor SSO 登录），且 `AUTH_EMAIL_VERIFICATION` 未开启，因此标记 `email_verified = true` 不会额外放开邮箱密码登录路径。

## 验证（2026-09-09 实测）

用 headless Chrome 跑完整 OIDC 流程（`/api/auth/sign-in/oauth2` → Casdoor 授权页点选 admin → 回跳 LobeChat）：

| 项目 | 修复前 | 修复后 |
| :--- | :--- | :--- |
| 落点 URL | `/auth-error?error=account_not_linked` | `https://lobe.west-beta.ts.net/` |
| 页面状态 | 登录遇到问题 | 已登录（显示 Casey TSui） |
| `accounts` | 无当前 Casdoor id 的链接 | 新增 `account_id = 176e931f-…` |
| `auth_sessions` | 无新会话 | 新增会话 |

## 预防

- **升级 lobehub 镜像后必须用真实 Casdoor 账号走一遍登录**。`/api/version` 探针和 Pod Ready 都只能证明进程活着，证明不了认证链路。
- 若其他账号报同样的 `account_not_linked`（例如 `cuikaidong@foxmail.com`，其 `email_verified` 仍为 false），执行同一段 SQL 即可；本次按用户要求只修复了 `admin@example.com`。
- 根本解法在上游：LobeChat 应显式设置 `accountLinking.requireLocalEmailVerified = false`，或在 v1→v2 迁移时把 `users.email_verified` 回填。截至 `v2.2.17-canary` 仍未处理（main 分支的 `define-config.ts` 依旧只有 `allowDifferentEmails / enabled / trustedProviders`，better-auth 1.7.3 的默认值仍是 `true`），**升级镜像不会自愈**。
