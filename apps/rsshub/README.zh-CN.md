# RssHub

RssHub + TTRss

## 迁移

从之前的一个普通 k3s 集群迁移到现在的 homelab2.

- Ingress 改变
- 域名改变
- StorageClass 改变
- ...

### 1. 备份

#### K8s Manifests 备份

- Deploy
- Service
- PVC
- IngressRoute(Traefik)

已经通过 Velero 备份为 json 文件. 再通过脚本 `kubectl-neat.sh` 转换为 yaml 并移除不需要的字段.

#### PVC 数据备份

- redis 数据: `dump.rdb`
- ttrss icons: 空. 无需备份.
- ttrss postgresql 数据: `pg_dumpall -c -U postgres > export.sql`

> 📚️**Reference**:
> [数据库更新或迁移|🐋 Awesome TTRSS](https://ttrss.henry.wang/zh/#%E6%95%B0%E6%8D%AE%E5%BA%93%E6%9B%B4%E6%96%B0%E6%88%96%E8%BF%81%E7%A7%BB)

### 2. 停机

原集群上, 停掉所有 Deploy, 停止所有服务.

### 3. 修改 Manifests

修改 Manifests 以适配新的 Homelab2 集群.

- NS 添加 `volsync.backube/privileged-movers` 注解以启用 volsync特权备份功能
- Deploy postgres 增加 initContainer 删除 PostgreSQL 数据库中的 `lost+found` 目录, 否则启动报错
- Deploy ttrss 增加 initContainer 使用 busybox 镜像执行 chmod 命令，将 `/var/www/feed-icons/` 目录的权限设置为 `777`
- 修改 IngressRoute 的 Host.
- 修改 depoly ttrss 中的 `SELF_URL_PATH` 为新的域名
- 将 rsshub 和 ttrss 的 traefik IngressRoute 改为 Ingress 配置并调整域名
- 将环境变量中的密码改为从 secrets 中获取(Secrets 添加到 `.gitignore`)

### 4. 部署

```bash
cd apps/rsshub
kubectl apply -f ns.yaml
kubectl apply -f deploy/ -f pvc/ -f secret/ -f service/ -f ingress/
```

### 5. 恢复数据

先停掉除了 Postgres 以外的所有 Deploy, 放置脏数据.

#### 5.1. Postgres

先将 `export.sql` 复制到 Postgres PV 中.

再进入 Postgres pod 中执行以下命令恢复数据:

```bash
cat export.sql | psql -U postgres
```

#### 5.2. Redis

将 `dump.rdb` 复制到 Redis PV 中.

### 6. 启动

启动所有 Deploy.

### 7. 修改 TTRss 供稿设置

登录 TTRss 域名: `ttrss.west-beta.ts.net`, 进入: **偏好设置** -> **供稿设置** -> 逐一查看, 将**URL**为 `https://rss.ewhisper.cn...` 修改为: `https://rss.west-beta.ts.net...`

### 8. 验证

1. 验证 RssHub 是否正常
2. 验证 TTRss 是否正常
   1. 登录 TTRss
   2. 阅读
   3. 验证是否可以正常订阅

### 9. 备份

1. 备份 Postgres 数据

### 10. 并行一段时间后清理原集群

1. node 回收
2. DNS 记录清理
3. 域名清理
4. 原集群备份 s3 删除
5. 其他杂项清理
