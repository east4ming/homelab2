# PostgreSQL Collation Version Mismatch 修复记录

**日期**: 2026-05-16

## 现象

Casdoor pod 持续 CrashLoopBackOff，日志报错：

```
panic: pq: template database "template1" has a collation version mismatch
goroutine 1 [running]:
github.com/casdoor/casdoor/object.InitAdapter()
    /go/src/casdoor/object/ormer.go:91 +0x230
main.main()
    /go/src/casdoor/main.go:37 +0x25
```

## 根因

PostgreSQL 镜像 `paradedb/paradedb:latest-pg17` 更新后，底层 glibc 从 collation version **2.36** 升级到了 **2.41**。数据库中记录的 collation version 仍是旧的 2.36，导致 PostgreSQL 拒绝 Casdoor 通过 `template1` 创建数据库对象。

## 诊断命令

```bash
# 查看各数据库的 collation version
kubectl -n lobe-chat exec <postgres-pod> -- psql -U postgres -c \
  "SELECT datname, datcollate, datcollversion FROM pg_database;"
```

## 修复

```sql
ALTER DATABASE template1 REFRESH COLLATION VERSION;
ALTER DATABASE postgres REFRESH COLLATION VERSION;
ALTER DATABASE lobechat REFRESH COLLATION VERSION;
ALTER DATABASE casdoor REFRESH COLLATION VERSION;
ALTER DATABASE paradedb REFRESH COLLATION VERSION;
```

然后重启 Casdoor：

```bash
kubectl -n lobe-chat rollout restart deployment/casdoor
```

## 预防

- 避免使用 `latest` tag 的 PostgreSQL 镜像，固定到具体版本号
- PostgreSQL 大版本升级时，预计需要 reindex 所有使用默认 collation 的索引
