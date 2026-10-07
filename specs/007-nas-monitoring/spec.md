# Feature Specification: QNAP NAS 指标监控

**Feature Branch**: `007-nas-monitoring`

**Created**: 2026-10-03

**Status**: Draft

**Input**: User description: 为 NAS NAS33657A（QNAP TS-453Bmini，QTS 5.2.10.3577）安装配置 metrics collector、Prometheus scrape、prometheus rules 与 Grafana dashboard，沿用 GitOps/ArgoCD 方式管理。

## User Scenarios & Testing

### User Story 1 - NAS 系统指标被 Prometheus 采集 (Priority: P1)

作为 homelab2 运维者，我希望 NAS 的 CPU、内存、卷容量、RAID 状态、磁盘与网络吞吐被 Prometheus 自动采集，以便在一处看到这台存储设备的状态，而不是登录 QTS 网页逐项查看。

**Why this priority**: 采集是所有告警与可视化的基础；这台 NAS 是 homelab 的唯一大容量存储（5 个卷、约 14TB 数据）。

**Independent Test**: Prometheus Targets 页面出现 `nas-node` job 且为 `UP`，查询 `node_filesystem_avail_bytes{job="nas-node"}` 返回 4 个 `cachedev` 卷与 USB 外接盘。

**Acceptance Scenarios**:

1. **Given** NAS 已运行 Container Station，**When** 导入采集容器并配置抓取，**Then** `nas-node` target 为 `UP`，且指标带 `nas="NAS33657A"` 标签。
2. **Given** 采集已生效，**When** 查询 `node_filesystem_avail_bytes`，**Then** 每个真实存储卷只出现一次（不因快照/NFS 重导出挂载而重复计数）。
3. **Given** NAS 重启，**When** 容器自动拉起，**Then** 抓取自动恢复，无需人工介入。

---

### User Story 2 - 磁盘 SMART 健康被采集 (Priority: P1)

作为 homelab2 运维者，我希望 4 个盘位的硬盘温度、SMART 自检结论与关键属性（重分配扇区、待映射扇区、CRC 错误、通电时长）被采集，以便在磁盘真正掉盘之前换盘。

**Why this priority**: 磁盘是这台 NAS 上唯一不可替换的数据载体；SMART 是唯一能提前发现劣化的信号。RAID5 已经在三盘上运行，且两个卷已用掉 61% 与 71%。

**Independent Test**: 查询 `smartctl_device_smart_status` 返回 4 块盘且均为 1，`smartctl_device_temperature{...}` 返回非零温度。

**Acceptance Scenarios**:

1. **Given** 采集容器已运行，**When** 查询 `smartctl_device_temperature`，**Then** 每块盘返回真实温度（不是 0），且指标带 `disk` 标签标明物理盘位。
2. **Given** 某块盘 SMART 自检失败，**When** 规则评估，**Then** 触发 `NASDiskSMARTCritical`。
3. **Given** 某块盘温度持续高于 55°C，**When** 规则评估，**Then** 触发 `NASDiskTemperatureHigh`。

---

### User Story 3 - 告警规则 (Priority: P2)

作为 homelab2 运维者，我希望卷将满、卷被重挂为只读、RAID 失去冗余、磁盘 SMART 失败或过热时收到通知，而不是等应用到写不进去才发现。

**Why this priority**: 告警把采集数据变成可执行信号。

**Independent Test**: Prometheus 中能查询到 6 条 NAS 告警规则，且全部为 `inactive`（不产生误报）。

**Acceptance Scenarios**:

1. **Given** 规则已加载，**When** 卷可用空间低于 15%，**Then** 触发 `NASVolumeSpaceLow`；低于 5% 时 `NASVolumeSpaceCritical`。
2. **Given** 某个数据阵列的活跃盘数少于所需盘数，**When** 规则评估，**Then** 触发 `NASRAIDNotRedundant`。
3. **Given** 规则基于当前真实环境评估，**When** 无异常发生，**Then** 6 条规则全部 `inactive`——尤其不得因 QTS 内部固定布局的阵列（`md9`/`md13`）或固件 DOM（`/mnt/ext`）持续误报。
4. **Given** NAS 整体不可达，**When** 抓取失败，**Then** 由既有 `TargetDown` 规则告警，不重复定义。

---

### User Story 4 - Grafana dashboard (Priority: P3)

作为 homelab2 运维者，我希望在 Grafana 中一屏看到 NAS 的容量、RAID、磁盘温度与吞吐。

**Why this priority**: 可视化用于快速定位与日常巡检，依赖 P1 的采集。

**Independent Test**: Grafana 中出现 `NAS (QNAP TS-453Bmini)` dashboard，所有面板有数据。

**Acceptance Scenarios**:

1. **Given** dashboard ConfigMap 已部署，**When** 打开 Grafana，**Then** 能在 `NAS` 目录下看到 dashboard。
2. **Given** dashboard 已打开，**When** 查看顶部状态行，**Then** 显示抓取状态、CPU/内存使用率、RAID 冗余、SMART 健康与最高盘温。
3. **Given** 磁盘温度面板，**When** 某块盘被强制为 `-d sat` 读取失败，**Then** 该盘曲线为 0 或缺失，可据此发现采集配置退化。

### Edge Cases

- NAS 关机或容器停止：target 变 `DOWN`，由既有 `TargetDown` 告警；历史指标按 Prometheus 保留策略过期。
- NAS IP 变更：需同步更新 `system/monitoring-system/values.yaml` 中的抓取目标（在 Git 中）。
- 盘位增删盘：采集容器禁用了自动重扫（因为显式指定了设备），需同步更新 `metal/nas/compose.yml` 并重建应用。
- QTS 升级后盘符变化（`sda`↔`sdb` 之类）：`disk` 标签的盘位映射会失准，需按 `qcli_storage -d` 复核。
- 硬盘休眠：`smartctl-exporter` 会唤醒磁盘读取 SMART，可能影响休眠策略（实测本机盘温 44–49°C，未休眠）。

## Requirements

### Functional Requirements

- **FR-001**: 系统 MUST 在 NAS 上以容器方式运行两个 exporter：`node_exporter`（主机指标）与 `smartctl_exporter`（磁盘 SMART），两者 MUST NOT 监听非本机可达地址之外的接口。
- **FR-002**: `smartctl_exporter` MUST 强制以 `-d sat` 读取 4 个盘位的 SATA 盘；该 QNAP 控制器会让 `smartctl --scan-open` 误判为 SCSI，导致温度恒为 0 且 ATA 属性缺失。
- **FR-003**: 两个容器 MUST 设置重启策略，使 NAS 重启后抓取自动恢复。
- **FR-004**: Prometheus MUST 抓取两个 exporter，并为每条序列附加 `nas` 标签；SMART 指标 MUST 额外附加物理盘位标签 `disk`。
- **FR-005**: 系统 MUST 在抓取时排除重复的挂载点（快照卷、NFS 重导出、QPKG 沙箱、宿主机 `/proc` 与 `/sys`），使每个真实存储卷只计一次。
- **FR-006**: 系统 MUST 提供 PrometheusRule 覆盖：卷容量（两级阈值）、卷只读、RAID 失去冗余、SMART 健康失败、磁盘高温；抓取中断 MUST 复用既有 `TargetDown` 而不重复定义。
- **FR-007**: 告警规则的评估范围 MUST 排除 QTS 内部固定布局的对象（`md9`/`md13` 固件 DOM 镜像、`/mnt/ext`），否则会产生永久误报。
- **FR-008**: 系统 MUST 通过 Grafana sidecar 提供 NAS dashboard，覆盖容量、RAID、磁盘温度/吞吐与 SMART 属性。
- **FR-009**: 所有集群侧资源（scrape 配置、规则、dashboard）MUST 通过 Git 管理并走 ArgoCD；NAS 侧容器 MUST 由入库存放的 compose 文件定义，可被重新导入 Container Station 复现。
- **FR-010**: 仓库中 MUST NOT 提交任何 NAS 凭据、私钥或明文密码。

### Key Entities

- **nas-monitoring（Container Station 应用）**: NAS 上的 compose 应用，含 `nas-node-exporter`（9100）与 `nas-smartctl-exporter`（9633）两个容器，使用 host 网络。
- **`nas-node` scrape job**: Prometheus 附加抓取配置，静态目标 `192.168.3.216:9100`。
- **`nas-smartctl` scrape job**: 静态目标 `192.168.3.216:9633`，含 `device`→`disk` 盘位重标记。
- **PrometheusRule `nas`**: 6 条告警规则。
- **Grafana dashboard `nas-qnap`**: sidecar 加载的 dashboard ConfigMap。

## Success Criteria

### Measurable Outcomes

- **SC-001**: Prometheus Targets 中 `nas-node` 与 `nas-smartctl` 均为 `UP`，且没有 `up == 0` 的 NAS target。
- **SC-002**: 6 条 NAS 告警规则全部 `inactive`，无持续 pending/firing 的误报。
- **SC-003**: `smartctl_device_temperature{temperature_type="current"}` 对 4 块盘返回非零温度；`smartctl_device_smart_status` 返回 5 个设备（含 USB 外接盘）。
- **SC-004**: `node_filesystem_avail_bytes{job="nas-node"}` 恰好返回 6 条真实存储卷（`/share/CACHEDEV1_DATA`…`CACHEDEV5_DATA` 与 `/share/external/DEV3303_1`），不含快照、NFS 重导出与固件 DOM。
- **SC-005**: Grafana 中出现 `NAS` 目录与 `NAS (QNAP TS-453Bmini)` dashboard，全部面板有数据。
- **SC-006**: NAS 重启后无需人工介入即恢复采集（容器重启策略生效）。

## Assumptions

- NAS 已安装并启用 Container Station（实测 Docker 27.1.2-qnap8、Compose v2.29.1-qnap2），且能拉取 Docker Hub 与 quay.io 镜像。
- 集群内 Prometheus 能直连 NAS LAN IP（实测 pod 可访问 `192.168.3.216:9100` 与 `:9633`；同一测试中 NAS 的 `:5252` 不可达，故不依赖 Tailscale IP 采集）。
- 这台 QNAP 的 `smartctl` 只能从宿主机或以 privileged 容器读取 `/dev/sd*`；容器默认 UID `nobody` 无法打开设备（`/dev/sda` 为 `brw------- root:root`）。
- NAS 上不存在 `smartctl`、SNMP 守护进程与 QCLI 免交互接口；`qcli_hdd` 需要交互式登录会话，因此不纳入采集链路。
- QNAP 控制器不通过 hwmon 暴露机箱温度与风扇转速（实测只有 CPU `coretemp`），因此温度监控只覆盖硬盘。
- 参考仓库中 `zottelbeyer/QNAP-collectdinfluxdbgrafana` 走 collectd + InfluxDB 推送模型，与本仓库的 Prometheus 拉取模型不同，仅作指标选择参考；`sandrotosi/qnap-dashboards` 依赖 SNMP（本机未启用）与 QNAP 上的 Prometheus 实例，同样只作参考。
