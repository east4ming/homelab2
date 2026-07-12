"""集成测试: DataVolume HTTP 导入 → Succeeded."""

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
)

MANIFEST = MANIFESTS_DIR / "integration" / "datavolume-cirros.yaml"
DV_NAME = "test-dv-cirros"
NAMESPACE = "kubevirt-test"

# DataVolume 导入超时（CirrOS ~15MB，给 5 分钟）
DV_TIMEOUT = 300


def _wait_for_datavolume(dv_name: str, timeout: int = DV_TIMEOUT, poll_interval: int = 10) -> bool:
    """轮询等待 DataVolume 进入 Succeeded 或 ImportFailed 状态."""
    elapsed = 0
    while elapsed < timeout:
        result = run_command([
            "kubectl", "get", f"dv/{dv_name}", "-n", NAMESPACE,
            "-o", "jsonpath={.status.phase}",
        ])
        phase = result.stdout.strip()
        if phase == "Succeeded":
            return True
        if phase in ("Failed", "ImportFailed", "Error"):
            log_warn(f"DataVolume 进入 {phase} 状态")
            return False
        time.sleep(poll_interval)
        elapsed += poll_interval
    return False


def test_datavolume_import():
    """测试 DataVolume HTTP 导入 CirrOS 镜像."""
    log_info("DataVolume HTTP 导入测试: 创建 → Import → Succeeded")

    try:
        # When: 创建 DataVolume
        log_info("创建 DataVolume 资源")
        result = kubectl_apply(MANIFEST, NAMESPACE)
        assert result.returncode == 0, f"kubectl apply 失败: {result.stderr}"

        # 确认 PVC 被创建
        time.sleep(3)
        pvc_result = kubectl_get("pvc", DV_NAME, NAMESPACE)
        assert pvc_result.returncode == 0, f"PVC '{DV_NAME}' 未创建"

        # Then: 等待导入完成
        log_info(f"等待 DataVolume 导入完成 (timeout={DV_TIMEOUT}s)")
        succeeded = _wait_for_datavolume(DV_NAME, timeout=DV_TIMEOUT)
        assert succeeded, f"DataVolume '{DV_NAME}' 在 {DV_TIMEOUT}s 内未完成导入"

        # 验证 PVC 存在且有数据
        result = kubectl_get("dv", DV_NAME, NAMESPACE, output="jsonpath={.status.phase}")
        assert "Succeeded" in result.stdout, f"DataVolume 状态异常: {result.stdout}"

        log_success(f"DataVolume '{DV_NAME}' 导入成功 (Succeeded)")
    finally:
        # When: 删除 DataVolume
        log_info("清理: 删除 DataVolume 资源")
        kubectl_delete(MANIFEST, NAMESPACE)

        # 确保 PVC 也被删除
        log_info("确保关联 PVC 也被清理")
        run_command(
            ["kubectl", "delete", "pvc", DV_NAME, "-n", NAMESPACE, "--ignore-not-found=true"],
            timeout=10,
        )
        log_success("DataVolume 资源清理完毕")
