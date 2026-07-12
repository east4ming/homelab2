"""集成测试: VM + DataVolume 组合 — 从 DataVolume 引导启动 VM."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.common import (
    MANIFESTS_DIR,
    get_resource_phase,
    kubectl_apply,
    kubectl_delete,
    log_info,
    log_success,
    log_warn,
    run_command,
    wait_for_condition,
)
from lib.resource_limiter import check_vm_limit

VM_MANIFEST = MANIFESTS_DIR / "integration" / "vm-datavolume.yaml"
DV_MANIFEST = MANIFESTS_DIR / "integration" / "datavolume-cirros.yaml"
DV_NAME = "test-dv-cirros"
VM_NAME = "test-vm-dv"
NAMESPACE = "kubevirt-test"
DV_TIMEOUT = 600  # DataVolume 导入超时 10 分钟


def test_vm_with_datavolume():
    """测试 VM 引用 DataVolume 引导启动 — DV Succeeded → VM Running."""
    log_info("VM+DataVolume 组合测试: DV 导入 → VM 引导")

    if not check_vm_limit(NAMESPACE):
        log_warn("VM 槽位已满 (max 2)，跳过测试")
        return

    dv_created = False
    vm_created = False
    try:
        # Step 1: 创建 DataVolume
        log_info("Step 1: kubectl apply DataVolume")
        result = kubectl_apply(DV_MANIFEST, NAMESPACE)
        assert result.returncode == 0, f"DataVolume apply 失败: {result.stderr}"
        dv_created = True

        # Step 2: 等待 DataVolume status.phase == Succeeded
        log_info(f"Step 2: 等待 DataVolume Succeeded (timeout={DV_TIMEOUT}s)")
        ok = wait_for_condition(f"dv/{DV_NAME}", "Succeeded", timeout=DV_TIMEOUT, poll_interval=15, namespace=NAMESPACE)
        assert ok, f"DataVolume '{DV_NAME}' 导入失败或超时"

        # Step 3: 独立验证 DataVolume phase
        dv_phase = get_resource_phase(f"dv/{DV_NAME}", NAMESPACE)
        assert dv_phase == "Succeeded", f"DataVolume status.phase 期望 'Succeeded'，实际 '{dv_phase}'"
        log_success(f"DataVolume 就绪 — status.phase=Succeeded")

        # Step 4: 创建 VM 引用该 DataVolume
        log_info("Step 3: kubectl apply VM (引用 DataVolume)")
        result = kubectl_apply(VM_MANIFEST, NAMESPACE)
        assert result.returncode == 0, f"VM apply 失败: {result.stderr}"
        vm_created = True

        # Step 5: 等待 VM printableStatus == Running
        log_info("Step 4: 等待 VM Running (timeout=180s)")
        running = wait_for_condition(f"vm/{VM_NAME}", "Running", timeout=180, namespace=NAMESPACE)
        assert running, f"VM '{VM_NAME}' 在 180s 内未进入 Running"

        # Step 6: 独立验证 VM printableStatus == Running
        vm_phase = get_resource_phase(f"vm/{VM_NAME}", NAMESPACE)
        assert vm_phase == "Running", f"VM printableStatus 期望 'Running'，实际 '{vm_phase}'"

        log_success(f"VM 从 DataVolume 引导成功 — printableStatus=Running")
    finally:
        # 清理: 先删 VM，再删 DataVolume
        log_info("清理资源: VM → DataVolume → PVC")
        if vm_created:
            kubectl_delete(VM_MANIFEST, NAMESPACE)
            time.sleep(5)
        if dv_created:
            kubectl_delete(DV_MANIFEST, NAMESPACE)
            run_command(
                ["kubectl", "delete", "pvc", DV_NAME, "-n", NAMESPACE, "--ignore-not-found=true"],
                timeout=10,
            )
        log_success("VM+DataVolume 资源清理完毕")
