"""公共函数：subprocess 封装、kubectl 操作、断言、日志."""

import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

# --- 路径常量 ---
TESTS_DIR = Path(__file__).resolve().parent.parent
MANIFESTS_DIR = TESTS_DIR / "manifests"
PROJECT_ROOT = TESTS_DIR.parent.parent  # homelab2 仓库根目录
CHART_DIR = TESTS_DIR.parent  # system/kubevirt/

# --- 日志函数 ---


def log_info(msg: str) -> None:
    """输出信息日志."""
    print(f"  [INFO] {msg}")


def log_success(msg: str) -> None:
    """输出成功日志."""
    print(f"  [OK]   {msg}")


def log_error(msg: str) -> None:
    """输出错误日志."""
    print(f"  [FAIL] {msg}")


def log_warn(msg: str) -> None:
    """输出警告日志."""
    print(f"  [WARN] {msg}")


# --- subprocess 封装 ---


def run_command(cmd: list[str], timeout: int = 300, check: bool = False) -> subprocess.CompletedProcess:
    """执行 shell 命令，返回 CompletedProcess.

    Args:
        cmd: 命令列表，如 ["kubectl", "get", "vm"]
        timeout: 超时秒数
        check: True 时非零退出码抛出 CalledProcessError

    Returns:
        subprocess.CompletedProcess (stdout/stderr 为 str)
    """
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=check,
    )


# --- kubectl 便捷封装 ---


def kubectl_apply(manifest_path: Path, namespace: str = "kubevirt-test") -> subprocess.CompletedProcess:
    """kubectl apply 资源清单."""
    return run_command([
        "kubectl", "apply", "-f", str(manifest_path), "-n", namespace,
    ])


def kubectl_delete(manifest_path: Path, namespace: str = "kubevirt-test", ignore_not_found: bool = True) -> subprocess.CompletedProcess:
    """kubectl delete 资源清单."""
    cmd = ["kubectl", "delete", "-f", str(manifest_path), "-n", namespace]
    if ignore_not_found:
        cmd.append("--ignore-not-found=true")
    return run_command(cmd)


def kubectl_get(
    resource_type: str,
    resource_name: str = "",
    namespace: str = "kubevirt-test",
    output: str = "",
) -> subprocess.CompletedProcess:
    """kubectl get 资源."""
    cmd = ["kubectl", "get", resource_type, "-n", namespace]
    if resource_name:
        cmd.append(resource_name)
    if output:
        cmd.extend(["-o", output])
    else:
        cmd.append("--no-headers")
    return run_command(cmd)


# --- 等待与条件检查 ---


def wait_for_condition(
    resource: str,
    expected_status: str,
    timeout: int = 120,
    poll_interval: int = 5,
    namespace: str = "kubevirt-test",
) -> bool:
    """轮询等待资源达到预期状态.

    Args:
        resource: 资源标识，如 "vm/my-vm" 或 "vmi/my-vmi"
        expected_status: 预期状态值，如 "Running"、"Succeeded"
        timeout: 超时秒数
        poll_interval: 轮询间隔秒数
        namespace: 命名空间

    Returns:
        True 如果达到预期状态，False 如果超时
    """
    elapsed = 0
    while elapsed < timeout:
        result = run_command([
            "kubectl", "get", resource, "-n", namespace,
            "-o", "jsonpath={.status.phase}",
        ])
        # DataVolume 使用 .status.phase，VM/VMI 使用 .status.printableStatus
        if result.returncode != 0:
            # 尝试 printableStatus（VM 用）
            result = run_command([
                "kubectl", "get", resource, "-n", namespace,
                "-o", "jsonpath={.status.printableStatus}",
            ])
        if result.returncode == 0 and result.stdout.strip() == expected_status:
            return True
        time.sleep(poll_interval)
        elapsed += poll_interval
    return False


def get_resource_status(
    resource: str,
    namespace: str = "kubevirt-test",
) -> str:
    """获取资源当前状态."""
    # 先尝试 .status.phase (VMI/DataVolume)
    result = run_command([
        "kubectl", "get", resource, "-n", namespace,
        "-o", "jsonpath={.status.phase}",
    ])
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    # 再尝试 .status.printableStatus (VM)
    result = run_command([
        "kubectl", "get", resource, "-n", namespace,
        "-o", "jsonpath={.status.printableStatus}",
    ])
    if result.returncode == 0:
        return result.stdout.strip()
    return "Unknown"


# --- 断言函数 ---


def assert_eq(actual, expected, message: str = "") -> tuple[bool, str]:
    """断言相等，返回 (通过, 错误消息)."""
    if actual == expected:
        return True, ""
    msg = message or f"期望 {expected!r}，实际 {actual!r}"
    return False, msg


def assert_in(item, container, message: str = "") -> tuple[bool, str]:
    """断言 item 在 container 中."""
    if item in container:
        return True, ""
    msg = message or f"期望 {item!r} 在 {container!r} 中"
    return False, msg


def assert_vm_running(vm_name: str, namespace: str = "kubevirt-test") -> tuple[bool, str]:
    """断言 VM 处于 Running 状态."""
    status = get_resource_status(f"vm/{vm_name}", namespace)
    if status == "Running":
        return True, ""
    return False, f"VM '{vm_name}' 状态为 '{status}'，期望 'Running'"


def assert_resource_exists(resource: str, namespace: str = "kubevirt-test") -> tuple[bool, str]:
    """断言资源存在."""
    result = run_command(["kubectl", "get", resource, "-n", namespace])
    if result.returncode == 0:
        return True, ""
    return False, f"资源 '{resource}' 不存在"


# --- 测试生命周期辅助 ---

_test_results: list = []  # 全局收集测试结果


def test_start(test_id: str, description: str) -> dict:
    """标记测试开始，返回测试上下文."""
    log_info(f"开始: {description}")
    return {
        "id": test_id,
        "description": description,
        "started_at": datetime.now(timezone.utc),
    }


def test_pass(ctx: dict, duration_seconds: float = 0) -> None:
    """标记测试通过."""
    from .report_generator import TestResult

    result = TestResult(
        test_id=ctx["id"],
        name=ctx["description"],
        suite_type="",
        status="PASS",
        duration_seconds=duration_seconds,
        error_message="",
        logs="",
        started_at=ctx["started_at"],
        finished_at=datetime.now(timezone.utc),
    )
    _test_results.append(result)
    log_success(f"PASS: {ctx['description']}")


def test_fail(ctx: dict, reason: str, duration_seconds: float = 0, logs: str = "") -> None:
    """标记测试失败."""
    from .report_generator import TestResult

    result = TestResult(
        test_id=ctx["id"],
        name=ctx["description"],
        suite_type="",
        status="FAIL",
        duration_seconds=duration_seconds,
        error_message=reason,
        logs=logs,
        started_at=ctx["started_at"],
        finished_at=datetime.now(timezone.utc),
    )
    _test_results.append(result)
    log_error(f"FAIL: {ctx['description']} — {reason}")


def test_skip(ctx: dict, reason: str) -> None:
    """标记测试跳过."""
    from .report_generator import TestResult

    result = TestResult(
        test_id=ctx["id"],
        name=ctx["description"],
        suite_type="",
        status="SKIP",
        duration_seconds=0,
        error_message=reason,
        logs="",
        started_at=ctx["started_at"],
        finished_at=datetime.now(timezone.utc),
    )
    _test_results.append(result)
    log_warn(f"SKIP: {ctx['description']} — {reason}")


def collect_results() -> list:
    """收集所有测试结果."""
    return list(_test_results)


def clear_results() -> None:
    """清空结果缓存."""
    _test_results.clear()
