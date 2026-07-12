"""pytest 全局配置 — sys.path + 测试 namespace 自动创建."""

import subprocess
import sys
from pathlib import Path

import pytest

# 将 tests/ 目录加入 sys.path，使 `from lib.common import ...` 可用
TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

TEST_NAMESPACE = "kubevirt-test"


@pytest.fixture(scope="session", autouse=True)
def ensure_test_namespace():
    """确保测试 namespace 存在，所有测试共享此 fixture."""
    # 检查 namespace 是否已存在
    result = subprocess.run(
        ["kubectl", "get", "ns", TEST_NAMESPACE],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode != 0:
        print(f"\n[conftest] 创建测试 namespace: {TEST_NAMESPACE}")
        result = subprocess.run(
            ["kubectl", "create", "ns", TEST_NAMESPACE],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            pytest.exit(f"无法创建 namespace '{TEST_NAMESPACE}': {result.stderr}")
        print(f"[conftest] namespace '{TEST_NAMESPACE}' 已创建")
    else:
        print(f"\n[conftest] namespace '{TEST_NAMESPACE}' 已存在")

    yield

    # teardown: 不删除 namespace — 保留给后续手动检查
    # 如需清理，运行: kubectl delete ns kubevirt-test
