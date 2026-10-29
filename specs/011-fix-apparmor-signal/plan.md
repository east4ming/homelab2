# 实施方案：修复 AppArmor 拒绝容器内信号投递

**Date**: 2026-10-29 | **目标集群**: 生产 homelab2（k3s v1.36.5+k3s1，4 节点，Ubuntu 26.04，内核 7.0.0-42）
**触发事件**: 2026-10-29 `apt upgrade`（`linux-image-generic 7.0.0-38 → 7.0.0-42`）后逐台重启
**参考**: [AppArmor unprivileged_unconfined](https://gitlab.com/apparmor/apparmor/-/wikis/unprivileged_unconfined)、[AppArmor unprivileged userns restriction](https://gitlab.com/apparmor/apparmor/-/wikis/unprivileged_userns_restriction)

---

## 1. 判定摘要

| 环节 | 现象 | 结论 |
| --- | --- | --- |
| 业务层 | 三个命名空间 Pod CrashLoop，应用报连不上库 | 下游症状，不是根因 |
| 数据库层 | gosu 100% CPU 自旋，无 mysqld/postgres 进程 | 根因所在：entrypoint 未 exec |
| 内核/安全层 | `apparmor_task_kill` 返回 -13，无 `signal_generate` | 容器内信号投递被 AppArmor 拒绝 |
| 标签层 | 任务标签为 `cri-containerd.apparmor.d//&unconfined` | 7.0.0-42 把 profile 转换改为 stacking |
| 开关层 | 仅 `kernel.apparmor_restrict_unprivileged_unconfined=0` 即可恢复 | 唯一需要改的配置 |

**结论**：功能改动只有一处——把该 sysctl 置 0 并由 metal 层固化；随后重建受影响的 Pod。

## 2. 取证（2026-10-29 实测）

### 2.1 进程与调用栈

```console
$ ssh n100-jumper-1 'ps -eo pid,stat,pcpu,cmd | grep gosu'
  51941 Rsl  98.2 gosu mysql /usr/local/bin/docker-entrypoint.sh mysqld
  52485 Rsl  99.9 gosu postgres /usr/local/bin/docker-entrypoint.sh postgres

# perf（pid 57081，一次 mysql:8 测试容器）
  28.76%  gosu  [k] entry_SYSRETQ_unsafe_stack
     runtime.osyield.abi0
     syscall.AllThreadsSyscall
     syscall.Setgid
     main.SetupUser
     main.main

# strace -p 57081
sched_yield()  = 0        # 无限循环
```

### 2.2 信号被 AppArmor 丢弃

```console
$ sudo bpftrace -e 'kretprobe:apparmor_task_kill /comm == "gosu"/ { printf("ret=%d\n", retval); }'
ret=-13        # 14 次，全部 EPERM
# 同时 tracepoint:signal:signal_generate 没有任何 gosu 的事件
```

容器内跨进程验证（同 Pod 内的 `sh`）：

```console
$ kill -TERM $p
/bin/sh: kill: (6) - Permission denied
STILL_ALIVE
```

### 2.3 标签与开关定位

```console
$ sudo cat /proc/<pid>/attr/current
cri-containerd.apparmor.d//&unconfined (enforce)     # stacking 标签

$ sysctl kernel.apparmor_restrict_unprivileged_unconfined kernel.apparmor_restrict_unprivileged_userns
kernel.apparmor_restrict_unprivileged_unconfined = 1
kernel.apparmor_restrict_unprivileged_userns = 1

$ sudo sysctl -w kernel.apparmor_restrict_unprivileged_unconfined=0
# 重建测试 Pod 后：gosu 正常 exec、容器内 kill 返回 0、目标进程 TERMINATED
```

对照矩阵（同一节点、同一镜像 `mysql:8`）：

| 容器配置 | apparmor 标签 | gosu | 容器内 kill |
| --- | --- | --- | --- |
| 默认 | `cri-containerd.apparmor.d//&unconfined` | 自旋 | Permission denied |
| `capabilities.add: ["CHOWN"]` | 同上（stacking） | 自旋 | — |
| `privileged: true` | `unconfined` | 正常 | 正常 |
| `appArmorProfile: Unconfined` | `unconfined` | 正常 | 正常 |
| `capabilities.add: ["ALL"]` | `cri-containerd.apparmor.d`（无 stacking） | 正常 | — |
| 默认 + `unprivileged_unconfined=0` | 不再 stacking | 正常 | 正常（`kill_rc=0`） |

因此**根因是 stacking 标签 + AppArmor 限制**，与租户能力、存储（Ceph 全程
`HEALTH_OK`）、CNI 连通性（修好后 ClusterIP 与 PodIP 均连通）无关。

### 2.4 被误判为「网络问题」的证据

`casdoor` 报 `dial tcp 10.43.36.163:5432: connect: no route to host`：DB 未 Ready
时 Service 没有 endpoint，属下游症状；修复后同一 ClusterIP 的连通性测试通过。

## 3. 实施

### 3.1 metal 层（唯一代码改动）

`metal/roles/prerequisites/tasks/main.yml` 的 sysctl loop 增加一行，附原因注释：

```yaml
- {name: "kernel.apparmor_restrict_unprivileged_unconfined", value: 0}
```

写入 `/etc/sysctl.d/90-homelab-prerequisites.conf`；该文件名排序晚于
`/usr/lib/sysctl.d/10-apparmor.conf`，因此覆盖默认值，且重启后仍生效。

### 3.2 线上应用

4 台节点（`n100-cheshi-0`、`n100-jumper-0/1/2`）执行 `sysctl -w` 并落盘；
`kernel.apparmor_restrict_unprivileged_userns` 保持 `1`（定点实验证明无需关闭）。

### 3.3 重建工作负载

标签在建容器时确定，已运行容器不会自愈。重建本次受影响的 Pod：
`lobe-chat/postgresql`、`lobe-chat/casdoor`、`lobe-chat/lobe`、
`semaphore/semaphore-mysql`、`semaphore/semaphore`、`rsshub/database-postgres`。
其余 Pod（含未受信号影响的）留待自然滚动，避免无谓扰动。

## 4. 验证

| 检查 | 期望 | 实测 |
| --- | --- | --- |
| `sysctl kernel.apparmor_restrict_unprivileged_unconfined` | 4 台均为 `0` | 4/4 = `0`，`userns` 仍为 `1` |
| 三个命名空间 Pod | 全部 Running | 全部 Running，无 CrashLoop |
| `pg_isready`（rsshub / lobe-chat） | `accepting connections` | 均通过 |
| `mysqladmin ping`（semaphore） | `mysqld is alive` | 通过 |
| HTTP | lobe 200 / casdoor 200 / semaphore 200 | 均通过 |
| 容器内 `kill -TERM` 兄弟进程 | 成功终止 | `kill_rc=0`、`TERMINATED` |

## 5. 备选方案与取舍

1. **内核回退到 7.0.0-38**（`/boot` 中仍在；是今天之前集群正常运行的内核）：
   可恢复原行为并保留 Ubuntu 默认加固，代价是 4 台依次重启 + apt pin 防止被
   unattended-upgrade 再升上去。本方案保留为回退路径，不实施。
2. **逐 Pod 用 `appArmorProfile: Unconfined` / `privileged` / `capabilities: ALL`**：
   已验证可行，但需改工作负载清单、削弱隔离、且只能治标（其它含 gosu 的镜像仍会中招），
   明确禁止入库。
3. **改 containerd CRI profile 增加 stacking peer 的 signal 规则**：profile 由
   containerd 内置加载，k3s 不提供覆盖入口，不可行。
4. **直接关 AppArmor**：影响面过大，拒绝。

## 6. 风险与遗留

- 关闭 `apparmor_restrict_unprivileged_unconfined` 等于回退这项 Ubuntu 加固；
  集群内容器不使用无特权 userns，暴露面有限，但应在内核修复后重新评估。
- 建议向 Ubuntu 报 bug（7.0.0-42 的 stacking 行为与 containerd CRI profile 的
  signal 规则不兼容）。
- 独立遗留：IPv6 `node-ip` 前缀过期（kubelet 持续报
  `failed to validate secondaryNodeIP`，hostNetwork Pod 的 IPv6 endpoint 指向
  不存在的地址）；修复需更新 `config.yaml` 并滚动重启 k3s，可在下次维护窗口执行。
