# Research: Disk SMART 监控

## 方案

采用 Prometheus 社区 `smartctl_exporter` 官方 Helm chart：

- Chart 仓库：https://prometheus-community.github.io/helm-charts
- Chart：`prometheus-smartctl-exporter`
- 版本：`0.17.1`
- App 版本：`v0.14.0`
- 默认资源：DaemonSet、Service、ServiceAccount、可选 ServiceMonitor/PrometheusRule

## 关键行为

- DaemonSet 容器以 `privileged: true` 和 `runAsUser: 0` 运行。
- 挂载宿主 `/dev` 到容器 `/hostdev`，用于扫描块设备。
- exporter 通过 `--smartctl.path=/usr/sbin/smartctl` 调用 smartctl。
- 默认 `--smartctl.interval=120s`，ServiceMonitor 每 60s 抓取一次。
- 内置 PrometheusRule 包含 6 条告警：
  - SmartCTLDeviceMediaErrors
  - SmartCTLDeviceCriticalWarning
  - SmartCTLDeviceAvailableSpareUnderThreshold
  - SmartCTLDeviceStatus
  - SmartCTLDInterfaceSlow
  - SmartCTLDDeviceTemperature

## RBAC 注意

chart 默认 `rbac.create: true` 会创建指向 `unrestricted-psp` ClusterRole 的 RoleBinding。现代 K3s 不一定存在该 ClusterRole，而 exporter 不需要访问 K8s API，因此本实现设置 `rbac.create: false`。

## Dashboard

采用 Grafana dashboard 22604 `SMARTctl Exporter Dashboard`：

- 使用 `smartctl_device_*` 新指标，与 exporter v0.14.0 兼容。
- 通过 Grafana sidecar 从 `monitoring-system` namespace 自动加载。
- 需将 `${DS_PROMETHEUS}` 替换为 kube-prometheus-stack datasource UID `prometheus`，并移除 `__inputs`/`__requires`。

## 参考

- https://github.com/prometheus-community/smartctl_exporter
- https://github.com/prometheus-community/helm-charts/tree/main/charts/prometheus-smartctl-exporter
- https://grafana.com/grafana/dashboards/22604-smartctl-exporter-dashboard/
