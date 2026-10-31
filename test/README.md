# Tests

在仓库根目录、进入 mise 环境后运行：

```sh
mise run setup
make -C test filter=<regex>
```

未激活 mise 时使用：

```sh
mise exec -- make -C test filter=<regex>
```

`filter` 会直接传给 `go test -run`，是匹配测试函数名的正则（`filter=Tools`
匹配 `TestToolsVersions` 与 `TestToolsDevEnv`）。

## 由谁运行

| 测试 | 需要集群 | 运行方式 |
| --- | --- | --- |
| `TestToolsVersions` | 否 | 本地（CI 镜像不含 Go，PR 中不再执行） |
| `TestToolsDevEnv` | 否 | 本地（校验 mise 能加载工具环境、uv 依赖可导入） |
| `TestTerraformExternal` | 否（需要网络下载 provider） | 本地 / 人工验收 |
| `TestSmoke` | 是（需要 kubeconfig 与 ingress） | 人工验收 |
| `TestArgoCDCheck` | 是（需要 kubeconfig 与 ingress） | 人工验收 |
| `TestNodeAddressing` | 是（需要 kubeconfig） | 人工验收（节点 IPv6 必须是站点 ULA） |

CI（`.woodpecker/static-checks.yaml`）只运行 pre-commit，并显式
`SKIP=tofu_fmt`：Go/ansible/opentofu 已从 CI 镜像移除，因此 Go 测试与
`tofu_fmt` 只在本地执行。CI 也没有 homelab2 集群的 kubeconfig，因此
**`TestSmoke` 与 `TestArgoCDCheck` 属于人工验收步骤，不在 CI 中执行**：部署后用
`mise exec -- make smoke-test` 或 `make -C test filter=ArgoCDCheck`
在能访问集群的机器上手动运行。

`TestToolsVersions` 里的版本区间现在对应 `.mise.toml`（mise 工具）、
`uv.lock`（Python 工具）与本地操作系统包（git）。升级工具或修改环境后，
用 `mise exec -- make -C test filter=Tools` 检查，失败信息会给出具体工具与区间。
