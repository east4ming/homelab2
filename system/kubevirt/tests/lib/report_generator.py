"""Markdown 测试报告生成."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal


@dataclass
class TestResult:
    """单个测试用例的执行结果."""
    __test__ = False  # 非 pytest 测试类

    test_id: str
    name: str
    suite_type: str  # unit / integration / e2e
    status: Literal["PASS", "FAIL", "SKIP"]
    duration_seconds: float
    error_message: str = ""
    logs: str = ""
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def status_icon(self) -> str:
        """状态图标."""
        return {"PASS": "✅", "FAIL": "❌", "SKIP": "⏭️"}.get(self.status, "❓")


@dataclass
class Summary:
    """按套件类型的汇总统计."""

    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0

    @property
    def pass_rate(self) -> float:
        """通过率 (0.0 ~ 1.0)."""
        if self.total == 0:
            return 0.0
        return self.passed / self.total


@dataclass
class TestReport:
    """一次完整测试执行的汇总报告."""
    __test__ = False  # 非 pytest 测试类

    executed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    total_duration_seconds: float = 0.0
    results: list[TestResult] = field(default_factory=list)

    @property
    def summary(self) -> Summary:
        """计算总体汇总."""
        s = Summary()
        for r in self.results:
            s.total += 1
            if r.status == "PASS":
                s.passed += 1
            elif r.status == "FAIL":
                s.failed += 1
            elif r.status == "SKIP":
                s.skipped += 1
        return s

    def summary_by_type(self) -> dict[str, Summary]:
        """按套件类型分组汇总."""
        by_type: dict[str, Summary] = {}
        for r in self.results:
            st = r.suite_type or "unknown"
            if st not in by_type:
                by_type[st] = Summary()
            s = by_type[st]
            s.total += 1
            if r.status == "PASS":
                s.passed += 1
            elif r.status == "FAIL":
                s.failed += 1
            elif r.status == "SKIP":
                s.skipped += 1
        return by_type


def generate_markdown_report(report: TestReport) -> str:
    """生成 Markdown 格式的测试报告.

    Args:
        report: 测试报告对象

    Returns:
        Markdown 字符串
    """
    lines: list[str] = []
    s = report.summary

    # 标题
    lines.append("# KubeVirt 测试报告")
    lines.append("")
    lines.append(f"**执行时间**: {report.executed_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    lines.append(f"**总耗时**: {_format_duration(report.total_duration_seconds)}")
    lines.append(f"**通过率**: {s.pass_rate:.0%}")
    lines.append("")

    # 摘要表
    lines.append("## 摘要")
    lines.append("")
    lines.append("| 类型 | 总数 | 通过 | 失败 | 跳过 | 通过率 |")
    lines.append("|------|------|------|------|------|--------|")

    by_type = report.summary_by_type()
    type_order = ["unit", "integration", "e2e"]
    for st in type_order:
        if st in by_type:
            bs = by_type[st]
            lines.append(
                f"| {_type_label(st)} | {bs.total} | {bs.passed} | {bs.failed} | {bs.skipped} | {bs.pass_rate:.0%} |"
            )

    # 合计行
    lines.append(
        f"| **合计** | **{s.total}** | **{s.passed}** | **{s.failed}** | **{s.skipped}** | **{s.pass_rate:.0%}** |"
    )
    lines.append("")

    # 详细结果
    lines.append("## 详细结果")
    lines.append("")
    lines.append("| # | 用例 | 类型 | 状态 | 耗时 | 备注 |")
    lines.append("|---|------|------|------|------|------|")

    for i, r in enumerate(report.results, 1):
        duration = _format_duration(r.duration_seconds)
        note = r.error_message if r.status == "FAIL" else "-"
        # 截断过长的备注
        if len(note) > 80:
            note = note[:77] + "..."
        lines.append(
            f"| {i} | {r.name} | {_type_label(r.suite_type)} | {r.status_icon} {r.status} | {duration} | {note} |"
        )

    lines.append("")

    # 失败详情
    failures = [r for r in report.results if r.status == "FAIL"]
    if failures:
        lines.append("## 失败详情")
        lines.append("")
        for r in failures:
            lines.append(f"### {r.name}")
            lines.append("")
            lines.append(f"- **错误**: {r.error_message}")
            if r.logs:
                lines.append(f"- **日志**:")
                lines.append("```")
                lines.append(r.logs[:1000])  # cap at 1000 chars
                lines.append("```")
            lines.append("")

    return "\n".join(lines)


def _type_label(suite_type: str) -> str:
    """套件类型的中文标签."""
    labels = {"unit": "单元测试", "integration": "集成测试", "e2e": "端到端测试"}
    return labels.get(suite_type, suite_type)


def _format_duration(seconds: float) -> str:
    """格式化耗时."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        m = int(seconds // 60)
        s = int(seconds % 60)
        return f"{m}m{s}s"
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    return f"{h}h{m}m"
