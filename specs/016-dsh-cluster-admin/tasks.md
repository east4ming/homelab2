# Tasks: DSH 在集群内以 cluster-admin 管理集群

**Input**: Design documents from `specs/016-dsh-cluster-admin/`
**Prerequisites**: [plan.md](plan.md)（必需）、[spec.md](spec.md)（必需）

**Organization**: 按交付链路分组；发布任务按 `docs/reference/versioning.md`。

## Phase 1: 实现

- [x] T001 新增 `apps/deepseek-harness/templates/rbac.yaml`：`ServiceAccount` + 指向内置 `cluster-admin` 的 `ClusterRoleBinding`
- [x] T002 修改 `apps/deepseek-harness/templates/statefulset.yaml`：`serviceAccountName`、`automountServiceAccountToken: true`
- [x] T003 修改 `apps/deepseek-harness/Chart.yaml`：`version: 0.1.29-homelab.2`
- [x] T004 修改 `apps/deepseek-harness/files/install-tools.sh`：mise 安装与校验清单加入 `kubectl`
- [x] T005 更新 `apps/deepseek-harness/README.md`：差异表、集群权限章节（验证命令/安全边界/收回方法）、工具清单、已知限制

## Phase 2: 本地验证

- [x] T006 `helm lint apps/deepseek-harness` 通过
- [x] T007 `helm template` + `yq` 断言：1 SA、1 CRB（`roleRef.name=cluster-admin`）、Pod 身份字段正确
- [x] T008 `pre-commit run --all-files` 通过
- [x] T009 `mkdocs build --strict` 通过

## Phase 3: 文档与版本

- [x] T010 `docs/reference/versioning.md`：Release 命令改为 `gt release create <tag> -R ...`，说明与 `gh` 的差异
- [x] T011 `specs/015-deepseek-harness-helm/{quickstart,plan,tasks}.md`：可执行命令改 `gt`；历史任务项注明当时的 `tea`
- [x] T012 `specs/016-dsh-cluster-admin/{spec,plan,tasks}.md`
- [x] T013 `AGENTS.md` 当前 Plan 指向 `specs/016-dsh-cluster-admin/plan.md`
- [x] T014 `docs/reference/changelog.md` 新增 `v2026.11.13` 条目

## Phase 4: 提交与上线

- [x] T015 主题分支 `016-dsh-cluster-admin` + Conventional Commits
- [x] T016 推送分支并在 Gitea 开 PR、合入 `master`
- [ ] T017 ArgoCD 同步后线上验收：`kubectl auth can-i '*' '*' --all-namespaces`、`kubectl get nodes`、
      维护者机器 `kubectl exec` 同一身份

## Phase 5: 发布

- [ ] T018 打 annotated tag `v2026.11.13`，推送 Gitea + GitHub 并双侧复核
- [ ] T019 Gitea（`gt release create`）与 GitHub（`gh release create --verify-tag`）创建 Release，正文与
      Changelog 一致
