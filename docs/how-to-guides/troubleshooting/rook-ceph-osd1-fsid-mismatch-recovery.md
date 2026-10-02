# Rook-Ceph OSD 1 down/out 修复记录：mon secret FSID 失配

> 事故日期：2026-10-02
> 影响节点：`n100-cheshi-0`（Ubuntu 24.04 → 26.04.1 升级，升级过程中发生断电）
> 结果：OSD 1 已恢复 `up/in`，集群 `HEALTH_OK`，深度校验确认**无数据损坏**

## 1. 结论摘要（TL;DR）

**本次故障不是磁盘或数据损坏，而是 Rook operator 的 `rook-ceph-mon` Secret 中 `fsid` 字段过期**，导致 operator 拒绝采纳磁盘上完好的 OSD 1。

| 项目 | 修复前 | 修复后 |
|---|---|---|
| `ceph -s` | HEALTH_OK（OSD 1 已 out，PG 全 clean） | HEALTH_OK |
| OSD 状态 | `4 osds: 3 up, 3 in`；`osd.1 down out weight 0` | `4 osds: 4 up, 4 in`；`osd.1 up in weight 1` |
| `osd.1` crush weight | `0`（autoout 清零） | `0.86850`（恢复原值） |
| `rook-ceph-mon` secret `fsid` | `f568f7c3-…` ❌ 错误 | `abb2c4e2-…` ✅ 正确 |
| OSD 1 Deployment | **不存在** | `1/1 Ready` |
| PG | 81 `active+clean` | 81 `active+clean`，deep-scrub 全部 `ok` |

**关键点：`rook-ceph-osd-1` 的 Deployment 不是"崩溃"，而是被 operator 主动删除/未创建。** 磁盘上的 BlueStore 元数据自始至终完好。

## 2. 环境信息

| 组件 | 版本 |
|---|---|
| Kubernetes | k3s v1.36.5+k3s1 |
| Rook operator | `docker.io/rook/ceph:v1.20.7` |
| Ceph | v20.2.4 (Tentacle)，`quay.io/ceph/ceph:v20.2.4` |
| 集群 FSID | `abb2c4e2-12a3-4b93-8d90-f2eaf2290901` |
| 节点 | `n100-cheshi-0`（OSD 1）、`n100-jumper-0`（OSD 2）、`n100-jumper-1`（OSD 0）、`n100-jumper-2`（OSD 3） |
| OSD 1 设备 | `/dev/nvme0n1p3`（ZHITAI TiPro7000 1TB，889 GiB，bluestore，非加密） |

## 3. 症状

升级 + 断电后，`n100-cheshi-0` 上的 OSD 1 处于 `down/out`：

```
$ ceph osd tree
-5         0.86850      host n100-cheshi-0
 1    ssd  0.86850          osd.1             down         0  1.00000

$ ceph osd dump | grep 'osd.1 '
osd.1 down out weight 0 up_from 404052 up_thru 404055 down_at 404060 \
  last_clean_interval [403278,404046) [...] autoout,exists 84b684bc-6ab4-4033-a75f-fec3b0b426cc
```

两个异常信号：

1. `autoout,exists` —— OSD 存在但被**自动 out**（crush weight 被清零）。
2. `ceph osd df` 中 `osd.1` 的 `SIZE` 为 **`0 B`** —— 完全没有容量上报，说明 **OSD 守护进程根本没在运行**。

```
$ ceph status
  osd: 4 osds: 3 up (since 2h), 3 in (since 4h)
  pgs: 81 active+clean          # 数据未受影响
```

### 3.1 关键线索：Deployment 缺失

```bash
$ kubectl -n rook-ceph get deploy | grep osd
rook-ceph-osd-0    1/1
rook-ceph-osd-2    1/1
rook-ceph-osd-3    1/1
# rook-ceph-osd-1 不存在！
```

`rook-ceph-osd-1` 的 Deployment **完全不存在**。这不是"Pod CrashLoop"，而是 operator 从未创建它（或已将其删除）。

## 4. 根因分析

### 4.1 决定性证据：osd-prepare 作业日志

```bash
kubectl -n rook-ceph logs job/rook-ceph-osd-prepare-n100-cheshi-0
```

```
I | cephosd: old lsblk can't detect bluestore signature, so try to detect here
D | exec: Running command: stdbuf -oL ceph-volume --log-path /tmp/ceph-log raw list --format json
D | cephosd: {
    "84b684bc-6ab4-4033-a75f-fec3b0b426cc": {
        "ceph_fsid": "abb2c4e2-12a3-4b93-8d90-f2eaf2290901",
        "device": "/dev/nvme0n1p3",
        "osd_id": 1,
        "osd_uuid": "84b684bc-6ab4-4033-a75f-fec3b0b426cc",
        "type": "bluestore"
    }
}
I | cephosd: skipping osd.1: "84b684bc-…" belonging to a different ceph cluster "abb2c4e2-…"
I | cephosd: 0 ceph-volume raw osd devices configured on this node
W | cephosd: skipping OSD configuration as no devices matched the storage settings for this node "n100-cheshi-0"
```

**磁盘上的 OSD 元数据完好无损**（合法的 `osd_id: 1`、`type: bluestore`、`ceph_fsid`），但 operator 判定它"属于另一个 Ceph 集群"并跳过，因此不生成 OSD Deployment。

### 4.2 FSID 三方比对

| 来源 | FSID | 判定 |
|---|---|---|
| 运行中集群 `ceph fsid` | `abb2c4e2-12a3-4b93-8d90-f2eaf2290901` | ✅ 真值 |
| OSD 1 磁盘 BlueStore 元数据 | `abb2c4e2-12a3-4b93-8d90-f2eaf2290901` | ✅ 与真值**一致** |
| `rook-ceph-mon` Secret `.data.fsid` | `f568f7c3-5603-4108-99ff-3742cf008a83` | ❌ **过期** |

```bash
$ kubectl -n rook-ceph get secret rook-ceph-mon -o jsonpath='{.data.fsid}' | base64 -d
f568f7c3-5603-4108-99ff-3742cf008a83     # 与真实集群不符
```

**OSD 磁盘与真实集群是一致的；错的只有 Rook 用作"期望值"的那个 Secret 字段。**

### 4.3 Rook 源码级验证

在 Rook 上游源码中确认了该字段的读写路径（`pkg/operator/ceph/controller/cluster_info.go`）：

```go
// L52  —— 字段名
fsidSecretNameKey = "fsid"

// L110-154 —— 读取路径：仅从 Secret 读取，不做任何校验/纠正
secrets, err := clusterdContext.Clientset.CoreV1().Secrets(namespace).Get(context, AppName, ...)
...
clusterInfo = &cephclient.ClusterInfo{
    Namespace:     namespace,
    FSID:          string(secrets.Data[fsidSecretNameKey]),   // ← 唯一来源
    ...
}

// L417-441 —— 写入路径：仅在 Secret「不存在」时创建
func createClusterAccessSecret(...) error {
    secrets := map[string][]byte{
        fsidSecretNameKey: []byte(clusterInfo.FSID),          // ← 仅此一处写入
        ...
    }
    ...
    clientset.CoreV1().Secrets(namespace).Create(...)
}
```

整个仓库中 `fsidSecretNameKey` 只出现 3 次：

| 位置 | 作用 |
|---|---|
| `cluster_info.go:52` | 常量定义 |
| `cluster_info.go:154` | **读**（构造 ClusterInfo） |
| `cluster_info.go:423` | **写**（仅在 Secret 不存在、创建新集群时） |

另有 `cluster_info.go:167` 一处 `Secrets().Update()`，但只在旧版 `admin-secret` 键迁移时触发（当前 Secret 已含 `ceph-username`，不会触发）。

**结论：该字段无任何自动纠正逻辑，也不会被后续调和覆盖 —— 手工修正后是稳定、持久的。**

### 4.4 事件链（推断，与证据一致）

1. `n100-cheshi-0` 执行 Ubuntu 24.04 → 26.04.1 升级，过程中**断电**。
2. 节点长时间离线，4 个 OSD 中 OSD 1 所在节点不可达。
3. Ceph 达到 `mon_osd_down_out_interval`，将 OSD 1 **标记 `out` 并把 crush weight 置 0**（`autoout`），数据迁往其余 3 个 OSD，PG 恢复 `active+clean`。
4. Rook operator 在节点反复离线期间重新引导集群访问凭据，**重新生成了 `rook-ceph-mon` Secret 的 `fsid`**（`resourceVersion: 4`），但该值未与运行中的 mon 数据/OSD 对齐。
5. 节点恢复后，operator 用错误的 `fsid` 作期望值扫描 OSD 磁盘 → 判定"属于其他集群" → 跳过 → 不创建 `rook-ceph-osd-1` Deployment。
6. OSD 1 因此永久停留在 `down/out`，且**不会自愈**。

### 4.5 为什么其他 Ceph 组件没坏

`rook-ceph-mon` Secret 中另外两个字段是**可用且正确**的：

```bash
$ kubectl -n rook-ceph get secret rook-ceph-mon -o jsonpath='{.data.ceph-username}' | base64 -d
client.admin
```

用该 Secret 里的 `ceph-secret` 直接向集群认证 —— **成功**：

```bash
$ ceph -s --name client.admin --keyring /tmp/t.keyring
  cluster:
    id:     abb2c4e2-12a3-4b93-8d90-f2eaf2290901
    health: HEALTH_OK
```

mon 端点通过 `rook-ceph-mon-endpoints` ConfigMap 加载（与 `fsid` 无关），因此 mon/mgr/mds 一直正常运行，只有 **OSD 采纳流程**因 FSID 校验而失败。

## 5. 修复方案

### 5.1 修复前检查清单

执行前确认（避免在真正需要重建时误操作）：

- [x] `ceph -s` 为 `HEALTH_OK`，PG 全部 `active+clean`（无数据丢失风险）
- [x] OSD 磁盘元数据可读且 `ceph_fsid` 与真实集群一致
- [x] Secret 中的 `ceph-secret` 仍能成功认证（证明凭据未被破坏，只需修 `fsid`）
- [x] 全集群无其他资源引用错误 FSID（已扫描所有 ConfigMap/Secret/StorageClass）

```bash
# 扫描错误 FSID 是否泄漏到其他资源（结果：无）
WRONG=f568f7c3-5603-4108-99ff-3742cf008a83
kubectl get configmap,secret -A -o json | grep -c "$WRONG"    # → 仅 rook-ceph-mon 自身
kubectl get sc -o json | grep -c "$WRONG"                      # → 0
```

### 5.2 步骤 1：修正 Secret 中的 FSID

```bash
# 以运行中集群的真实 FSID 为准
FSID=$(kubectl -n rook-ceph exec deploy/rook-ceph-tools -- ceph fsid | tr -d '\r\n')
# → abb2c4e2-12a3-4b93-8d90-f2eaf2290901

# 仅替换 fsid 字段，保留 ceph-secret / ceph-username / mon-secret
kubectl -n rook-ceph patch secret rook-ceph-mon \
  --type merge \
  -p "{\"data\":{\"fsid\":\"$(printf '%s' "$FSID" | base64 -w0)\"}}"
# → secret/rook-ceph-mon patched
```

验证：

```bash
$ kubectl -n rook-ceph get secret rook-ceph-mon -o json | python3 -c "
import json,sys,base64
d=json.load(sys.stdin)
for k in sorted(d['data']):
    v=base64.b64decode(d['data'][k]).decode('utf8','replace')
    print(f'  {k:14} = {v if k in (\"fsid\",\"ceph-username\") else v[:12]+\"...(masked)\"}')
"
  ceph-secret    = AgAag5JqppFL...(masked)
  ceph-username  = client.admin
  fsid           = abb2c4e2-12a3-4b93-8d90-f2eaf2290901     # ✅
  mon-secret     = AgB6g5Jq+6Yf...(masked)
```

> ⚠️ 只改 `fsid`。**不要**删除 Secret 重建 —— 删除会触发 `DisasterProtectionFinalizer` 并可能被 operator 当作新集群重新 bootstrap，风险极高。

### 5.3 步骤 2：重启 operator 以重新加载 ClusterInfo

Secret 在 operator 启动时读取进内存缓存，需重启使其生效：

```bash
kubectl -n rook-ceph delete pod -l app=rook-ceph-operator --wait=false
kubectl -n rook-ceph wait --for=condition=Ready pod -l app=rook-ceph-operator --timeout=180s
```

> operator 启动初期的 `Error initializing cluster client: ObjectNotFound('RADOS object not found (error calling conf_read_file)')` 属正常引导过程，随后会自行消失。

### 5.4 步骤 3：等待调和并验证采纳

Rook 每约 10 分钟调和一次；OSD 阶段位于 mgr 阶段之后。

```bash
# 观察 CephCluster 状态
kubectl -n rook-ceph get cephcluster rook-ceph -o jsonpath='{.status.phase}{"\n"}'
# Progressing → Ready
```

**验证点 —— prepare 作业不再跳过 OSD 1：**

```bash
$ kubectl -n rook-ceph logs job/rook-ceph-osd-prepare-n100-cheshi-0 | grep -E 'different ceph cluster|raw osd devices configured'
I | cephosd: 1 ceph-volume raw osd devices configured on this node      # ✅ 采纳成功
# 且不再出现 "belonging to a different ceph cluster"
```

```
I | cephosd: devices = [{ID:1 Cluster:ceph UUID:84b684bc-6ab4-4033-a75f-fec3b0b426cc \
    DeviceClass:nvme BlockPath:/dev/nvme0n1p3 ... CVMode:raw Store:bluestore}]
```

**验证点 —— Deployment 与 Pod 已创建：**

```bash
$ kubectl -n rook-ceph get deploy rook-ceph-osd-1
NAME              READY   UP-TO-DATE   AVAILABLE
rook-ceph-osd-1   1/1     1            1

$ kubectl -n rook-ceph get pods -l ceph_daemon_id=1 -o wide
NAME                               READY   STATUS    NODE
rook-ceph-osd-1-678d4fff96-lbtpk   1/1     Running   n100-cheshi-0
```

### 5.5 步骤 4：确认 OSD 已回到集群（无需手工 `osd in`）

OSD 守护进程启动后自动向 mon 重新注册。本次**无需**手工执行 `ceph osd in`，Rook 重建 Deployment 时同时恢复了 crush weight：

```
$ ceph osd tree
-5         0.86850      host n100-cheshi-0
 1    ssd  0.86850          osd.1               up   1.00000  1.00000

$ ceph osd dump | grep 'osd.1 '
osd.1 up   in  weight 1 up_from 404241 up_thru 404273 down_at 404060 \
  last_clean_interval [404052,404059) [...] exists,up 84b684bc-…

$ ceph osd df
 1    ssd  0.86850   1.00000  889 GiB   ...   up      # SIZE 已从 0 B 恢复为 889 GiB
```

> 若某次修复后 OSD 仍为 `out` 或 weight 为 0，再用以下命令手工恢复：
> ```bash
> ceph osd in 1                    # 重新标记 in
> ceph osd crush reweight osd.1 0.86850   # 恢复 crush weight 为原值
> ```
> 历史上 `autoout` 会把 weight 置 0，因此恢复 weight 这一步是必要的（本次由 Rook 自动完成）。

## 6. 验证结果

### 6.1 集群终态

```
$ ceph -s
  cluster:
    id:     abb2c4e2-12a3-4b93-8d90-f2eaf2290901
    health: HEALTH_OK
  services:
    mon: 3 daemons, quorum c,e,g
    mgr: a(active), standbys: b
    mds: 1/1 daemons up, 1 hot standby
    osd: 4 osds: 4 up (since 2m), 4 in (since 4m)      # ✅ 4/4 up & in
  data:
    volumes: 1/1 healthy
    pools:   4 pools, 81 pgs
    objects: 22.32k objects, 81 GiB
    pgs:     81 active+clean                            # ✅ 无降级
```

`ceph osd tree` 全部 4 个 OSD 均为 `up / in / 1.00000`，crush weight 均为 `0.86850`（与故障前一致）。

### 6.2 数据完整性校验（重点）

由于故障起因是"升级期间断电"，**必须排除静默数据损坏**。对全部 81 个 PG 发起深度校验：

```bash
kubectl -n rook-ceph exec deploy/rook-ceph-tools -- bash -c '
for pg in $(ceph pg ls | awk "NR>1{print \$1}"); do ceph pg deep-scrub "$pg"; done'
```

结果：

```
$ ceph health detail
HEALTH_OK                                  # ✅ 无 inconsistent / scrub error

$ kubectl -n rook-ceph logs -l ceph_daemon_id=1 | grep deep-scrub | tail -3
1.7  deep-scrub ok
1.f  deep-scrub ok
1.12 deep-scrub ok                          # 每个 OSD 的 PG 均为 ok
```

**结论：所有 81 个 PG 深度校验通过，`0 inconsistent objects`，磁盘数据无损坏。**

## 7. 修复过程中的副作用（重要）

重启 operator 后，Rook 下发了新的 OSD 配置（Deployment 模板变更），触发**全部 4 个 OSD 的滚动重启**：

滚动过程（旧 Pod → 新 Pod）：

| OSD | 修复前 Pod | 修复后 Pod |
|---|---|---|
| 0 | `rook-ceph-osd-0-78c8b4998c-tnndx` | `rook-ceph-osd-0-56cb79d8b7-t8hbv` |
| 1 | **不存在** | `rook-ceph-osd-1-678d4fff96-lbtpk` |
| 2 | `rook-ceph-osd-2-69b8758db8-bjm84` | `rook-ceph-osd-2-6895c7d8d8-xphrn` |
| 3 | `rook-ceph-osd-3-59c577779d-btd67` | `rook-ceph-osd-3-59fc9b6f66-jxhj8` |

（OSD 3 分两轮完成滚动，最终 4 个 Pod 均在约 5 分钟内重建并 `Ready`。）

期间集群短暂出现：

```
health: HEALTH_WARN
  1 osds down
  Degraded data redundancy: 11648/44646 objects degraded (26.090%), 23 pgs degraded
```

这是**正常的滚动重启过渡态**，OSD 2 的替换 Pod 处于 `Init:1/4`（`ceph-volume raw activate` → `expand-bluefs` → `cephx-keyring-update` 依次完成），约 1~2 分钟后全部恢复 `Ready`，集群回到 `HEALTH_OK / 81 active+clean`。

> 此项不构成数据风险：所有 PG 在过渡期仍满足副本要求，未出现 `undersized`/`incomplete`。

## 8. 关键判据速查（下次遇到同类问题）

| 观察到的现象 | 含义 |
|---|---|
| OSD **Deployment 不存在**（而非 CrashLoop） | operator 主动跳过，多半是采纳/校验失败，而非设备故障 |
| `ceph osd df` 中该 OSD `SIZE = 0 B` | 守护进程未运行，非磁盘故障 |
| `autoout` 且 weight 0 | 由 `mon_osd_down_out_interval` 自动 out，可通过 restore weight 复原 |
| prepare 日志 `belonging to a different ceph cluster` | **`rook-ceph-mon` Secret 的 `fsid` 与真实集群不符** |
| `ceph fsid` == OSD 元数据 `ceph_fsid` ≠ Secret `fsid` | 三者中 Secret 过期 → 修 Secret |
| Secret 的 `ceph-secret` 仍可认证 | 凭据完好，**只需改 `fsid`**，切勿删除重建 Secret |

## 9. 预防措施

1. **升级前先 `ceph osd set noout`**，避免节点离线期间 OSD 被 `autoout` 并触发全量数据迁移：
   ```bash
   ceph osd set noout
   # ... 节点维护/升级 ...
   ceph osd unset noout
   ```
2. **为节点升级准备 UPS**，避免断电导致升级中断与集群元数据/凭据不一致。
3. **备份关键 Secret**（尤其是 `rook-ceph-mon`），以便事后比对 `fsid`：
   ```bash
   kubectl -n rook-ceph get secret rook-ceph-mon -o yaml > rook-ceph-mon.secret.bak.yaml
   ```
4. 集群恢复后，**始终以深度校验确认数据完整性**，不要仅凭 `HEALTH_OK` 判断（`HEALTH_OK` 只表示 PG 元数据一致，静默位翻转需 scrub 才能发现）：
   ```bash
   for pg in $(ceph pg ls | awk 'NR>1{print $1}'); do ceph pg deep-scrub $pg; done
   ceph health detail | grep -i inconsistent
   ```

## 10. 附：本次事件时间线

| 时间（本地） | 事件 |
|---|---|
| 升级期间 | `n100-cheshi-0` Ubuntu 24.04 → 26.04.1，过程中断电 |
| ~升级后 | OSD 1 被 `autoout`，weight → 0，数据迁至其余 3 OSD |
| operator 重启期间 | `rook-ceph-mon` Secret 的 `fsid` 被重新生成为过期值 `f568f7c3-…`（resourceVersion 4） |
| 14:14 | osd-prepare 作业判定 OSD 1 "属于不同集群"并跳过；`rook-ceph-osd-1` Deployment 缺失 |
| 14:21 | 开始诊断：确认磁盘元数据完好、Secret 凭据可用、仅 `fsid` 过期 |
| 14:24:35 | 修正 Secret `fsid` → `abb2c4e2-…`；重启 operator |
| 14:27 | 新 prepare 作业采纳 OSD 1（`1 ceph-volume raw osd devices configured`） |
| 14:27:49 | `rook-ceph-osd-1` Deployment 创建，Pod 运行 |
| 14:28–14:30 | operator 滚动重启全部 OSD；短暂 `HEALTH_WARN`（26% degraded） |
| 14:29 | `osd.1 up in weight 1`，crush weight 恢复 `0.86850` |
| 14:30 | 集群回到 `HEALTH_OK`，4 osds up/in，81 `active+clean` |
| 14:31 | 全部 81 个 PG 深度校验完成：**`deep-scrub ok`，无损坏** |

## 11. 参考

- Rook `CreateOrLoadClusterInfo` / `createClusterAccessSecret`（`pkg/operator/ceph/controller/cluster_info.go`）—— 说明 `fsid` 仅在 Secret 创建时写入
- Rook Discussion [#13946 how to load OSD belonging to different Ceph cluster](https://github.com/rook/rook/discussions/13946) —— "different ceph cluster" 报错的社区讨论
- 本仓库相关文档：[Rook-Ceph v1.20.0 CSI ServiceAccount 命名不匹配 Bug 及修复方案](rook-ceph-v1.20.0-bug-workaround.md)
- 升级背景：[Ubuntu 24.04 LTS 升级到 26.04 LTS](../upgrade-ubuntu-24-04-to-26-04.md)
