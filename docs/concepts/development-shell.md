# 开发环境

本仓库的本地开发环境由两部分组成：

- **mise**：管理 Python 以外的工具与版本（`.mise.toml`）。
- **uv**：管理 Python 解释器、依赖与 Python 编写的 CLI 工具（`pyproject.toml` + `uv.lock`）。

不再依赖额外的开发 shell 或包管理器。

## 前置条件

- Linux x86_64（Ubuntu 24.04+/26.04）。
- [mise](https://mise.jdx.dev) >= 2026.10.22 与 [uv](https://docs.astral.sh/uv/) >= 0.13.6。
- Docker Engine 29.x（含 Compose v2 插件）。
- 系统包（由操作系统提供，不由 mise/uv 管理）：

```sh
sudo apt install -y git make bmake diffutils docker.io docker-compose-v2 \
  iproute2 locales openssh-client xorriso 7zip qrencode wireguard-tools
```

安装 mise 与 uv（若尚未安装）：

```sh
curl https://mise.run | sh
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## 准备环境

```sh
cd homelab2
mise trust
mise run setup
```

`mise run setup` 会安装 `.mise.toml` 中固定的全部工具，并执行
`uv sync --all-groups` 创建 `.venv`。

激活 mise（每个 shell 配置一次）后，进入仓库即可直接使用这些工具：

```sh
echo 'eval "$(mise activate bash)"' >> ~/.bashrc   # zsh 用 mise activate zsh
```

不激活时也可以显式执行：

```sh
mise exec -- helm version --short
mise exec -- make -C test filter=Tools
```

## 验证

```sh
make -C test filter=Tools          # 工具版本 + mise/uv 环境检查
pre-commit run --all-files         # 含防回潮门禁
uv run --frozen mkdocs build --strict
```

## 工具来源

- **mise**（`.mise.toml`，精确版本）：argocd、dyff、go、gotestsum、helm、jq、k3d、k9s、kubectl、kustomize、neovim、opentofu、shellcheck。
- **uv**（`pyproject.toml` groups）：
  - `scripts`：脚本运行依赖（jinja2、kubernetes、netaddr、pexpect、requests、rich）。
  - `dev`：ansible、ansible-lint、pre-commit、yamllint。
  - `docs`：mkdocs 及文档构建依赖（版本来自原 `requirements.txt`，现已锁定在 `uv.lock`）。
- **kanidm**：`bin/kanidm` 通过官方 `kanidm/tools:1.11.2` 容器提供；服务器端仍为 1.3.3，本仓库不升级服务端。
- **操作系统**：Docker、git、make、iproute2、locales、openssh-client、xorriso、7zip、qrencode、wireguard-tools。

## 添加或升级工具

```sh
mise use <tool>@<version>                 # 更新 .mise.toml
uv add --group <scripts|dev|docs> <pkg>   # 更新 pyproject.toml + uv.lock
```

改完版本先本地跑 `make -C test filter=Tools`；CI 镜像不会自动重建，需要按
`specs/013-replace-nix-with-mise/quickstart.md` 重跑 `scripts/build-ci-image`。
