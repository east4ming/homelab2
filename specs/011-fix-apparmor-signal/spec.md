# Feature Specification: 修复 AppArmor 拒绝容器内信号投递（数据库无法启动）

**Feature Branch**: `011-fix-apparmor-signal`

**Created**: 2026-10-29

**Status**: Implemented

**Input**: User description: 修复 7.0.0-42 内核升级后 AppArmor 拒绝容器内信号投递导致 gosu 自旋、postgres/mysql 无法启动的问题

## 背景与现状

2026-10-29 对 4 台节点执行 `apt upgrade` 后逐台重启（涉及
`linux-image-generic 7.0.0-38 → 7.0.0-42`，见 `/var/log/apt/history.log` 的
`Start-Date: 2026-10-29 18:08:56`），随后 `rsshub`、`lobe-chat`、`semaphore`
三个命名空间的 Pod 进入 CrashLoop，应用侧报连不上各自的数据库。

初步判断（「连不上数据库」）只对了一半：数据库容器自身根本没起来。实测证据：

| 观测点 | 结果 | 说明 |
| --- | --- | --- |
| jumper-1 进程表 | `gosu mysql ...`、`gosu postgres ...` 各占 ~100% CPU，**没有 mysqld/postgres 进程** | entrypoint 卡在 gosu |
| `perf` 调用栈 | `main.SetupUser → syscall.Setgid → syscall.AllThreadsSyscall → runtime.osyield` | Go 的全线程 setuid 广播在自旋 |
| `strace` | 只有无穷 `sched_yield()` | 等待循环永远不满足退出条件 |
| `bpftrace kretprobe:apparmor_task_kill` | 对 gosu 返回 **-13 (EPERM)**，且无 `signal_generate` | 信号在 AppArmor 层被丢弃 |
| 容器内 `kill -TERM` 兄弟进程 | `Permission denied`，目标进程存活 | 不是 gosu 特例，容器内信号投递全部被拒 |
| 任务 AppArmor 标签 | `cri-containerd.apparmor.d//&unconfined`（stacking） | 与 containerd CRI profile 的 `signal ... peer=cri-containerd.apparmor.d` 规则不匹配 |
| 对照实验 | `privileged` / `appArmorProfile: unconfined` / `capabilities: ALL` 的容器 gosu 正常 | 确认是 AppArmor 限制，而非 gosu 或存储问题 |
| 定点实验 | 仅把 `kernel.apparmor_restrict_unprivileged_unconfined` 设为 0（保留 `..._userns=1`）后，`kill` 与 gosu 均恢复 | 锁定唯一开关 |

因果链：内核 7.0.0-42 下 Ubuntu 的 `unprivileged_unconfined` 限制会把容器的
profile 转换改为 **stacking**，stacking 标签无法匹配 containerd CRI profile 里的
`signal` 规则 → 容器内所有信号投递返回 EPERM → gosu（以及 glibc 多线程 setuid、
postgres 自身的 backend 信号）永久挂起 → 数据库容器不启动 → 应用连不上库。

受影响镜像：任何 entrypoint 走 `gosu` 的（官方 `postgres`/`mysql`、
`paradedb/paradedb` 等）。本次命中 `rsshub/database-postgres`（静默失败：Pod 显示
Running 但库没跑）、`lobe-chat/postgresql`、`semaphore/semaphore-mysql`。

## User Scenarios & Testing

### User Story 1 - 数据库容器恢复启动（Priority: P1）

作为 homelab2 运维者，我希望内核升级重启后数据库容器能正常完成 setuid 并启动，
使三个业务命名空间恢复可用，而不是面对「应用连不上库」的连锁故障。

**Why this priority**: 这是本特性的全部价值；没有它，rsshub/lobe-chat/semaphore
都不可用。

**Independent Test**: 在任一节点启动一个使用 `gosu` 的 entrypoint 容器
（如 `mysql:8` 的默认 entrypoint），容器 MUST 进入 Running 并监听端口；
在容器内 `kill -TERM` 一个兄弟进程 MUST 生效。

**Acceptance Scenarios**:

1. **Given** 4 台节点已应用修复，**When** 重启 `lobe-chat/postgresql`、
   `semaphore/semaphore-mysql`、`rsshub/database-postgres`，**Then** 三个 Pod
   均 Running，且 `pg_isready` / `mysqladmin ping` 返回 ready。
2. **Given** 数据库就绪，**When** 访问 lobe、casdoor、semaphore，
   **Then** 三者 HTTP 返回 200。
3. **Given** 修复已应用，**When** 在测试容器内执行
   `sleep 60 & sleep 1; kill -TERM $!`，**Then** 退出码为 0 且目标进程被终止。

### User Story 2 - 配置可重复、重启后仍有效（Priority: P1）

作为 homelab2 运维者，我希望修复是 metal 层声明的状态，而不是节点上的手工临时改动，
这样重建节点、批量重装或 kured 再次重启后行为一致。

**Why this priority**: 本仓库的契约是「Git 是集群状态的唯一来源」；只改线上会在
下次装机或重跑 Ansible 后丢失，故障复发。

**Independent Test**: 重跑 metal 的 prerequisites role 不产生第二次变更；节点重启
后 `sysctl kernel.apparmor_restrict_unprivileged_unconfined` 仍为 0。

**Acceptance Scenarios**:

1. **Given** 配置已落盘，**When** 再次执行 prerequisites role，**Then**
   `/etc/sysctl.d/90-homelab-prerequisites.conf` 内容不变、无第二次 reload。
2. **Given** 节点重启，**When** 读取该 sysctl，**Then** 值为 0（`90-` 文件晚于
   `/usr/lib/sysctl.d/10-apparmor.conf` 生效），且 `..._userns` 仍为 1。

### User Story 3 - 症状可诊断（Priority: P2）

作为 homelab2 运维者，我希望下次出现「容器起不来但没日志」时，能用几条命令判定
是不是 AppArmor 信号投递问题，而不是重新排查一整天。

**Why this priority**: 该故障的呈现方式极具误导性（无日志、进程 100% CPU、
应用报连不上库），没有诊断路径就会误判为数据库或网络问题。

**Independent Test**: 故障文档中的进程表、`perf`、`bpftrace`、`kill` 四条命令均在
现网可直接执行，并能给出判据。

**Acceptance Scenarios**:

1. **Given** 节点上存在卡死的 gosu 进程，**When** 执行文档中的
   `kretprobe:apparmor_task_kill` 探针，**Then** 能看到 `ret=-13` 且无信号产生事件。
2. **Given** 已应用修复，**When** 重复同一探针，**Then** gosu 已 exec 出真实进程，
   不再出现自旋。

### Edge Cases

- **旧 Pod 不会自动恢复**：AppArmor 标签在容器创建时确定，修复 sysctl 后已运行的
  容器仍带 stacking 标签，必须重建 Pod 才生效。
- **hostNetwork Pod**：`semaphore` 与 `semaphore-mysql` 使用 hostNetwork，
  进程在宿主机上可见，容易误判为宿主机问题。
- **静默失败的数据库**：没有 readiness probe 的库（如 rsshub 的
  `database-postgres`）在库没跑时仍显示 Running 1/1，必须显式验证
  `pg_isready`，不能只看 Pod 状态。
- **kured 自动重启**：kured 会在重启哨兵出现后再次重启节点；sysctl 若只 `sysctl -w`
  而不落盘，重启后故障复现。
- **升级回潮**：若后续内核修复合入并恢复默认值 1，需要重新评估本 sysctl 是否还必要；
  本仓库通过 Ansible 显式声明，避免依赖内核默认值。
- **IPv6 相关问题**：同期还存在 `node-ip` 中 IPv6 前缀过期（ISP 前缀
  由 `240e:3a3:20ba:ae43::/64` 变为 `240e:3a3:2002:6440::/64`），会持续产生
  kubelet `failed to validate secondaryNodeIP` 日志；它与本次故障无因果关系，
  单列为本特性的 Out of Scope。

## Requirements

### Functional Requirements

- **FR-001**: metal 层 MUST 在 4 台节点把 `kernel.apparmor_restrict_unprivileged_unconfined` 设为 `0`。
- **FR-002**: 修复 MUST NOT 关闭 `kernel.apparmor_restrict_unprivileged_userns`（保持 `1`），也 MUST NOT 关闭 AppArmor 或 k3s 的安全特性。
- **FR-003**: 配置 MUST 写入 `/etc/sysctl.d/90-homelab-prerequisites.conf`，使 `/usr/lib/sysctl.d/10-apparmor.conf` 的默认值 `1` 被覆盖，并在节点重启后仍然有效。
- **FR-004**: 配置 MUST 由 `metal/roles/prerequisites` 下发，重复执行幂等，不产生第二次变更。
- **FR-005**: 修复 MUST NOT 修改业务工作负载清单，**禁止**用 `privileged: true`、`appArmorProfile: Unconfined`、`capabilities.add: ALL` 等降级手段绕过（这些只允许用于取证实验，不得入库）。
- **FR-006**: 修复 MUST 包含对已运行容器的重建（至少是本次受影响的数据库与业务 Pod），使新标签生效。
- **FR-007**: 文档 MUST 记录症状、取证命令与判据、根因、修复、验证与回退步骤，并说明安全取舍与内核回退这一替代方案。
- **FR-008**: 文档 MUST 明确本修复对「新启动容器」与「已运行容器」的差异，并给出批量重建的判定方法。

### Key Entities

- **AppArmor sysctl**：`kernel.apparmor_restrict_unprivileged_unconfined`，决定容器 profile 转换是否被降级为 stacking。
- **/etc/sysctl.d/90-homelab-prerequisites.conf**：metal 层下发的 sysctl 聚合文件，本特性的持久化载体。
- **Ansible prerequisites role**：`metal/roles/prerequisites`，负责渲染上述文件。

## Success Criteria

### Measurable Outcomes

- **SC-001**: 4 台节点 `sysctl kernel.apparmor_restrict_unprivileged_unconfined` 均为 `0`，`..._userns` 均为 `1`。
- **SC-002**: `rsshub`、`lobe-chat`、`semaphore` 三个命名空间无 CrashLoop/非 Running Pod；两个 PostgreSQL 与一个 MySQL 均通过就绪探测。
- **SC-003**: lobe、casdoor、semaphore 三个应用 HTTP 探测返回 200。
- **SC-004**: 容器内 `kill -TERM` 兄弟进程成功（不再 `Permission denied`）。
- **SC-005**: 重跑 prerequisites role 幂等；节点重启后 sysctl 仍为 `0`。

## Out of Scope

- 内核回退到 7.0.0-38 / apt 版本锁定（作为备选方案记录在 plan，不在本次实施）。
- 修复 IPv6 `node-ip` 前缀过期（独立问题，见 Edge Cases）。
- 修复 Ubuntu 侧 containerd CRI profile 与 stacking 标签的 signal 规则、向上游报 bug
  （属于内核/发行版范围）。
- 给工作负载补 readiness probe（属各应用自身工程，另行处理）。

## Assumptions

- 集群内没有工作负载依赖 `apparmor_restrict_unprivileged_unconfined=1` 提供的额外限制；
  容器均不创建无特权 user namespace，因此关闭该限制的实际暴露面有限。
- 本修复等价于回退到 7.0.0-38 内核下的既有 AppArmor 行为，而非引入新能力。
- 节点 `apt upgrade` 后必然伴随重启，因此持久化到 `sysctl.d` 是必须的，不能只做 `sysctl -w`。
