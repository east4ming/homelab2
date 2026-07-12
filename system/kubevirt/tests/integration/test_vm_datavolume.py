"""集成测试: VM + DataVolume 组合 — 从 DataVolume 引导启动 VM."""

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


def _create_datavolume_and_wait() -> bool:
    """创建 DataVolume 并等待 Succeeded."""
    result = kubectl_apply(DV_MANIFEST, NAMESPACE)
    if result.returncode != 0:
        log_warn(f"DataVolume apply 失败: {result.stderr}")
        return False

    # 等待导入完成
    elapsed = 0
    while elapsed < DV_TIMEOUT:
        r = run_command(
            ["kubectl", "get", f"dv/{DV_NAME}", "-n", NAMESPACE,
             "-o", "jsonpath={.status.phase}"],
        )
        phase = r.stdout.strip()
        if phase == "Succeeded":
            return True
        if phase in ("Failed", "ImportFailed"):
            log_warn(f"DataVolume 进入 {phase}")
            return False
        time.sleep(15)
        elapsed += 15
    return False


def test_vm_with_datavolume():
    """测试 VM 引用 DataVolume 启动."""
    log_info("VM+DataVolume 组合测试: DV 导入 → VM 引导")

    if not check_vm_limit(NAMESPACE):
        log_warn("VM 槽位已满 (max 2)，跳过测试")
        return

    dv_created = False
    vm_created = False
    try:
        # Step 1: 创建 DataVolume 并等待
        log_info("Step 1: 创建 DataVolume")
        dv_created = True
        succeeded = _create_datavolume_and_wait()
        assert succeeded, f"DataVolume '{DV_NAME}' 导入失败或超时"

        # Step 2: 创建 VM 引用该 DataVolume
        log_info("Step 2: 创建 VM 引用 DataVolume")
        result = kubectl_apply(VM_MANIFEST, NAMESPACE)
        assert result.returncode == 0, f"VM apply 失败: {result.stderr}"
        vm_created = True

        # Step 3: 等待 VM Running
        log_info("等待 VM 进入 Running 状态 (timeout=180s)")
        running = wait_for_condition(f"vm/{VM_NAME}", "Running", timeout=180, namespace=NAMESPACE)
        assert running, f"VM '{VM_NAME}' 在 180s 内未进入 Running"

        # Step 4: 验证 VM 可见
        result = kubectl_get("vm", VM_NAME, NAMESPACE)
        assert result.returncode == 0
        log_success("VM 从 DataVolume 引导成功")
    finally:
        # 清理: 先删 VM，再删 DataVolume
        log_info("清理资源")
        if vm_created:
            kubectl_delete(VM_MANIFEST, NAMESPACE)
            time.sleep(5)
        if dv_created:
            kubectl_delete(DV_MANIFEST, NAMESPACE)
            run_command(
                ["kubectl", "delete", "pvc", DV_NAME, "-n", NAMESPACE,
                 "--ignore-not-found=true"],
                timeout=10,
            )
        log_success("VM+DataVolume 资源清理完毕")
