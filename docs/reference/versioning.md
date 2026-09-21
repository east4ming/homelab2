# 版本管理

本页定义 homelab2 仓库的版本号体系，覆盖 git、Gitea 与 GitHub 三处。

## 为什么用 CalVer 而不是 SemVer

本仓库的产物是**集群状态**，不是可以被外部依赖的库：

- 没有 API 消费者，SemVer 的 MAJOR / MINOR / PATCH 语义在这里没有可判定的依据，最终只能靠主观感觉，必然漂移。
- `master` 是部署分支，ArgoCD ApplicationSet 以 `refs/heads/master` 为 `targetRevision`，并开启 `automated` + `selfHeal` + `prune`（见 `system/argocd/values.yaml`）。**每次合并即上线**，所以标签不是发布门禁。
- 集群已连续生产运行 600+ 天。标签的首要用途是**定位一个已知良好的状态以便回滚**，其次才是变更索引。

因此版本号表达的是「某个时间点的集群状态快照」，用日期编号最贴切。

## 版本号格式

```
vYYYY.MM.DD          # 当日第 1 个状态快照
vYYYY.MM.DD.N        # 当日第 N 个状态快照（N 从 2 开始，为 1 时省略）
```

- 例：`v2026.09.21`、`v2026.09.21.2`。
- 日期取 `Asia/Shanghai`（与仓库提交历史的时区一致），月、日零填充，便于排序。
- 一律使用 **annotated tag**（`git tag -a`），不打轻量标签。
- **已推送的标签永不删除、永不移动。** 打错了也只追加一个新标签。

## 历史遗留标识

以下标识保留原样，不改写：

| 标识 | 说明 |
| --- | --- |
| `v1.0.0` | 2024-11-27 创建的 annotated tag（"Prod Ready"），fork 前遗留，不适用本版式 |
| `v2025.02.16`、`v2025.02.17` | [Changelog](changelog.md) 中的日期条目，**从未创建过对应的 git tag** |

fork 自上游 khuedoan/homelab 的 `0.0.1-alpha` … `0.0.8` 记录，归入 changelog 的「上游历史（fork 前）」分区。

## 分支模型

采用简化的 GitHub Flow：

| 分支 | 用途 |
| --- | --- |
| `master` | 唯一的长期分支，也是 ArgoCD 部署分支。合入即上线 |
| `<nnn>-<slug>` | Spec Kit 主题分支，例如 `005-smartctl-monitoring` |
| `renovate/*` | Renovate 自动依赖更新分支 |

规则：

- 所有变更经主题分支 → Pull Request → `master`，不直接推 `master`。
- 合并后删除主题分支。当前仓库存在 51 个已合并但未删除的远端主题分支，属历史欠账，待清理。
- 紧急回退同样走分支 + PR，见下文「回滚」。

## 提交信息规范

格式为 [Conventional Commits](https://www.conventionalcommits.org/)：

```
<type>(<scope>): <subject>
```

- `type` 白名单：`feat` `fix` `docs` `chore` `refactor` `perf` `build` `test` `ci` `revert`。
- `scope` 建议填写模块名，如 `lobe-chat`、`cilium`、`metal/roles/tailscale`。
- `subject` 可以使用中文（见项目 Constitution 原则 V「优先使用中文」）。
- 破坏性变更：在 `type` 后加 `!`，或在页脚写 `BREAKING CHANGE: ...`。

禁止的写法（仓库历史中确实出现过，不要沿用）：

- `[Spec Kit] Add tasks` — Spec Kit 产出的提交同样使用上面的白名单前缀，例如 `docs(005): 添加任务清单`。
- `update`、`fixed`、`Fix` 这类没有类型的提交。
- 直接以整段中文叙述作为标题。

## 打标签

前置检查：

```sh
git checkout master
git pull --ff-only origin master
test -z "$(git status --porcelain)"   # 工作区干净
git fetch origin --tags
```

创建并推送标签：

```sh
git tag -a v2026.09.21 -m "状态快照：<一句话说明>"
git push origin master v2026.09.21
```

!!! warning "两个远端，一次推送"

    本仓库的 `origin` 配置了**两条** `remote.origin.url`：

    - `https://git.west-beta.ts.net/ops/homelab2.git`（Gitea，权威）
    - `https://github.com/east4ming/homelab2.git`（GitHub，镜像）

    一次 `git push` 会按顺序推往两处。**任意一处失败，整条命令以 128 退出，但另一处可能已经推送成功。**
    所以推送后必须双侧复核，不能只看退出码：

    ```sh
    git ls-remote --tags origin
    git ls-remote --tags https://github.com/east4ming/homelab2.git
    ```

    详见 [同时使用 GitHub 和 Gitea](../how-to-guides/use-both-github-and-gitea.md)。

## 发布 Release

Gitea 为权威来源，GitHub 为镜像，两侧都建 Release：

```sh
# Gitea（权威）
tea releases create -r ops/homelab2 --tag v2026.09.21 \
  --title v2026.09.21 --note-file /tmp/release-note.md

# GitHub（镜像）
gh release create v2026.09.21 --verify-tag \
  --title v2026.09.21 --notes-file /tmp/release-note.md
```

- `--verify-tag` 不可省略：它阻止 `gh` 在标签不存在时自行从默认分支创建标签。
- Release 正文与 changelog 中同一标签的条目保持一致。
- 若某侧 Release 已存在，改用 `tea releases edit` / `gh release edit`，不要重复创建。

## Changelog 规范

- 唯一位置：[docs/reference/changelog.md](changelog.md)，新条目置顶，标题即标签名。
- 内容从提交历史归并：

  ```sh
  git log <prev-tag>..<tag> --no-merges --format='%s'
  ```

  按 `feat` / `fix` / `refactor` / `perf` / `build` / `docs` / `chore` 分组。
- **不为每一个 Renovate 合并单独记录**，依赖更新聚合进对应的状态快照条目。
- 条目内的每一条都必须能追溯到真实提交，不要凭印象写。

## 回滚

- 查看某个状态：`git checkout v2026.09.21`（只读，看完 `git switch -` 返回）。
- 让 ArgoCD 同步到某个状态：ArgoCD UI → Application → **Sync** → 勾选 **Revision** 并填入标签或 commit SHA。
- 需要撤销已上线的改动时，**用 `git revert` 产生一个新的提交**，不要对 `master` 做 `reset --hard` 或强推——`master` 是部署分支，重写历史会让 ArgoCD 与两个远端的状态失去一致性。

## 已知问题：GitHub 侧推送失败

若 `git push` 报 `无法读取远程仓库` 或整体退出 128，通常是本机 SSH 全线不可用导致的（GitHub 远端曾配置为 SSH）。
症状、成因与规避方案见 [同时使用 GitHub 和 Gitea](../how-to-guides/use-both-github-and-gitea.md)。
