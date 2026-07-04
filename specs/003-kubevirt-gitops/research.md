# Phase 0: 技术调研 — KubeVirt GitOps 部署

**Feature**: 003-kubevirt-gitops | **Date**: 2026-07-04

## R1: KubeVirt 安装方式

**Decision**: 自建 wrapper Helm Chart，将 KubeVirt 上游 YAML 清单封装为 Helm 模板。

**Rationale**:
- KubeVirt 官方不提供 Helm Chart，安装方式为 `kubectl apply -f` 原始 YAML 清单（operator + CR）
- homelab2 项目要求所有 `system/` 目录下的组件必须是 Helm Chart（ApplicationSet 自动发现的前提）
- 社区存在第三方 Chart（encircle360、cloudymax/kubevirt-community-stack），但维护活跃度不确定，不使用第三方依赖
- Wrapper Chart 模式简单可靠：直接嵌入上游发布清单，仅参数化关键配置（版本号、useEmulation、资源限制）

**Alternatives considered**:
- 直接提交原始 YAML 到 Git（非 Helm）→ 违反项目 ApplicationSet 契约，无法被 ArgoCD 自动发现
- 使用社区 Helm Chart → 依赖第三方维护，版本滞后风险
- 使用 HCO（HyperConverged Cluster Operator）→ 重型方案，面向 OpenShift/Virtualization，k3s 场景过于复杂

## R2: CDI（Containerized Data Importer）

**Decision**: 必须安装 CDI 作为 KubeVirt 的配套组件，与 KubeVirt 部署在同一 Helm Chart 中。

**Rationale**:
- DataVolume（spec 中 FR-008 要求）需要 CDI 提供 `DataVolume` CRD 和控制器
- CDI 负责从 HTTP URL / 容器镜像导入虚拟机磁盘镜像到 PVC
- CDI 与 KubeVirt 同为 `kubevirt` 生态核心组件，版本需匹配
- CDI 同样无官方 Helm Chart，采用与 KubeVirt 相同的 wrapper 策略

**Alternatives considered**:
- 不使用 CDI，手动创建 PVC 并预填充镜像 → 操作繁琐，不符合 GitOps 声明式原则
- 使用单独的 ArgoCD Application 管理 CDI → 增加管理复杂度，CDI 与 KubeVirt 生命期高度耦合

## R3: 硬件虚拟化支持

**Decision**: 使用硬件虚拟化（`/dev/kvm`），不启用 `useEmulation`。

**Rationale**:
- SSH 验证确认：N100 节点 CPU 支持 VT-x（`vmx` flags），`/dev/kvm` 已存在，`kvm_intel` / `kvm` 内核模块已加载
- Intel N100 原生支持硬件虚拟化，Ubuntu 24.04 Server 默认已加载 KVM 模块
- 硬件虚拟化性能远优于 QEMU 软件模拟（TCG），VM 响应速度和资源利用率更高
- KubeVirt virt-handler 会自动检测并使用 `/dev/kvm`

**前置检查**:
- 部署前需确保所有节点 `/dev/kvm` 存在且 `kvm` / `kvm_intel` 模块已加载
- 如有节点缺少 `/dev/kvm`，需安装 `qemu-kvm` 包或加载 KVM 内核模块

**Alternatives considered**:
- 启用 `useEmulation: true` → 性能大幅下降，仅在硬件虚拟化完全不可用时作为后备
- 混合模式（部分节点硬件、部分软件）→ 增加调度复杂性，v1 不采用

## R4: VM 镜像选择

**Decision**: 使用 Ubuntu Cloud Image 26.04 LTS（qcow2 格式），通过 cloud-init 自动配置。

**Rationale**:
- Ubuntu 26.04 LTS（已经发布）是最新的 LTS 版本，支持周期长
- Ubuntu Cloud Image 官方提供 qcow2 格式，兼容 KubeVirt
- 原生支持 cloud-init，可通过 `cloudInitNoCloud` 注入 SSH 公钥和用户数据
- 用户明确指定 Ubuntu Cloud Image 26.04 LTS

**Alternatives considered**:
- Fedora Cloud Base → KubeVirt 官方示例首选，但用户偏好 Ubuntu 生态
- Debian Cloud Image → 同样成熟，但 26.04 LTS 更符合长期使用需求

## R5: 资源限制策略

**Decision**: 为 KubeVirt 组件和 VM 设置保守的资源限制，适配 N100 集群资源。

**Rationale**:
- Constitution IV 要求所有工作负载显式设置 `resources.requests/limits`
- KubeVirt 控制面组件资源消耗较低（参考 KubeVirt 社区建议）：
  - virt-operator: 50m CPU / 200Mi mem
  - virt-api: 50m CPU / 200Mi mem
  - virt-controller: 100m CPU / 300Mi mem
  - virt-handler: 100m CPU / 300Mi mem
- Demo VM: 2 vCPU / 4Gi RAM（硬件虚拟化场景，性能充足）

## R6: GitOps 目录结构

**Decision**: 所有 KubeVirt 相关资源集中在 `system/kubevirt/`，VM 定义放在同目录下的 `vm/` 子目录。

**Rationale**:
- 符合项目 `system/` 目录约定（ApplicationSet 扫描 `system/*`）
- `vm/` 子目录下的 YAML 作为 Helm Chart 的一部分被渲染，与 KubeVirt 平台同时部署
- 后续如需独立管理 VM 生命周期，可将 VM 清单移至独立的 ArgoCD Application
