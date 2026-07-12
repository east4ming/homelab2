"""单元测试: Helm Chart 模板渲染正确性验证."""

import subprocess
import sys
from pathlib import Path

import yaml

# 确保 lib 包可导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.common import CHART_DIR, MANIFESTS_DIR, log_info, log_success


def _helm_template(values_path: str | None = None) -> list[dict]:
    """运行 helm template 并解析多文档 YAML 输出."""
    cmd = ["helm", "template", "kubevirt-test", str(CHART_DIR), "--namespace", "kubevirt-test"]
    if values_path:
        cmd.extend(["-f", values_path])

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"helm template 失败: {result.stderr}")

    docs = []
    for doc in yaml.safe_load_all(result.stdout):
        if doc is not None:
            docs.append(doc)
    return docs


def test_helm_template_default_values():
    """验证默认 values 渲染 — 输出包含 4 个核心资源."""
    log_info("helm template 默认 values 渲染测试")
    docs = _helm_template()
    kinds = [d.get("kind") for d in docs if d]

    assert len(docs) >= 4, f"期望至少 4 个资源，实际 {len(docs)}"
    for expected_kind in ["Deployment", "CustomResourceDefinition", "KubeVirt", "CDI"]:
        assert expected_kind in kinds, f"缺少资源类型: {expected_kind}"
    log_success("默认 values 渲染通过 — 包含所有核心资源")


def test_helm_template_custom_values():
    """验证自定义 values 覆盖 — emulation 参数生效."""
    log_info("helm template 自定义 values 覆盖测试")
    override_path = str(MANIFESTS_DIR / "unit" / "values-override.yaml")
    docs = _helm_template(override_path)

    # 查找包含 useEmulation 的资源
    found_emulation = False
    for doc in docs:
        doc_str = yaml.dump(doc)
        if "useEmulation" in doc_str and "true" in doc_str:
            found_emulation = True
            break

    assert found_emulation, "自定义 values 中 useEmulation: true 未传递到渲染输出"
    log_success("自定义 values 覆盖通过")


def test_helm_template_yaml_syntax():
    """验证渲染输出 YAML 语法合法."""
    log_info("helm template YAML 语法校验")
    docs = _helm_template()
    assert len(docs) > 0, "helm template 无输出"

    for i, doc in enumerate(docs):
        assert doc is not None, f"文档 {i} 为 null"
        assert "apiVersion" in doc, f"文档 {i} 缺少 apiVersion"
        assert "kind" in doc, f"文档 {i} 缺少 kind"
        assert "metadata" in doc, f"文档 {i} 缺少 metadata"

    log_success(f"全部 {len(docs)} 个文档 YAML 语法合法")
