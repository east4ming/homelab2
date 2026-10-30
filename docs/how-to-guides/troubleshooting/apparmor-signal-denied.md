# 容器内信号被 AppArmor 拒绝（gosu 自旋、数据库起不来）

## 症状

- 数据库容器（官方 `postgres`/`mysql`，或任何 entrypoint 走 `gosu` 的镜像）一直
  `CrashLoopBackOff` 或「Running 但端口没监听」，**日志几乎为空**。
- 依赖它的应用报连不上库，例如：
  - `casdoor`: `panic: dial tcp 10.43.36.163:5432: connect: no route to host`
  - `semaphore`: `Pinging database on semaphore-mysql port 3306...` 一直重试
- 宿主机上能看到 `gosu mysql ...` / `gosu postgres ...` 进程**占满一个 CPU 核**，
  但没有真正的 `mysqld` / `postgres` 进程。
- Pod 状态具有迷惑性：没有 readiness probe 的库会一直显示 `Running 1/1`。

## 快速判定

```sh
# 1) 是否有 gosu 在自旋（%CPU 接近 100，且没有真实服务进程）
ssh <node> 'ps -eo pid,stat,pcpu,etime,cmd | grep -E "gosu|mysqld|postgres" | grep -v grep'

# 2) 容器内信号是否被拒绝（决定性判据）
kubectl -n <ns> run sigtest --image=mysql:8 --restart=Never --command -- \
  /bin/sh -c 'sleep 60 & p=$!; sleep 1; kill -TERM $p; echo kill_rc=$?'
kubectl -n <ns> logs sigtest
#   正常: kill_rc=0
#   故障: kill: (N) - Permission denied   → 命中本问题
```

再看调用栈与内核判定（可选，但能一次定死）：

```sh
# Go 的全线程 setuid 广播卡在自旋
sudo perf record -g -p <gosu-pid> -- sleep 3 && sudo perf report -i perf.data --stdio | head -20
#   runtime.osyield → syscall.AllThreadsSyscall → syscall.Setgid → main.SetupUser

# AppArmor 把信号吃掉（-13 即 EPERM，且没有 signal_generate 事件）
sudo bpftrace -e '
  kretprobe:apparmor_task_kill /comm == "gosu"/ { printf("ret=%d\n", retval); }
  tracepoint:signal:signal_generate /comm == "gosu"/ { printf("sig=%d\n", args->sig); }'

# 任务标签是 stacking 形态
sudo cat /proc/<pid>/attr/current
#   cri-containerd.apparmor.d//&unconfined (enforce)
```

## 根因

内核 `7.0.0-42`（Ubuntu 26.04，2026-10-29 由 `7.0.0-38` 升级）配合
`kernel.apparmor_restrict_unprivileged_unconfined=1` 时，容器的 profile 转换会被
改成 **stacking**，任务标签变成 `cri-containerd.apparmor.d//&unconfined`。

该标签不匹配 containerd CRI profile 里的 `signal ... peer=cri-containerd.apparmor.d`
规则，于是**容器内任意信号投递都返回 EPERM**。后果：

- `gosu` 用 `syscall.AllThreadsSyscall` 给每个线程发 `SIGSETXID` 来广播
  `setgid/setuid`；信号被丢弃 → 等待循环永不结束 → 100% CPU 自旋，永远不会 exec
  出真正的 entrypoint。
- 同样地，glibc 多线程程序的 setuid 广播、postgres 给自身 backend 发信号都会失败。

与存储、CNI 无关：Ceph 全程 `HEALTH_OK`，Service EndpointSlice 正常，
修复后 ClusterIP 与 PodIP 都连通。应用报的 `no route to host` 只是「库没 Ready、
Service 无 endpoint」的下游症状。

## 修复

在**所有节点**关闭该 AppArmor 限制（保留 userns 限制），并落盘：

```sh
sudo sysctl -w kernel.apparmor_restrict_unprivileged_unconfined=0
echo 'kernel.apparmor_restrict_unprivileged_unconfined = 0' \
  | sudo tee -a /etc/sysctl.d/90-homelab-prerequisites.conf
sudo sysctl --system     # 校验 90- 文件覆盖 10-apparmor.conf 的默认值
```

本仓库已由 `metal/roles/prerequisites` 下发该配置，重建节点或重跑 Ansible 后一致。

**然后必须重建 Pod**：AppArmor 标签在容器创建时确定，已运行的容器不会自愈。

```sh
kubectl delete pod -n lobe-chat postgresql-<hash> casdoor-<hash>
kubectl delete pod -n semaphore semaphore-mysql-<hash> semaphore-<hash>
kubectl delete pod -n rsshub database-postgres-<hash>
```

## 验证

```sh
# 节点级
for h in n100-cheshi-0 n100-jumper-0 n100-jumper-1 n100-jumper-2; do
  ssh $h 'sysctl -n kernel.apparmor_restrict_unprivileged_unconfined kernel.apparmor_restrict_unprivileged_userns'
done   # 期望：0 / 1

# 数据库级
kubectl -n rsshub exec deploy/database-postgres -- pg_isready
kubectl -n lobe-chat exec deploy/postgresql -- pg_isready
kubectl -n semaphore exec deploy/semaphore-mysql -- mysqladmin ping -h 127.0.0.1 -usemaphore -psemaphore

# 应用级
kubectl -n lobe-chat logs deploy/lobe --tail=5      # Gateway: Started successfully
kubectl -n semaphore logs deploy/semaphore --tail=5 # Server is running
```

## 回退

若需要恢复 Ubuntu 默认加固（例如内核已修复）：

```sh
sudo sysctl -w kernel.apparmor_restrict_unprivileged_unconfined=1
# 从 /etc/sysctl.d/90-homelab-prerequisites.conf 删除对应行后重跑：
sudo sysctl --system
```

然后重建所有使用 `gosu`/`su-exec` 的工作负载（否则它们会再次卡死）。
**替代方案**：把内核钉回 `7.0.0-38`（`/boot` 中仍在）并阻止其被再次升级，
代价是 4 台节点依次重启。二者都是回退，不是同时保留安全默认值又修好功能的手段。

## 风险与遗留

- 关闭 `apparmor_restrict_unprivileged_unconfined` 等于回退一项 Ubuntu 加固。
  本集群容器不使用无特权 user namespace，暴露面有限，但应在内核修复后重新评估。
- 建议向 Ubuntu 报 bug：7.0.0-42 的 stacking 行为与 containerd CRI profile 的
  `signal` 规则不兼容。
- 同一批节点的另一个独立问题：`node-ip` 中的 IPv6 前缀随 ISP 前缀轮换而过期
  （`240e:3a3:20ba:ae43::/64` → `240e:3a3:2002:6440::/64`），kubelet 每 10s 报
  `failed to validate secondaryNodeIP`，hostNetwork Pod 的 IPv6 endpoint 指向不存在的
  地址。**已于 2026-10-30 修复**：节点 IPv6 改用固定站点 ULA，见
  [节点 IPv6 前缀漂移](node-ipv6-drift.md) 与
  [specs/012](../../specs/012-stable-node-ula-ipv6/plan.md)。
