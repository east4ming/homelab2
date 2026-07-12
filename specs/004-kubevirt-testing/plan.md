# Implementation Plan: KubeVirt 测试体系

**Branch**: `004-kubevirt-testing` | **Date**: 2026-07-12 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/004-kubevirt-testing/spec.md`

## Summary

为 `system/kubevirt/` Helm Chart 及已部署的 KubeVirt 平台构建三层测试体系（单元/集成/端到端），使用 Python 3 通过 subprocess 编排 `kubectl` + `virtctl` 操作，`uv` 管理依赖，生成 Markdown 测试报告。测试严格限制最多 2 个 VM 同时运行，单 VM ≤ 2C4G。

## Technical Context

**Language/Version**: Python 3.12+（纯 Python，不使用 Shell 脚本）

**Primary Dependencies**: `uv`（包管理），`pytest`（测试框架），`kubernetes`（Python K8s client），`pyyaml`（YAML 处理），`pexpect`（SSH/console 交互），`rich`（终端输出）

**Storage**: CSI PVC（已有 Rook Ceph 集群）

**Testing**: pytest + 自建 test runner，生成 Markdown 报告；lint 使用 ruff

**Target Platform**: K3s 集群（4 × N100 mini-host，~64-128GB RAM）

**Project Type**: 测试套件（Python + YAML manifests）

**Performance Goals**: 单元测试 ≤30s，集成测试 ≤5min，端到端测试 ≤15min

**Constraints**: 同时 ≤2 VM，单 VM ≤2C4G；所有资源测试后自动清理

**Scale/Scope**: ≥15 个测试用例，覆盖 unit / integration / e2e 三层

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. 代码质量 | ✅ PASS | Python 代码通过 ruff lint；YAML manifests 通过 yamllint；Helm Chart 测试通过 helmlint |
| II. 测试标准 | ✅ PASS | 测试本身就是本 feature 的核心交付物；遵循 TDD：spec → plan → test cases → code → test → commit |
| III. 用户体验一致性 | N/A | 测试代码，非用户面向服务 |
| IV. 性能要求 | ✅ PASS | VM 资源限制 ≤2C4G，同时 ≤2 VM；测试结束后资源完全清理 |
| V. 中文优先 | ✅ PASS | 所有代码注释、文档、报告使用中文 |
| 安全与合规 - Secret | ✅ PASS | SSH 测试密钥使用临时生成（Python `cryptography` 或 subprocess `ssh-keygen`），不提交仓库 |
| 开发与部署工作流 - GitOps | ⚠️ VIOLATION | 测试脚本使用 `kubectl apply` 直接操作集群，违反"严禁手动 kubectl apply"原则。参见下方 Justification |

### Violation Justification: 测试框架中使用 kubectl apply

| 项目 | 说明 |
|------|------|
| **违规项** | 开发与部署工作流 — 严禁手动 `kubectl apply` |
| **为何必须** | 测试需要动态创建/验证/销毁临时资源（VM、VMI、DataVolume），这些资源不在 ArgoCD ApplicationSet 管理范围内。测试资源是短生命周期、一次性的验证对象，不是持久化部署的基础设施。ArgoCD 的 GitOps 流程无法适应测试的创建→验证→清理循环（每次测试的资源名称、时间、参数都不同） |
| **为何无法用 GitOps 替代** | ArgoCD 的 sync 周期（默认 3min）无法满足测试对资源状态实时验证的需求。且 ArgoCD 的自动 prune 会与测试清理逻辑冲突，导致资源泄漏或误删 |
| **缓解措施** | 1) 所有测试资源带有明确 label（`app.kubernetes.io/test: "kubevirt-suite"`），ArgoCD 忽略这些资源；2) 测试在独立 namespace 中运行（`kubevirt-test`），与 GitOps 管理的生产 namespace 隔离；3) 测试框架保证 100% 资源清理，不会残留 |

## Project Structure

### Documentation (this feature)

```text
specs/004-kubevirt-testing/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (skip — no external interfaces)
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

```text
system/kubevirt/
├── Chart.yaml
├── values.yaml
├── README.md
├── templates/
│   ├── cdi-operator.yaml
│   ├── cdi-cr.yaml
│   ├── kubevirt-operator.yaml
│   └── kubevirt-cr.yaml
├── examples/
│   └── demo-vm.yaml
└── tests/                       # NEW — 本 feature 的全部产出
    ├── pyproject.toml           # uv 项目配置 + 依赖声明
    ├── run.py                   # 主入口，按序执行三层测试
    ├── lib/
    │   ├── __init__.py
    │   ├── common.py            # 公共函数：日志、断言、kubectl wait 封装
    │   ├── resource_limiter.py  # VM 并发控制（≤2 VM）
    │   └── report_generator.py  # Markdown 测试报告生成
    ├── manifests/               # 测试用 YAML 资源定义
    │   ├── unit/                # helm template 输出验证
    │   ├── integration/         # 单资源 + 组合资源 YAML
    │   └── e2e/                 # 生产级 VM 完整 YAML
    ├── unit/
    │   └── test_helm_template.py
    ├── integration/
    │   ├── test_vm_lifecycle.py
    │   ├── test_vmi_lifecycle.py
    │   ├── test_datavolume.py
    │   ├── test_vm_datavolume.py
    │   └── test_vm_service.py
    └── e2e/
        ├── test_production_vm.py
        └── test_vm_connectivity.py
```

**Structure Decision**: 单项目结构，测试代码内嵌于 `system/kubevirt/tests/`，与 Chart 源码同目录。Python 包管理使用 `uv`（`pyproject.toml`），不依赖 flake.nix。`lib/` 提供共享 Python 模块，`manifests/` 存放测试用 YAML 模板。

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| kubectl apply 直接操作集群 | 测试框架必须动态创建/销毁临时资源，ArgoCD GitOps 无法满足实时验证需求 | 通过 ArgoCD ApplicationSet 管理测试资源：sync 周期过长（3min），且 prune 逻辑与测试清理冲突，会引入更复杂的 hack |
