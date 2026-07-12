#!/usr/bin/env python3
"""KubeVirt 测试体系 — 主入口.

用法:
    uv run python run.py                    # 执行全部测试
    uv run python run.py --suite unit       # 仅单元测试
    uv run python run.py --suite integration # 仅集成测试
    uv run python run.py --suite e2e        # 仅端到端测试
    uv run python run.py --verbose          # 详细模式
    uv run python run.py --report path.md   # 指定报告路径
"""

import argparse
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS_DIR))

from lib.common import log_error, log_info, log_success, log_warn, run_command


def check_environment() -> bool:
    """Phase 0: 环境检查 — 验证所有前置依赖可用."""
    log_info("=" * 50)
    log_info("Phase 0: 环境检查")
    log_info("=" * 50)

    checks = {
        "kubectl": ["kubectl", "version", "--client", "--short"],
        "virtctl": ["virtctl", "version", "--client"],
        "helm": ["helm", "version", "--short"],
    }

    all_ok = True
    for name, cmd in checks.items():
        result = run_command(cmd, timeout=10)
        if result.returncode == 0:
            version = result.stdout.strip().split("\n")[0][:60]
            log_success(f"{name}: {version}")
        else:
            log_error(f"{name}: 不可用 — {result.stderr.strip()[:80]}")
            all_ok = False

    # 检查集群状态
    cluster_checks = {
        "KubeVirt": ["kubectl", "get", "kubevirt", "-A", "--no-headers"],
        "CDI": ["kubectl", "get", "cdi", "-A", "--no-headers"],
        "StorageClass": ["kubectl", "get", "sc", "--no-headers"],
    }
    for name, cmd in cluster_checks.items():
        result = run_command(cmd, timeout=15)
        if result.returncode == 0 and result.stdout.strip():
            log_success(f"{name}: 可用")
        else:
            log_warn(f"{name}: 不可用或未部署")

    # 确保测试 namespace 存在
    run_command(["kubectl", "create", "ns", "kubevirt-test", "--dry-run=client", "-o", "yaml"], timeout=5)
    run_command(["kubectl", "create", "ns", "kubevirt-test"], timeout=10)

    return all_ok


def run_pytest(suite: str, verbose: bool = False) -> list:
    """运行 pytest 测试套件，返回 TestResult 列表."""
    from lib.report_generator import TestResult  # noqa: F811

    suite_dir = TESTS_DIR / suite
    if not suite_dir.exists() or not any(suite_dir.glob("test_*.py")):
        log_warn(f"套件 '{suite}' 无测试文件，跳过")
        return []

    cmd = ["uv", "run", "pytest", str(suite_dir), "-v", "--tb=short"]
    if verbose:
        cmd.append("-s")  # 显示 print 输出

    log_info(f"执行: {' '.join(cmd)}")
    start = time.time()
    result = subprocess.run(cmd, capture_output=not verbose, text=True, timeout=900, cwd=str(TESTS_DIR))
    duration = time.time() - start

    # 解析 pytest 输出提取结果
    results = []
    output = result.stdout + result.stderr
    for line in output.split("\n"):
        if "PASSED" in line or "FAILED" in line:
            # 简单解析 — pytest 的详细输出模式
            pass

    # 如果 pytest 退出码为 0，全部通过
    if result.returncode == 0:
        log_success(f"套件 '{suite}' 全部通过 ({duration:.0f}s)")
    else:
        log_warn(f"套件 '{suite}' 存在失败 ({duration:.0f}s)")

    return results


def main():
    parser = argparse.ArgumentParser(description="KubeVirt 测试体系")
    parser.add_argument("--suite", choices=["unit", "integration", "e2e"],
                        help="仅执行指定测试套件")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="详细模式，显示实时输出")
    parser.add_argument("--report", default=str(TESTS_DIR / "test-report.md"),
                        help="测试报告输出路径 (默认: system/kubevirt/tests/test-report.md)")
    args = parser.parse_args()

    log_info("KubeVirt Test Suite v0.1.0")
    overall_start = time.time()

    # Phase 0
    env_ok = check_environment()
    if not env_ok:
        log_warn("部分环境检查未通过，继续执行可用的测试...")

    # 确定执行哪些套件
    suite_order = ["unit", "integration", "e2e"]
    if args.suite:
        suite_order = [args.suite]

    # 执行测试 — 使用 pytest 作为 runner
    exit_code = 0

    for suite in suite_order:
        log_info(f"\n{'=' * 50}")
        log_info(f"执行套件: {suite}")
        log_info(f"{'=' * 50}")

        # 直接使用 pytest 执行对应目录
        test_dir = TESTS_DIR / suite
        if not test_dir.exists() or not any(test_dir.glob("test_*.py")):
            log_warn(f"套件 '{suite}' 无测试文件，跳过")
            continue

        cmd = ["uv", "run", "pytest", str(test_dir), "-v", "--tb=short", "--timeout=300"]
        if args.verbose:
            cmd.append("-s")

        suite_start = time.time()
        result = subprocess.run(
            cmd,
            capture_output=not args.verbose,
            text=True,
            timeout=900,
            cwd=str(TESTS_DIR),
        )
        suite_duration = time.time() - suite_start

        if result.returncode == 0:
            log_success(f"套件 '{suite}' 全部通过 ({suite_duration:.0f}s)")
        else:
            log_warn(f"套件 '{suite}' 存在测试失败 ({suite_duration:.0f}s)")
            exit_code = 1

        if not args.verbose and result.stdout:
            # 输出 pytest 结果摘要
            for line in result.stdout.split("\n"):
                if "passed" in line or "failed" in line or "error" in line or "===" in line:
                    print(f"  {line}")

    # Phase 4: 生成报告
    total_duration = time.time() - overall_start
    log_info(f"\n{'=' * 50}")
    log_info("生成测试报告")
    log_info(f"{'=' * 50}")

    # 解析 pytest 输出文件或生成简化报告
    report_lines = [
        "# KubeVirt 测试报告",
        "",
        f"**执行时间**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"**总耗时**: {total_duration:.0f}s",
        "",
        "## 说明",
        "",
        "详细测试结果请查看上方 pytest 输出。各套件对应目录:",
        "",
        "- `unit/` — Helm Chart 模板渲染 + 报告生成器验证",
        "- `integration/` — 单资源 + 关联资源集成测试",
        "- `e2e/` — 生产级 VM 端到端验证",
        "",
        "### 运行命令",
        "",
        "```bash",
        "uv run pytest unit/ -v           # 仅单元测试",
        "uv run pytest integration/ -v    # 仅集成测试",
        "uv run pytest e2e/ -v            # 仅端到端测试",
        "uv run pytest unit/ integration/ e2e/ -v  # 全部测试",
        "```",
    ]
    report_content = "\n".join(report_lines)

    report_path = Path(args.report)
    report_path.write_text(report_content)
    log_success(f"测试报告已生成: {report_path}")

    # 退出码
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
