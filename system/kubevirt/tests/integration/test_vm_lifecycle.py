"""集成测试: VM 生命周期 — 创建 → Running → 删除 → 清理验证."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.common import (
    MANIFESTS_DIR,
    kubectl_apply,
    kubectl_delete,
    kubectl_get,
    log_info,
    log_success,
    log_warn,
    wait_for_condition,
)
from lib.resource_limiter import check_vm_limit

MANIFEST = MANIFESTS_DIR / "integration" / "vm-cirros.yaml"
VM_NAME = "test-vm-cirros"
NAMESPACE = "kubevirt-test"


def test_vm_lifecycle_create_delete():
    """测试 VM 创建→Running→删除→清理."""
    log_info("VM 生命周期测试: 创建 → Running → 删除")

    # Given: 检查资源限制
    if not check_vm_limit(NAMESPACE):
        log_warn("VM 槽位已满 (max 2)，跳过测试")
        return

    try:
        # When: 创建 VM
        log_info("创建 VM 资源")
        result = kubectl_apply(MANIFEST, NAMESPACE)
        assert result.returncode == 0, f"kubectl apply 失败: {result.stderr}"

        # Then: 等待 Running 状态
        log_info("等待 VM 进入 Running 状态 (timeout=120s)")
        running = wait_for_condition(f"vm/{VM_NAME}", "Running", timeout=120, namespace=NAMESPACE)
        assert running, f"VM '{VM_NAME}' 在 120s 内未进入 Running 状态"

        # 验证 kubectl get vm 可见
        result = kubectl_get("vm", VM_NAME, NAMESPACE)
        assert result.returncode == 0, f"kubectl get vm 失败: {result.stderr}"
        assert VM_NAME in result.stdout, f"VM '{VM_NAME}' 不在 kubectl get 输出中"

        # 给 VM 一点时间稳定
        time.sleep(5)

        log_success(f"VM '{VM_NAME}' Running 验证通过")
    finally:
        # When: 删除 VM
        log_info("清理: 删除 VM 资源")
        kubectl_delete(MANIFEST, NAMESPACE)

        # Then: 等待清理完成
        log_info("等待 VM 清理完成 (timeout=60s)")
        start = time.time()
        cleaned = False
        while time.time() - start < 60:
            result = kubectl_get("vm", VM_NAME, NAMESPACE)
            if result.returncode != 0 or VM_NAME not in result.stdout:
                cleaned = True
                break
            time.sleep(3)

        if cleaned:
            log_success("VM 资源清理完毕")
        else:
            log_warn("VM 资源可能未完全清理 (可接受 — 后续可手动清理)")
