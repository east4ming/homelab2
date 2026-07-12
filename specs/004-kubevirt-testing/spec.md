# Feature Specification: KubeVirt 测试体系

**Feature Branch**: `004-kubevirt-testing`

**Created**: 2026-07-12

**Status**: Draft

**Input**: User description: "为 @system/kubevirt/ 添加测试. 具体需求为: 单元测试, 集成测试, 端到端测试 都要. 测试方式为: 通过 kubectl 或 virtctl 创建单独资源; 创建多个关联的资源; 创建完整的生产级别vm(网络, 存储持久化, 安全, ssh 等完善) 并且验证通过. 如: virtctl console登陆, ssh 登陆, 网络联通性正常, 持久化存储正常等. apt 安装等日常使用."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 基础资源单元验证 (Priority: P1)

作为平台运维人员，我需要验证 KubeVirt 的单个核心资源（VM、VMI、DataVolume、PVC）能否被正确创建、运行和销毁，以确保基础 API 功能正常。

**Why this priority**: 单个资源的 CRUD 是所有上层功能的基础。如果基础资源创建失败，所有后续测试都无法进行。这是 CI/CD 流水线的第一道门禁，必须优先通过。

**Independent Test**: 可通过 `kubectl apply` 创建单个 VM/VMI/DataVolume 资源，等待就绪，然后 `kubectl delete` 清理，全程自动化验证状态变化。无需依赖其他测试用例。

**Acceptance Scenarios**:

1. **Given** KubeVirt 集群已部署，**When** 创建一个最小化 VirtualMachine 资源（2C4G 以内），**Then** VM 自动启动并进入 Running 状态，且可通过 `kubectl get vm` 确认
2. **Given** KubeVirt 集群已部署，**When** 创建一个 VirtualMachineInstance 资源，**Then** VMI 在 120 秒内进入 Running 状态
3. **Given** CDI 已部署，**When** 创建一个 DataVolume 资源（从 HTTP 源导入镜像），**Then** DataVolume 在超时时间内完成导入并进入 Succeeded 状态
4. **Given** 一个 Running 状态的 VM，**When** 执行 `kubectl delete vm`，**Then** VM 及其关联的 VMI 在 60 秒内被完全清理，不残留 Pod 或 PVC（若未单独指定保留）
5. **Given** 集群资源紧张，**When** 同时创建超过 2 个 VM，**Then** 测试框架拒绝创建第 3 个 VM，并输出资源限制警告

---

### User Story 2 - 关联资源集成验证 (Priority: P2)

作为平台运维人员，我需要验证多个 KubeVirt 资源之间的关联关系是否正确工作，包括 VM + DataVolume、VM + Service 等组合，确保资源编排的可靠性。

**Why this priority**: 生产环境中 VM 从来不是孤立存在的，它需要存储、网络的配合。单资源验证通过后，必须确认资源间的依赖和联动正确。

**Independent Test**: 可通过创建 VM + DataVolume + Service 组合，验证 VM 从 DataVolume 引导启动并通过 Service 暴露端口，最后验证外部可访问。

**Acceptance Scenarios**:

1. **Given** 已有一个 Succeeded 状态的 DataVolume，**When** 创建一个 VM 引用该 DataVolume 作为启动盘，**Then** VM 正常启动并可使用该持久化存储
2. **Given** 两个 VM 在同一网络，**When** 从一个 VM ping 另一个 VM 的 IP，**Then** 网络互通且延迟在正常范围内
3. **Given** VM 已创建 Service，**When** 从集群内访问该 Service，**Then** 流量正确路由到 VM 内部服务

---

### User Story 3 - 生产级 VM 端到端验证 (Priority: P3)

作为平台运维人员，我需要验证一个完整配置的生产级别 VM（包含网络、持久化存储、安全加固、SSH 访问）能够正常运行，且用户可以像使用传统 VM 一样进行日常操作（SSH 登录、apt 安装软件、重启后数据持久化）。

**Why this priority**: 这是最终的用户验收标准。只有生产级 VM 的所有特性全部通过验证，才能证明 KubeVirt 平台真正可用。但由于对资源要求较高（需要完整 VM），优先级放在基础验证之后。

**Independent Test**: 可创建一个完整生产配置的 VM（网络 + PVC 持久化存储 + cloud-init SSH 密钥 + 安全上下文），执行以下端到端验证流程：创建 → 等待就绪 → SSH 登录 → 写入测试文件 → 重启 VM → 再次 SSH 登录验证文件存在 → `apt install` 测试 → 网络连通性测试 → 清理。全程自动化。

**Acceptance Scenarios**:

1. **Given** 集群资源充足（≤2 个 VM 运行中），**When** 创建一个生产级 VM（含 cloud-init SSH 密钥、PVC 持久化存储、网络配置），**Then** VM 在 180 秒内进入 Running 状态，可通过 `virtctl console` 和 SSH 两种方式登录
2. **Given** 生产级 VM 运行中且已通过 SSH 登录，**When** 在 VM 内执行 `echo test > /persistent/data.txt && sync` 后重启 VM，**Then** VM 重启完成后再次 SSH 登录，文件 `/persistent/data.txt` 内容保持不变
3. **Given** 生产级 VM 运行中，**When** 执行 `apt update && apt install -y nginx`，**Then** 软件安装成功，nginx 服务可正常启动，监听端口可接受请求
4. **Given** 生产级 VM 运行中，**When** 从 VM 内部 ping 外部地址（如 `8.8.8.8` 或集群 DNS），**Then** 网络连通性正常
5. **Given** 生产级 VM 运行中，**When** 多次重启 VM（至少 3 次），**Then** 每次重启后 VM 均能在 120 秒内恢复正常运行状态

---

### User Story 4 - 测试报告生成 (Priority: P4)

作为平台运维人员，我需要在每次测试执行后获得一份完整的测试报告，清楚展示各项测试的通过/失败状态、耗时、以及失败原因，以便快速定位问题。

**Why this priority**: 测试报告是测试价值的最终交付物。即使所有测试都能运行，如果没有清晰的报告，测试结果无法有效指导决策。但报告依赖于测试用例先完成，故排在最后。

**Independent Test**: 可在任意测试集执行完成后自动生成报告，通过人工检查报告格式和内容完整性来验证。

**Acceptance Scenarios**:

1. **Given** 全部测试执行完毕，**When** 查看生成的测试报告，**Then** 报告包含：每项测试的名称、状态（PASS/FAIL/SKIP）、耗时、失败原因摘要、总体通过率
2. **Given** 部分测试失败，**When** 查看测试报告，**Then** 失败用例附带关键日志和错误信息，便于定位问题根因
3. **Given** 测试报告已生成，**When** 查看报告格式，**Then** 报告采用可读性强的格式（Markdown 或 HTML），支持在 CI/CD 流水线中被自动采集

---

### Edge Cases

- 当集群节点资源不足（CPU/内存低于 VM 请求量）时，VM 应进入 Scheduling 状态而非假死等待，测试应在超时后报告 FAIL 并输出调度失败原因
- 当 DataVolume 镜像源 URL 不可达时，DataVolume 应进入 ImportFailed 状态，测试应检测到该状态并报告具体错误
- 当 VM 启动过程中被手动删除，测试框架应能区分「VM 被外部删除」和「VM 启动失败」两种不同情况
- 当 PVC 存储后端（如 Ceph/Rook）出现故障时，VM 应无法正常读写数据，测试应检测到 I/O 错误
- 当并发创建 2 个 VM（恰好达到上限）时，两个 VM 应都能正常启动；当尝试创建第 3 个时，测试框架应拒绝并给出明确提示
- 当 SSH 密钥未正确注入时，SSH 登录应失败，测试应报告密钥配置错误而非连接超时（区分错误类型）
- 当 VM 资源超过限制上限（>2C4G）时，测试框架应拒绝创建或在报告中标记为警告

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 测试框架 MUST 支持单元测试，验证 KubeVirt 相关配置模板（Chart 模板）的渲染正确性，包括输出结构校验和默认配置值校验
- **FR-002**: 测试框架 MUST 支持集成测试，通过 `kubectl` 和 `virtctl` 创建、查询、销毁 KubeVirt 资源（VM、VMI、DataVolume 等），并验证状态转换
- **FR-003**: 测试框架 MUST 支持端到端测试，创建完整配置的生产级 VM 并验证其全部功能（网络、存储、安全、日常操作）
- **FR-004**: 测试框架 MUST 强制执行资源限制：同时运行 VM 数量 ≤ 2 个，单个 VM 资源 ≤ 2C4G
- **FR-005**: 测试框架 MUST 在每次执行后生成测试报告，包含用例名称、状态、耗时、失败原因、总体通过率
- **FR-006**: 测试 MUST 覆盖单独资源创建（VM、VMI、DataVolume、PVC），验证每个资源的生命周期（创建→就绪→销毁）
- **FR-007**: 测试 MUST 覆盖关联资源组合（VM + DataVolume、VM + Service），验证资源间依赖和联动
- **FR-008**: 测试 MUST 验证 `virtctl console` 和 SSH 两种 VM 登录方式均可正常使用
- **FR-009**: 测试 MUST 验证 VM 持久化存储：写入数据 → 重启 VM → 数据依然存在
- **FR-010**: 测试 MUST 验证 VM 内部日常操作：`apt update/install`、服务启动、进程管理
- **FR-011**: 测试 MUST 支持超时控制：每个测试步骤有明确的超时时间，超时后自动标记失败并清理资源
- **FR-012**: 测试 MUST 确保无论测试成功或失败，创建的资源在测试结束后被正确清理（测试框架保证资源回收）
- **FR-013**: 测试用例设计 SHOULD 参考 KubeVirt 和 CDI 上游项目的官方示例配置进行扩展
- **FR-014**: 测试 SHOULD 验证 VM 网络连通性，包括 VM 间通信和 VM 到外部网络的通信
- **FR-015**: 测试 SHOULD 以代码形式管理（infrastructure as code），所有测试用例可版本控制和重复执行

### Key Entities

- **TestSuite（测试套件）**: 组织测试用例的顶层结构，包含名称、类型（unit/integration/e2e）、关联的测试用例集合
- **TestCase（测试用例）**: 单个测试场景的定义，包含名称、前置条件（Given）、操作步骤（When）、预期结果（Then）、超时时间、清理步骤
- **TestReport（测试报告）**: 每次测试执行的产物，包含执行时间、各用例通过/失败/跳过状态、失败日志、汇总统计
- **VMResource（VM 资源配置规范）**: 定义 VM 的 CPU、内存、磁盘、网络配置，包含资源上限约束（2C4G/VM）
- **ResourceLimit（资源限制）**: 全局并发控制，追踪当前运行中 VM 数量，拒绝超过上限（2 个）的创建请求

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 全部单元测试在 30 秒内完成，且通过率 100%
- **SC-002**: 全部集成测试（不含 VM 启动）在 5 分钟内完成，通过率 ≥ 90%
- **SC-003**: 端到端测试能完整验证一个生产级 VM 从创建到销毁的全生命周期，单次端到端测试在 15 分钟内完成
- **SC-004**: 测试报告包含 100% 测试用例的结果记录，失败用例 100% 附带诊断日志
- **SC-005**: 资源限制机制 100% 生效：在测试执行期间从未同时存在超过 2 个 VM
- **SC-006**: 测试资源清理覆盖率 100%：测试结束后无残留 VM/VMI/DataVolume/PVC/Service 资源
- **SC-007**: 测试用例总数 ≥ 15 个，覆盖单元、集成、端到端三种类型

## Assumptions

- KubeVirt 和 CDI Operator 已在集群中正常部署（由 `system/kubevirt/` Helm Chart 管理）
- 集群中有足够的计算资源运行至少 2 个 2C4G VM（即至少 4C8G 可用资源）
- 测试使用的容器镜像（如 `quay.io/kubevirt/cirros-container-disk-demo`）可正常拉取，或已预缓存到集群
- 集群已配置 CSI 存储后端（Rook Ceph 或其他），支持 PVC 动态创建
- 集群已配置 Multus 或默认 Pod 网络（如 Cilium），VM 可获取 IP 地址
- SSH 密钥注入通过 cloud-init NoCloud 方式实现（参考 `vmi-nocloud.yaml`）
- 测试框架使用项目已安装的工具链（`kubectl`, `virtctl`, `helm`），无需额外安装
- 测试环境限定为 homelab2 内部集群，不涉及外网穿透或公网访问
- 端到端测试使用的完整 VM 镜像参考 KubeVirt 官方 examples 中的 Fedora/Alpine VM 配置进行定制
