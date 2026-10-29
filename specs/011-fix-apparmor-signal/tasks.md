# Tasks: 修复 AppArmor 拒绝容器内信号投递

**Input**: Design documents from `specs/011-fix-apparmor-signal/`

**Prerequisites**: plan.md (required), spec.md (required)

**Organization**: 按交付链路分组，每个任务可独立验证。

## Phase 1: 取证与判定

**Purpose**: 把「连不上数据库」的表象拆到真正的故障点，避免误修网络或存储

- [x] T001 收集症状：三个命名空间 CrashLoop、`casdoor` 报 `dial tcp 10.43.36.163:5432: no route to host`
- [x] T002 排除存储与 CNI：`ceph -s` 全程 `HEALTH_OK`；Service EndpointSlice 正常；修复后 ClusterIP/PodIP 连通
- [x] T003 定位到 entrypoint：jumper-1 上 `gosu mysql`/`gosu postgres` 各 ~100% CPU，无 mysqld/postgres 进程
- [x] T004 `perf` 取调用栈：`main.SetupUser → syscall.Setgid → syscall.AllThreadsSyscall → runtime.osyield`
- [x] T005 `strace` 确认自旋：只有无穷 `sched_yield()`
- [x] T006 `bpftrace kretprobe:apparmor_task_kill`：返回 `-13 (EPERM)`，且无 `signal_generate`
- [x] T007 容器内跨进程 `kill -TERM`：`Permission denied`，目标进程存活
- [x] T008 取任务 AppArmor 标签：`cri-containerd.apparmor.d//&unconfined`（stacking）
- [x] T009 对照实验：`privileged` / `appArmorProfile: Unconfined` / `capabilities: ALL` 正常；`capabilities: CHOWN` 仍失败
- [x] T010 定点实验：仅 `kernel.apparmor_restrict_unprivileged_unconfined=0` 即恢复，`..._userns` 保持 1
- [x] T011 关联触发事件：`/var/log/apt/history.log` `2026-10-29 18:08` 升级 `7.0.0-38 → 7.0.0-42`
- [x] T012 确认影响面：受影响镜像均为 `gosu` entrypoint（postgres/mysql/paradedb）

## Phase 2: metal 层实现

- [x] T013 `metal/roles/prerequisites/tasks/main.yml` sysctl loop 增加 `kernel.apparmor_restrict_unprivileged_unconfined=0`，附原因注释
- [x] T014 YAML 可解析校验（`yaml.safe_load`）

## Phase 3: 上线与验证

- [x] T015 4 台节点 `sysctl -w` 并写入 `/etc/sysctl.d/90-homelab-prerequisites.conf`
- [x] T016 `sysctl --system` 验证优先级：`10-apparmor.conf` 之后由 `90-homelab-prerequisites.conf` 覆盖为 0
- [x] T017 重建受影响 Pod：`lobe-chat/{postgresql,casdoor,lobe}`、`semaphore/{semaphore-mysql,semaphore}`、`rsshub/database-postgres`
- [x] T018 验证数据库就绪：两个 `pg_isready` + 一个 `mysqladmin ping`
- [x] T019 验证应用：lobe/casdoor/semaphore HTTP 200
- [x] T020 复测容器内 `kill -TERM`：`kill_rc=0`、`TERMINATED`
- [x] T021 集群复查：无非 Running Pod，4 节点 Ready

## Phase 4: 文档与交付

- [x] T022 `specs/011-fix-apparmor-signal/{spec,plan,tasks}.md` 与 `checklists/requirements.md`
- [x] T023 新增 `docs/how-to-guides/troubleshooting/apparmor-signal-denied.md`，`mkdocs.yml` 导航加入该页
- [x] T024 `docs/reference/changelog.md` 增加 `v2026.10.29` 条目
- [x] T025 `AGENTS.md` 当前 Plan 指向 `specs/011-fix-apparmor-signal/plan.md`
- [x] T026 主题分支 `011-fix-apparmor-signal` + PR 合入 `master`
- [x] T027 打 annotated tag `v2026.10.29`，推送 Gitea + GitHub 并双侧复核
- [x] T028 在 Gitea（权威）与 GitHub（镜像）创建 Release，正文与 changelog 一致
