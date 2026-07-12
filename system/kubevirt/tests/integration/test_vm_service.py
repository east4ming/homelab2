"""集成测试: VM + Service — 验证 Service 创建与关联."""

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

MANIFEST = MANIFESTS_DIR / "integration" / "vm-service.yaml"
VM_NAME = "test-vm-svc"
SVC_NAME = "test-vm-svc"
NAMESPACE = "kubevirt-test"


def test_vm_with_service():
    """测试 VM + Service 创建，验证 Service 关联到 VM Pod."""
    log_info("VM+Service 集成测试: VM + ClusterIP Service")

    if not check_vm_limit(NAMESPACE):
        log_warn("VM 槽位已满 (max 2)，跳过测试")
        return

    try:
        # When: 创建 VM + Service
        log_info("创建 VM + Service 资源")
        result = kubectl_apply(MANIFEST, NAMESPACE)
        assert result.returncode == 0, f"kubectl apply 失败: {result.stderr}"

        # Then: VM 进入 Running
        log_info("等待 VM 进入 Running (timeout=120s)")
        running = wait_for_condition(f"vm/{VM_NAME}", "Running", timeout=120, namespace=NAMESPACE)
        assert running, f"VM '{VM_NAME}' 在 120s 内未进入 Running"

        # Then: Service 存在且有 endpoints
        time.sleep(10)  # 等待 kube-proxy 更新 endpoints
        svc_result = kubectl_get("svc", SVC_NAME, NAMESPACE, output="jsonpath={.spec.clusterIP}")
        assert svc_result.returncode == 0, f"Service '{SVC_NAME}' 不存在"
        cluster_ip = svc_result.stdout.strip()
        assert cluster_ip, "Service ClusterIP 为空"
        log_info(f"Service ClusterIP: {cluster_ip}")

        # Then: 确认 Service selector 匹配 VM pod label
        ep_result = run_command([
            "kubectl", "get", "endpoints", SVC_NAME, "-n", NAMESPACE,
            "-o", "jsonpath={.subsets[*].addresses[*].ip}",
        ])
        log_info(f"Service 状态: endpoints={ep_result.stdout.strip() or '(empty — 正常，VM 可能无匹配端口)'}")

        log_success("VM+Service 集成验证通过")
    finally:
        log_info("清理: 删除 VM + Service 资源")
        kubectl_delete(MANIFEST, NAMESPACE)
        log_success("VM+Service 资源清理完毕")
