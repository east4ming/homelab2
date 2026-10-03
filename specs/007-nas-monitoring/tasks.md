# Tasks: QNAP NAS 指标监控

**Input**: Design documents from `specs/007-nas-monitoring/`

**Prerequisites**: plan.md (required), spec.md (required), research.md, quickstart.md

**Organization**: 按部署链路分组，每个任务可独立验证。

## Phase 1: NAS 侧采集器

**Purpose**: 让 NAS 暴露主机指标与磁盘 SMART

- [x] T001 实测 NAS 环境：Container Station/Docker 27.1.2、Compose v2.29.1、`/dev/sd*` 仅在 privileged 容器可见、容器默认 UID `nobody` 无法打开设备
- [x] T002 验证 node_exporter 可用（3101 条序列），并定位挂载点噪声（25 个快照挂载 + NFS 重导出 + QPKG 沙箱 + 宿主 `/proc`/`/sys`）
- [x] T003 定位 SMART 失效根因：`smartctl --scan-open` 把 4 块 SATA 盘误判为 `scsi`，温度恒 0 且 ATA 属性缺失
- [x] T004 确定必须在 v0.14.0 上使用 `--smartctl.device=/dev/sdX;sat`（v0.12.0 不支持该语法，已实测报错）
- [x] T005 新增 `metal/nas/compose.yml`（两个服务、host 网络、重启策略、挂载点排除、`;sat` 设备类型、privileged + root）
- [x] T006 在 NAS 上部署并验证：node_exporter 挂载点收敛为 10 个（真实存储卷 6 个），5 块盘温度非 0（44–49°C）、`smart_status` 全为 1
- [x] T007 在 Container Station 应用目录建立 `nas-monitoring`（`docker-compose.yml`、`docker-compose.resource.yml`、`qnap.json`），使其出现在 UI 中

## Phase 2: Prometheus 采集

**Purpose**: 抓取 NAS 指标并补齐盘位标签

- [x] T008 在 `system/monitoring-system/values.yaml` 增加 `additionalScrapeConfigs`（job `nas-node`、`nas-smartctl`，附加 `nas` 标签）
- [x] T009 为 `nas-smartctl` 增加 `device`→`disk` 盘位重标记（依据 `qcli_storage -d` 实测：sdc→bay1、sdd→bay2、sda→bay3、sdb→bay4）
- [x] T010 集群侧只读验证：从集群 pod 内抓取两个端点成功（node 3101 条 / smart 496 条序列），两个端点均通过 `promtool check metrics` 语义校验

## Phase 3: 告警规则

**Purpose**: 把指标变成可执行信号

- [x] T011 新增 `system/monitoring-system/templates/prometheusrule-nas.yaml`（卷容量两级阈值、卷只读、RAID 失去冗余、SMART 失败、磁盘高温）
- [x] T012 按实测样本逐条评估 6 条表达式，发现并修正两处必然误报：`/mnt/ext` 固件 DOM 只剩 7.69% 可用；`md9`/`md13` 固件镜像 32 槽位只用 4 槽导致 `active < required` 恒成立
- [x] T013 修正后复评：6 条规则在当前环境全部 `inactive`；`promtool check rules` 通过（SUCCESS: 6 rules found）
- [x] T014 抓取中断复用既有 `TargetDown`，不重复定义 NAS 专用 down 告警

## Phase 4: Grafana dashboard

**Purpose**: 一屏查看容量、RAID、磁盘温度与吞吐

- [x] T015 新增 `system/monitoring-system/files/dashboards/nas.json`（13 个面板）与 `templates/dashboard-nas.yaml`（sidecar ConfigMap，`grafana_dashboard_folder: NAS`）
- [x] T016 交叉核对 dashboard 中每个 PromQL 引用的指标名，移除本机不存在的 SMART 属性（`Media_Wearout_Indicator`、`Wear_Leveling_Count`）
- [x] T017 卷容量面板限定 `mountpoint=~"/share/.+"`，与告警范围一致

## Phase 5: 校验与交付

- [x] T018 `docker compose config` 校验 compose；`yamllint` 通过
- [x] T019 `helm template` 渲染通过；渲染产物中的 PrometheusRule、ConfigMap 与内嵌 JSON 均可解析
- [x] T020 `promtool check config` 校验抓取配置（SUCCESS: valid prometheus config file syntax）
- [x] T021 新增 `specs/007-nas-monitoring/`（spec、plan、research、quickstart、checklist、tasks）并在 `AGENTS.md` 更新当前 Plan
- [ ] T022 主题分支 `007-nas-monitoring` + PR 合入 `master`，触发 ArgoCD 同步
- [ ] T023 合并后按 [quickstart.md](./quickstart.md) 验证：两个 target `UP`、6 条规则 `inactive`、Grafana `NAS` 目录出现 dashboard
