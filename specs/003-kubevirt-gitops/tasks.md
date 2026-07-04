# Tasks: KubeVirt GitOps 部署与虚拟机管理

**Input**: Design documents from `/specs/003-kubevirt-gitops/`

**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, quickstart.md

**Tests**: 手动验证（无自动化测试要求，IaC 项目以 ArgoCD 同步状态和组件健康检查为验证手段）

**Organization**: Tasks grouped by user story for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- Infrastructure charts: `system/<name>/`
- All tasks operate within `system/kubevirt/` and its subdirectories
- VM manifests: `system/kubevirt/templates/`

---

## Phase 1: Setup — 集群前置检查

**Purpose**: 验证集群节点硬件虚拟化支持，确保 KubeVirt 部署前提条件满足

- [ ] T001 验证所有集群节点 `/dev/kvm` 存在且 KVM 内核模块已加载，在 `system/kubevirt/` 目录创建前完成节点巡检
- [ ] T002 如有节点缺少 `/dev/kvm`（参考 quickstart.md 前置条件），安装 `qemu-kvm` 包并加载 `kvm_intel` 内核模块

---

## Phase 2: Foundational — Helm Chart 骨架

**Purpose**: 创建符合项目 ApplicationSet 规范的 Helm Chart 基本结构，阻塞所有 user story

**⚠️ CRITICAL**: 无 Chart.yaml + values.yaml 则 ArgoCD 无法发现此 Chart

- [ ] T003 Create `system/kubevirt/Chart.yaml` — umbrella chart，声明 KubeVirt 和 CDI 的上游清单依赖关系
- [ ] T004 Create `system/kubevirt/values.yaml` — 参数化配置：KubeVirt 版本号、useEmulation 开关（默认 false）、组件资源 limits/requests、workload/infra nodePlacement

**Checkpoint**: Chart 骨架就绪 — 可开始填充模板

---

## Phase 3: User Story 1 - 通过 ArgoCD GitOps 安装 KubeVirt (Priority: P1) 🎯 MVP

**Goal**: KubeVirt + CDI 通过 ArgoCD GitOps 在 k3s 集群上部署运行

**Independent Test**: `kubectl get kv -n kubevirt` 显示 `Deployed`，所有 virt-* Pod Running

### Implementation for User Story 1

- [ ] T005 [P] [US1] Create CDI Operator 模板 in `system/kubevirt/templates/cdi-operator.yaml` — 从上游 https://github.com/kubevirt/containerized-data-importer/releases 获取稳定版 operator YAML，参数化命名空间为 `kubevirt`
- [ ] T006 [P] [US1] Create CDI CR 模板 in `system/kubevirt/templates/cdi-cr.yaml` — CDI Custom Resource，触发 operator 部署 CDI 组件
- [ ] T007 [P] [US1] Create KubeVirt Operator 模板 in `system/kubevirt/templates/kubevirt-operator.yaml` — 从上游 https://github.com/kubevirt/kubevirt/releases 获取稳定版 operator YAML，参数化命名空间
- [ ] T008 [P] [US1] Create KubeVirt CR 模板 in `system/kubevirt/templates/kubevirt-cr.yaml` — KubeVirt Custom Resource，引用 values.yaml 中的 `useEmulation` 和 nodePlacement 配置
- [ ] T009 [US1] 提交代码到 Git 仓库，合并 feature 分支到 `master` 分支并 `git push origin master`，触发 ArgoCD ApplicationSet 自动扫描 `system/` 目录
- [ ] T010 [US1] 等待 ArgoCD 自动同步完成：在 ArgoCD UI 中确认 Application `system-kubevirt` 创建且同步状态为 `Synced`，或通过 `kubectl get app -n argocd system-kubevirt` 验证
- [ ] T011 [US1] 验证 KubeVirt 部署完成：`kubectl get kv -n kubevirt kubevirt` 状态 `Deployed`，所有 virt-* Pod Running，CDI Pod Running

**Checkpoint**: KubeVirt 平台就绪 — VM 可以在此之上创建

---

## Phase 4: User Story 2 - 创建带持久化磁盘的虚拟机 (Priority: P2)

**Goal**: 通过 GitOps 声明式创建运行 Ubuntu 26.04 LTS 的虚拟机，配置持久化数据磁盘

**Independent Test**: VM Running，写入数据到持久化磁盘，重启后数据不丢失

### Implementation for User Story 2

- [ ] T012 [P] [US2] Create Ubuntu Cloud Image DataVolume 模板 in `system/kubevirt/templates/demo-vm-dv.yaml` — DataVolume 从 Ubuntu Cloud Image URL 导入 qcow2 镜像到 PVC（storageClassName: standard-rwo, 10Gi）
- [ ] T013 [P] [US2] Create cloud-init Secret 模板 in `system/kubevirt/templates/demo-vm-cloudinit.yaml` — 注入 SSH 公钥和 hostname 配置，使用 Kubernetes Secret 存储 cloud-init user-data
- [ ] T014 [US2] Create VirtualMachine 模板 in `system/kubevirt/templates/demo-vm.yaml` — 引用 DataVolume 作为 rootDisk，挂载持久化数据磁盘 PVC（data-disk, 10Gi, standard-rwo），配置 runStrategy: Always，2 vCPU / 4Gi RAM，网络使用 masquerade 模式
- [ ] T015 [US2] 提交 VM 清单到 Git 仓库，合并到 `master` 并 push，ArgoCD 自动同步后验证 VM 状态：`kubectl get vm -n kubevirt demo-vm` 显示 `Running`
- [ ] T016 [US2] 验证数据持久化：登录 VM 控制台写入测试文件 → virtctl restart → 重新登录验证文件存在

**Checkpoint**: 带持久化磁盘的 VM 可正常运行，数据重启不丢失

---

## Phase 5: User Story 3 - 访问和管理虚拟机 (Priority: P3)

**Goal**: 通过 virtctl 访问 VM 控制台并管理生命周期

**Independent Test**: `virtctl console demo-vm` 成功进入控制台，可登录并执行命令

### Implementation for User Story 3

- [ ] T017 [US3] 验证 virtctl console 访问：`virtctl console -n kubevirt demo-vm` → 出现登录提示，使用 cloud-init 配置的凭据登录
- [ ] T018 [US3] 验证 VM 生命周期管理：执行 virtctl stop / start / restart，确认 VM 状态转换正确（Running ↔ Stopped）
- [ ] T019 [US3] 编写 VM 运维操作文档 in `system/kubevirt/README.md` — 常用 virtctl 命令、故障排查、镜像更新流程

**Checkpoint**: VM 可完全通过 virtctl 管理，运维文档就绪

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: 质量门禁、文档验证、最终检查

- [ ] T020 [P] 运行 `helm lint system/kubevirt/` — 确保 Chart 通过 helmlint 校验（Constitution I）
- [ ] T021 [P] 运行 `yamllint system/kubevirt/` — 确保所有 YAML 通过 yamllint 校验（Constitution I）
- [ ] T022 [P] 运行 `kubectl get events -n kubevirt --sort-by='.lastTimestamp'` — 检查无异常事件
- [ ] T023 按 quickstart.md 执行端到端验证流程：部署 → 创建 VM → 控制台访问 → 数据持久化 → 生命周期管理
- [ ] T024 将 KubeVirt 组件状态检查纳入 `make smoke-test` 冒烟测试（可选增强，需在测试脚本中添加 `kubectl get kv -n kubevirt` 状态检查）

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: No dependencies on Phase 1（可并行）— blocks all user stories
- **User Story 1 (Phase 3)**: Depends on Phase 2 completion — blocks US2, US3
- **User Story 2 (Phase 4)**: Depends on US1 (KubeVirt running) — blocks US3 validation
- **User Story 3 (Phase 5)**: Depends on US2 (VM running) — 验证型任务
- **Polish (Phase 6)**: Depends on all user stories complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Phase 2 — No dependencies on other stories — **MVP**
- **User Story 2 (P2)**: Depends on US1 (KubeVirt + CDI must be deployed for DataVolume to work)
- **User Story 3 (P3)**: Depends on US2 (VM must exist and be running to test console/lifecycle)

### Within Each Phase

- Phase 3 (US1): T005–T008 all [P] — can run in parallel → T009 (commit + merge to master + push) → T010 (wait ArgoCD sync) → T011 (verify deployment)
- Phase 4 (US2): T012–T013 [P] — can run in parallel → T014 (sequential, references both) → T015 (merge master + push + ArgoCD sync) → T016 (verify persistence)
- Phase 5 (US3): T017–T019 — sequential validation
- Phase 6 (Polish): T020–T022 [P] — can run in parallel → T023 → T024

### GitOps 关键流程

**ArgoCD ApplicationSet 配置监听 `master` 分支**（repo: `http://gitea-http.gitea:3000/ops/homelab2`），因此：

1. 在 feature 分支（`003-kubevirt-gitops`）上完成所有文件创建
2. 合并到 `master` 分支：`git checkout master && git merge 003-kubevirt-gitops`
3. 推送到远程：`git push origin master`
4. ArgoCD ApplicationSet 检测到 `master` 分支变更后自动创建/更新 Application
5. Application 按 syncPolicy 自动同步到集群（automated prune + selfHeal）

### Parallel Opportunities

- Phase 1 + Phase 2 can run in parallel (KVM check + Chart skeleton are independent)
- T005, T006, T007, T008: all 4 templates can be created in parallel
- T012, T013: DataVolume + cloud-init can be created in parallel
- T020, T021, T022: linting checks can run in parallel

---

## Parallel Example: User Story 1 Templates

```bash
# Launch all 4 template creation tasks in parallel:
Task: "Create CDI Operator 模板 in system/kubevirt/templates/cdi-operator.yaml"
Task: "Create CDI CR 模板 in system/kubevirt/templates/cdi-cr.yaml"
Task: "Create KubeVirt Operator 模板 in system/kubevirt/templates/kubevirt-operator.yaml"
Task: "Create KubeVirt CR 模板 in system/kubevirt/templates/kubevirt-cr.yaml"
```

## Parallel Example: Polish Checks

```bash
# Launch all 3 linting/event checks in parallel:
Task: "helm lint system/kubevirt/"
Task: "yamllint system/kubevirt/"
Task: "kubectl get events -n kubevirt"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: KVM 节点检查
2. Complete Phase 2: Chart 骨架 (Chart.yaml + values.yaml)
3. Complete Phase 3: User Story 1 — KubeVirt + CDI templates
4. **合并到 master 并 push** → ArgoCD 自动同步
5. **STOP and VALIDATE**: `kubectl get kv -n kubevirt` → Deployed，所有 virt-* Pod Running
6. KubeVirt 平台就绪即为可交付 MVP

### Incremental Delivery

1. Phase 1 + 2 → Foundation ready
2. 创建模板 + merge master push → US1 (KubeVirt deployed) → **MVP!**
3. 创建 VM 清单 + merge master push → US2 (VM with persistent disk) → VM 可运行、数据持久
4. 验证控制台/生命周期 → US3 (Console access + lifecycle) → 完整的 VM 管理能力
5. Phase 6 (Polish) → 质量门禁通过、文档完善

### Single Developer Strategy

由于 US2 依赖 US1（需要 KubeVirt 运行）、US3 依赖 US2（需要 VM 运行），单开发者按 Phase 1 → 2 → 3 → 4 → 5 → 6 顺序执行。**每个 Phase 完成后需 merge 到 master 并 push 才能触发 ArgoCD 同步**，每阶段约 5-15 分钟（不含 ArgoCD 同步等待时间）。

---

## Notes

- [P] tasks = 不同文件，无依赖，可并行
- [US?] label = 映射到 spec.md 中的 user story
- **GitOps 触发机制**：ArgoCD ApplicationSet 监听 `master` 分支（repo URL: `http://gitea-http.gitea:3000/ops/homelab2`），所有代码变更必须 merge 到 master 并 push 后才能触发 ArgoCD 自动同步。feature 分支上的变更不会被 ArgoCD 感知。
- **Merge 流程**：`git checkout master && git merge 003-kubevirt-gitops && git push origin master`
- T001/T002 中的 SSH 节点检查已在 plan 阶段完成一次验证（192.168.3.158 节点 `/dev/kvm` 可用），正式部署前需确认所有 4 个节点
- CDI 与 KubeVirt 版本需匹配，模板中应引用 `.Values.kubevirtVersion` 和 `.Values.cdiVersion` 参数
- 镜像导入（DataVolume）可能耗时较长（取决于 Ubuntu Cloud Image 下载速度），不计入 SC-002 的 60 秒指标
- KubeVirt virt-handler 为 DaemonSet，每个节点运行一个实例，需确保所有节点 KVM 就绪
