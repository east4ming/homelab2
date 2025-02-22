# RssHub

RssHub + TTRss

## Migration

Migrating from a previous ordinary k3s cluster to the current homelab2.

- Ingress changes
- Domain changes
- StorageClass changes
- ...

### 1. Backup

#### K8s Manifests Backup

- Deploy
- Service
- PVC
- IngressRoute (Traefik)

Already backed up as JSON files via Velero. Then converted to YAML and unnecessary fields removed using the script `kubectl-neat.sh`.

#### PVC Data Backup

- Redis data: `dump.rdb`
- TTRSS icons: Empty. No need to backup.
- TTRSS PostgreSQL data: `pg_dumpall -c -U postgres > export.sql`

> 📚️**Reference**:
> [Database Update or Migration | 🐋 Awesome TTRSS](https://ttrss.henry.wang/zh/#%E6%95%B0%E6%8D%AE%E5%BA%93%E6%9B%B4%E6%96%B0%E6%88%96%E8%BF%81%E7%A7%BB)

### 2. Shutdown

On the original cluster, shut down all Deploys and stop all services.

### 3. Modify Manifests

Modify Manifests to adapt to the new Homelab2 cluster.

- Add `volsync.backube/privileged-movers` annotation to NS to enable volsync privileged backup feature
- Add initContainer to Deploy postgres to remove the `lost+found` directory in the PostgreSQL database, otherwise startup errors occur
- Add initContainer to Deploy ttrss using busybox image to execute chmod command, setting the permissions of `/var/www/feed-icons/` directory to `777`
- Modify the Host in IngressRoute.
- Modify `SELF_URL_PATH` in deploy ttrss to the new domain
- Change rsshub and ttrss Traefik IngressRoute to Ingress configuration and adjust the domain
- Change passwords in environment variables to be retrieved from secrets (add Secrets to `.gitignore`)

### 4. Deployment

```bash
cd apps/rsshub
kubectl apply -f ns.yaml
kubectl apply -f deploy/ -f pvc/ -f secret/ -f service/ -f ingress/
```

### 5. Data Recovery

First, shut down all Deploys except Postgres to prevent dirty data.

#### 5.1. Postgres

First, copy `export.sql` to the Postgres PV.

Then enter the Postgres pod and execute the following command to restore data:

```bash
cat export.sql | psql -U postgres
```

#### 5.2. Redis

Copy `dump.rdb` to the Redis PV.

### 6. Startup

Start all Deploys.

### 7. Modify TTRss Feed Settings

Log in to the TTRss domain: `ttrss.west-beta.ts.net`, go to: **Preferences** -> **Feed Settings** -> check one by one, change the **URL** from `https://rss.ewhisper.cn...` to: `https://rss.west-beta.ts.net...`

### 8. Verification

1. Verify if RssHub is functioning normally
2. Verify if TTRss is functioning normally
   1. Log in to TTRss
   2. Read
   3. Verify if subscriptions work normally

### 9. Backup

1. Backup Postgres data

### 10. Clean up the original cluster after running in parallel for a period

1. Node recycling
2. DNS record cleanup
3. Domain cleanup
4. Delete original cluster backup from s3
5. Other miscellaneous cleanup
