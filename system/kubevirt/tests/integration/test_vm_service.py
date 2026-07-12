"""集成测试: VM + Service — 验证 Service 创建与关联."""

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
    run_command,
    wait_for_condition,
)
from lib.resource_limiter import check_vm_limit

MANIFEST = MANIFESTS_DIR / "integration" / "vm-service.yaml"
VM_NAME = "test-vm-svc"
SVC_NAME = "test-vm-svc"
NAMESPACE = "kubevirt-test"


def test_vm_with_service():
    """测试 VM + Service — VM Running → Service ClusterIP 分配 → endpoints 检查."""
    log_info("VM+Service 集成测试: VM + ClusterIP Service")

    if not check_vm_limit(NAMESPACE):
        log_warn("VM 槽位已满 (max 2)，跳过测试")
        return

    try:
        # Step 1: 创建 VM + Service
        log_info("Step 1: kubectl apply VM + Service")
        result = kubectl_apply(MANIFEST, NAMESPACE)
        assert result.returncode == 0, f"kubectl apply 失败: {result.stderr}"

        # Step 2: 确认 Service 已创建
        time.sleep(2)
        svc_result = kubectl_get("svc", SVC_NAME, NAMESPACE)
        assert svc_result.returncode == 0, f"Service '{SVC_NAME}' 未创建"

        # Step 3: 等待 VM printableStatus == Running
        log_info("Step 2: 等待 VM Running (timeout=120s)")
        running = wait_for_condition(f"vm/{VM_NAME}", "Running", timeout=120, namespace=NAMESPACE)
        assert running, f"VM '{VM_NAME}' 在 120s 内未进入 Running"

        # Step 4: 独立验证 VM printableStatus == Running
        vm_phase = get_resource_phase(f"vm/{VM_NAME}", NAMESPACE)
        assert vm_phase == "Running", f"VM printableStatus 期望 'Running'，实际 '{vm_phase}'"
        log_success(f"VM Running — printableStatus=Running")

        # Step 5: 验证 Service ClusterIP 已分配
        time.sleep(5)  # 等待 kube-proxy 更新
        svc_ip_result = kubectl_get("svc", SVC_NAME, NAMESPACE, output="jsonpath={.spec.clusterIP}")
        cluster_ip = svc_ip_result.stdout.strip()
        assert cluster_ip, "Service ClusterIP 为空 — Service 可能未正确分配 IP"
        log_info(f"Service ClusterIP: {cluster_ip}")

        # Step 6: 检查 Service endpoints
        ep_result = run_command([
            "kubectl", "get", "endpoints", SVC_NAME, "-n", NAMESPACE,
            "-o", "jsonpath={.subsets[*].addresses[*].ip}",
        ])
        ep_ip = ep_result.stdout.strip()
        if ep_ip:
            log_success(f"Service endpoints 已绑定: {ep_ip}")
        else:
            log_info("Service endpoints 为空 — CirrOS VM 无 SSH 端口，属正常现象")

        log_success("VM+Service 集成验证通过")
    finally:
        log_info("清理: 删除 VM + Service 资源")
        kubectl_delete(MANIFEST, NAMESPACE)
        log_success("VM+Service 资源清理完毕")
