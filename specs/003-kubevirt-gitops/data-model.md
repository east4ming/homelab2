# Phase 1: 数据模型 — KubeVirt GitOps 部署

**Feature**: 003-kubevirt-gitops | **Date**: 2026-07-04

## 实体关系概览

```
KubeVirt (CR) ◄── 管理 ──► KubeVirt Operator (Deployment)
                               │
                               ├── virt-api (Deployment)
                               ├── virt-controller (Deployment)
                               └── virt-handler (DaemonSet)

CDI (CR) ◄── 管理 ──► CDI Operator (Deployment)
                           │
                           └── cdi-controller (various)

VirtualMachine (CR) ── 创建 ──► VirtualMachineInstance (CR)
    │                                │
    ├── DataVolume (CR)              ├── virt-launcher (Pod/QEMU)
    │       │                        │       │
    │       └── PVC                  │       ├── rootDisk (PVC/containerDisk)
    └── cloudInitNoCloud             │       └── dataDisk (PVC)
                                     └── Pod 网络 (masquerade)
```

## Key Entities

### 1. KubeVirt (CR)

KubeVirt 平台全局配置，一个集群仅一个实例。

| 字段 | 类型 | 描述 |
|------|------|------|
| `spec.configuration.developerConfiguration.useEmulation` | bool | 软件模拟开关（默认 `false`，使用硬件虚拟化） |
| `spec.infra.nodePlacement` | NodePlacement | 控制面组件（virt-api/controller）节点调度 |
| `spec.workloads.nodePlacement` | NodePlacement | 工作负载（virt-handler/VM）节点调度 |
| `spec.workloadUpdateStrategy` | UpdateStrategy | VM 工作负载更新策略 |

### 2. CDI (CR)

Containerized Data Importer 配置，一个集群仅一个实例。

| 字段 | 类型 | 描述 |
|------|------|------|
| `spec.config.imagePullPolicy` | string | 镜像拉取策略 |
| `spec.config.scratchSpaceStorageClass` | string | 导入临时空间 StorageClass |

### 3. VirtualMachine (CR)

虚拟机定义，声明式描述 VM 规格。

| 字段 | 类型 | 描述 |
|------|------|------|
| `spec.runStrategy` | string | 运行策略（`Always`/`RerunOnFailure`/`Manual`/`Halted`） |
| `spec.template.metadata.labels` | map | VM 标签（特殊标签 `kubevirt.io/vm: <name>` 必须匹配） |
| `spec.template.spec.domain.cpu.cores` | int | vCPU 数量 |
| `spec.template.spec.domain.resources.requests.memory` | string | 内存请求量 |
| `spec.template.spec.domain.devices.disks[]` | array | 磁盘设备列表 |
| `spec.template.spec.volumes[]` | array | 卷定义（PVC / containerDisk / DataVolume / cloudInitNoCloud） |
| `spec.dataVolumeTemplates[]` | array | DataVolume 模板（内联定义导入源和 PVC 规格） |

### 4. DataVolume (CR)

磁盘镜像导入资源，由 CDI 控制器处理。

| 字段 | 类型 | 描述 |
|------|------|------|
| `spec.source` | DataVolumeSource | 导入源（`http.url` / `registry.url` / `blank`） |
| `spec.pvc` | PVC Spec | 目标 PVC 规格（accessModes、storage、storageClassName） |
| `status.phase` | string | 导入状态（`ImportScheduled` → `ImportInProgress` → `Succeeded` / `Failed`） |

### 5. PersistentVolumeClaim (PVC)

Kubernetes 标准持久化存储卷，作为 VM 磁盘后端。

| 字段 | 类型 | 描述 |
|------|------|------|
| `spec.accessModes` | []string | 访问模式（`ReadWriteOnce` / `ReadWriteMany`） |
| `spec.resources.requests.storage` | string | 存储容量（如 `10Gi`） |
| `spec.storageClassName` | string | 存储类（`standard-rwo` / `standard-rwx`） |

## 状态转换

### VirtualMachine 生命周期

```
[Created] ──runStrategy=Always──► [Starting] ──► [Running]
    │                                │                │
    └──runStrategy=Manual────────────┘          virtctl stop
                                                  │
                                                  ▼
                                              [Stopped] ──virtctl start──► [Starting] → [Running]
                                                  │
                                            virtctl restart
                                                  │
                                                  ▼
                                              [Starting] → [Running]
```

### DataVolume 导入生命周期

```
[Created] → [ImportScheduled] → [ImportInProgress] → [Succeeded]
                                     │
                                     └──► [Failed] ── (需人工介入或重试)
```
