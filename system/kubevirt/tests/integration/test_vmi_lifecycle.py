"""集成测试: VMI 生命周期 — 创建 → Running → 删除."""

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

MANIFEST = MANIFESTS_DIR / "integration" / "vmi-ephemeral.yaml"
VMI_NAME = "test-vmi-ephemeral"
NAMESPACE = "kubevirt-test"


def test_vmi_lifecycle():
    """测试 VMI 创建→Running→删除."""
    log_info("VMI 生命周期测试: 创建 → Running → 删除")

    try:
        # When: 创建 VMI
        log_info("创建 VMI 资源")
        result = kubectl_apply(MANIFEST, NAMESPACE)
        assert result.returncode == 0, f"kubectl apply 失败: {result.stderr}"

        # Then: 等待 Running
        log_info("等待 VMI 进入 Running 状态 (timeout=120s)")
        running = wait_for_condition(f"vmi/{VMI_NAME}", "Running", timeout=120, namespace=NAMESPACE)
        assert running, f"VMI '{VMI_NAME}' 在 120s 内未进入 Running 状态"

        # 确认 VMI 可见
        result = kubectl_get("vmi", VMI_NAME, NAMESPACE)
        assert result.returncode == 0, f"kubectl get vmi 失败: {result.stderr}"

        log_success(f"VMI '{VMI_NAME}' Running 验证通过")
    finally:
        # When: 删除 VMI
        log_info("清理: 删除 VMI 资源")
        kubectl_delete(MANIFEST, NAMESPACE)

        # Then: 等待清理
        log_info("等待 VMI 清理完成 (timeout=60s)")
        start = time.time()
        cleaned = False
        while time.time() - start < 60:
            result = kubectl_get("vmi", VMI_NAME, NAMESPACE)
            if result.returncode != 0 or VMI_NAME not in result.stdout:
                cleaned = True
                break
            time.sleep(3)

        if cleaned:
            log_success("VMI 资源清理完毕")
        else:
            log_warn("VMI 资源可能未完全清理")
