# Quickstart: QNAP NAS 指标监控

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

NAS: `NAS33657A`（TS-453Bmini，QTS 5.2.10），LAN `192.168.3.216`，容器用 host 网络监听 `9100`（node）与 `9633`（SMART）。

## 1. 导入 Container Station 应用

NAS 侧容器不由 ArgoCD 管理，需要在 Container Station 里建立这个应用。

**方式 A（Container Station UI，推荐）**

1. 打开 Container Station → **应用程序（Applications）** → **创建（Create）**。
2. 应用程序名称填 `nas-monitoring`。
3. 把 [metal/nas/compose.yml](../../metal/nas/compose.yml) 的内容整段粘贴到 YAML 编辑区。
4. 创建并启动。

!!! warning "粘贴 YAML，不要只填表单"

    表单模式会强制 bridge 网络，而这两个 exporter 必须用 host 网络才能让集群按 `192.168.3.216:9100` / `:9633` 抓取。

**方式 B（命令行）**

```sh
ssh -p 52882 casey@nas
export PATH=$PATH:/share/CACHEDEV1_DATA/.qpkg/container-station/bin
cd <compose.yml 所在目录>
docker compose -p nas-monitoring up -d
```

启动后确认两个容器都在跑：

```sh
docker ps --filter name=nas- --format '{{.Names}}  {{.Status}}'
# nas-node-exporter       Up ...
# nas-smartctl-exporter   Up ...
```

## 2. 合并到 master 触发 ArgoCD 同步

集群侧资源（采集配置、规则、dashboard）走 ArgoCD，`master` 合入即生效。同步后确认：

```sh
kubectl -n monitoring-system get prometheusrule nas -o jsonpath='{.spec.groups[0].rules[*].alert}'
kubectl -n monitoring-system get configmap nas-dashboard
```

## 3. 验证

### 3.1 两个 target 都 UP

Prometheus → Status → Targets，或在 Prometheus 里查询：

```promql
up{job=~"nas-.*"}
# {job="nas-node",nas="NAS33657A",...}      1
# {job="nas-smartctl",nas="NAS33657A",...}  1
```

不通时先在集群内确认网络可达：

```sh
kubectl -n monitoring-system run -it --rm --restart=Never nascheck \
  --image=busybox:1.36 --command -- nc -zv 192.168.3.216 9100
```

### 3.2 指标正确（重点看 SMART 温度不为 0）

```promql
# 每个真实存储卷只出现一次，共 6 条
count(node_filesystem_avail_bytes{job="nas-node"})

# 5 块盘，全部应为 1
smartctl_device_smart_status{job="nas-smartctl"}

# 4 个盘位温度必须非 0；若为 0 说明 -d sat 丢了
smartctl_device_temperature{job="nas-smartctl",temperature_type="current"}
```

!!! danger "温度恒为 0 = 静默失效"

    这块 QNAP 的控制器会让 `smartctl --scan-open` 把 SATA 盘误判成 SCSI。少了 `;sat` 设备类型，exporter 照常有输出、面板照常有曲线，但温度恒为 0、ATA 属性全缺。看到 0 请检查 `metal/nas/compose.yml` 的 `--smartctl.device=/dev/sdX;sat` 是否还在，以及镜像是否仍是 `v0.14.0`（v0.12.0 不支持该语法）。

### 3.3 盘位标签可用

```promql
smartctl_device_temperature{job="nas-smartctl"} 
# 应带 disk="bay1".."bay4"，与 QTS「存储与快照」里的盘位一致
```

### 3.4 告警规则不误报

Prometheus → Alerts，或：

```promql
ALERTS{alertname=~"NAS.+"}
# 当前环境下应为空（inactive）
```

若出现 `NASRAIDNotRedundant` 指向 `md9`/`md13`，或 `NASVolumeSpaceLow` 指向 `/mnt/ext`，说明规则里的范围限制被改掉了——那两个对象在 QTS 上是固定布局，永远满足触发条件，见 [research.md](./research.md) 第 4 节。

### 3.5 Dashboard

Grafana → Dashboards → **NAS** 目录 → `NAS (QNAP TS-453Bmini)`。顶部状态行应显示 `UP`、CPU/内存百分比、RAID 冗余 `OK`、SMART `OK` 与最高盘温。

## 4. 日常运维

| 场景 | 操作 |
| --- | --- |
| NAS 重启 | 无需介入，`restart: unless-stopped` 自动拉起 |
| 增删硬盘 | 更新 `metal/nas/compose.yml` 的 `--smartctl.device` 列表并在 Container Station 重建应用（显式指定设备后 exporter 不再自动重扫） |
| QTS 升级导致盘符变化 | 用 `qcli_storage -d` 复核盘位，必要时调整 `values.yaml` 的 `device`→`disk` 映射 |
| 镜像升级 | 更新 `metal/nas/compose.yml` 的 tag，重建应用；`v0.14.0` 是 `;sat` 语法的最低要求 |
| NAS 换 IP | 更新 `system/monitoring-system/values.yaml` 的两个静态目标 |

## 5. 排障

```sh
ssh -p 52882 casey@nas
export PATH=$PATH:/share/CACHEDEV1_DATA/.qpkg/container-station/bin

docker logs nas-node-exporter --tail 50
docker logs nas-smartctl-exporter --tail 50

# 直接看 exporter 输出
curl -s localhost:9100/metrics | head
curl -s localhost:9633/metrics | grep smartctl_device_temperature

# 确认 /dev/sd* 在容器内可见（不可见说明丢了 privileged）
docker exec nas-smartctl-exporter ls /dev/sd*
```

常见症状：

| 症状 | 原因 |
| --- | --- |
| `Smartctl open device: /dev/sda failed: Permission denied` | 容器以 `nobody` 运行；需要 `user: "0:0"` |
| `Smartctl open device: /dev/sda;sat failed: No such device` | 镜像低于 v0.14.0，不支持 `<device>;<type>` 语法 |
| 温度恒为 0、无 ATA 属性 | 未强制 `-d sat`（本机 4 块 SATA 盘会被误判为 SCSI） |
| 每个卷出现 6 次 | `--collector.filesystem.mount-points-exclude` 丢失，快照挂载被当成独立卷 |
| `/sys`、`/proc` 被当成卷 | 同上，宿主根挂载泄漏 |
