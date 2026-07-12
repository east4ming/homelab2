"""单元测试: 报告生成器格式验证."""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.report_generator import (
    TestReport,
    TestResult,
    generate_markdown_report,
)


def _make_result(test_id: str, name: str, suite: str, status: str,
                 duration: float = 1.0, error: str = "") -> TestResult:
    """快速创建 TestResult."""
    now = datetime.now(timezone.utc)
    return TestResult(
        test_id=test_id,
        name=name,
        suite_type=suite,
        status=status,  # type: ignore[arg-type]
        duration_seconds=duration,
        error_message=error,
        logs="sample log" if status == "FAIL" else "",
        started_at=now,
        finished_at=now,
    )


def test_report_contains_required_fields():
    """验证报告包含必要字段：标题、执行时间、摘要表、详细结果."""
    results = [
        _make_result("t1", "单元测试 A", "unit", "PASS"),
        _make_result("t2", "集成测试 B", "integration", "PASS"),
        _make_result("t3", "端到端测试 C", "e2e", "FAIL", error="连接超时"),
    ]
    report = TestReport(
        executed_at=datetime(2026, 7, 12, 14, 30, 0, tzinfo=timezone.utc),
        total_duration_seconds=512,
        results=results,
    )
    md = generate_markdown_report(report)

    # 必要元素检查
    assert "# KubeVirt 测试报告" in md, "缺少标题"
    assert "执行时间" in md, "缺少执行时间"
    assert "摘要" in md, "缺少摘要表"
    assert "详细结果" in md, "缺少详细结果表"
    assert "单元测试 A" in md, "缺少测试名称"
    assert "✅ PASS" in md, "缺少通过标记"
    assert "❌ FAIL" in md, "缺少失败标记"
    assert "连接超时" in md, "缺少错误详情"


def test_report_empty_results():
    """验证空结果集报告 — 无异常、通过率 0%."""
    report = TestReport(total_duration_seconds=0, results=[])
    md = generate_markdown_report(report)

    assert "通过率" in md and "0%" in md, "空结果应显示通过率 0%"
    assert "0 | 0 | 0" in md.replace("*", ""), "摘要应全为零"


def test_report_all_failed():
    """验证全部失败时报告格式正确."""
    results = [
        _make_result("f1", "失败测试 1", "unit", "FAIL", error="E1"),
        _make_result("f2", "失败测试 2", "integration", "FAIL", error="E2"),
    ]
    report = TestReport(results=results)
    md = generate_markdown_report(report)

    assert "通过率" in md and "0%" in md, "全部失败应显示通过率 0%"
    assert "失败详情" in md, "应有失败详情章节"
    assert "E1" in md, "应包含失败原因 E1"
    assert "E2" in md, "应包含失败原因 E2"


def test_report_all_skipped():
    """验证全部跳过的边界情况."""
    results = [
        _make_result("s1", "跳过测试 1", "unit", "SKIP"),
        _make_result("s2", "跳过测试 2", "e2e", "SKIP"),
    ]
    report = TestReport(results=results)
    md = generate_markdown_report(report)

    assert "⏭️ SKIP" in md, "应有跳过标记"
    assert "失败详情" not in md, "无失败时不应有失败详情"


def test_summary_by_type():
    """验证按套件类型分组汇总."""
    results = [
        _make_result("u1", "U1", "unit", "PASS"),
        _make_result("u2", "U2", "unit", "PASS"),
        _make_result("i1", "I1", "integration", "PASS"),
        _make_result("i2", "I2", "integration", "FAIL", error="x"),
        _make_result("e1", "E1", "e2e", "PASS"),
    ]
    report = TestReport(results=results)
    by_type = report.summary_by_type()

    assert by_type["unit"].total == 2 and by_type["unit"].passed == 2
    assert by_type["integration"].total == 2 and by_type["integration"].failed == 1
    assert by_type["e2e"].total == 1 and by_type["e2e"].passed == 1

    s = report.summary
    assert s.total == 5
    assert s.passed == 4
    assert s.failed == 1
    assert s.pass_rate == 0.8
