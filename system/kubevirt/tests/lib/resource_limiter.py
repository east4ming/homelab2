"""VM 并发控制：限制同时运行 VM ≤ 2，单 VM ≤ 2C4G."""

import time
import subprocess


class ResourceLimit:
    """VM 资源配置限制."""

    def __init__(self, max_vms: int = 2, max_cpu: str = "2", max_memory: str = "4Gi"):
        self.max_vms = max_vms
        self.max_cpu = max_cpu
        self.max_memory = max_memory

    @property
    def current_count(self) -> int:
        """查询当前 namespace 中 Running 状态的 VM 数量."""
        return current_vm_count()


def current_vm_count(namespace: str = "kubevirt-test") -> int:
    """查询当前 Running 状态的 VM 数量."""
    try:
        result = subprocess.run(
            [
                "kubectl", "get", "vm", "-n", namespace,
                "--no-headers",
                "-o", "custom-columns=NAME:.metadata.name,STATUS:.status.printableStatus",
            ],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return 0
        count = 0
        for line in result.stdout.strip().split("\n"):
            if line and "Running" in line:
                count += 1
        return count
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return 0


def check_vm_limit(namespace: str = "kubevirt-test", max_vms: int = 2) -> bool:
    """检查是否允许创建新 VM.

    Returns:
        True 如果当前 VM 数 < 上限，可以创建
    """
    count = current_vm_count(namespace)
    return count < max_vms


def validate_vm_resources(cpu: str, memory: str, max_cpu: str = "2", max_memory: str = "4Gi") -> bool:
    """验证 VM 资源规格不超过上限.

    简单的字符串比较 — 对于 K8s 资源值格式（如 "2", "500m", "4Gi"）
    使用更宽松的检查：检查数字部分不超过上限。

    Returns:
        True 如果资源规格在限制内
    """
    # 解析 CPU
    cpu_val = _parse_cpu(cpu)
    max_cpu_val = _parse_cpu(max_cpu)
    if cpu_val > max_cpu_val:
        return False

    # 解析内存
    mem_val = _parse_memory(memory)
    max_mem_val = _parse_memory(max_memory)
    if mem_val > max_mem_val:
        return False

    return True


def wait_for_vm_slot(timeout: int = 600, poll_interval: int = 10, namespace: str = "kubevirt-test") -> bool:
    """等待有空闲 VM 槽位.

    Args:
        timeout: 总等待时间（秒）
        poll_interval: 轮询间隔（秒）
        namespace: 命名空间

    Returns:
        True 如果有空闲槽位，False 如果超时
    """
    elapsed = 0
    while elapsed < timeout:
        if check_vm_limit(namespace):
            return True
        time.sleep(poll_interval)
        elapsed += poll_interval
    return False


def _parse_cpu(cpu_str: str) -> float:
    """解析 K8s CPU 资源值为核数."""
    cpu_str = cpu_str.strip()
    if cpu_str.endswith("m"):
        return float(cpu_str[:-1]) / 1000
    return float(cpu_str)


def _parse_memory(mem_str: str) -> float:
    """解析 K8s 内存资源值为 MiB."""
    mem_str = mem_str.strip().upper()
    multipliers = {
        "KI": 1 / 1024,
        "MI": 1,
        "GI": 1024,
        "TI": 1024 * 1024,
        "K": 1 / 1024,
        "M": 1,
        "G": 1024,
        "T": 1024 * 1024,
    }
    for suffix, mult in multipliers.items():
        if mem_str.endswith(suffix):
            return float(mem_str[:-len(suffix)]) * mult
    # 默认假定为字节
    try:
        return float(mem_str) / (1024 * 1024)
    except ValueError:
        return 0.0
