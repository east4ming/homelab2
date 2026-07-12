"""集成测试: DataVolume HTTP 导入 → Succeeded."""

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
    run_command,
    wait_for_condition,
)

MANIFEST = MANIFESTS_DIR / "integration" / "datavolume-cirros.yaml"
DV_NAME = "test-dv-cirros"
NAMESPACE = "kubevirt-test"

# DataVolume 导入超时（CirrOS ~15MB，给 5 分钟）
DV_TIMEOUT = 300


def test_datavolume_import():
    """测试 DataVolume HTTP 导入 CirrOS 镜像 → Succeeded."""
    log_info("DataVolume HTTP 导入测试: 创建 → Import → Succeeded")

    try:
        # Step 1: 创建 DataVolume
        log_info("Step 1: kubectl apply DataVolume")
        result = kubectl_apply(MANIFEST, NAMESPACE)
        assert result.returncode == 0, f"kubectl apply 失败: {result.stderr}"

        # Step 2: 确认 PVC 被创建（CDI 在 DataVolume 创建后立即创建 PVC）
        time.sleep(5)
        pvc_result = kubectl_get("pvc", DV_NAME, NAMESPACE)
        assert pvc_result.returncode == 0, f"PVC '{DV_NAME}' 未创建 — CDI 可能未就绪"

        # Step 3: 轮询等待 DataVolume status.phase 变为 Succeeded
        log_info(f"Step 2: 等待 DataVolume 导入完成 (timeout={DV_TIMEOUT}s)")
        succeeded = wait_for_condition(f"dv/{DV_NAME}", "Succeeded", timeout=DV_TIMEOUT, poll_interval=10, namespace=NAMESPACE)
        assert succeeded, f"DataVolume '{DV_NAME}' 在 {DV_TIMEOUT}s 内未完成导入"

        # Step 4: 独立验证 — kubectl get dv -o json 确认 status.phase == Succeeded
        log_info("Step 3: 独立验证 DataVolume status.phase == Succeeded")
        phase = get_resource_phase(f"dv/{DV_NAME}", NAMESPACE)
        assert phase == "Succeeded", f"DataVolume status.phase 期望 'Succeeded'，实际 '{phase}'"

        # Step 5: 验证底层 PVC 存在且已绑定
        pvc_phase = get_resource_phase(f"pvc/{DV_NAME}", NAMESPACE)
        log_info(f"PVC 状态: {pvc_phase}")
        assert pvc_phase in ("Bound", "Succeeded"), f"PVC 期望 Bound，实际 '{pvc_phase}'"

        log_success(f"DataVolume '{DV_NAME}' 导入成功 — status.phase=Succeeded, PVC={pvc_phase}")
    finally:
        log_info("清理: 删除 DataVolume + PVC")
        kubectl_delete(MANIFEST, NAMESPACE)
        run_command(
            ["kubectl", "delete", "pvc", DV_NAME, "-n", NAMESPACE, "--ignore-not-found=true"],
            timeout=10,
        )
        log_success("DataVolume 资源清理完毕")
