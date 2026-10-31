# 快速验证：移除 Nix

> 在实施分支上按顺序执行。所有命令在仓库根目录运行。

## 0. 记录基线（迁移前，仅一次）

1. 打开 Woodpecker，取最近 5 次成功的 PR pipeline（`static-checks` + `helm-diff`），记录总耗时（分钟）。
2. 保存到本文件或 PR 描述，作为 SC-005 的对比基线。

2026-10-31 从 Woodpecker API（`/api/repos/1/pipelines`）取得的最近 5 次成功 `pull_request` pipeline：

| Pipeline | 耗时（秒） | 开始时间 |
| --- | --- | --- |
| #2698 | 754 | 2026-10-31 09:03 |
| #2694 | 1174 | 2026-10-30 12:43 |
| #2690 | 226 | 2026-10-30 09:03 |
| #2681 | 1343 | 2026-10-29 09:04 |
| #2680 | 1284 | 2026-10-29 09:04 |

- 中位数：**1174s**；SC-005 目标：迁移后冷启动 ≤ 1174 × 1.2 ≈ **1409s**。
- 宿主机前置（2026-10-31 确认）：mise 2026.10.22、uv 0.13.6、buildx v0.38.1、`ghcr.io` 已登录。

## 1. 本地环境（必须没有 Nix）

前置：Ubuntu 24.04+、已安装 mise 与 uv、Docker Engine 运行中。

```sh
mise trust
mise run setup                      # 安装 mise 工具 + uv sync
mise exec -- helm version --short    # 任取一个工具验证
make -C test filter=Tools           # TestToolsVersions + TestToolsDevEnv
pre-commit run --all-files          # 含防回潮门禁
uv run --frozen mkdocs build --strict
```

预期：全部退出码 0；`which nix` 不存在或未被调用；`TestToolsDevEnv` 通过。

额外检查（门禁脚本即 SC-002 的判定器；历史记录与 `specs/` 除外）：

```sh
scripts/check-no-nix                # 无输出，退出码 0
git ls-files | grep -E '(flake\.(nix|lock)|\.envrc|run_nix_develop\.sh)$'   # 无输出
```

说明：直接 `git grep -i -w nix` 会命中 `.specify/feature.json`、`AGENTS.md` 中的
`specs/013-replace-nix-with-mise` 路径名与门禁自身名字，这些属于特性元数据，不是 Nix
工具引用。

`bin/kanidm --help`（可选）：需 Docker；服务器端保持 1.3.3，不升级。

## 2. 镜像本地冒烟

```sh
docker build -f .woodpecker/ci/Dockerfile -t homelab2-ci:local .
docker run --rm -e MISE_TRUSTED_CONFIG_PATHS=/woodpecker -e SKIP=tofu_fmt \
  -v "$PWD:/woodpecker/src" -w /woodpecker/src homelab2-ci:local \
  sh -c 'helm version --short && dyff version && shellcheck --version >/dev/null && pre-commit run --all-files'
```

预期：helm/dyff/shellcheck/pre-commit 可用；pre-commit hooks（跳过 `tofu_fmt`，含 `no-nix`）通过；
镜像内不存在 go/opentofu/ansible/kubectl/docker。

## 3. CI 镜像与 PR 验证

### 3.1 GHCR 凭据（宿主机，一次性）

当前 `gh` 登录账号 `east4ming` 的 token scope 不含 `write:packages`，需先补：

```sh
gh auth refresh -h github.com -s write:packages,read:packages
gh auth token        # 输出作为 PAT 使用（不要提交到仓库）
```

或在 <https://github.com/settings/tokens/new> 创建 classic PAT，勾选 `write:packages`、`read:packages`。然后：

```sh
docker login ghcr.io -u east4ming    # 密码处粘贴 PAT
```

### 3.2 构建并推送镜像（宿主机）

```sh
scripts/build-ci-image
```

预期：推送 `ghcr.io/east4ming/homelab2-ci:latest` 与 `:sha-<short>`，并打印 digest（记录到 PR 描述）。首次推送后把 package 设为 public：GitHub → Packages → `homelab2-ci` → Settings → Change visibility。

2026-10-31 构建记录：

- 首版全量镜像（argocd/k9s/k3d/neovim + docs 组）3.57GB，k8s agent 拉取超时，pipeline #2701 失败
- 精简镜像（CI 工具子集 + uv `ci`/`scripts` 组）：digest `sha256:a4ab2fa0b703230722470f9ec673f53e5270f7a4302a14b61db0e9d825c5e55b`，tags `latest`、`sha-776ad98e`
- 优化镜像（ansible-core + `ci` 组、BuildKit cache mount，不把 mise/uv 缓存写入层）：digest `sha256:d5bbb18d642c95da9df8cfc0c9ca4967c836b06e68f044f215895da7b2358d9d`，tags `latest`、`sha-ae8f935a`；`docker image inspect` 解压大小 **1.68GB**（上一版 2.36GB）
- 极简镜像（移除 go/opentofu/ansible/kubectl/kustomize/gotestsum/docker CLI；只留 helm/dyff/shellcheck + pre-commit）：digest `sha256:af68392e106d46374c07e5c7523d004fea4479b759e6514291986be25379019c`，tags `latest`、`sha-728dabba`；解压大小 **842MB**
- 匿名 `docker pull` 通过（package 已 public）
- 镜像内 `SKIP=tofu_fmt pre-commit run --all-files` 通过（Go/ansible/opentofu 已不在镜像内）
- `scripts/build-ci-image` 要求工作区干净；后续仅文档提交不会改变镜像内容，但 `sha-<short>` 会落后于 `HEAD`

### 3.3 PR 验证

1. 推送分支并创建 PR（目标 `master`）。
2. 确认两条 pipeline 的步骤镜像都是 `ghcr.io/east4ming/homelab2-ci:latest` 且 `pull: true`；pipeline 中没有镜像构建步骤。
3. 确认 `static-checks` 只有 pre-commit 步骤且显式 `SKIP=tofu_fmt`；`helm-diff` 对改动 stack 输出 diff。工具版本测试只在本地运行。
4. 记录冷启动耗时，与第 0 步基线比较，应 ≤ 基线 × 1.2。
5. 构造一个包含 `nixos/nix` 或 `flake.nix` 的测试 PR，确认 `no-nix` hook 失败并指出文件/行号。
6. 若 PR 改动 `.mise.toml`、`pyproject.toml`、`uv.lock` 或 `.woodpecker/ci/Dockerfile`：合并前必须重跑 `scripts/build-ci-image`，并让 CI 在重建后的镜像上通过。

2026-10-31 结果（PR #600）：

- pipeline #2702 **success**；总耗时 423s（基线 1174s，SC-005 通过）
- 优化镜像后 pipeline #2704 **success**；总耗时 569s（仍 ≤ 基线 ×1.2）
- `static-checks`：只有 pre-commit（`SKIP=tofu_fmt`）并成功；pipeline 中无镜像构建步骤
- `helm-diff`：三个 matrix workflow 均只执行 clone；`diff` 步骤因改动不涉及 `system/`/`platform/`/`apps/` 被 path 过滤跳过（符合预期）

## 4. 回滚

- 代码回滚：`git revert` 本分支合并提交；旧 Nix 文件仍在历史中，可临时恢复用于救急（不作为长期方案）。
- 镜像：`latest` 是可变指针；回滚时把旧 `sha-<short>` 重新 tag 为 `latest` 并推送，或从旧提交重跑 `scripts/build-ci-image`。
- 集群：本特性不改集群资源，无需回滚部署。

## 5. 验收映射

| 标准 | 验证 | 2026-10-31 状态 |
| --- | --- | --- |
| SC-001 | 第 1 节全部通过，记录 setup 耗时 ≤ 15 分钟 | 本地通过：首次工具安装约 113s，`TestToolsVersions`/`TestToolsDevEnv`、pre-commit、`mkdocs --strict` 均通过 |
| SC-002 | `scripts/check-no-nix` 无命中（历史记录与 `specs/` 除外） | 通过 |
| SC-003 | 第 3 节 pipeline 通过；无 `nixos/nix`/`nixery.dev` 镜像；static-checks 只跑 pre-commit（跳过 `tofu_fmt`） | 通过：#2702/#2704/#2706 success，步骤镜像仅 GHCR 自建镜像 |
| SC-004 | 本地工具版本检查通过；CI 只校验 pre-commit 工具链 | 通过：本地 `ToolsVersions`；CI 不再运行 Go 版本测试 |
| SC-005 | 冷启动耗时 ≤ 基线 × 1.2 | 通过：423s ≤ 1409s |
| SC-006 | 第 1 节无 `nix` 命令；文档无安装步骤 | 通过（门禁扫描） |
| SC-007 | 测试 PR 被门禁阻断 | 通过（本地 + 镜像内验证违规文件被 `no-nix` 拒绝；未单独构造失败 PR） |
| SC-008 | `uv sync --frozen --all-groups` 在干净环境成功；`uv.lock` 已入库 | 通过 |
