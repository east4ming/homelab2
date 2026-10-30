# Tasks: 节点 IPv6 身份改用站点 ULA

**Input**: Design documents from `specs/012-stable-node-ula-ipv6/`

**Prerequisites**: plan.md (required), spec.md (required)

**Organization**: 按交付链路分组，每个任务可独立验证。

## Phase 1: 设计

- [x] T001 确认根因：`node-ip` 里的 IPv6 是 ISP GUA 字面量，前缀轮换后指向不存在的地址
- [x] T002 确认影响面：kubelet `secondaryNodeIP` 告警、`CiliumNode` 旧地址、跨节点 IPv6 直连路由缺失、hostNetwork endpoint 失效
- [x] T003 确认 Cilium 侧无需改配置：`ipam: cluster-pool` 只分配 Pod 网段；节点地址由 agent 启动时写入 `CiliumNode`
- [x] T004 验证 netplan 合并语义：独立文件只写 ULA 时 `addresses` 追加、IPv4 保留（`netplan generate` 产物取证）
- [x] T005 定址：节点用 `fdb5:92d0:b067:1::/64`，主机位 `::11`~`::14`（Pod `/56`、Service `/112` 不变）

## Phase 2: metal 层实现

- [x] T006 `metal/inventories/prod.yml`：新增 `dualstack_ipv6_node_cidr` 与 4 台 host 的 `node_ipv6`
- [x] T007 `metal/roles/prerequisites/templates/netplan-ula.yaml.j2` + task + `Apply netplan` handler
- [x] T008 `metal/roles/k3s/tasks/main.yml`：删除运行时探测 GUA，改为断言 `node_ipv6` 已在接口上
- [x] T009 `metal/roles/pxe_server/templates/user-data.j2`：新装机 netplan 带 ULA
- [x] T010 `yamllint` / `ansible-lint` / `pre-commit` 通过（新任务无 lint 命中）

## Phase 3: 文档与测试

- [x] T011 `docs/reference/architecture/networking.md`：地址规划、为什么不用 GUA、路由器无需改动、流量路径
- [x] T012 新增 `docs/how-to-guides/troubleshooting/node-ipv6-drift.md` + `mkdocs.yml` 导航
- [x] T013 `specs/012-stable-node-ula-ipv6/{spec,plan,tasks}.md` + `checklists/requirements.md`
- [x] T014 新增 `test/node_addressing_test.go`（`TestNodeAddressing`）+ `test/README.md` 登记
- [x] T015 `specs/009/runbook.md` 与 `troubleshooting/apparmor-signal-denied.md` 增加指向本次修复的交叉引用

## Phase 4: 线上应用（2026-10-30）

- [x] T016 备份：4 台 `/etc/netplan`、`/etc/rancher/k3s/config.yaml` → `/root/backup-20261030/`；路由器 `/etc/config` + `uci export`
- [x] T017 4 台写入 `/etc/netplan/60-homelab-ula.yaml`（0600）并 `netplan apply`，确认 ULA 在接口上、GUA 与默认路由未变
- [x] T018 4 台节点间 `ping6` ULA 互通（L2，不经过路由器）
- [x] T019 4 台改 `config.yaml` 的 `node-ip` / `kubelet-arg` 为 ULA，逐台重启 k3s（worker 先）
- [x] T020 逐台重启 cilium agent，`cilium-dbg node list` 与 `ip -6 route` 切换为 ULA
- [x] T021 验证：4 台 IPv6 InternalIP = 规划值、`secondaryNodeIP` 计数 0、3 条跨节点直连路由、跨节点 pod IPv6 通、三命名空间 Running、应用 HTTP 可用
- [x] T022 `go test -run TestNodeAddressing` PASS

## Phase 5: 交付流程（versioning.md）

- [x] T023 主题分支 `012-stable-node-ula-ipv6`
- [x] T024 提交（Conventional Commits，scope 到 `metal/*`、`docs`、`test`）
- [x] T025 推送分支并在 Gitea 开 PR，合入 `master`
- [x] T026 `docs/reference/changelog.md` 增加 `v2026.10.30`；`AGENTS.md` 当前 Plan 指向 012
- [x] T027 打 annotated tag `v2026.10.30`，推送 Gitea + GitHub 并双侧复核
- [x] T028 在 Gitea（权威）与 GitHub（镜像）创建 Release，正文与 changelog 一致

## Phase 6: 路由器结论

- [x] T029 只读核查 `192.168.3.1`：LAN 是 `br-lan` 桥、无 ULA 配置、无该 `/64` 路由与邻居表项
- [x] T030 结论：**GUA→ULA 不需要改路由器**；节点间 IPv6 走二层转发，外部访问仍走 Tailscale
