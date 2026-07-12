# KubeVirt 测试体系

为 `system/kubevirt/` Helm Chart 及已部署的 KubeVirt 平台提供的三层测试体系。

## 目录结构

```text
tests/
├── run.py                   # 主入口
├── pyproject.toml           # uv 依赖管理
├── lib/                     # 共享基础库
│   ├── common.py            # kubectl/helm/virtctl 封装、断言、日志
│   ├── resource_limiter.py  # VM 并发控制 (≤2 VM, ≤2C4G/VM)
│   └── report_generator.py  # Markdown 报告生成
├── manifests/               # 测试用 YAML 资源清单
│   ├── unit/                # helm template 测试 values
│   ├── integration/         # VM/VMI/DataVolume/Service
│   └── e2e/                 # 生产级 VM 完整定义
├── unit/                    # 单元测试
│   ├── test_helm_template.py
│   └── test_report_generator.py
├── integration/             # 集成测试
│   ├── test_vm_lifecycle.py
│   ├── test_vmi_lifecycle.py
│   ├── test_datavolume.py
│   ├── test_vm_datavolume.py
│   └── test_vm_service.py
└── e2e/                     # 端到端测试
    ├── test_production_vm.py
    └── test_vm_connectivity.py
```

## 快速开始

### 前置条件

- Python 3.12+
- `uv` 已安装
- `kubectl`、`virtctl`、`helm` 在 PATH 中
- KubeVirt + CDI 已部署
- CSI 存储后端可用

### 安装

```bash
cd system/kubevirt/tests
uv sync
```

### 运行测试

```bash
# 全部测试
uv run python run.py

# 仅单元测试 (≤30s，无需集群 VM 资源)
uv run pytest unit/ -v

# 仅集成测试 (需要集群创建 VM)
uv run pytest integration/ -v

# 仅端到端测试 (需要集群创建生产级 VM)
uv run pytest e2e/ -v

# 详细模式
uv run python run.py --verbose

# 指定报告路径
uv run python run.py --report /tmp/kubevirt-report.md
```

## 资源限制

测试框架强制执行以下限制：

- 同时运行 VM ≤ 2 个
- 单 VM CPU ≤ 2 核
- 单 VM 内存 ≤ 4Gi

所有测试资源带 label `app.kubernetes.io/test: kubevirt-suite`，在独立 namespace `kubevirt-test` 中运行，测试结束后自动清理。

## 测试覆盖

| 类型 | 测试 | 说明 |
|------|------|------|
| 单元测试 | helm template 渲染 | 验证默认 values + 自定义 values 覆盖 |
| 单元测试 | 报告生成器 | 验证 Markdown 报告格式和边界情况 |
| 集成测试 | VM 生命周期 | 创建→Running→删除 |
| 集成测试 | VMI 生命周期 | 创建→Running→删除 |
| 集成测试 | DataVolume 导入 | HTTP 导入 CirrOS 镜像 |
| 集成测试 | VM + DataVolume | DataVolume 引导启动 VM |
| 集成测试 | VM + Service | ClusterIP Service 路由 |
| 端到端测试 | 生产级 VM | SSH/console/持久化/dnf/重启 |
| 端到端测试 | VM 网络连通性 | 双 VM IP 分配 + 网络状态 |

## 添加新测试

1. 在 `manifests/<suite>/` 创建 YAML 清单
2. 在 `<suite>/` 创建 `test_*.py` 文件
3. 从 `lib` 导入公共函数
4. 遵循 pytest 命名约定

示例:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.common import kubectl_apply, wait_for_condition, log_info, log_success

def test_my_feature():
    log_info("测试描述")
    # Given: ...
    # When: kubectl_apply(manifest)
    # Then: wait_for_condition(...)
    log_success("通过")
```
