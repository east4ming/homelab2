# Tests

Run everything from the repository root inside the Nix devShell:

```sh
nix develop --command make -C test filter=<regex>
```

`filter` is passed straight to `go test -run`, so it is a regular expression
matched against the test function name (`filter=Tools` matches
`TestToolsVersions` and `TestToolsNixShell`).

## 由谁运行

| 测试 | 需要集群 | 运行方式 |
| --- | --- | --- |
| `TestToolsVersions` | 否 | CI（PR 改动 `flake.*` 或 `test/**`）+ 本地 |
| `TestToolsNixShell` | 否 | 本地（校验 devShell 能求值并进入） |
| `TestTerraformExternal` | 否（需要网络下载 provider） | 本地 / 人工验收 |
| `TestSmoke` | 是（需要 kubeconfig 与 ingress） | 人工验收 |
| `TestArgoCDCheck` | 是（需要 kubeconfig 与 ingress） | 人工验收 |
| `TestNodeAddressing` | 是（需要 kubeconfig） | 人工验收（节点 IPv6 必须是站点 ULA） |

CI（`.woodpecker/static-checks.yaml`）只有一个 runner 内的静态检查环境，没有
homelab2 集群的 kubeconfig，因此 **`TestSmoke` 与 `TestArgoCDCheck` 属于人工验收
步骤，不在 CI 中执行**：部署后用
`nix develop --command make smoke-test` 或 `make -C test filter=ArgoCDCheck`
在能访问集群的机器上手动运行。

`TestToolsVersions` 里的版本区间对应 `flake.nix` 所钉的 nixpkgs 版本
（当前 nixos-26.05）。升级 `flake.lock` 后需要同步更新这些区间：在 devShell 里
用 `nix eval --impure --expr` 读出各工具版本，或直接跑该测试看失败信息。
