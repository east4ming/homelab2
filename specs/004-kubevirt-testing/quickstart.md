# Quickstart: KubeVirt 测试体系

**Created**: 2026-07-12

## 前置条件

1. KubeVirt + CDI 已部署且正常运行
2. `kubectl` 可访问集群，`virtctl` 已安装
3. Python 3.12+ 已安装
4. `uv` 已安装
5. CSI 存储后端可用，支持 PVC 动态创建

## 快速开始

```bash
# 进入测试目录
cd system/kubevirt/tests

# 首次使用：安装依赖
uv sync

# 执行全部测试
uv run python run.py

# 仅执行单元测试
uv run python run.py --suite unit

# 仅执行集成测试
uv run python run.py --suite integration

# 仅执行端到端测试
uv run python run.py --suite e2e

# 详细模式（显示每个步骤的实时日志）
uv run python run.py --verbose

# 指定测试报告输出路径
uv run python run.py --report /tmp/kubevirt-test-report.md
```

## 测试执行顺序

```text
run.py
  ├── Phase 0: 环境检查
  │   ├── kubectl 可用性 + 版本
  │   ├── virtctl 可用性 + 版本
  │   ├── helm 可用性 + 版本（unit 测试需要）
  │   └── KubeVirt/CDI/CSI 集群状态
  │
  ├── Phase 1: 单元测试（≤30s）
  │   └── test_helm_template.py
  │
  ├── Phase 2: 集成测试（≤5min）
  │   ├── test_vm_lifecycle.py
  │   ├── test_vmi_lifecycle.py
  │   ├── test_datavolume.py
  │   ├── test_vm_datavolume.py
  │   └── test_vm_service.py
  │
  ├── Phase 3: 端到端测试（≤15min）
  │   ├── test_production_vm.py
  │   └── test_vm_connectivity.py
  │
  └── Phase 4: 报告生成
```

## 资源限制说明

测试框架通过 `lib/resource_limiter.py` 强制执行：
- 同时运行 VM 数 ≤ 2
- 单 VM CPU ≤ 2 核
- 单 VM 内存 ≤ 4Gi

违反限制时测试会标记为 FAIL 或 SKIP，并在报告中说明原因。

## 典型输出示例

```text
$ uv run python run.py
==> KubeVirt Test Suite v0.1.0
==> Phase 0: Environment Check
  [OK] kubectl: v1.29.0
  [OK] virtctl: v1.2.0
  [OK] KubeVirt: Deployed (v1.2.0)
  [OK] CDI: Deployed (v1.59.0)
  [OK] StorageClass: ceph-block (default)

==> Phase 1: Unit Tests
  [PASS] (2s)   helm-template-default-values
  [PASS] (1s)   helm-template-custom-values
  [PASS] (1s)   helm-template-yaml-syntax

==> Phase 2: Integration Tests
  [PASS] (45s)  vm-lifecycle-create-delete
  [PASS] (32s)  vmi-ephemeral-lifecycle
  [PASS] (120s) datavolume-http-import
  [PASS] (68s)  vm-with-datavolume-boot
  [PASS] (55s)  vm-service-clusterip

==> Phase 3: End-to-End Tests
  [PASS] (420s) production-vm-full-lifecycle
  [PASS] (180s) vm-network-connectivity

==> Phase 4: Report
  Report generated: system/kubevirt/tests/test-report.md

Summary: 10/10 PASS | 0 FAIL | 0 SKIP | Duration: 15m24s
```

## 添加新测试用例

1. 在 `manifests/<suite>/` 下创建 YAML 清单文件
2. 在 `<suite>/` 下创建 Python 测试模块
3. 从 `lib.common` 引入公共函数
4. 测试函数遵循模式：

```python
"""测试 VM 生命周期：创建 → 就绪 → 销毁"""

from lib.common import (
    test_start, test_pass, test_fail, test_skip,
    kubectl_apply, kubectl_delete, wait_for_condition,
)
from lib.resource_limiter import check_vm_limit

MANIFEST = MANIFESTS_DIR / "integration" / "vm-cirros.yaml"


def test_vm_lifecycle():
    test_id = "vm-lifecycle-create-delete"
    test_start(test_id, "验证 VM 创建→运行→删除")

    # Given
    if not check_vm_limit():
        test_skip(test_id, "VM 槽位已满 (max 2)")
        return

    # When
    kubectl_apply(MANIFEST)
    ok = wait_for_condition("vm/test-vm", "Running", timeout=120)

    # Then
    if not ok:
        test_fail(test_id, "VM 未在 120s 内进入 Running 状态")
        kubectl_delete(MANIFEST)
        return

    test_pass(test_id)
    kubectl_delete(MANIFEST)
```
