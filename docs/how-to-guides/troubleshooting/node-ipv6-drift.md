# 节点 IPv6 前缀漂移（kubelet 报 secondaryNodeIP）

## 症状

```console
$ kubectl get nodes -o wide
# 某台节点的 IPv6 是 240e:... 旧地址，或只有 IPv4

$ ssh <node> 'sudo journalctl -u k3s | grep secondaryNodeIP | tail -1'
E1029 kubelet_node_status.go:673] "Failed to set some node status fields"
  err="failed to validate secondaryNodeIP: node IP: \"240e:...\" not found in the host's network interfaces"
```

可能伴随：

- `cilium-dbg node list` 的 IPv6 列是旧地址；
- `ip -6 route | grep fdb5` 缺少**其他节点**的 `/64` 直连路由（只有本机那条）→ 跨节点
  IPv6 pod 通信不通；
- hostNetwork pod（如 semaphore/mysql）的 IPv6 EndpointSlice 指向不存在的地址。

## 根因

`/etc/rancher/k3s/config.yaml` 的 `node-ip` 里写死了某个 IPv6 地址，而该地址已不在
任何接口上 —— 通常是 ISP 重新下发了不同的 `240e:` 前缀（PPPoE 重拨、节点重启、
运营商侧变更）。kubelet 启动时会校验 `node-ip` 是否存在于本机接口，校验失败的字段
不会被写进 Node 状态。

## 处置

2026-10-30 起（[specs/012](../specs/012-stable-node-ula-ipv6/plan.md)），节点 IPv6 使用
**固定站点 ULA**（`fdb5:92d0:b067:1::/64`），不再取 ISP GUA。因此**正常情况下这个
故障不会再出现**。如果仍然出现，按下面处理：

1. 确认接口上到底有哪些地址：

   ```sh
   ip -6 -br addr show scope global
   ```

2. 确认 `config.yaml` 里应该是 ULA 而不是 `240e:`：

   ```sh
   grep -n 'node-ip' /etc/rancher/k3s/config.yaml
   ```

   正确形态（以 jumper-1 为例）：

   ```yaml
   node-ip: 192.168.3.174,fdb5:92d0:b067:1::12
   kubelet-arg:
     - "node-ip=192.168.3.174,fdb5:92d0:b067:1::12"
   ```

   若是 `240e:` 地址，说明是旧配置（或某次人工回退），改成 ULA 后继续第 3 步。

3. 逐台重启 k3s，再逐台重启 cilium agent（agent 只在启动时把节点地址写进
   `CiliumNode`，不重启就一直用旧值）：

   ```sh
   sudo systemctl restart k3s                       # 逐台，等 Ready
   kubectl -n kube-system delete pod <cilium-pod>   # 逐台，等 1/1 Running
   ```

4. 验收：

   ```sh
   kubectl get nodes -o custom-columns='NAME:.metadata.name,V6:.status.addresses[?(@.type=="InternalIP")].address' --no-headers
   ssh <node> 'sudo journalctl -u k3s --since -2min | grep -c secondaryNodeIP'   # 期望 0
   ip -6 route | grep fdb5        # 期望每个远端节点一条 via <对方 ULA>
   ```

## 相关

- 地址规划与「为什么不用 GUA」：[Networking](../reference/architecture/networking.md)
- 2026-10-29 的 AppArmor 事故（同一次重启的另一个独立故障）：
  [AppArmor 拒绝容器内信号](apparmor-signal-denied.md)
