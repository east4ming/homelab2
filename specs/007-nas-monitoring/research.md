# Research: QNAP NAS 指标监控

**Date**: 2026-10-03
**Feature**: [spec.md](./spec.md)

本文件记录方案取舍与实测取证。所有「实测」结论均来自本次对 NAS（`ssh -p 52882 casey@nas`）与集群（`kubectl`）的直接操作。

## 1. 参考仓库的模型与本仓库不兼容

| 仓库 | 模型 | 结论 |
| --- | --- | --- |
| [zottelbeyer/QNAP-collectdinfluxdbgrafana](https://github.com/zottelbeyer/QNAP-collectdinfluxdbgrafana) | NAS 上跑 collectd，**推送**到 InfluxDB，Grafana 读 InfluxDB | 本仓库是 Prometheus **拉取**模型，且数据源已固定。仅参考其指标选择（CPU/内存/磁盘/网络），不引入 collectd/InfluxDB |
| [sandrotosi/qnap-dashboards](https://github.com/sandrotosi/qnap-dashboards) | 用 snmp_exporter 抓 QNAP SNMP（附 `NAS.mib` 与生成的 `snmp.yml`），Prometheus/Grafana 直接装在 NAS 上 | 实测本机 **无 snmpd**（`netstat -tulnp` 无 161 端口，`ps` 无 snmp 进程），且不需要在 NAS 上再装一套 Prometheus |

两个仓库都不能直接套用，但确认了监控维度：CPU、内存、卷容量、磁盘、网络。磁盘 SMART 由需求单独提出，参考仓库均未覆盖。

## 2. NAS 侧采集器选型

实测环境：

```
uname -a        Linux NAS33657A 5.10.60-qnap #1 SMP ... x86_64
QTS             5.2.10（/etc/version；QPKG 20260731）
Model           TS-X53B（TS-453Bmini）
RAM             16GB（node_memory_MemTotal_bytes 1.66e10）
Container Station  Docker 27.1.2-qnap8 / API 1.46 / Compose v2.29.1-qnap2
```

逐个验证过的候选：

1. **QNAP 自带 SNMP** —— 未启用，`netstat` 无 161，`ps` 无 snmpd。否决。
2. **Entware/QPKG 的 node-exporter** —— 需要往 QTS 上装第三方包并改 `autorun.sh`，与「容器化、可复现」相悖。否决。
3. **容器化的 node_exporter** —— ✅ 采用。镜像已有，拉取成功，实测暴露 **3101** 条序列。

### node-exporter 在 QTS 上的三个坑（均已实测）

- `--pid=host`：QNAP 内核下容器看不到宿主机 PID 命名空间。改为 `--path.rootfs=/host` 读取。
- `chroot` / `mount` procfs：QTS 上不生效，因此显式传 `--path.procfs=/host/proc`、`--path.sysfs=/host/sys`。
- **挂载点噪声**：容器挂载宿主机根后，以下挂载会一起冒出来，若不排除，每个真实卷会被计多次并被当成独立卷：

  | 噪声来源 | 原因 | 处理 |
  | --- | --- | --- |
  | `/mnt/snapshot/<pool>/<snap>`（实测 25 个） | fuse 快照视图，与 `cachedev` 是同一存储 | `mount-points-exclude` |
  | `/share/NFSv=4/*` | NFS 重导出的 bind mount | `mount-points-exclude` |
  | `/share/CACHEDEV*_DATA/.qpkg/*` | QPKG 应用沙箱（含 `/proc`、`/sys`、`dev/pts`） | `mount-points-exclude` |
  | 宿主机 `/sys`、`/proc`、`/var/lib/nfs`、container-station netns | 只因容器挂了宿主机根 | `mount-points-exclude` + `fs-types-exclude` |

  排除后 `node_filesystem_size_bytes` 恰好剩 10 个挂载点，其中真实存储卷 6 个（`/share/CACHEDEV1..5_DATA` + `/share/external/DEV3303_1`）。

### 磁盘设备可见性

- `/dev/sd*` 在普通容器内**不可见**（实测 `ls /host/dev/sda` 不存在；node-exporter 只拿到 `dm-*` 与 `/sys`）。
- 加 `--privileged` 后可见（`/proc/partitions` 出现 `sda`…`sde`）。
- 容器默认 UID 是 `nobody`，而 `/dev/sda` 权限为 `brw------- root:root`，因此 `smartctl-exporter` 必须 `privileged: true` **且** `user: "0:0"`。实测以 `nobody` 运行时日志为 `Smartctl open device: /dev/sda failed: Permission denied`。

### 磁盘 SMART：必须强制 `-d sat`（关键坑）

`smartctl --scan-open` 把 4 个盘位上的 SATA 盘**误判为 `scsi`**：

```json
{"name":"/dev/sda","type":"scsi","protocol":"SCSI"}   ← 4 块 WD 机械盘
{"name":"/dev/sdc","info_name":"/dev/sdc [SAT]","type":"sat","protocol":"ATA"}   ← SSD
```

后果（对照实测）：

| 命令 | 温度 | ATA 属性 |
| --- | --- | --- |
| `smartctl --all --json=c /dev/sda` | `{"current":0,"drive_trip":0}` | 缺失 |
| `smartctl --device=sat --all --json=c /dev/sda` | `{"current":46}` | 完整（Reallocated_Sector_Ct、Power_On_Hours…） |

因此 **smartctl_exporter 默认抓取会让 4 块机械盘温度恒为 0、SMART 属性全缺**，而面板看起来「有数据」，属于最危险的静默错误。

解决路径的取证过程：

1. `--smartctl.device=/dev/sda` 单独指定 —— 无效，仍为 scsi 路径。
2. `--smartctl.scan-device-type` —— **v0.12.0 镜像无此 flag**。
3. `--smartctl.device=/dev/sda;sat`（README 的 `<device>;<type>` 语法）—— **v0.12.0 不支持**，日志 `Smartctl open device: /dev/sda;sat failed: No such device`；**v0.14.0 支持**。

结论：**必须用 `prometheuscommunity/smartctl-exporter:v0.14.0`**（Docker Hub `latest`，也是 quay 的最新可用版本；quay.io 的 `prometheus-community/smartctl-exporter` 实测返回 `unauthorized`）。升级后 5 块盘全部返回真实温度与 `smart_status=1`。

### QNAP 专有指标为什么没纳入

- **机箱温度与风扇转速**：`/sys/class/hwmon/` 下只有 `coretemp`（CPU），无 QNAP EC 传感器。因此温度监控只覆盖硬盘。
- **`qcli_hdd`（QNAP 官方磁盘智能工具）**：需要交互式 QCLI 登录（`Please use qcli -l login first!`），要在采集链路里保存 NAS 管理员凭据。与「不提交凭据」冲突，否决。
- **`get_hd_smartinfo`**：`-d 1..4` 与 `-i 1` 组合实测均无输出；`strings` 显示其依赖 QNAP 私有库。否决。
- **NAS 上安装 smartctl**：`find / -name smartctl` 无结果。因此 SMART 只能从 privileged 容器读 `/dev/sd*`。

## 3. Prometheus 采集配置

沿用既有 `additionalScrapeConfigs`（与 node-exporter、tailscale-nodes 同一种模式），原因：

- 目标是集群外主机，无 K8s Service 可被 ServiceMonitor 发现。
- 静态目标与 `metal/inventories/prod.yml` 的 LAN IP 一起放在 Git 中，便于核对。

### `disk` 盘位标签怎么加

需求要盘位名（QNAP UI 语义），而 exporter 的 `device` 标签是内核名 `sda`。实测 `qcli_storage -d`：

```
Enclosure  Port  Sys_Name   Type        Size       Alias              Model
NAS_HOST   1     /dev/sdc   SSD:cache   931.51 GB  3.5" SATA SSD 1    Crucial CT1000MX500SSD1
NAS_HOST   2     /dev/sdd   HDD:data    10.91 TB   3.5" SATA HDD 2    WDC WD120EMFZ-11A6JA0
NAS_HOST   3     /dev/sda   HDD:data    10.91 TB   3.5" SATA HDD 3    WDC WD120EMFZ-11A6JA0
NAS_HOST   4     /dev/sdb   HDD:data    10.91 TB   3.5" SATA HDD 4    WDC WD120EMFZ-11A6JA0
```

因此映射为 `sdc→bay1`、`sdd→bay2`、`sda→bay3`、`sdb→bay4`，在 `metric_relabel_configs` 中逐条给出（13 行静态映射，无需自制 exporter 或 recording rule）。

**否决的替代方案**：用 `relabel_configs` + `regex`/`replacement`/`separator` 做 `labelmap` 批量映射。`separator` 是 relabel 的全局参数（不是按条生效），结果标签名会带分隔符，无法得到干净的 `disk=bay3`。逐条映射更直白。

## 4. 告警规则：实测发现两处必然误报

把 6 条表达式按实测样本逐条评估后，发现两个**上线即永久 firing** 的问题：

### `/mnt/ext` 只剩 7.69% 可用

```
node_filesystem_avail_bytes{...,mountpoint="/mnt/ext"} / node_filesystem_size_bytes{...} = 0.0769
```

`/mnt/ext` 是 436MB 的固件 DOM（`/dev/md13`），QTS 设计上就让它接近满。→ 卷容量规则限定 `mountpoint=~"/share/.+"`。

### `md9` / `md13` 的 `active < required` 永久成立

`/proc/mdstat`：

```
md13 : active raid1 sdc4[35] sdb4[34] sda4[32] sdd4[33]   [32/4] [UUUU____________________________]
md9  : active raid1 sdc1[0]  sdb1[34] sda1[32] sdd1[33]   [32/4] [UUUU____________________________]
md321: active raid1 sdc5[0]                                [2/1] [U_]
```

`md9`/`md13` 是 32 槽位的固件 DOM 镜像，只用 4 槽；`md321` 是单盘镜像，本就不冗余。三者 `node_md_disks{state="active"} < node_md_disks_required` 恒成立。→ 规则限定 `device=~"md1|md2|md256|md322"`，并用 `on (device)` 做向量匹配。

排除后 6 条规则在当前环境下全部 `inactive`（数据卷 `/share/CACHEDEV*` 可用空间 29%–90%；`md1/md2/md256/md322` 活跃盘数等于所需；SMART 全 `1`；最高盘温 49°C）。

## 5. ArgoCD 能管什么、不能管什么

ArgoCD 的同步单元是 K8s 对象。这台 NAS 不是集群节点，也不在 `metal/inventories/prod.yml` 里（该 inventory 被 `boot.yml` 的 Wake-on-LAN 与 `cluster.yml` 的 K3s 初始化消费，加入 NAS 会误操作）。逐条评估过的替代路径：

| 方案 | 结论 |
| --- | --- |
| 在 NAS 上装 k3s，让 ArgoCD 管它 | 与现有集群职责重复，NAS 只需两个只读 exporter。否决 |
| ArgoCD `ConfigManagementPlugin` 直接落容器到 NAS | 插件只在 repo-server 渲染清单，无法在集群外执行 Docker。否决 |
| 用 ArgoCD 的 `Application` + 自定义 resource 走 webhook 触发 NAS | 需要自建控制器，为 2 个容器引入一个自研组件。否决 |
| NAS 上用 Entware 装 node-exporter（非容器） | 需要改 `autorun.sh`，QTS 升级易丢。否决 |
| **compose 入库 + Container Station 导入** | ✅ 采用：配置可追溯、NAS 重装可复现；导入这一步是人工的 |

## 6. 实测记录汇总

| 项目 | 结果 |
| --- | --- |
| 集群 → NAS 连通性 | `:9100`、`:9633`、`:5000`、`:5001`、`:3000`、`:8200` 可达；`:5252` 不可达 |
| node-exporter 序列数 | 3101（排除噪声挂载后） |
| smartctl-exporter 序列数 | 496 |
| 磁盘温度（实测） | sda 46°C、sdb 49°C、sdc 45°C、sdd 44°C、sde 44°C |
| SMART 自检 | 5 块盘全部 `smart_status=1` |
| 容器内存占用 | node-exporter 19.89MiB、smartctl-exporter 6.449MiB |
| 镜像大小 | node-exporter v1.8.2 23.3MB、smartctl-exporter v0.14.0 32.2MB |
| 注册表可用性 | quay.io/node-exporter ✅；quay.io/prometheus-community/smartctl-exporter ❌（unauthorized）；docker.io/prometheuscommunity/smartctl-exporter ✅ |
