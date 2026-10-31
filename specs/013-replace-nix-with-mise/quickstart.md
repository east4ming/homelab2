# 快速验证：移除 Nix

> 在实施分支上按顺序执行。所有命令在仓库根目录运行。

## 0. 记录基线（迁移前，仅一次）

1. 打开 Woodpecker，取最近 5 次成功的 PR pipeline（`static-checks` + `helm-diff`），记录总耗时（分钟）。
2. 保存到本文件或 PR 描述，作为 SC-005 的对比基线。

## 1. 本地环境（必须没有 Nix）

前置：Ubuntu 24.04+、已安装 mise 与 uv、Docker Engine 运行中。

```sh
mise trust
mise run setup                      # 安装 mise 工具 + uv sync
mise exec -- helm version --short    # 任取一个工具验证
make -C test filter=Tools           # TestToolsVersions + TestToolsDevEnv
pre-commit run --all-files          # 含 no-nix 门禁
uv run --frozen mkdocs build --strict
```

预期：全部退出码 0；`which nix` 不存在或未被调用；`TestToolsDevEnv` 通过。

额外检查：

```sh
git ls-files | grep -E '(flake\.(nix|lock)|\.envrc|run_nix_develop\.sh)$'   # 无输出
git grep -n -i -w nix -- ':!docs/reference/changelog.md' \
  ':!docs/reference/architecture/decision-records.md' ':!specs/**' \
  ':!.pre-commit-config.yaml' ':!scripts/check-no-nix'                       # 无输出
```

`bin/kanidm --help`（可选）：需 Docker；服务器端保持 1.3.3，不升级。

## 2. 镜像本地冒烟

```sh
docker build -f .woodpecker/ci/Dockerfile -t homelab2-ci:local .
docker run --rm -e MISE_TRUSTED_CONFIG_PATHS=/woodpecker \
  -v "$PWD:/woodpecker/src" -w /woodpecker/src homelab2-ci:local \
  sh -c 'make -C test filter=ToolsVersions && pre-commit run --all-files'
```

预期：9 个工具版本通过；pre-commit 全部 hook（含 `no-nix`）通过。

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

### 3.3 PR 验证

1. 推送分支并创建 PR（目标 `master`）。
2. 确认两条 pipeline 的步骤镜像都是 `ghcr.io/east4ming/homelab2-ci:latest` 且 `pull: true`；pipeline 中没有镜像构建步骤。
3. 确认 `static-checks` 的 tools-versions 与 pre-commit 检查项与迁移前一致；`helm-diff` 对改动 stack 输出 diff。
4. 记录冷启动耗时，与第 0 步基线比较，应 ≤ 基线 × 1.2。
5. 构造一个包含 `nixos/nix` 或 `flake.nix` 的测试 PR，确认 `no-nix` hook 失败并指出文件/行号。
6. 若 PR 改动 `.mise.toml`、`pyproject.toml`、`uv.lock` 或 `.woodpecker/ci/Dockerfile`：合并前必须重跑 `scripts/build-ci-image`，并让 CI 在重建后的镜像上通过。

## 4. 回滚

- 代码回滚：`git revert` 本分支合并提交；旧 Nix 文件仍在历史中，可临时恢复用于救急（不作为长期方案）。
- 镜像：`latest` 是可变指针；回滚时把旧 `sha-<short>` 重新 tag 为 `latest` 并推送，或从旧提交重跑 `scripts/build-ci-image`。
- 集群：本特性不改集群资源，无需回滚部署。

## 5. 验收映射

| 标准 | 验证 |
| --- | --- |
| SC-001 | 第 1 节全部通过，记录 setup 耗时 ≤ 15 分钟 |
| SC-002 | 第 1 节 grep 无输出 |
| SC-003 | 第 3 节 pipeline 通过；无 `nixos/nix`/`nixery.dev` 镜像 |
| SC-004 | 同一 PR 中本地与 CI 的 `ToolsVersions` 都通过 |
| SC-005 | 冷启动耗时 ≤ 基线 × 1.2 |
| SC-006 | 第 1 节无 `nix` 命令；文档无安装 Nix 步骤 |
| SC-007 | 第 3 节测试 PR 被 `no-nix` 阻断 |
| SC-008 | `uv sync --frozen --all-groups` 在干净环境成功；`uv.lock` 已入库 |
