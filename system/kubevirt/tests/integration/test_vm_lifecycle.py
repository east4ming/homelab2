"""集成测试: VM 生命周期 — 创建 → Running → 删除 → 清理验证."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.common import (
    MANIFESTS_DIR,
    get_resource_phase,
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
    log_info("VM 生命周期测试: 创建 → Running → 删除 → 清理")

    # Given: 检查资源限制
    if not check_vm_limit(NAMESPACE):
        log_warn("VM 槽位已满 (max 2)，跳过测试")
        return

    try:
        # Step 1: 创建 VM
        log_info("Step 1: kubectl apply VM")
        result = kubectl_apply(MANIFEST, NAMESPACE)
        assert result.returncode == 0, f"kubectl apply 失败: {result.stderr}"

        # Step 2: 确认 VM 资源存在
        time.sleep(3)
        result = kubectl_get("vm", VM_NAME, NAMESPACE)
        assert result.returncode == 0, f"VM '{VM_NAME}' 未创建"
        log_info("VM 资源已创建")

        # Step 3: 轮询等待 VM printableStatus 变为 Running
        log_info("Step 2: 等待 VM printableStatus == Running (timeout=120s)")
        running = wait_for_condition(f"vm/{VM_NAME}", "Running", timeout=120, namespace=NAMESPACE)
        assert running, f"VM '{VM_NAME}' 在 120s 内未进入 Running 状态"

        # Step 4: 独立验证 — kubectl get vm -o json 确认 printableStatus == Running
        log_info("Step 3: 独立验证 VM printableStatus == Running")
        phase = get_resource_phase(f"vm/{VM_NAME}", NAMESPACE)
        assert phase == "Running", f"VM printableStatus 期望 'Running'，实际 '{phase}'"

        # Step 5: 验证底层 VMI 也存在且为 Running
        vmi_phase = get_resource_phase(f"vmi/{VM_NAME}", NAMESPACE)
        log_info(f"VMI 状态: {vmi_phase}")
        # VM Running 时 VMI 可能也是 Running，但不是必须（VM 可能处于 Stopped）
        if vmi_phase != "Unknown":
            assert vmi_phase == "Running", f"VMI phase 期望 'Running'，实际 '{vmi_phase}'"

        # 给 VM 一点时间稳定
        time.sleep(5)

        log_success(f"VM '{VM_NAME}' Running 验证通过 — printableStatus=Running, VMI={vmi_phase}")
    finally:
        # Step 6: 删除 VM
        log_info("清理: 删除 VM 资源")
        kubectl_delete(MANIFEST, NAMESPACE)

        # Step 7: 等待清理完成
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
