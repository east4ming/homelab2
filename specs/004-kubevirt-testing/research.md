# Research: KubeVirt 测试体系

**Created**: 2026-07-12

## R1: 测试 VM 镜像选择

**Decision**: 集成测试使用 CirrOS，端到端测试使用 Fedora 40

**Rationale**:
- CirrOS 镜像极小（~15MB），启动速度 <30s，适合集成测试中频繁创建/销毁 VM 的场景
- Fedora 40 提供完整 systemd、dnf、SSH server，适合端到端验证生产场景
- 两个镜像均在 KubeVirt 官方 examples 中有现成配置，可直接复用修改

**Alternatives considered**:
- Alpine: 也轻量，但 musl libc 与部分测试场景（apt/dnf）不兼容 → 拒绝
- Ubuntu: 镜像较大，启动慢，资源消耗高 → 拒绝（与资源上限冲突）
- 仅用 CirrOS: 无 SSH server、无包管理器，无法验证端到端场景 → 拒绝

## R2: VM 登录与命令执行方式

**Decision**: SSH 密钥注入 + Python `subprocess` 调用 `ssh` 为主，`virtctl console` + `pexpect` 为辅助验证

**Rationale**:
- SSH 方式可自动化执行命令并获取退出码，适合断言验证
- `virtctl console` 需要 expect/pexpect 交互，Python `pexpect` 库原生支持
- cloud-init NoCloud 注入 SSH 公钥是 KubeVirt 官方推荐方式（参考 `examples/vmi-nocloud.yaml`）

**Alternatives considered**:
- 仅用 `virtctl console`: 交互式终端，自动化困难 → 仅用于手动验证和 console 登录能力验证
- `sshpass` 密码登录: 需在镜像中预设密码，安全风险 → 拒绝
- Serial console + expect: 需要 guest agent，复杂度高 → 仅备用

## R3: 资源限制实现方案

**Decision**: Python 通过 subprocess 调用 `kubectl get vm -n kubevirt-test` 计数 + in-memory 槽位管理

**Rationale**:
- 简单可靠：每次创建 VM 前查询 namespace 中 Running 状态的 VM 数量
- 无需外部依赖：Python subprocess + kubectl
- 失败安全：若计数检查失败（kubectl 不可用），默认拒绝创建
- Python argparse 提供的槽位管理比文件锁更可靠

**Alternatives considered**:
- 文件锁（`/tmp/vm-count.lock`）: 进程崩溃后锁不释放 → 需要额外清理逻辑
- Kubernetes ResourceQuota: 限制整个 namespace 的 VM 数量，但无法精确控制"同时 Running"数量 → 粒度不够
- 内存变量: 仅限单进程，但 Python `run.py` 作为单一入口可管理全局状态

**Implementation**: `lib/resource_limiter.py` 提供 `check_vm_limit()` 和 `wait_for_vm_slot()` 两个函数。

## R4: 测试报告格式

**Decision**: Markdown 表格 + 摘要统计，Python 字符串模板生成

**Rationale**:
- Markdown 可在终端直接查看，也可渲染为 HTML
- CI/CD 友好：GitHub/Gitea Actions 原生支持 Markdown 渲染
- Python f-string + 模板简单直接，无需第三方报告库
- 项目已有 Markdown 大量使用（spec, plan, README）

**Format**:
```markdown
# KubeVirt 测试报告
**执行时间**: 2026-07-12 14:30:00
**总耗时**: 8m32s

## 摘要
| 类型 | 总数 | 通过 | 失败 | 跳过 |
|------|------|------|------|------|
| 单元测试 | 3 | 3 | 0 | 0 |
| 集成测试 | 7 | 6 | 1 | 0 |
| 端到端测试 | 5 | 5 | 0 | 0 |
| **合计** | **15** | **14** | **1** | **0** |

## 详细结果
| # | 用例 | 类型 | 状态 | 耗时 | 备注 |
|---|------|------|------|------|------|
| 1 | helm-template-rendering | unit | PASS | 2s | - |
...
```

**Alternatives considered**:
- JUnit XML: 更标准化，但需要 XML 生成工具，增加复杂度 → 拒绝
- HTML 报告: 需要 CSS/JS 模板，过度设计 → 拒绝
- TAP (Test Anything Protocol): 简单但可读性差 → 拒绝
- pytest-html 插件: 引入额外依赖，且样式不可控 → 拒绝

## R5: VM 重启实现

**Decision**: `virtctl restart <vm-name>`（graceful）或 `virtctl stop && virtctl start`（hard）

**Rationale**:
- `virtctl restart` 是 KubeVirt 原生命令，触发 VMI 重启
- 优雅重启（graceful）需 Guest Agent 支持，Fedora 默认安装 qemu-guest-agent
- 无 Guest Agent 时 fallback 到 hard restart（等效 stop + start）

**Alternatives considered**:
- `kubectl delete vmi && wait for vm to recreate`: VM（非 VMI）会自动重建，但需要 Running:true runStrategy
- `kubectl rollout restart`: 不适用于 VM 资源 → 拒绝

## R6: DataVolume 镜像源

**Decision**: 使用 KubeVirt 官方 cirros 镜像 URL 作为集成测试导入源；端到端测试 Fedora 使用已缓存的 containerDisk

**Rationale**:
- CirrOS: `https://download.cirros-cloud.net/0.6.3/cirros-0.6.3-x86_64-disk.img`（~15MB，导入快速）
- Fedora containerDisk: `quay.io/containerdisks/fedora:40`（使用 registry 方式导入，避免 HTTP 下载大文件）
- 两者均来自 KubeVirt 官方推荐源

**Alternatives considered**:
- 本地 HTTP 服务器提供镜像: 需要额外部署 HTTP server → 增加复杂度
- 仅用 containerDisk (registry): 无法测试 DataVolume HTTP 导入场景 → 拒绝

## R7: 测试资源 namespace 隔离

**Decision**: 所有测试资源部署在独立 namespace `kubevirt-test`

**Rationale**:
- 与 GitOps 管理的生产资源（`default`/`system-*` namespaces）完全隔离
- 清理简单：测试结束后 `kubectl delete namespace kubevirt-test --wait`
- 避免 ArgoCD 检测到不属于 ApplicationSet 的资源和产生 sync 冲突

**Caveat**: DataVolume 可能需要访问特定 StorageClass 和 StorageProfile，需确认 namespace 无额外限制。

## R8: Helm Chart 单元测试方式

**Decision**: Python subprocess 调用 `helm template` + `yaml.safe_load_all` 结构校验

**Rationale**:
- 无需部署到集群，纯本地验证
- 校验项：必要字段存在（apiVersion, kind, metadata.name）、资源数量正确、values 默认值生效
- Python `pyyaml` 可解析多文档 YAML 输出并逐资源断言

**Key assertions**:
- Chart 渲染不出错（exit code 0）
- 输出包含 CDI Operator + KubeVirt Operator + KubeVirt CR + CDI CR
- 自定义 values（如修改 storageClass）正确传递到渲染输出

## R9: Python 依赖与包管理

**Decision**: 使用 `uv` 管理 Python 依赖，不依赖 flake.nix

**Rationale**:
- `uv` 是用户指定的包管理工具，符合项目开发流程
- `pyproject.toml` 声明所有依赖，`uv sync` 一键安装
- 测试目录作为独立 Python 项目，不污染全局环境

**核心依赖**:
- `pytest` — 测试框架
- `pyyaml` — YAML 解析（helm template 输出 + manifest 加载）
- `kubernetes` — K8s Python client（可选，用于复杂 API 操作）
- `pexpect` — SSH/console 交互
- `rich` — 终端美化输出

**pyproject.toml 结构**:
```toml
[project]
name = "kubevirt-tests"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "pyyaml>=6.0",
    "kubernetes>=30.0",
    "pexpect>=4.9",
    "rich>=13.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "ruff>=0.4",
]
```
