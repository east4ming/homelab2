# Quickstart: Tailscale 指标监控

## 组成

| 部分 | 位置 | 部署方式 |
| --- | --- | --- |
| 节点只读 metrics 端点 | `metal/roles/prerequisites/` | Ansible |
| ProxyClass / ProxyGroup | `metal/roles/tailscale/templates/` | Ansible（K8s CR） |
| Prometheus 抓取、告警、dashboard | `system/monitoring-system/` | ArgoCD |

## 部署

### 1. 节点侧（4 台 node）

```sh
cd metal
make cluster                       # 需要 inventory 中真实凭据
# 或只跑节点侧任务，不触碰 k3s / operator：
ansible-playbook --inventory inventories/prod.yml cluster.yml --tags tailscale
```

### 2. Tailscale CR（ProxyClass + ProxyGroup）

```sh
cd metal
ansible-playbook --inventory inventories/prod.yml cluster.yml --tags tailscale-cr
```

### 3. 监控资源

合并到 `master` 后由 ArgoCD 自动同步；也可手动触发：

```sh
argocd app sync monitoring-system
```

## 验证

```sh
# 节点端点：4 台都应返回 200，且只监听 LAN IP
for ip in 192.168.3.226 192.168.3.174 192.168.3.158 192.168.3.154; do
  curl -s -o /dev/null -w "$ip %{http_code}\n" "http://$ip:5252/metrics"
done

# 节点 target
curl -s --data-urlencode 'query=up{job="tailscale-nodes"}' \
  https://prometheus.west-beta.ts.net/api/v1/query | jq -r '.data.result[] | "\(.metric.node) \(.value[1])"'

# 代理 target（应全部为 1，且没有 up=0 的 ts_* 目标）
curl -s --data-urlencode 'query=up{job=~"ts_.*"}' \
  https://prometheus.west-beta.ts.net/api/v1/query | jq -r '.data.result[] | "\(.metric.job) \(.value[1])"'

# 告警规则已加载
curl -s 'https://prometheus.west-beta.ts.net/api/v1/rules?type=alert' \
  | jq -r '.data.groups[].rules[].name' | grep '^Tailscale'

# dashboard 已加载
kubectl get configmap -n monitoring-system tailscale-dashboard
```

Grafana：<https://grafana.west-beta.ts.net> → Dashboards → `Tailscale` 目录。

## 预期结果

- `tailscale-nodes`：4 个 target `up=1`，指标带 `node` 标签（节点名）。
- `ts_proxygroup_ingress-proxies` / `ts_proxygroup_egress-proxies`：各 4 个 target `up=1`。
- 8 个带 `experimental-forward-cluster-traffic-via-ingress` 注解的独立 Ingress 代理**没有** target（上游不支持 metrics）。
- 告警规则：`TailscaleNodeHealthMessages`、`TailscaleNodeDroppedPackets`、`TailscaleProxyHealthMessages`。
- Grafana `Tailscale` dashboard：节点与代理两组面板均有数据。

## 常见问题

| 现象 | 原因 / 处理 |
| --- | --- |
| 某节点 target `DOWN` | 该节点 `systemctl status tailscale-metrics`；`journalctl -u tailscale-metrics` |
| 新增 Ingress 没有代理指标 | 只有走 `ingress-proxies` / `egress-proxies` 的代理会被采集；独立 Ingress 若带 forwarding 注解则上游不支持 metrics |
| 代理 target 消失 | 检查 `kubectl get sts -n tailscale`，容器组未就绪时 Service 没有 endpoints；由 `KubePodNotReady` / `KubeStatefulSetReplicasMismatch` 覆盖 |
| 节点 LAN IP 变更 | 同时改 `metal/inventories/prod.yml` 与 `system/monitoring-system/values.yaml` 的 `additionalScrapeConfigs` |

## 回滚

- 节点侧：`ansible-playbook ... --tags tailscale` 前先把 `tailscale-metrics.service` 从 role 中移除，或直接 `systemctl disable --now tailscale-metrics`（手工操作仅限紧急情况，正常走 Git 回退）。
- 集群侧：`git revert` 对应提交，ArgoCD 自动同步；ProxyGroup 的 `spec.proxyClass` 移除后 operator 会自动删除 metrics Service / ServiceMonitor。
