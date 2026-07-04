# Feature Specification: KubeVirt GitOps 部署与虚拟机管理

**Feature Branch**: `003-kubevirt-gitops`

**Created**: 2026-07-04

**Status**: Draft

**Input**: User description: "根据文档: https://kubevirt.io/user-guide/cluster_admin/installation/ 和 https://kubevirt.io/user-guide/cluster_admin/gitops/ 在我的 k3s 集群上通过 argoCD gitops 的方式安装 kubevirt. 最终 goal 是使用 kubevirt 启动一个配置了持久化磁盘的虚拟机, 并能正常对该vm进行访问, 管理和使用."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 通过 ArgoCD GitOps 安装 KubeVirt (Priority: P1)

运维人员将 KubeVirt 的 Helm Chart（包含 Operator 和 KubeVirt CR）提交到 homelab2 Git 仓库的 `system/kubevirt/` 目录，ArgoCD ApplicationSet 自动发现并创建 Application，完成 KubeVirt 在 k3s 集群上的部署。部署后，所有 KubeVirt 核心组件（virt-operator、virt-api、virt-controller、virt-handler）在 `kubevirt` 命名空间中正常运行。

**Why this priority**: KubeVirt 是整个功能的基础平台——没有 KubeVirt，无法创建和管理虚拟机。

**Independent Test**: 将 KubeVirt Helm Chart 放入 `system/kubevirt/` 后，ArgoCD 自动同步，`kubectl get kv -n kubevirt` 显示 `kubevirt` CR 状态为 `Deployed`，且所有 virt-* Pod 处于 Running 状态。

**Acceptance Scenarios**:

1. **Given** `system/kubevirt/` 目录包含 KubeVirt Helm Chart，**When** ArgoCD ApplicationSet 扫描 system 目录，**Then** Application `system-kubevirt` 被自动创建且同步状态为 `Synced`
2. **Given** ArgoCD 已同步 KubeVirt Application，**When** KubeVirt Operator 处理 KubeVirt CR，**Then** virt-api、virt-controller Deployment 和 virt-handler DaemonSet 在 `kubevirt` 命名空间中 Running
3. **Given** 集群节点不支持硬件虚拟化（嵌套虚拟化不可用），**When** KubeVirt CR 中配置 `useEmulation: true`，**Then** KubeVirt 组件仍正常启动，虚拟机可使用软件模拟运行

---

### User Story 2 - 创建带持久化磁盘的虚拟机 (Priority: P2)

运维人员通过 GitOps 方式定义一个 VirtualMachine 资源，该虚拟机配置了持久化数据磁盘（DataVolume 或 PersistentVolumeClaim）。虚拟机使用指定的操作系统镜像启动，数据磁盘在虚拟机重启或迁移后保留数据不丢失。

**Why this priority**: 持久化磁盘是虚拟机可用性的核心——没有持久化，VM 重启即丢失所有数据和配置，无法用于实际工作负载。

**Independent Test**: 应用 VirtualMachine 清单后，VM 成功启动运行，向数据磁盘写入测试文件，重启 VM 后文件仍然存在。

**Acceptance Scenarios**:

1. **Given** KubeVirt 已部署就绪，**When** 提交一个配置了 DataVolume/PVC 作为数据磁盘的 VirtualMachine 清单，**Then** VM 进入 `Running` 状态
2. **Given** VM 已运行，**When** 在 VM 内写入数据到持久化磁盘，重启 VM，**Then** 写入的数据仍然可读
3. **Given** VM 已运行，**When** 删除 VM 资源但不删除 DataVolume/PVC，使用同一 PVC 创建新 VM，**Then** 新 VM 可读取原有数据

---

### User Story 3 - 访问和管理虚拟机 (Priority: P3)

运维人员能够通过 `virtctl` 命令行工具连接到虚拟机的串行控制台和 VNC 图形界面，对虚拟机执行启动、停止、重启等生命周期管理操作。

**Why this priority**: 访问和管理是虚拟机运维的基础操作——部署 VM 后必须能进入系统、执行管理任务。

**Independent Test**: 使用 `virtctl console <vm-name>` 连接到 VM 控制台，能够登录操作系统并执行命令。

**Acceptance Scenarios**:

1. **Given** VM 处于 Running 状态，**When** 执行 `virtctl console <vm-name>`，**Then** 成功进入虚拟机串行控制台，可登录并执行命令
2. **Given** VM 处于 Running 状态，**When** 执行 `virtctl stop <vm-name>`，**Then** VM 优雅关机进入 `Stopped` 状态
3. **Given** VM 处于 Stopped 状态，**When** 执行 `virtctl start <vm-name>`，**Then** VM 启动并进入 `Running` 状态

---

### Edge Cases

- k3s 默认使用 containerd 运行时不支持硬件虚拟化嵌套时，虚拟机能否通过软件模拟（useEmulation）正常运行？
- 集群节点资源（CPU/内存）不足时，VM 创建请求应如何反馈——Pending 等待资源还是明确拒绝？
- DataVolume 使用 URL 导入镜像时网络中断，导入流程如何处理——自动重试还是需人工介入？
- 多个 VM 共享同一 PVC（ReadWriteMany 模式）时的数据一致性问题？
- VM 所在节点宕机时，VM 是否自动在其他节点重建？

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: KubeVirt 必须通过 ArgoCD GitOps 方式安装，所有清单文件存储在 Git 仓库 `system/kubevirt/` 目录中，且提交后 ArgoCD 自动同步部署
- **FR-002**: KubeVirt 安装必须包含 Operator 部署和 KubeVirt Custom Resource 两部分，CR 需支持配置软件模拟（`useEmulation`）开关，用于不支持硬件虚拟化的节点
- **FR-003**: KubeVirt 核心组件（virt-api、virt-controller、virt-handler、virt-operator）必须在 `kubevirt` 命名空间中部署并正常运行
- **FR-004**: 系统必须支持通过 VirtualMachine CRD 定义和创建虚拟机，VM 规格（CPU、内存、磁盘）可在清单中声明式配置
- **FR-005**: 虚拟机必须支持挂载持久化数据磁盘，使用 PersistentVolumeClaim 作为磁盘后端，数据在 VM 重启后不丢失
- **FR-006**: 系统必须支持虚拟机生命周期管理操作：启动（start）、停止（stop）、重启（restart）
- **FR-007**: 运维人员必须能够通过 `virtctl` CLI 工具访问虚拟机串行控制台（console）
- **FR-008**: 虚拟机操作系统镜像必须通过 DataVolume（容器化磁盘镜像或 HTTP 导入）方式提供，支持从 URL 自动拉取并写入 PVC

### Key Entities

- **KubeVirt (CR)**: KubeVirt 平台的顶层配置资源，控制 Operator 的部署行为、工作负载节点选择、软件模拟开关等全局参数
- **VirtualMachine (VM)**: 虚拟机定义资源，描述虚拟机的 CPU/内存/磁盘规格、运行策略（runStrategy）、网络配置等
- **VirtualMachineInstance (VMI)**: 虚拟机运行时实例，当 VM 运行时自动创建，代表一个正在运行的虚拟机进程
- **DataVolume (DV)**: 数据卷资源，管理虚拟机磁盘镜像的导入、克隆和 PVC 分配，支持从 URL 或容器镜像拉取操作系统镜像
- **PersistentVolumeClaim (PVC)**: Kubernetes 持久卷声明，作为虚拟机数据磁盘的后端存储，由集群的存储类（CSI/Rook-Ceph）动态供给

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 从提交 KubeVirt 清单到 Git 仓库到所有 virt-* 组件 Running 就绪，全过程在 5 分钟内完成
- **SC-002**: 从提交 VirtualMachine 清单到 VM 进入 Running 状态（含镜像导入），在操作系统镜像拉取完成后 60 秒内完成
- **SC-003**: 虚拟机串行控制台连接延迟不超过 2 秒（从执行命令到出现登录提示）
- **SC-004**: 虚拟机持久化磁盘上的数据在 VM 经历 3 次重启后仍然完整可读
- **SC-005**: 运维人员可在 10 分钟内完成从 Git 提交到 VM 可访问的完整流程（不含镜像下载时间）

## Assumptions

- 目标 k3s 集群已安装 ArgoCD 并配置 ApplicationSet 自动发现 `system/` 目录下的 Helm Chart
- k3s 集群使用 containerd 作为容器运行时（KubeVirt 官方支持）
- 集群节点可能不支持硬件虚拟化嵌套，因此 KubeVirt 需要默认启用软件模拟（`useEmulation: true`）作为后备方案
- 集群已配置持久化存储（如 Rook-Ceph 或 local-path-provisioner），可动态供给 PVC
- 虚拟机操作系统镜像使用公开可访问的容器镜像或 HTTP URL（如 Fedora Cloud、Ubuntu Cloud Image 等 cloud-init 兼容镜像）
- 运维人员本地安装 `virtctl` CLI 工具，且 kubeconfig 已配置指向目标集群
- 虚拟机网络采用 KubeVirt 默认的 Pod 网络模式（masquerade 或 bridge），不需要 Multus 多网络
- 本功能 MVP 范围为单虚拟机场景，多 VM 编排、实时迁移、快照等高级功能不在 v1 范围
