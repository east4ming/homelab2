# Tasks: 节点交换内存（Node Swap，LimitedSwap）

**Input**: Design documents from `specs/010-node-swap/`

**Prerequisites**: plan.md (required), spec.md (required)

**Organization**: 按交付链路分组，每个任务可独立验证。

## Phase 1: 取证与判定

**Purpose**: 确认现状与上游行为，避免把「已满足」当成「待实现」

- [x] T001 读博客《Scaling Kubernetes Workloads with Node Swap》，确认 v1.34 GA 与 `failSwapOn`/`memorySwap` 配置
- [x] T002 实测 4 台节点：`/swap.img` 已 swapon、cgroup v2、`free -m` 见 swap
- [x] T003 实测 kubelet `/configz`：`failSwapOn=false`、`memorySwap={}`（默认 NoSwap）、`nodeInfo.swap.capacity` 非空
- [x] T004 读 k3s 源码：`pkg/daemons/agent/agent.go` 默认 `FailSwapOn=false`、kubelet 带 `--config-dir`、目录内 `00-k3s-defaults.conf` 每次重写
- [x] T005 读 kubelet 源码：`GetContainerSwapBehavior` 的 LimitedSwap 条件与 `calcSwapForBurstablePods` 公式
- [x] T006 读 k3s 源码 `extractConfigArgs`/`writeKubeletConfig`：确认 drop-in 目录与文件命名规则 (`.conf`、字典序)

## Phase 2: metal 层实现

- [x] T007 新增 `metal/roles/k3s/templates/kubelet-swap.conf.j2`（`failSwapOn: false` + `memorySwap.swapBehavior: LimitedSwap`）
- [x] T008 `defaults/main.yml` 增加 `k3s_kubelet_config_dir`
- [x] T009 `tasks/main.yml` 确保 drop-in 目录（0700）+ 渲染 `90-swap.conf`（0600）+ notify Restart k3s
- [x] T010 本地校验：`yamllint`、`ansible-playbook --syntax-check`、模板 YAML 可解析

## Phase 3: 上线与验证

- [x] T011 串行应用：worker → master-0 → master-1 → master-2，逐台重启并等 Ready
- [x] T012 4 台 `/configz` 均为 `memorySwap.swapBehavior == LimitedSwap`
- [x] T013 Burstable 测试 Pod 的 `memory.swap.max > 0`；Guaranteed/BestEffort 为 0；测试后删除
- [x] T014 `kubectl get nodes` 全 Ready、`kubectl top nodes --show-swap` 正常
- [x] T015 幂等复跑：drop-in 无变化、不触发重启

## Phase 4: 文档与交付

- [x] T016 新增 `docs/how-to-guides/node-swap.md`（背景/条件/公式/验证/回退/风险）
- [x] T017 `mkdocs.yml` 导航加入该页；`.venv/bin/mkdocs build --strict` 通过
- [x] T018 `docs/reference/changelog.md` 增加 `v2026.10.17.2` 条目
- [x] T019 `AGENTS.md` 当前 Plan 指向 `specs/010-node-swap/plan.md`
- [ ] T020 主题分支 `010-node-swap` + PR 合入 `master`
- [ ] T021 打 annotated tag `v2026.10.17.2`，推送 Gitea + GitHub 并双侧复核
- [ ] T022 在 Gitea（权威）与 GitHub（镜像）创建 Release，正文与 changelog 一致
