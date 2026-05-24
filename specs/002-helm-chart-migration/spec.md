# Feature Specification: Raw Manifests to Helm Chart Migration

**Feature Branch**: `002-helm-chart-migration`

**Created**: 2026-05-24

**Status**: Draft

**Input**: User description: "将 rsshub 和 lobe-chat 2个raw manifests 应用改写为最简封装的helm chart. 目的是通过 ci helm-diff 的验证, 因为当前raw manifest会导致ci验证失败. 要求: 修改后的helm chart 应与修改前保持一致, 除了允许新增部分k8s manifests的labels和 annotation 之外, 其他都应保持不变. 以使得此次变更对环境的影响最小."

## User Scenarios & Testing

### User Story 1 - CI Helm-Diff Passes for Affected Apps (Priority: P1)

As a platform operator, when I open a pull request that modifies the rsshub or lobe-chat deployments, the CI helm-diff validation step must succeed so the PR can be reviewed and merged.

**Why this priority**: The raw manifest format currently causes CI pipeline failure on every PR touching these apps, blocking all changes. This is the primary driver for the migration.

**Independent Test**: Run `helm template` on the converted chart and verify it produces the same rendered resources as `kubectl apply --dry-run` on the original manifests (modulo the allowed label/annotation additions).

**Acceptance Scenarios**:

1. **Given** the rsshub app directory is structured as a valid Helm chart (with Chart.yaml, templates/), **When** `helm template --namespace rsshub rsshub apps/rsshub` is executed, **Then** it renders all resources without errors.
2. **Given** the lobe-chat app directory is structured as a valid Helm chart, **When** `helm template --namespace lobe-chat lobe-chat apps/lobe-chat` is executed, **Then** it renders all resources without errors.
3. **Given** a PR modifying files under `apps/rsshub/**` or `apps/lobe-chat/**`, **When** the CI `.woodpecker/helm-diff.yaml` step runs, **Then** the `dyff between` comparison completes successfully.

---

### User Story 2 - Existing Deployments Remain Unchanged (Priority: P1)

As a platform operator managing production workloads, I expect the rendered Kubernetes resources from the new Helm chart to be identical to the previously deployed raw manifests, so ArgoCD does not detect any drift or trigger unnecessary sync/redeploy operations when the change is rolled out.

**Why this priority**: Avoiding disruption to running services is critical. Any unintended resource change could cause service downtime.

**Independent Test**: Render the Helm chart with `helm template` and diff the output against the original manifests, confirming the only differences are the allowed label/annotation additions.

**Acceptance Scenarios**:

1. **Given** the rsshub Helm chart is rendered, **When** compared against the original raw manifests via `dyff between`, **Then** the only differences are the newly added standard Helm labels and annotations.
2. **Given** the lobe-chat Helm chart is rendered, **When** compared against the original raw manifests via `dyff between`, **Then** the only differences are the newly added standard Helm labels and annotations.

---

### User Story 3 - ArgoCD Continues to Sync Successfully (Priority: P2)

As a platform operator, after the migration, ArgoCD must continue to recognize and manage these applications as before, with sync status remaining healthy.

**Why this priority**: ArgoCD is the deployment mechanism — if it can't reconcile the new chart format, deployments will fail.

**Independent Test**: Point an ArgoCD Application at the new chart directory and verify sync status remains "Synced" and "Healthy".

**Acceptance Scenarios**:

1. **Given** the rsshub ArgoCD Application is configured to source from the new Helm chart directory, **When** ArgoCD performs a sync, **Then** the application status is "Synced" and "Healthy".
2. **Given** the lobe-chat ArgoCD Application is configured to source from the new Helm chart directory, **When** ArgoCD performs a sync, **Then** the application status is "Synced" and "Healthy".

---

### Edge Cases

- What happens when a manifest references a Secret that doesn't exist as a template? The chart must still render (Secrets are managed externally).
- What about the `.example` ConfigMap file (`casdoor-cm0-configmap.yaml.example`) in lobe-chat? It should be excluded from templates since it's not a deployable resource.
- What about shell scripts and README files in the app directories? They must remain in place but excluded from the Helm chart's template rendering.
- What about the `.gitignore` in rsshub? It should remain at the app root level.

## Requirements

### Functional Requirements

- **FR-001**: Each app directory (rsshub, lobe-chat) MUST contain a valid `Chart.yaml` with `apiVersion: v2`, a descriptive `name`, and a `version` field.
- **FR-002**: Each app directory MUST contain a `templates/` subdirectory containing all Kubernetes resource manifests as raw YAML (minimally templated).
- **FR-003**: The rendered Helm chart output MUST produce resource specs identical to the original raw manifests, with the exception of allowed additional labels and annotations.
- **FR-004**: Standard Helm labels (`app.kubernetes.io/managed-by: {{ .Release.Service }}`, `helm.sh/chart`) MAY be added to resource metadata to identify them as Helm-managed.
- **FR-005**: Non-manifest files (README, shell scripts, `.gitignore`, example files, docs) MUST remain in the app directory but outside the `templates/` directory.
- **FR-006**: All existing resource names, selectors, ports, volumes, environment variables, probes, and other spec fields MUST remain unchanged.
- **FR-007**: Existing kompose annotations and labels on resources MUST be preserved as-is.
- **FR-008**: The namespace handling MUST be preserved: hardcoded namespaces (rsshub) remain as-is; namespace-less resources (lobe-chat) remain without explicit namespace.
- **FR-009**: Each chart MUST include a `.helmignore` file to exclude non-template files from the chart package.
- **FR-010**: The existing ArgoCD Application configuration for both apps MUST continue to work without modification, or with minimal path adjustment from raw manifest directory to Helm chart directory.

### Key Entities

- **Helm Chart**: The packaging format wrapping Kubernetes manifests, consisting of Chart.yaml (metadata), templates/ (K8s resources), and values.yaml (configuration values).
- **Kubernetes Resource Manifests**: Individual YAML files defining Deployments, Services, Ingresses, PersistentVolumeClaims, and Namespaces for each application.
- **CI Helm-Diff Pipeline**: The Woodpecker CI step that clones source/target branches, runs `helm template`, and compares rendered output with `dyff`.

## Success Criteria

### Measurable Outcomes

- **SC-001**: `helm template` executes successfully on both app directories with zero errors.
- **SC-002**: The `dyff between` comparison of rendered output vs original manifests shows zero differences in resource specs (excluding allowed label/annotation additions).
- **SC-003**: The Woodpecker CI `helm-diff` step passes for PRs touching `apps/rsshub/**` or `apps/lobe-chat/**`.
- **SC-004**: ArgoCD sync status for both applications remains "Synced" and "Healthy" after the migration is deployed.
- **SC-005**: All 22 rsshub resource manifests and all 15 lobe-chat resource manifests are preserved in the `templates/` directory with their original content intact.

## Assumptions

- The CI helm-diff script (`scripts/helm-diff`) will be updated (or already handles) the transition period where target branch has raw manifests and source branch has Helm charts. See the existing comment about empty renders for new/removed charts; the same principle applies but needs implementation.
- ArgoCD is configured to auto-detect Helm charts (looking for Chart.yaml) or the Application spec will be updated with the new chart path.
- Secrets referenced by the deployments (e.g., `rsshub-secret`, `postgres-secret`, `lobe-auth`, `lobe-db-secrets`, `lobe-s3-secrets`, `lobe-ai-api-keys`) are managed externally and do not need to be part of the Helm chart.
- The `casdoor-cm0-configmap.yaml.example` file is an example/reference and is intentionally excluded from templates.
- The migration targets `apps/` subpath since that's where CI scans per `.woodpecker/helm-diff.yaml` matrix STACK=apps configuration.
