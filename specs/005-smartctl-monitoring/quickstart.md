# Quickstart: Disk SMART 监控

## 1. 安装宿主机 smartmontools

```bash
make -C metal cluster
```

或仅对 metal 主机执行 Ansible prerequisites。

验证：

```bash
ansible metal -i metal/inventories/prod.yml -m command -a 'smartctl --version'
```

## 2. 通过 ArgoCD 部署监控资源

将本分支合并/推送到 ArgoCD 使用的 Git 仓库后，ArgoCD 会自动同步：

- `system/monitoring-system` Helm chart 更新
- `prometheus-smartctl-exporter` DaemonSet
- Service / ServiceMonitor / PrometheusRule
- Grafana Dashboard ConfigMap

## 3. 验证

```bash
kubectl -n monitoring-system get pods -l app.kubernetes.io/name=prometheus-smartctl-exporter
kubectl -n monitoring-system get servicemonitors | grep smartctl
kubectl -n monitoring-system get prometheusrules | grep smartctl
kubectl -n monitoring-system get configmap smartctl-exporter-dashboard
```

### Prometheus

- 打开 Prometheus Target 页面，确认 smartctl-exporter job 为 `UP`。
- 打开 Prometheus Rules 页面，确认 SmartCTL 规则已加载。

### Grafana

- 打开 Grafana，进入 `SMARTctl Exporter Dashboard`。
- 选择节点/磁盘，确认温度、SMART 状态、寿命等面板有数据。
