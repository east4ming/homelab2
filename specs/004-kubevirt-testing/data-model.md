# Data Model: KubeVirt 测试体系

**Created**: 2026-07-12

## 核心实体

### TestSuite（测试套件）

测试的顶层组织单元，按测试类型划分。

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | str | 套件名称，如 "unit" / "integration" / "e2e" |
| `type` | Literal["unit", "integration", "e2e"] | 套件类型 |
| `test_cases` | list[TestCase] | 包含的测试用例列表 |
| `setup` | Callable \| None | 套件级别的前置准备（可选） |
| `teardown` | Callable \| None | 套件级别的清理（可选） |

### TestCase（测试用例）

单个可执行的测试场景。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | str | 唯一标识，如 "vm-lifecycle-create-delete" |
| `name` | str | 人类可读的名称 |
| `suite_type` | str | 所属套件类型 |
| `given` | list[str] | 前置条件描述 |
| `when` | list[str] | 操作步骤描述 |
| `then` | list[str] | 预期结果描述 |
| `timeout` | int | 超时时间（秒） |
| `run` | Callable | 实际执行逻辑（Python 函数） |
| `cleanup` | Callable | 资源清理逻辑（无论成功失败都执行） |

**状态转换**:

```
Pending → Running → Passed
                  → Failed
                  → Skipped
```

### TestResult（测试结果）

单个测试用例的执行结果。

| 字段 | 类型 | 说明 |
|------|------|------|
| `test_id` | str | 关联的 TestCase ID |
| `status` | Literal["PASS", "FAIL", "SKIP"] | 执行状态 |
| `duration_seconds` | float | 执行耗时 |
| `error_message` | str | 失败原因（PASS/SKIP 时为空字符串） |
| `logs` | str | 关键日志（失败时包含） |
| `started_at` | datetime | 开始时间 |
| `finished_at` | datetime | 结束时间 |

### TestReport（测试报告）

一次完整测试执行的汇总产物。

| 字段 | 类型 | 说明 |
|------|------|------|
| `executed_at` | datetime | 执行时间 |
| `total_duration_seconds` | float | 总耗时 |
| `results` | list[TestResult] | 全部用例结果 |
| `summary` | Summary | 按类型汇总统计 |

### Summary（汇总统计）

| 字段 | 类型 | 说明 |
|------|------|------|
| `total` | int | 总用例数 |
| `passed` | int | 通过数 |
| `failed` | int | 失败数 |
| `skipped` | int | 跳过数 |
| `by_type` | dict[str, Summary] | 按套件类型的分组统计 |

### ResourceLimit（资源限制）

VM 并发控制实体，追踪当前测试 namespace 中运行中的 VM 数量。

| 字段 | 类型 | 说明 |
|------|------|------|
| `max_vms` | int | 最大同时运行 VM 数（= 2） |
| `max_cpu_per_vm` | str | 单 VM CPU 上限（"2"） |
| `max_memory_per_vm` | str | 单 VM 内存上限（"4Gi"） |

**方法**:
- `check_vm_limit() -> bool`: 返回当前是否允许创建新 VM（current_count < max_vms）
- `validate_vm_resources(cpu: str, memory: str) -> bool`: 验证 VM 规格不超过上限
- `wait_for_slot(timeout: int) -> bool`: 等待有空闲 VM 槽位，超时返回 False
- `current_count -> int`: property，通过 `kubectl get vm` 实时查询

### TestVMConfig（VM 测试配置）

定义测试用 VM 的规格参数（dataclass）。

```python
@dataclass
class TestVMConfig:
    name: str              # VM 名称
    image: str             # 启动镜像（containerDisk 或 DataVolume 引用）
    cpu: str = "1"         # CPU 请求/限制（≤ "2"）
    memory: str = "2Gi"    # 内存请求/限制（≤ "4Gi"）
    disk_size: str = "10Gi"  # 持久化磁盘大小
    ssh_public_key: str = ""  # 注入的 SSH 公钥（临时生成）
    cloud_init_userdata: str = ""  # cloud-init user-data 内容
    network: str = "masquerade"    # 网络类型
    run_strategy: str = "Always"   # 运行策略
```

## 文件系统布局

```text
system/kubevirt/tests/
├── pyproject.toml           # uv 项目配置 + 依赖
├── run.py                   # 主入口
├── lib/
│   ├── __init__.py
│   ├── common.py            # 日志、断言、kubectl wait 封装
│   ├── resource_limiter.py  # VM 并发控制
│   └── report_generator.py  # 报告生成
├── manifests/
│   ├── unit/
│   │   └── values-override.yaml   # helm template 测试用 values
│   ├── integration/
│   │   ├── vm-cirros.yaml         # 最小化 CirrOS VM
│   │   ├── vmi-ephemeral.yaml     # 临时 VMI
│   │   ├── datavolume-cirros.yaml # DataVolume HTTP 导入
│   │   ├── vm-datavolume.yaml     # VM 引用 DataVolume
│   │   └── vm-service.yaml        # VM + Service 组合
│   └── e2e/
│       ├── production-vm.yaml     # 生产级 VM 完整定义
│       └── cloud-init-secret.yaml # SSH 密钥 Secret
├── unit/
│   └── test_helm_template.py
├── integration/
│   ├── test_vm_lifecycle.py
│   ├── test_vmi_lifecycle.py
│   ├── test_datavolume.py
│   ├── test_vm_datavolume.py
│   └── test_vm_service.py
└── e2e/
    ├── test_production_vm.py
    └── test_vm_connectivity.py
```
