# Tasks: Raw Manifests to Helm Chart Migration

**Input**: Design documents from `/specs/002-helm-chart-migration/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md

**Tests**: 不需要新增测试代码。通过 `helm lint` + `helm template` + `dyff` 对比即可验证。

**Organization**: 任务按用户故事分组，每个故事可独立实现和验证。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可并行执行（操作不同文件，无依赖）
- **[Story]**: 所属用户故事（US1, US2, US3）
- 每个任务包含具体文件路径

---

## Phase 1: Setup（共享基础设施）

**Purpose**: 创建 Helm chart 结构文件（Chart.yaml、values.yaml、.helmignore）

- [ ] T001 [P] 创建 rsshub Helm chart 元数据文件 `apps/rsshub/Chart.yaml`（name: rsshub, apiVersion: v2, version: 0.1.0）
- [ ] T002 [P] 创建 rsshub 空 values.yaml `apps/rsshub/values.yaml`
- [ ] T003 [P] 创建 rsshub .helmignore `apps/rsshub/.helmignore`（排除 *.sh、README*、secret-*.yaml、.gitignore）
- [ ] T004 [P] 创建 lobe-chat Helm chart 元数据文件 `apps/lobe-chat/Chart.yaml`（name: lobe-chat, apiVersion: v2, version: 0.1.0）
- [ ] T005 [P] 创建 lobe-chat 空 values.yaml `apps/lobe-chat/values.yaml`
- [ ] T006 [P] 创建 lobe-chat .helmignore `apps/lobe-chat/.helmignore`（排除 *.example、*.sh、README*、docs/、examples/、CLAUDE.md）

---

## Phase 2: Foundational（阻塞性前置任务）

**Purpose**: 修复 CI helm-diff 脚本，使其在目标分支缺少 Chart.yaml 时不崩溃

**⚠️ CRITICAL**: 必须完成此阶段，否则 PR CI 会因目标分支（master）渲染失败而无法通过

- [ ] T007 修复 `scripts/helm-diff` 中的 `render_helm_chart` 函数：当 `Chart.yaml` 不存在时跳过渲染而非报错退出

**Checkpoint**: CI 基础设施就绪——可以开始用户故事实现

---

## Phase 3: User Story 1 - rsshub Helm Chart 转换 (Priority: P1) 🎯 MVP

**Goal**: 将 rsshub 的 22 个原始 YAML manifests 转换为 Helm chart，`helm template` 能成功渲染

**Independent Test**: `helm template --namespace rsshub rsshub apps/rsshub` 退出码 0，渲染出 22 个 Kubernetes 资源

### Implementation for User Story 1

- [ ] T008 [US1] 创建 `apps/rsshub/templates/` 目录
- [ ] T009 [P] [US1] 移入 Namespace: 移动 `apps/rsshub/ns.yaml` → `apps/rsshub/templates/ns.yaml`（删除原文件，内容不变）
- [ ] T010 [P] [US1] 移入 Deployments (1/4): 移动 `apps/rsshub/deploy-rsshub.yaml` → `apps/rsshub/templates/deploy-rsshub.yaml`
- [ ] T011 [P] [US1] 移入 Deployments (2/4): 移动 `apps/rsshub/deploy-browserless.yaml` → `apps/rsshub/templates/deploy-browserless.yaml`
- [ ] T012 [P] [US1] 移入 Deployments (3/4): 移动 `apps/rsshub/deploy-database-postgres.yaml` → `apps/rsshub/templates/deploy-database-postgres.yaml`
- [ ] T013 [P] [US1] 移入 Deployments (4/4): 移动 `apps/rsshub/deploy-redis.yaml` → `apps/rsshub/templates/deploy-redis.yaml`
- [ ] T014 [P] [US1] 移入 Deployments (5/7): 移动 `apps/rsshub/deploy-service-mercury.yaml` → `apps/rsshub/templates/deploy-service-mercury.yaml`
- [ ] T015 [P] [US1] 移入 Deployments (6/7): 移动 `apps/rsshub/deploy-service-opencc.yaml` → `apps/rsshub/templates/deploy-service-opencc.yaml`
- [ ] T016 [P] [US1] 移入 Deployments (7/7): 移动 `apps/rsshub/deploy-service-rss.yaml` → `apps/rsshub/templates/deploy-service-rss.yaml`
- [ ] T017 [P] [US1] 移入 Services (1/8): 移动 `apps/rsshub/service-rsshub.yaml` → `apps/rsshub/templates/service-rsshub.yaml`
- [ ] T018 [P] [US1] 移入 Services (2/8): 移动 `apps/rsshub/service-browserless.yaml` → `apps/rsshub/templates/service-browserless.yaml`
- [ ] T019 [P] [US1] 移入 Services (3/8): 移动 `apps/rsshub/service-database-postgres.yaml` → `apps/rsshub/templates/service-database-postgres.yaml`
- [ ] T020 [P] [US1] 移入 Services (4/8): 移动 `apps/rsshub/service-database-postgres-np.yaml` → `apps/rsshub/templates/service-database-postgres-np.yaml`
- [ ] T021 [P] [US1] 移入 Services (5/8): 移动 `apps/rsshub/service-redis.yaml` → `apps/rsshub/templates/service-redis.yaml`
- [ ] T022 [P] [US1] 移入 Services (6/8): 移动 `apps/rsshub/service-external-rsshub.yaml` → `apps/rsshub/templates/service-external-rsshub.yaml`
- [ ] T023 [P] [US1] 移入 Services (7/8): 移动 `apps/rsshub/service-service-mercury.yaml` → `apps/rsshub/templates/service-service-mercury.yaml`
- [ ] T024 [P] [US1] 移入 Services (8/8): 移动 `apps/rsshub/service-service-opencc.yaml` → `apps/rsshub/templates/service-service-opencc.yaml`
- [ ] T025 [P] [US1] 移入最后一个 Service: 移动 `apps/rsshub/service-service-rss.yaml` → `apps/rsshub/templates/service-service-rss.yaml`
- [ ] T026 [P] [US1] 移入 Ingresses: 移动 `apps/rsshub/ingress-rsshub.yaml` → `apps/rsshub/templates/ingress-rsshub.yaml`
- [ ] T027 [P] [US1] 移入 Ingresses: 移动 `apps/rsshub/ingress-ttrss.yaml` → `apps/rsshub/templates/ingress-ttrss.yaml`
- [ ] T028 [P] [US1] 移入 PVCs: 移动 `apps/rsshub/pvc-database-postgres-claim0.yaml` → `apps/rsshub/templates/pvc-database-postgres-claim0.yaml`
- [ ] T029 [P] [US1] 移入 PVCs: 移动 `apps/rsshub/pvc-feed-icons.yaml` → `apps/rsshub/templates/pvc-feed-icons.yaml`
- [ ] T030 [P] [US1] 移入 PVCs: 移动 `apps/rsshub/pvc-redis-data.yaml` → `apps/rsshub/templates/pvc-redis-data.yaml`
- [ ] T031 [US1] 新增 `app.kubernetes.io/managed-by: {{ "{{ .Release.Service }}" }}` 标签到所有 rsshub templates 中资源的 `metadata.labels`
- [ ] T032 [US1] 运行 `helm lint apps/rsshub` 验证 chart 语法正确
- [ ] T033 [US1] 运行 `helm template --namespace rsshub rsshub apps/rsshub` 验证渲染成功且资源数量 = 22

**Checkpoint**: rsshub Helm chart 可独立渲染且通过 lint

---

## Phase 4: User Story 2 - lobe-chat Helm Chart 转换 (Priority: P1)

**Goal**: 将 lobe-chat 的 15 个原始 YAML manifests 转换为 Helm chart，`helm template` 能成功渲染

**Independent Test**: `helm template --namespace lobe-chat lobe-chat apps/lobe-chat` 退出码 0，渲染出 15 个 Kubernetes 资源

### Implementation for User Story 2

- [ ] T034 [US2] 创建 `apps/lobe-chat/templates/` 目录
- [ ] T035 [P] [US2] 移入 Deployments (1/4): 移动 `apps/lobe-chat/deploy-lobe.yaml` → `apps/lobe-chat/templates/deploy-lobe.yaml`
- [ ] T036 [P] [US2] 移入 Deployments (2/4): 移动 `apps/lobe-chat/deploy-casdoor.yaml` → `apps/lobe-chat/templates/deploy-casdoor.yaml`
- [ ] T037 [P] [US2] 移入 Deployments (3/4): 移动 `apps/lobe-chat/deploy-postgresql.yaml` → `apps/lobe-chat/templates/deploy-postgresql.yaml`
- [ ] T038 [P] [US2] 移入 Deployments (4/4): 移动 `apps/lobe-chat/deploy-redis.yaml` → `apps/lobe-chat/templates/deploy-redis.yaml`
- [ ] T039 [P] [US2] 移入 Services (1/6): 移动 `apps/lobe-chat/svc-lobe.yaml` → `apps/lobe-chat/templates/svc-lobe.yaml`
- [ ] T040 [P] [US2] 移入 Services (2/6): 移动 `apps/lobe-chat/svc-casdoor.yaml` → `apps/lobe-chat/templates/svc-casdoor.yaml`
- [ ] T041 [P] [US2] 移入 Services (3/6): 移动 `apps/lobe-chat/svc-postgresql.yaml` → `apps/lobe-chat/templates/svc-postgresql.yaml`
- [ ] T042 [P] [US2] 移入 Services (4/6): 移动 `apps/lobe-chat/svc-redis.yaml` → `apps/lobe-chat/templates/svc-redis.yaml`
- [ ] T043 [P] [US2] 移入 Services (5/6): 移动 `apps/lobe-chat/svc-egress-lobe.yaml` → `apps/lobe-chat/templates/svc-egress-lobe.yaml`
- [ ] T044 [P] [US2] 移入 Services (6/6): 移动 `apps/lobe-chat/svc-egress-casdoor.yaml` → `apps/lobe-chat/templates/svc-egress-casdoor.yaml`
- [ ] T045 [P] [US2] 移入 Services: 移动 `apps/lobe-chat/svc-egress-rustfs.yaml` → `apps/lobe-chat/templates/svc-egress-rustfs.yaml`
- [ ] T046 [P] [US2] 移入 Ingresses: 移动 `apps/lobe-chat/ingress-lobe.yaml` → `apps/lobe-chat/templates/ingress-lobe.yaml`
- [ ] T047 [P] [US2] 移入 Ingresses: 移动 `apps/lobe-chat/ingress-casdoor.yaml` → `apps/lobe-chat/templates/ingress-casdoor.yaml`
- [ ] T048 [P] [US2] 移入 PVCs: 移动 `apps/lobe-chat/pvc-postgresql-claim1.yaml` → `apps/lobe-chat/templates/pvc-postgresql-claim1.yaml`
- [ ] T049 [P] [US2] 移入 PVCs: 移动 `apps/lobe-chat/pvc-redis.yaml` → `apps/lobe-chat/templates/pvc-redis.yaml`
- [ ] T050 [US2] 新增 `app.kubernetes.io/managed-by: {{ "{{ .Release.Service }}" }}` 标签到所有 lobe-chat templates 中资源的 `metadata.labels`
- [ ] T051 [US2] 运行 `helm lint apps/lobe-chat` 验证 chart 语法正确
- [ ] T052 [US2] 运行 `helm template --namespace lobe-chat lobe-chat apps/lobe-chat` 验证渲染成功且资源数量 = 15

**Checkpoint**: lobe-chat Helm chart 可独立渲染且通过 lint

---

## Phase 5: User Story 3 - 部署一致性验证 (Priority: P2)

**Goal**: 验证两个 Helm chart 的渲染输出与原始 manifests 在 spec 层面完全一致（仅允许新增的 label 差异）

**Independent Test**: `dyff between` 原始 manifests 与 Helm 渲染输出仅显示 label 差异，无 spec 差异

### Implementation for User Story 3

- [ ] T053 [US3] 使用 `dyff between` 对比 rsshub 原始 manifests（cat 拼接）与 `helm template` 输出，确认仅差异为新增的 managed-by label
- [ ] T054 [US3] 使用 `dyff between` 对比 lobe-chat 原始 manifests（cat 拼接）与 `helm template` 输出，确认仅差异为新增的 managed-by label
- [ ] T055 [US3] 验证 ArgoCD ApplicationSet 能自动发现新的 Helm chart（检查 `apps/` 目录下的 Chart.yaml 是否被 ApplicationSet 扫描到）

**Checkpoint**: 两个 chart 的渲染输出与原始 manifests 一致，ArgoCD 兼容

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: 清理和最终验证

- [ ] T056 删除 rsshub 根目录下的原始 YAML 文件（已移入 templates/ 的文件）
- [ ] T057 删除 lobe-chat 根目录下的原始 YAML 文件（已移入 templates/ 的文件）
- [ ] T058 运行 `./scripts/helm-diff` 模拟 CI 流程，确认 rsshub 和 lobe-chat 的 helm-diff 能正常完成
- [ ] T059 运行 `helm lint apps/rsshub && helm lint apps/lobe-chat` 做最终 lint 验证
- [ ] T060 按 quickstart.md 执行完整验证流程

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: 无依赖——所有任务可并行执行
- **Foundational (Phase 2)**: 依赖 Phase 1 completion——BLOCKS 所有用户故事
- **US1 (Phase 3)**: 依赖 Phase 2——rsshub 转换
- **US2 (Phase 4)**: 依赖 Phase 2——lobe-chat 转换（可与 US1 并行）
- **US3 (Phase 5)**: 依赖 US1 + US2 完成——对比验证
- **Polish (Phase 6)**: 依赖 US3 完成

### User Story Dependencies

- **US1 (P1)**: 可独立完成——仅涉及 `apps/rsshub/` 目录
- **US2 (P1)**: 可独立完成——仅涉及 `apps/lobe-chat/` 目录
- **US3 (P2)**: 依赖 US1 和 US2 的渲染输出

### Within Each User Story

- 移入文件 → 添加标签 → lint 验证 → template 验证

### Parallel Opportunities

- T001-T006（Phase 1 全部）可并行
- T009-T030（US1 所有文件移动）可并行
- T035-T049（US2 所有文件移动）可并行
- US1 和 US2 整体可并行执行

---

## Parallel Example: US1 File Moves

```bash
# 以下所有 move 任务操作不同文件，可同时执行：
Task: "移入 deploy-rsshub.yaml → templates/"
Task: "移入 deploy-browserless.yaml → templates/"
Task: "移入 deploy-database-postgres.yaml → templates/"
# ... 共 22 个并发任务
```

## Parallel Example: US1 + US2

```bash
# US1 和 US2 无文件冲突，可完全并行：
# Developer A: Phase 3 (rsshub 转换)
# Developer B: Phase 4 (lobe-chat 转换)
```

---

## Implementation Strategy

### MVP First (US1 Only)

1. 完成 Phase 1: Setup（创建 Chart.yaml 等元数据文件）
2. 完成 Phase 2: Foundational（修复 helm-diff 脚本）
3. 完成 Phase 3: US1（rsshub 转换）
4. **STOP and VALIDATE**: `helm lint` + `helm template` 验证 rsshub
5. 此时 rsshub 已可通过 CI

### Incremental Delivery

1. Setup + Foundational → 基础设施就绪
2. 添加 US1 (rsshub) → 独立验证 → rsshub CI 通过 (MVP!)
3. 添加 US2 (lobe-chat) → 独立验证 → lobe-chat CI 通过
4. 添加 US3 (一致性验证) → dyff 对比通过 → 可合入
5. 每个 story 独立增加价值，不破坏已有 story

---

## Notes

- [P] = 操作不同文件，无依赖，可并行
- [US1]/[US2]/[US3] = 映射到 spec.md 中对应的用户故事
- 每个用户故事可独立完成和验证
- 原始 YAML 文件内容完全不变——仅执行文件移动和标签新增
- 非模板文件（README.md、*.sh、.gitignore 等）保持在 app 根目录，不移入 templates/
- `casdoor-cm0-configmap.yaml.example` 保持在 `apps/lobe-chat/` 根目录（示例文件，不入 chart）
- 每个 checkpoint 后提交
