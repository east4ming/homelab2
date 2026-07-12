# Tasks: KubeVirt 测试体系

**Input**: Design documents from `specs/004-kubevirt-testing/`

**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, quickstart.md

**Tests**: 本 feature 以测试为交付物 — 所有用户故事均包含测试实现任务。测试即实现。

**Organization**: 任务按用户故事分组，每个故事可独立实现和验证。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可并行执行（不同文件，无依赖）
- **[Story]**: 所属用户故事（US1, US2, US3, US4）
- 描述中包含精确文件路径

## Path Conventions

源码根目录: `system/kubevirt/tests/`

---

## Phase 1: Setup（项目初始化）

**Purpose**: 创建项目骨架和依赖管理

- [ ] T001 创建目录结构：`system/kubevirt/tests/{lib,manifests/unit,manifests/integration,manifests/e2e,unit,integration,e2e}`
- [ ] T002 初始化 `system/kubevirt/tests/pyproject.toml`，声明 uv 依赖（pytest, pyyaml, kubernetes, pexpect, rich）
- [ ] T003 [P] 在 `system/kubevirt/tests/pyproject.toml` 中配置 ruff lint 规则，与项目惯例对齐

---

## Phase 2: Foundational（共享基础库）

**Purpose**: 所有用户故事依赖的公共 Python 模块，MUST 在本阶段完成后才能开始任何用户故事

**⚠️ CRITICAL**: 用户故事实现本阶段完成前不能开始

- [ ] T004 创建 `system/kubevirt/tests/lib/__init__.py` 包初始化，导出公共 API
- [ ] T005 [P] 实现 `system/kubevirt/tests/lib/common.py`：subprocess 封装（kubectl/helm/virtctl 调用）、wait_for_condition()、断言函数、日志函数
- [ ] T006 [P] 实现 `system/kubevirt/tests/lib/resource_limiter.py`：check_vm_limit()、validate_vm_resources()、wait_for_slot()、current_count property
- [ ] T007 [P] 实现 `system/kubevirt/tests/lib/report_generator.py`：TestResult/Summary dataclass、generate_markdown_report()、支持按套件分组统计

**Checkpoint**: 共享库就绪 — 用户故事实现可开始

---

## Phase 3: User Story 1 - 基础资源单元验证 (Priority: P1) 🎯 MVP

**Goal**: 验证 KubeVirt 单个核心资源（VM、VMI、DataVolume）的创建→就绪→销毁生命周期

**Independent Test**: `uv run pytest unit/ integration/ -k "vm_lifecycle or vmi_lifecycle or datavolume or helm_template"` — 全部通过即 US1 完成

### Implementation for User Story 1

- [ ] T008 [P] [US1] 创建 `system/kubevirt/tests/manifests/unit/values-override.yaml` 和 `system/kubevirt/tests/unit/test_helm_template.py`：验证 Chart 默认渲染 + 自定义 values 覆盖，断言 4 个核心资源（CDI Operator、KubeVirt Operator、KubeVirt CR、CDI CR）存在
- [ ] T009 [P] [US1] 创建 `system/kubevirt/tests/manifests/integration/vm-cirros.yaml` 和 `system/kubevirt/tests/integration/test_vm_lifecycle.py`：测试 VM 创建→Running（≤120s）→kubectl delete→资源清理验证
- [ ] T010 [P] [US1] 创建 `system/kubevirt/tests/manifests/integration/vmi-ephemeral.yaml` 和 `system/kubevirt/tests/integration/test_vmi_lifecycle.py`：测试 VMI 创建→Running→删除，≤120s 超时
- [ ] T011 [P] [US1] 创建 `system/kubevirt/tests/manifests/integration/datavolume-cirros.yaml` 和 `system/kubevirt/tests/integration/test_datavolume.py`：测试 DataVolume HTTP 导入 CirrOS 镜像→Succeeded，验证状态转换和超时处理

**Checkpoint**: US1 独立可测 — 4 个单资源测试全部通过

---

## Phase 4: User Story 2 - 关联资源集成验证 (Priority: P2)

**Goal**: 验证 VM + DataVolume 组合启动 和 VM + Service 流量路由

**Independent Test**: `uv run pytest integration/ -k "vm_datavolume or vm_service"` — 全部通过即 US2 完成

### Implementation for User Story 2

- [ ] T012 [P] [US2] 创建 `system/kubevirt/tests/manifests/integration/vm-datavolume.yaml` 和 `system/kubevirt/tests/integration/test_vm_datavolume.py`：先创建 DataVolume，待 Succeeded 后创建 VM 引用该 DV，验证 VM 正常启动
- [ ] T013 [P] [US2] 创建 `system/kubevirt/tests/manifests/integration/vm-service.yaml` 和 `system/kubevirt/tests/integration/test_vm_service.py`：创建 VM + ClusterIP Service，验证从集群内可访问 Service 端口

**Checkpoint**: US1 + US2 均可独立通过

---

## Phase 5: User Story 3 - 生产级 VM 端到端验证 (Priority: P3)

**Goal**: 验证完整生产配置 VM（网络 + PVC 持久存储 + cloud-init SSH 密钥）的全部功能

**Independent Test**: `uv run pytest e2e/ -k "production_vm or vm_connectivity"` — 全部通过即 US3 完成

### Implementation for User Story 3

- [ ] T014 [P] [US3] 创建 `system/kubevirt/tests/manifests/e2e/production-vm.yaml`（Fedora 40, 2C4G, PVC 启动盘 + 数据盘, cloud-init SSH 密钥注入, masquerade 网络）和 `system/kubevirt/tests/manifests/e2e/cloud-init-secret.yaml`
- [ ] T015 [US3] 实现 `system/kubevirt/tests/e2e/test_production_vm.py`：VM 创建→Running→SSH 登录→virtctl console 登录→文件写入持久化盘→virtctl restart→SSH 再次登录验证文件存在→dnf install nginx→nginx 启动验证→多次重启稳定性
- [ ] T016 [US3] 实现 `system/kubevirt/tests/e2e/test_vm_connectivity.py`：创建 2 个 VM→VM 间 ping 互通→VM 内 ping 外部地址（DNS/公网）→验证网络连通性

**Checkpoint**: US1 + US2 + US3 全部通过 — 三层测试覆盖完成

---

## Phase 6: User Story 4 - 测试报告生成 (Priority: P4)

**Goal**: 验证测试报告格式正确、内容完整、CI 可采集

**Independent Test**: 执行任意测试后检查生成的 Markdown 报告结构完整性

### Implementation for User Story 4

- [ ] T017 [US4] 创建 `system/kubevirt/tests/unit/test_report_generator.py`：单元测试验证 report_generator 输出包含必要字段（标题、执行时间、摘要表、详细结果表、通过率），以及边界情况（0 用例、全部失败、全部跳过）

**Checkpoint**: 报告生成逻辑已验证

---

## Phase 7: Polish & 集成串联

**Purpose**: 主入口、文档、端到端验证

- [ ] T018 实现 `system/kubevirt/tests/run.py`：CLI 入口（argparse: --suite, --verbose, --report），Phase 0 环境检查（kubectl/virtctl/helm/KubeVirt/CDI/CSI），按序执行 suite，资源清理确保，退出码映射
- [ ] T019 [P] 创建 `system/kubevirt/tests/README.md`：使用说明、依赖安装、命令示例、报告样例
- [ ] T020 按 `specs/004-kubevirt-testing/quickstart.md` 完整走一遍流程，验证所有步骤可执行且输出符合预期

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: 无依赖 — 立即开始
- **Foundational (Phase 2)**: 依赖 Setup 完成 — **阻塞所有用户故事**
- **User Stories (Phase 3-6)**: 全部依赖 Foundational 完成
  - US1 (P1) → US2 (P2) → US3 (P3) → US4 (P4) 建议顺序执行（资源需求递增）
  - US4 可与 US1/US2 并行（纯单元测试，不依赖集群资源）
- **Polish (Phase 7)**: 依赖所有用户故事完成

### User Story Dependencies

- **US1 (P1)**: Foundational 完成后即可开始 — 不依赖其他故事
- **US2 (P2)**: Foundational 完成后即可开始 — 逻辑上依赖 US1 中 DataVolume 测试的经验，但代码独立
- **US3 (P3)**: Foundational 完成后即可开始 — 资源需求最高（2 VM），建议 US1 通过后再启动以降低排查难度
- **US4 (P4)**: Foundational 完成后即可开始 — 纯单元测试，可与其他故事并行

### Within Each User Story

- YAML manifests 与 Python test script 为同一任务的产出（紧耦合，不拆分）
- 同一 Story 内标记 [P] 的任务可并行实现

### Parallel Opportunities

- Phase 1: T002, T003 可并行
- Phase 2: T005, T006, T007 全部可并行
- Phase 3 (US1): T008, T009, T010, T011 全部可并行（不同文件）
- Phase 4 (US2): T012, T013 可并行
- Phase 5 (US3): T014 先于 T015/T016（manifest 是前提）；T015, T016 可并行
- Phase 7: T018, T019 可并行

---

## Parallel Example: User Story 1

```bash
# 4 个测试可并行实现（不同文件，无依赖）:
Task: "T008 [P] [US1] unit/test_helm_template.py"
Task: "T009 [P] [US1] integration/test_vm_lifecycle.py"
Task: "T010 [P] [US1] integration/test_vmi_lifecycle.py"
Task: "T011 [P] [US1] integration/test_datavolume.py"
```

---

## Implementation Strategy

### MVP First (US1 Only)

1. Complete Phase 1: Setup（创建骨架 + pyproject.toml）
2. Complete Phase 2: Foundational（lib/common, resource_limiter, report_generator）
3. Complete Phase 3: US1（4 个基础资源测试）
4. **STOP and VALIDATE**: `uv run pytest unit/ integration/` — 验证全部通过
5. 查看生成报告 → 确认 Markdown 格式正确

### Incremental Delivery

1. Setup + Foundational → 共享库就绪
2. Add US1 → 单资源测试通过 → **MVP!**
3. Add US2 → 关联资源测试通过 → 集成覆盖完整
4. Add US3 → 端到端测试通过 → 生产级验证完成
5. Add US4 → 报告格式验证通过
6. Polish → run.py + README → 交付

---

## Notes

- [P] 任务 = 不同文件，无依赖，可并行
- [Story] 标签将任务映射到具体用户故事
- 每个 User Story 应独立可测、可交付
- 测试即实现：每个任务的产出是可运行的测试脚本 + 对应的 YAML manifest
- 执行测试前确保 namespace `kubevirt-test` 存在且无残留资源
- SSH 密钥临时生成（`ssh-keygen` subprocess），不提交仓库
- 单个 VM ≤2C4G，同时运行 ≤2 VM（resource_limiter 强制）
- 提交粒度：每个任务或逻辑组完成后提交一次
