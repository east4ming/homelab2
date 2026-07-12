"""KubeVirt 测试体系 — 共享基础库."""

from .common import (
    assert_eq,
    assert_in,
    assert_resource_exists,
    assert_vm_running,
    kubectl_apply,
    kubectl_delete,
    kubectl_get,
    log_error,
    log_info,
    log_success,
    log_warn,
    run_command,
    wait_for_condition,
)
from .report_generator import (
    Summary,
    TestReport,
    TestResult,
    generate_markdown_report,
)
from .resource_limiter import (
    ResourceLimit,
    check_vm_limit,
    current_vm_count,
    validate_vm_resources,
    wait_for_vm_slot,
)

__all__ = [
    # common
    "run_command",
    "kubectl_apply",
    "kubectl_delete",
    "kubectl_get",
    "wait_for_condition",
    "log_info",
    "log_success",
    "log_error",
    "log_warn",
    "assert_eq",
    "assert_in",
    "assert_vm_running",
    "assert_resource_exists",
    # resource_limiter
    "ResourceLimit",
    "check_vm_limit",
    "validate_vm_resources",
    "wait_for_vm_slot",
    "current_vm_count",
    # report_generator
    "TestResult",
    "TestReport",
    "Summary",
    "generate_markdown_report",
]
