# Research: Tailscale 指标监控

## 数据源盘点

Tailscale 在本环境有两种安装方式，指标来源不同：

| 来源 | 数量 | 指标端点 | 说明 |
| --- | --- | --- | --- |
| 4 台 node 上的原生 `tailscaled` | 4 | `http://<node-lan-ip>:5252/metrics` | 由 cloud-init 安装（`metal/roles/pxe_server/templates/user-data.j2`），版本 1.102.4 |
| operator ProxyGroup 代理 | 8 | `http://<pod-ip>:9002/metrics` | `ingress-proxies`（4）+ `egress-proxies`（4） |
| operator 独立 Ingress 代理（带 forwarding 注解） | 8 | 无 | 上游明确不支持 metrics，见下文 |
| operator 独立 egress 代理 | 10 | 无 | 上游明确不支持 metrics |
| operator Deployment 自身 | 1 | `:8080/metrics` | 仅 controller-runtime / Go 运行时指标，无 Tailscale 语义，本次不接入 |

## 节点侧：如何暴露客户端指标

官方文档《Tailscale client metrics》给出三种采集方式：

1. 本机访问 `http://100.100.100.100/metrics`（监控 agent 与客户端同机时）。
2. `tailscale set --webclient` 后经 tailnet 访问 `:5252`（需要 tailnet policy 放行 5252）。
3. `tailscale web --readonly --listen <addr>:<port>`，把只读 web 服务绑定到指定网络接口。
4. `tailscale metrics write <file>` + node_exporter textfile collector。

**实测取证**（`n100-jumper-0`）：

```
$ sudo systemd-run --unit=ts-metrics-probe --collect \
    /bin/sh -c "exec timeout 45 /usr/bin/tailscale web --readonly --listen 0.0.0.0:5252"
$ ss -tlnp | grep 5252
LISTEN 0 4096 *:5252 *:*
$ curl -s http://192.168.3.226:5252/metrics | grep -c '^tailscaled_'
27
$ curl -s http://100.100.100.100:5252/metrics -o /dev/null -w '%{http_code}'
000
```

同时验证了集群内 pod 到节点 LAN IP 的连通性（在 `n100-jumper-0` 上的 smartctl-exporter pod 内）：

```
$ kubectl exec <pod> -- wget -qO- http://192.168.3.226:5252/metrics | grep -c '^tailscaled_'
27
```

**结论**：采用方式 3，`--readonly --listen <node-lan-ip>:5252`。理由：

- `--readonly` 不暴露可写控制界面，安全性优于方式 2 的 `--webclient`（后者会暴露完整控制 UI）。
- 相比方式 4（textfile collector），无需改动 node-exporter 参数与 hostPath，也不存在文件写入的 staleness 问题。
- 绑定到节点 LAN IP（而非 `0.0.0.0`），与现有 node-exporter 的暴露模型一致（`--web.listen-address=[$(HOST_IP)]:9100`）。

节点侧实测可用指标（12 个 family / 27 条序列）：

```
tailscaled_advertised_routes / tailscaled_approved_routes
tailscaled_health_messages{type=...}
tailscaled_home_derp_region_id
tailscaled_inbound_bytes_total / tailscaled_inbound_packets_total
tailscaled_inbound_dropped_packets_total{reason=...}
tailscaled_outbound_bytes_total / tailscaled_outbound_packets_total
tailscaled_outbound_dropped_packets_total{reason=...}
tailscaled_serve_inbound_bytes_total / tailscaled_serve_outbound_bytes_total
```

## Kubernetes Operator 侧

### 启用方式（源码核实）

`cmd/k8s-operator/metrics_resources.go`：

```go
func reconcileMetricsResources(...) error {
	if opts.proxyType == proxyTypeEgress {
		// Metrics are currently not being enabled for standalone egress proxies.
		return nil
	}
	if pc == nil || pc.Spec.Metrics == nil || !pc.Spec.Metrics.Enable {
		return maybeCleanupMetricsResources(ctx, opts, cl)
	}
	metricsSvc := &corev1.Service{ ... Ports: []corev1.ServicePort{{Port: 9002, Name: "metrics"}} ... }
```

- egress 代理直接 `return nil`，**不会报错**，只是没有指标 —— 因此可以安全地对所有代理使用同一个默认 ProxyClass。
- 每个启用 metrics 的代理会得到 `<sts>-metrics` Service（operator namespace）与同名 ServiceMonitor（当 `serviceMonitor.enable=true`）。
- Service / ServiceMonitor 上带标签：`tailscale.com/metrics-target`、`ts_proxy_type`、`ts_proxy_parent_name`、`ts_proxy_parent_namespace`、`ts_prom_job`。
- job 名由 `promJobName()` 决定：ProxyGroup 为 `ts_proxygroup_<name>`，独立 Ingress 为 `ts_ingress_resource_<ns>_<name>`，Tailscale Service 为 `ts_ingress_service_<ns>_<name>`。

### 默认 ProxyClass：实测不可用（重要发现）

Helm chart 值 `proxyConfig.defaultProxyClass` → operator env `PROXY_DEFAULT_CLASS`（`helm template` 渲染确认），源码中 Ingress/Service reconciler 与 ProxyGroup reconciler 都会回落到它（`cmd/k8s-operator/proxygroup.go:190`）。实测（2026-10-02）后发现两个问题：

1. **上游不支持 metrics 的代理会得到永远失败的抓取目标。** 本集群有 8 个 Ingress 带 `tailscale.com/experimental-forward-cluster-traffic-via-ingress: "true"` 注解：

   ```
   $ kubectl get ingress -A -o json | jq -r '...'   # 见下
   dex/dex  gitea/gitea  kanidm/kanidm  lobe-chat/casdoor  lobe-chat/lobe
   rsshub/rsshub  rustfs/rustfs  woodpecker/woodpecker-server
   ```

   `cmd/k8s-operator/sts.go:1045` `applyProxyClassToStatefulSet()` 对这些代理打印
   "metrics should be enabled, but this is currently not supported for Ingress proxies that accept cluster traffic" 并跳过，
   但 `reconcileMetricsResources()` 仍然创建了 metrics Service/ServiceMonitor，
   导致 8 个 target 永久 `up=0`，并让 kube-prometheus-stack 默认的 `TargetDown`
   产生 8 条 pending/firing 告警（实测已确认 pending）。

2. 因此默认 ProxyClass 方案被否决。

### 采用的方案：显式指定到 ProxyGroup

在两个 ProxyGroup 上设置 `spec.proxyClass: tailscale-metrics`：

- `ingress-proxies`（4 副本，承载 22 个 Ingress）→ 实测 `up=1`。
- `egress-proxies`（4 副本）→ 实测 `up=1`（"不支持 metrics" 只针对**独立** egress 代理，ProxyGroup 类型的 egress 代理支持）。

共 8 个可用 target，全部 `up=1`；8 个不支持 metrics 的独立 Ingress 代理不生成 target，不产生误报。
代价：新增 Ingress 若走 `ingress-proxies` 自动获得采集；若是不带 proxy-group 的独立 Ingress，
需要显式加 `tailscale.com/proxy-class` 注解才能采集（且只有不带 forwarding 注解时才有效）。

Prometheus 侧无需额外配置：本仓库 `prometheusSpec.serviceMonitorSelectorNilUsesHelmValues: false`，即选择所有 namespace 的所有 ServiceMonitor。

## Grafana dashboard 调研

| Dashboard | 指标来源 | 是否适用 |
| --- | --- | --- |
| [24177 Tailscale / Overview](https://grafana.com/grafana/dashboards/24177-tailscale-overview/) | `tailscale_*`（API 型 `grafana/tailscale-exporter`，需要 Tailscale API Key） | ❌ 指标不匹配 |
| [24178 Tailscale / Machine](https://grafana.com/grafana/dashboards/24178-tailscale-machine/) | 同上 | ❌ 指标不匹配 |
| [Zydepoint/Tailscale-dashboard](https://github.com/Zydepoint/Tailscale-dashboard) | `tailscaled_*`（端口 5252 客户端指标） | ⚠️ 参考，但仅节点视角、且不在 grafana.com |

grafana.com 上不存在基于客户端指标（`tailscaled_*`）的 dashboard（`api/dashboards?name=tailscale` 精确匹配无结果，站内搜索仅返回上述 API 型 dashboard）。因此本 feature 在仓库内维护 dashboard JSON，查询语句以客户端指标为基础，并补齐 operator 代理维度。

## 部署路径的约束（重要）

`metal/inventories/prod.yml` 中 `tailscale_client_id` / `tailscale_client_secret` 是占位值，而集群中 operator release 的 user-supplied values 是真实凭据：

```
$ helm get values tailscale-operator -n tailscale
oauth:
  clientId: kbGW...
  clientSecret: tskey-client-...
```

因此**不能**直接重跑 `metal/Makefile cluster`：`kubernetes.core.helm` 会用占位凭据覆盖 release，导致 operator 无法创建代理。

本次采用的部署方式：

- 节点侧：`ansible-playbook` 跑 `prerequisites` role 的 `tailscale` tag（只新增 systemd 服务，不触碰 k3s/operator）。本次因环境缺少 `kubernetes.core` collection，使用 `tmp/` 下的临时 play 只加载该 role，任务本身与 `metal/roles/prerequisites` 中提交的代码完全一致。
- tailscale CR：`kubectl apply -f metal/roles/tailscale/templates/*.yaml`（文件无模板变量，与 role 中 `kubernetes.core.k8s: template:` 等价；`proxyclass.yaml` / `proxygroup.yaml` 均为多文档，与仓库既有写法一致）。
- operator：本次先用 `helm upgrade --reuse-values --set proxyConfig.defaultProxyClass=tailscale-metrics` 验证默认 ProxyClass 方案，确认问题后改回 `--set proxyConfig.defaultProxyClass=` 清除该 env。全程未触碰 release 中已有的真实 OAuth 凭据。

## 参考

- <https://tailscale.com/docs/reference/tailscale-client-metrics>
- <https://tailscale.com/docs/kubernetes-operator/manage-and-configure/expose-metrics>
- <https://github.com/tailscale/tailscale/blob/main/cmd/k8s-operator/metrics_resources.go>
- 本仓库 `specs/005-smartctl-monitoring/research.md`（同类监控接入的既有模式）
