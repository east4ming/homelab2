# 契约：本地开发环境（mise + uv）

## 适用对象

维护者与贡献者在 Linux x86_64（Ubuntu 24.04+/26.04）上的本地开发环境。macOS 不在验收范围。

## 前置条件

| 依赖 | 最低版本 | 检查方式 |
| --- | --- | --- |
| mise | 2026.10.22 | `mise --version` |
| uv | 0.13.6 | `uv --version` |
| git | 2.47 | `git --version` |
| make | 发行版默认 | `make --version` |
| Docker Engine + Compose v2 | 29.x / v2 | `docker --version`、`docker compose version` |
| 其他系统包 | 发行版默认 | `ip`、`ssh`、`xorriso`、`7z`、`qrencode`、`wg`、`locale` |

## 命令契约

| 命令 | 行为 | 成功条件 |
| --- | --- | --- |
| `mise trust` | 信任仓库内 `.mise.toml` | 退出码 0；只需一次 |
| `mise run setup` | 安装 `.mise.toml` 中全部工具，并执行 `uv sync --all-groups` | 退出码 0；重复执行幂等 |
| `mise exec -- <command>` / 激活后的 shell | 以项目工具环境执行命令 | `PATH` 含 mise 工具与 `.venv/bin` |
| `make -C test filter=Tools` | 运行 `TestToolsVersions` 与 `TestToolsDevEnv` | 退出码 0 |
| `pre-commit run --all-files` | 运行全部质量门禁（含 `no-nix`） | 退出码 0 |
| `uv run --frozen mkdocs build --strict` | 构建文档 | 退出码 0，生成 `site/` |
| `bin/kanidm --help`（可选） | 通过 `kanidm/tools:1.11.2` 容器调用 CLI | 退出码 0；需要 Docker |

## 保证

- 仓库内不存在 `flake.nix`、`flake.lock`、`.envrc`、`run_nix_develop.sh`，上述命令不调用 `nix`。
- 非 Python 工具版本由 `.mise.toml` 精确固定；Python 依赖由 `uv.lock` 锁定且入库。
- 系统前置条件缺失时，命令以非零退出码失败并指出缺失项；不得回退到 Nix。
- `scripts/onboard-user` 等既有脚本的参数与输出保持不变。

## 环境变量（由 `.mise.toml` / 镜像提供）

| 变量 | 来源 | 用途 |
| --- | --- | --- |
| `PATH` | `.mise.toml` `[env] _.path = ["bin", ".venv/bin"]` | 暴露 `bin/kanidm`、uv 工具入口 |
| `MISE_TRUSTED_CONFIG_PATHS` | CI 镜像 | 允许非交互环境加载项目配置 |
| `UV_PROJECT_ENVIRONMENT` | CI 镜像 | 固定使用镜像内 `/opt/venv` |
