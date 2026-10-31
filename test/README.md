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
| `TestToolsVersions` | 否 | CI（PR 改动 `.mise.toml`、`pyproject.toml`、`uv.lock`、`.woodpecker/ci/**` 或 `test/**`）+ 本地 |
| `TestToolsDevEnv` | 否 | 本地 + CI 镜像冒烟（校验 mise 能加载工具环境、uv 依赖可导入） |
| `TestTerraformExternal` | 否（需要网络下载 provider） | 本地 / 人工验收 |
| `TestSmoke` | 是（需要 kubeconfig 与 ingress） | 人工验收 |
| `TestArgoCDCheck` | 是（需要 kubeconfig 与 ingress） | 人工验收 |
| `TestNodeAddressing` | 是（需要 kubeconfig） | 人工验收（节点 IPv6 必须是站点 ULA） |

CI（`.woodpecker/static-checks.yaml`）只有一个 runner 内的静态检查环境，没有
homelab2 集群的 kubeconfig，因此 **`TestSmoke` 与 `TestArgoCDCheck` 属于人工验收
步骤，不在 CI 中执行**：部署后用
`mise exec -- make smoke-test` 或 `make -C test filter=ArgoCDCheck`
在能访问集群的机器上手动运行。

`TestToolsVersions` 里的版本区间现在对应 `.mise.toml`（mise 工具）、
`uv.lock`（Python 工具）与 CI 镜像基础包（git）。升级工具或重建镜像后，
用 `mise exec -- make -C test filter=Tools` 检查，失败信息会给出具体工具与区间。
