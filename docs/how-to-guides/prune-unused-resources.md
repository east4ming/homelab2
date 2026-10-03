# 清理未使用的集群资源（kor 审计 → 备份 → 删除 → 恢复）

kor 以只读 exporter 形态常驻，把「没有任何工作负载引用」的资源暴露成
`kubernetes_orphaned_resources` 指标（见 `specs/008-kor-monitoring/spec.md`）。
本页说明**怎么读这些结果、哪些能删、删之前怎么备份、删错了怎么恢复**。

!!! danger "三条铁律"

    1. **GitOps 管理的资源一律不手动删**。删了 ArgoCD 会重建，只会产生漂移与同步抖动；
       确实不该存在的，请改 Git 或删对应的 Application。
    2. **`standard-rwo` 的回收策略是 `Delete`**。删 PVC 会连 Ceph RBD 镜像一起删，
       数据当场消失；etcd 快照只含对象定义，**救不回数据**。
    3. **etcd 快照的恢复窗口只有约 12–24 小时**（见下文实测）。删完要立刻验证。

## 1. 数据来源与本次快照

| 来源 | 用途 |
| --- | --- |
| 指标 `kubernetes_orphaned_resources{kind,namespace,resourceName}` | 全量发现结果（在线、始终最新） |
| Grafana `Kor Dashboard`（uid `Zrue32P7Ik`） | 总量、按 namespace、按 kind 分布 |
| `scripts/kor-audit` | 把指标结果与集群实况交叉核对，输出 A/B/C 分级报告 |

```sh
scripts/kor-audit --out /tmp/kor-audit.md
```

快照（2026-10-03）：**925 条**，13 类。

| kind | 数量 | kind | 数量 |
| --- | --- | --- | --- |
| ReplicaSet | 486 | Secret | 90 |
| Crd | 127 | ConfigMap | 68 |
| Job | 40 | Pvc | 30 |
| ClusterRole | 26 | VolumeAttachment | 25 |
| Service | 11 | ClusterRoleBinding | 10 |
| RoleBinding | 7 | ServiceAccount | 4 |
| StorageClass | 1 | | |

!!! note "这个快照早于 exporter 的过滤配置，数字对不上是正常的"

    后来给 exporter 加了两个 `--exclude-labels`（见 `system/kor/values.yaml` 的注释），
    以下对象不再出现在报告里：

    - `app.kubernetes.io/managed-by=Helm`：声明式对象由 Git 管理，不该按 Pod 使用情况判定。
      副作用是 **ReplicaSet 会从 Pod 模板继承该标签，183 个旧 RS 因此不再出现**。
    - `tailscale.com/managed=true`：Tailscale operator 管理的 21 张 Ingress 证书与
      8 个 ProxyGroup/operator 状态 Secret。这批对象**无法**用 `kor/used=true` 排除——
      operator 会重写 Secret 元数据把外部标签冲掉（实测）。

    两个注意点：**集群级 CRD 不受任何 `--exclude-labels` 影响**（kor v0.6.9 的
    `crds.go` 把过滤器参数丢掉了，实测该标签过滤对 127 条 CRD 完全无效），
    `--ignore-owner-references` 则会把全部派生对象一起藏掉（486 个 RS → 0），不建议使用。

## 2. kor 的判定语义（决定哪些是假阳性）

不看这一节就会删错。kor 的判定是「**有没有 Pod/EndpointSlice 引用**」，而集群里大量资源
是被 **CR、Ingress、sidecar、operator 按名字引用**的，不上 Pod，于是被误报：

| kind | kor 的判据 | 主要假阳性 |
| --- | --- | --- |
| Crd | 该 CRD 的所有 served 版本都查不到自定义资源 | CRD 属于已安装的 operator/chart，删了会被重建；且删 CRD 会**级联删掉其全部 CR** |
| Secret | 没被 Pod 挂载或作为环境变量引用 | VolSync 备份仓库口令、Tailscale TLS 证书（被 Ingress 的 `spec.tls` 引用）、ESO/operator 生成的密钥、k3s etcd 快照凭据 |
| ConfigMap | 同上 | Grafana dashboard（sidecar 读）、rook/kubevirt 的 operator 配置与 CA（被 CR/webhook 引用） |
| ClusterRole / Role | 没有任何 RoleBinding/ClusterRoleBinding 引用 | operator 的内置聚合角色、已卸载组件的遗留 |
| Service | 其 EndpointSlice 为空 | prometheus-operator 的手工 Endpoints 型 headless Service；后端暂时不健康的服务；已 scale 到 0 的工作负载 |
| Pvc | 没有 Pod 挂载 | **停止中的 VM 的数据盘**（VM 定义里按名引用）、VolSync 的 restic 缓存卷 |
| ReplicaSet | `spec.replicas=0` 且状态全 0 | 无（旧 revision 就是旧 revision） |
| Job | 已完成 / 失败 / 挂起 | 无（但日志会随对象一起消失） |
| VolumeAttachment | 引用的 PV、节点或 CSIDriver 不存在 | 无 |
| StorageClass | 没有 PV/PVC 使用它 | GitOps 管理，删了会被重建 |

!!! warning "两个最容易看错的地方"

    - **`namespace` ≠ `exported_namespace`**。指标里的 `namespace` 是采集目标自己的
      namespace（恒为 `kor`），资源真正所属的 namespace 在 `exported_namespace`。
    - **RS 上的 ArgoCD 注解是继承来的**。486 个 ReplicaSet 中 258 个带
      `argocd.argoproj.io/tracking-id`，但那是从 Deployment 的 Pod 模板继承的；
      ArgoCD 管的是 Deployment，**不会**重建 RS。所以判「是不是派生对象」要看
      `ownerReferences`，不能看标签。

## 3. 分级结果

```
A 类  可直接批量清理   557 个   （ReplicaSet 486 / Job 32 / VolumeAttachment 25 / PVC 7 / Service 7）
B 类  需人工确认        36 个
C 类  禁止删除         332 个
```

### A 类：可直接批量清理

| 对象 | 数量 | 为什么安全 |
| --- | --- | --- |
| ReplicaSet（旧 revision） | 486 | 由 Deployment 生成，`replicas=0` 且状态全 0；删除后不会被重建，只少一条 `kubectl rollout undo` 历史 |
| Job（已完成） | 32 | 27 个 renovate 运行历史 + `kube-bench` + 4 个 CronJob 历史；CronJob 不重建历史运行 |
| VolumeAttachment | 25 | 引用的 PV 已不存在，是 CSI 残留的元数据 |
| PVC（Woodpecker 流水线工作区） | 7 | 2026-05 的孤儿流水线工作区，无 Pod 挂载、无 owner |
| Service（Woodpecker 临时 headless） | 7 | 与上面同批流水线的残留 |

**收益要如实说**：

- 这 557 个对象只占 etcd 元数据（当前 DB 约 **71 MiB**），清理不会显著改变集群规模；
  价值在于让 kor 的后续报告不再被历史噪声淹没。
- **唯一有实际空间收益的是 7 个 Woodpecker PVC**：名义申请 70 GiB，`rbd du` 实测
  实际占用合计约 **0.5 GiB**（1 个 0 B，6 个约 80–84 MiB）。RBD 是精简置配，
  所以别期待释放 70 GiB。
- 那 25 条陈旧 VolumeAttachment **没有任何空间收益**：已核实 Ceph 池里 55 个
  `csi-vol-*` 镜像与 55 个 PV 一一对应，**没有孤儿镜像**，删的只是 k8s 侧记录。

### B 类：需人工确认

| 对象 | 结论 |
| --- | --- |
| kubevirt / cdi 的内置 ClusterRole、`kubevirt-apiserver-auth-delegator`、`kube-apiserver-kubelet-admin` | **不删**：属 kubevirt/CDI 安装的一部分 |
| `loft-cluster-*` ClusterRole ×4、`pod-impersonation-shell-*` ×2（ClusterRole+Binding） | 已卸载组件的遗留（集群中已无 loft/cattle 命名空间）。可删，但收益几乎为零，建议随下次大扫除一起处理 |
| `kubevirt-*-ca` 等 ConfigMap ×5、`default/scheduled-jobs`、`grafana/pcp-app-provisioning` | **不删**：被 CR / webhook / 应用按名字引用 |
| `volsync-src-*-cache` PVC ×17 | 无收益：VolSync 会重建 |
| `kubevirt-test/prod-vm-datadisk` | **不删**：`virtualmachine/prod-vm`（当前 Stopped）的 `datadisk` 就指向它 |
| `kubevirt/virt-exportproxy` Service | **不删**：kubevirt-operator 管理 |

### C 类：禁止删除（332）

- **Crd 127**、**Secret 90**、**StorageClass 1**（`standard-rwx`，GitOps 管理且无 PVC 使用，
  但删了会被重建）。
- **GitOps 管理 85**、**operator/CR 拥有 24**、**DataVolume 生成的 VM 根盘 5**。

其中最危险的三个具体对象，删掉直接出事：

| 对象 | 后果 |
| --- | --- |
| `kube-system/k3s-etcd-snapshot-s3-config` | 集群的 etcd 备份立刻停摆——**这是最后一道防线** |
| `<app>/volsync-src-*`、`*-backup-repository` | VolSync 的 restic 仓库口令；删了对应卷的历史备份就再也解不开 |
| `tailscale/<域名>` TLS Secret | 该域名的 HTTPS 当场失效（Tailscale operator 会重新签发，但有中断） |

## 4. 方案：备份 → 删除 → 恢复

### 4.1 备份（删除前必须完成）

三层，缺一层就有不可恢复的场景：

**① etcd 快照（整集群对象定义）** —— 已有自动化，实测可用：

```sh
# 凭据在 kube-system/k3s-etcd-snapshot-s3-config；bucket 在 NAS 上
# 本机没有 aws/mc，用 rclone 直接读同一份凭据（只列对象，不打印凭据）
```

实测状态：S3 端点 `http://192.168.3.216:8010`（NAS，**明文 HTTP**），bucket
`k3s-etcd-snapshot`，每 12 小时（00:00 / 12:00）每台控制面各一份，当前共 8 个对象，
最新一份是当天 12:00。

!!! warning "恢复窗口很短"

    实测每台控制面在 S3 里只留最近 1–2 份快照。也就是说**「误删 → 恢复」的窗口大约
    只有 12–24 小时**。删完必须立刻验证，不要隔天再看。

    k3s 侧的备份配置见 [Backup K3s Etcd Snapshot To S3](backup-k3s-etcd-snapshot-to-s3.md)；
    在节点上核对可用 `sudo k3s etcd-snapshot ls`（本机 SSH 不可用，未从本机验证）。

**② 待删对象的 YAML 导出** —— 针对 A 类（它们不在 Git 里，没有第二份定义）：

```sh
mkdir -p ~/kor-backup/2026-10-03 && cd ~/kor-backup/2026-10-03
# 用 scripts/kor-audit 生成的清单逐条导出（保留 metadata，便于原样 apply 回去）
kubectl -n woodpecker get pvc wp-01kq... -o yaml > woodpecker-pvc-wp-01kq....yaml
kubectl -n woodpecker get svc wp-hsvc-7257 -o yaml > woodpecker-svc-wp-hsvc-7257.yaml
kubectl -n renovate get job renovate-1763392138332 -o yaml > renovate-job-....yaml
```

!!! danger "导出物不能入库"

    这里会包含 Secret 的内容。导出的目录**不要放进仓库**（宪法禁止提交凭据），
    放在本机仓库之外，或用 `age`/`gpg` 加密后再写进备份介质。

**③ PVC 数据（若确实要删有数据的卷）**：

```sh
# VolSync 已有现成通道：先备份，再删
./scripts/backup --action setup --namespace=<ns> --pvc=<pvc>
# 恢复时
./scripts/backup --action restore --namespace=<ns> --pvc=<pvc>
```

另有一条**单对象保险**：把 PV 的回收策略改成 `Retain`，删 PVC 后镜像仍在，
可以手工重建 PVC 指回去。

```sh
kubectl patch pv <pv-name> -p '{"spec":{"persistentVolumeReclaimPolicy":"Retain"}}'
```

!!! note "本页涉及的 A 类 PVC 不需要这一层"

    7 个 Woodpecker PVC 是构建工作区，实测合计约 0.5 GiB，没有保留价值。
    但如果你把 B/C 类里有数据的 PVC 纳入清理范围，这一层是必须的。

### 4.2 删除

**前置检查（逐项打勾）**

- [ ] 目标对象不在 Git 中（`scripts/kor-audit` 判为 A 类，且不属于 C 类任一判据）
- [ ] 当前没有工作负载在用（Woodpecker 场景：`kubectl -n woodpecker get pods` 只有 server/agent）
- [ ] 已导出 YAML（4.1 ②），且导出文件可被 `kubectl apply --dry-run=server -f` 通过
- [ ] etcd 快照在窗口内（上面验证过最新一份的时间）
- [ ] 若涉及 PVC：已确认 `rbd du` 里的实际占用可以放弃，或已完成 VolSync 备份

**分批执行，每批之后验证**

```sh
# 第 1 批：Ceph 上的真实占用（唯一有空间收益的一批）
# 这些对象没有任何 label，只能按名字删，所以必须显式列出来
kubectl -n woodpecker delete service --dry-run=server \
  wp-hsvc-7257 wp-hsvc-7409 wp-hsvc-7410 wp-hsvc-7411 wp-hsvc-7413 wp-hsvc-7414 wp-hsvc-7415
# 确认无误后去掉 --dry-run=server 执行；再删 7 个孤儿工作区 PVC
# （回收策略是 Delete，PV 与 Ceph 镜像会一并删除）
kubectl -n woodpecker delete pvc --dry-run=server \
  wp-01kqr81vtqk2t1dm9b666wce2h-0-default \
  wp-01krmt5vnn0y6pfqjye8j8ts52-0-default \
  wp-01krmt5vnn0y6pfqjye9zq9y13-0-default \
  wp-01krmt5vnt96s7cv2b5p11gb42-0-default \
  wp-01krmt5vnvp0bhbfy33pm1xvp9-0-default \
  wp-01krmt5vp1x4fprxac7eew4kwc-0-default \
  wp-01krmt5vp1x4fprxac7fe9x620-0-default

# 第 2 批：Job 历史（建议先留日志）
kubectl -n renovate logs job/renovate-1763392138332 > ~/kor-backup/2026-10-03/renovate-...log
kubectl -n renovate delete job renovate-1763392138332

# 第 3 批：陈旧 CSI 记录（无空间收益，纯清理）
kubectl delete volumeattachment csi-0e90cfe4... csi-10888edc...

# 第 4 批：旧 ReplicaSet（数量大，务必先导出清单再批量删）
kubectl -n rook-ceph delete rs <按 /tmp/kor-audit.md 的 A 类清单>
```

**删除后立即验证**

```sh
# 1) 没有新的异常
kubectl get pods -A | grep -vE "Running|Completed"
# 2) ArgoCD 全绿（A 类不在 Git 里，不应产生任何漂移）
kubectl get applications -A -o custom-columns=NAME:.metadata.name,SYNC:.status.sync.status,HEALTH:.status.health.status | grep -v "Synced.*Healthy"
# 3) kor 重新扫描后数字下降（下一次扫描周期内，或重启 exporter 触发）
make smoke-test
```

### 4.3 误删除恢复

按对象的来源分路径，**先看它是谁管理的**：

| 对象来源 | 恢复方式 | 时效 |
| --- | --- | --- |
| ArgoCD / Helm 管理（C 类，原则上不该删） | 什么都不用做——`selfHeal` 会在下一个同步周期自动重建；也可在 ArgoCD UI 点 Sync，或 `git revert` 后合入 | 约 3 分钟内自动 |
| operator/CR 生成（Secret、RBAC、DataVolume 的 PVC） | 删除/重建其父对象（如 `ExternalSecret`、`CephCluster`）触发重建；ESO 与 rook 会重新 reconcile | 分钟级 |
| 声明式但不在 Git（A 类） | 用 4.1 ② 的 YAML 导出 `kubectl apply -f`；ReplicaSet/VolumeAttachment 无需恢复（无意义） | 即时 |
| **PVC 数据**（回收策略 `Delete`） | 只有 VolSync 一条路：`./scripts/backup --action restore ...`。**etcd 快照救不回数据**——它只有对象定义，Ceph 镜像已经没了 | 取决于备份周期 |
| PVC（已先把 PV 改成 `Retain`） | 手工重建同名 PVC 绑定回那个 PV（`spec.volumeName`），或直接用该 PV 重建工作负载 | 即时 |
| 整集群级事故（如误删 CRD 导致 CR 级联删除） | 从 S3 取最近一份 etcd 快照，在**一台**控制面执行 `k3s server --cluster-reset --cluster-reset-restore-path=<快照>`，其余控制面清掉本地 etcd 数据后重新加入 | 见 k3s 官方文档；窗口 12–24 小时 |

!!! danger "etcd 快照能救什么、不能救什么"

    - **能**：所有 k8s 对象（含 Secret、RBAC、CRD 与 CR 的定义）、被级联删掉的对象定义。
    - **不能**：已经随 PVC 一起删掉的 Ceph RBD 镜像里的**数据**。快照恢复后 PV/PVC 会
      指向已经不存在的镜像，卷起不来——这种场景只能靠 VolSync。
    - 恢复 etcd 是**整集群回滚**：快照之后的所有变更都会丢。它只用于兜住灾难，
      不用于修单个对象。

## 5. 复现与排障

```sh
scripts/kor-audit                                   # 重新生成 A/B/C 分级
kubectl -n kor logs deploy/kor-exporter --tail=20   # exporter 在跑整集群 LIST
```

| 症状 | 处理 |
| --- | --- |
| 报告里 C 类突然变多 | 多半是 GitOps 标记的判断变了；确认 `scripts/kor-audit` 的 `gitops` 判据与你删的东西一致 |
| 删完 ArgoCD 出现 OutOfSync | 说明删到了 C 类对象（在 Git 里）。不要手工重建，用 Sync 让它自己修复 |
| PVC 删了但 Ceph 里镜像还在 | 回收策略被改成 `Retain` 了；镜像需人工 `rbd rm`（谨慎） |
| 想确认某 PVC 在 Ceph 里的真实占用 | `kubectl -n rook-ceph exec deploy/rook-ceph-tools -- rbd du -p standard-rwo <csi-vol-...>` |

## 6. 已知限制

- `scripts/kor-audit` 的分级是**保守规则 + 启发式**，B 类必须人工看；规则见脚本内 `classify()`。
- kor 的判定本身有上游已知假阳性（见 `specs/008-kor-monitoring/spec.md` 与上游 README），
  任何批量删除前都应保留 4.1 的 YAML 导出。
- 本页不提供自动删除（kor 的 `--delete` 不启用：它需要写权限，且会照单全删）。
  删除动作始终由人确认后执行。
