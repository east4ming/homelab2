# Tasks: 新增 StyleFerry 应用

**Input**: Design documents from `specs/001-add-styleferry-app/`

**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/, quickstart.md

**Tests**: 本项目不要求额外的单元测试。验证通过 helmlint、yamllint（pre-commit hooks）和 `make smoke-test` 完成。

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Helm Chart**: `apps/styleferry/` — Chart.yaml, values.yaml, templates/
- **Homepage**: `apps/homepage/values.yaml`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 创建 StyleFerry Helm Chart 的目录结构

- [ ] T001 Create directory structure `apps/styleferry/templates/`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 创建 Chart 元数据和 Secret 管理资源——所有用户故事的前置依赖

**⚠️ CRITICAL**: 完成此阶段后用户故事实现才能开始

- [ ] T002 [P] Create `apps/styleferry/Chart.yaml` with app-template v5.0.1 dependency
- [ ] T003 [P] Create `apps/styleferry/templates/secret.yaml` (ExternalSecret → global-secrets → key `styleferry`)

**Checkpoint**: Chart 骨架就绪——可开始填充 values.yaml

---

## Phase 3: User Story 1 - 部署 StyleFerry Helm Chart (Priority: P1) 🎯 MVP

**Goal**: values.yaml 包含控制器、镜像、环境变量、Secret 引用、探针和资源限制，Pod 可成功启动

**Independent Test**: ArgoCD ApplicationSet 自动发现 Chart 并创建 Application，Pod 启动后探活通过

### Implementation for User Story 1

- [ ] T004 [US1] Configure controller and image (`registry.cn-hangzhou.aliyuncs.com/caseycui/styleferry:1.0.0`) in `apps/styleferry/values.yaml`
- [ ] T005 [US1] Configure non-sensitive env vars (BLOG_LLM_PROVIDER, BLOG_LLM_BASE_URL, BLOG_LLM_MODEL, BLOG_SEARCH_PROVIDER, BLOG_SEARXNG_URL, BLOG_MONTHLY_COST_LIMIT, BLOG_LOG_LEVEL, BLOG_TRACING_PROVIDER, BLOG_RECALL_BASE_URL, BLOG_SQLITE_PATH, BLOG_CACHE_DIR) in `apps/styleferry/values.yaml`
- [ ] T006 [US1] Configure `envFrom` secret reference pointing to `styleferry` (via `{{ .Release.Name }}-secret`) in `apps/styleferry/values.yaml`
- [ ] T007 [US1] Configure startup/liveness/readiness probes in `apps/styleferry/values.yaml`
- [ ] T008 [US1] Configure service port (8000, HTTP) in `apps/styleferry/values.yaml`
- [ ] T009 [US1] Set resources.requests (CPU 50m / Memory 128Mi) and resources.limits (CPU 500m / Memory 512Mi) in `apps/styleferry/values.yaml`
- [ ] T010 [US1] Run `helmlint` and `yamllint` on `apps/styleferry/`

**Checkpoint**: Chart 核心功能完整——ArgoCD 可部署并启动 StyleFerry Pod

---

## Phase 4: User Story 2 - 通过 Tailscale Ingress 访问 StyleFerry (Priority: P2)

**Goal**: 配置 Tailscale Ingress，用户可通过 MagicDNS 域名 `https://styleferry.west-beta.ts.net` 访问服务

**Independent Test**: Tailscale 网络内设备访问 `https://styleferry.west-beta.ts.net` 返回 HTTP 200

### Implementation for User Story 2

- [ ] T011 [US2] Configure ingress section (enabled: true, className: tailscale) with proxy-group annotation in `apps/styleferry/values.yaml`
- [ ] T012 [US2] Set ingress host `styleferry.west-beta.ts.net` with TLS in `apps/styleferry/values.yaml`

**Checkpoint**: StyleFerry 可通过 Tailscale MagicDNS 域名访问

---

## Phase 5: User Story 3 - 数据持久化 (Priority: P3)

**Goal**: `/data` 目录挂载到 PVC，Pod 重启后数据不丢失

**Independent Test**: 写入测试数据后删除 Pod，新 Pod 启动后数据一致

### Implementation for User Story 3

- [ ] T013 [US3] Configure persistence PVC (accessMode: ReadWriteOnce, size: 10Gi) in `apps/styleferry/values.yaml`
- [ ] T014 [US3] Configure advancedMounts mapping `/data` to PVC in `apps/styleferry/values.yaml`

**Checkpoint**: StyleFerry 数据持久化，Pod 重启数据不丢失

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: 集成到项目仪表盘和冒烟测试

- [ ] T015 [P] Register StyleFerry entry in `apps/homepage/values.yaml` config.services
- [ ] T016 [P] Add `https://styleferry.west-beta.ts.net` endpoint to `make smoke-test`
- [ ] T017 Run final `helmlint`, `yamllint` verification on all changed files

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational completion
- **User Story 2 (Phase 4)**: Depends on US1 (shares values.yaml)
- **User Story 3 (Phase 5)**: Depends on US1 (shares values.yaml)
- **Polish (Phase 6)**: Depends on all user stories

### User Story Dependencies

- **User Story 1 (P1)**: Core deployment — foundation for US2 and US3
- **User Story 2 (P2)**: Ingress access — independent testable after US1
- **User Story 3 (P3)**: Persistence — independent testable after US1

### Within Each User Story

- env vars → envFrom → probes → resources → lint (US1)
- ingress → TLS (US2)
- PVC → mounts (US3)

### Parallel Opportunities

- T002 and T003 can run in parallel (Chart.yaml and secret.yaml are different files)
- T015 and T016 can run in parallel (homepage values + smoke test are different files)
- US2 and US3 modifications target the same values.yaml — execute sequentially

---

## Parallel Example: Foundational Phase

```bash
# Launch foundational tasks together:
Task: "Create apps/styleferry/Chart.yaml with app-template v5.0.1 dependency"
Task: "Create apps/styleferry/templates/secret.yaml (ExternalSecret → global-secrets → key styleferry)"
```

## Parallel Example: Polish Phase

```bash
# Launch polish tasks together:
Task: "Register StyleFerry entry in apps/homepage/values.yaml config.services"
Task: "Add https://styleferry.west-beta.ts.net endpoint to make smoke-test"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational
3. Complete Phase 3: User Story 1 (T004-T010)
4. **STOP and VALIDATE**: `helmlint` 通过、yamllint 通过、ArgoCD 可部署 Pod
5. Deploy/demo if ready

### Incremental Delivery

1. Setup + Foundational + US1 → Core Chart ready → Pod starts ✅
2. Add US2 → Ingress accessible → `curl https://styleferry.west-beta.ts.net` returns 200 ✅
3. Add US3 → Data persists across restarts ✅
4. Polish → Homepage entry + smoke test integration ✅

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Most tasks modify `apps/styleferry/values.yaml` — execute sequentially within phase
- Verify `helmlint` and `yamllint` pass after each phase before proceeding
- Secret `styleferry` 需在部署前由用户手动创建（ExternalSecret 自动同步）
- Commit after each phase or logical group
- Stop at any checkpoint to validate independently
