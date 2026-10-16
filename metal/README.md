# metal —— 裸机与集群引导

用 Ansible 把 4 台裸机装成 k3s 集群，并把 Cilium、tailscale-operator 这些 addon
装上去。

```sh
make -C metal boot      # PXE 装机 + Wake-on-LAN
make -C metal cluster   # 装 k3s、Cilium、tailscale-operator
```

对应 `metal/Makefile` 的两个目标，分别跑 `boot.yml` 与 `cluster.yml`。
`env=stag` 可切换到 `metal/inventories/stag.yml`。

## 先装依赖

外部 collection 已钉死版本，新 clone 必须先装，否则任务会以 unknown-module 失败：

```sh
ansible-galaxy collection install -r metal/requirements.yml
```

## 操作者必须提供的值

仓库里**不含**任何真实凭据、真实 MAC 或生产 `registries.yaml` 内容 —— 公开仓库
（含 GitHub 镜像）上任何人都能看到提交进去的东西。这些值放在一个**不进版本控制的
本地文件**里：

```
metal/inventories/group_vars/all/zz-secrets.yml          # 真实值，已 gitignore
metal/inventories/group_vars/all/zz-secrets.yml.example  # 提交进仓库的模板
```

```sh
cp metal/inventories/group_vars/all/zz-secrets.yml.example \
   metal/inventories/group_vars/all/zz-secrets.yml
chmod 600 metal/inventories/group_vars/all/zz-secrets.yml
$EDITOR metal/inventories/group_vars/all/zz-secrets.yml
```

要填的变量：

| 变量 | 用途 | 哪里拿 |
| --- | --- | --- |
| `registries_config_yaml` | 节点 `/etc/rancher/k3s/registries.yaml` 的**整份**内容 | 节点上 `sudo cat /etc/rancher/k3s/registries.yaml` |
| `tailscale_auth_key` | 节点加入 tailnet（boot 阶段的 cloud-init 用） | Tailscale 管理台 → Settings → Keys |
| `tailscale_client_id` | tailscale-operator 的 OAuth client | Tailscale 管理台 → Settings → OAuth clients（需 Devices: write） |
| `tailscale_client_secret` | 同上，**只在创建时显示一次** | 同上，创建时立即记录 |
| `metal_macs` | 每个节点的网卡 MAC（PXE / Wake-on-LAN） | `ip link show <iface>` 或路由器 DHCP 表 |

### 为什么必须这样

- `registries_config_yaml` 是**整体覆盖**，不是合并。生产节点上该文件含多个 mirror
  与 6 组 registry auth；一旦被占位内容覆盖，非 docker.io 的镜像源与私有仓库认证
  **全部丢失**。所以请从节点上原样取回，不要凭记忆手写。
- `tailscale_client_secret` 经 Helm 推到线上 `tailscale-operator` release。用假
  凭据升级会让 operator 失去 tailnet API 权限，**所有 tailscale ingress / proxy
  失效**。
- Helm release 的历史版本里留有旧凭据。轮换 OAuth client 后，旧值仍可从
  `kubectl -n tailscale get secret sh.helm.release.v1.tailscale-operator.v<N>` 解出，
  必要时按需清理历史 revision。

### 缺值时会怎样

不会静默用占位值跑。`boot.yml` / `cluster.yml` 的第一个 play 是 `guard` role，
它检查上面那个文件是否存在；随后每个真正写配置的 role 都会在**写之前** assert：

| 位置 | 拒绝执行的条件 |
| --- | --- |
| `roles/guard` | `zz-secrets.yml` 不存在 → 立即 fail，提示复制模板 |
| `roles/prerequisites` | `registries_config_yaml` 为空/仍是占位值/解析不出 `mirrors` 键 → 不覆盖 `/etc/rancher/k3s/registries.yaml` |
| `roles/tailscale` | tailscale 三个凭据任一缺失或仍是占位值 → 不升级 release |
| `roles/pxe_server` | 任一节点没有可用 `mac` → 不生成错误目录名的 cloud-init 配置 |

占位串是 `metal_var_placeholder`（定义在 `metal/group_vars/all.yml`，默认
`REPLACE_ME`）。值没提供时由 `metal/vars/placeholders.yml` 兜底填入，因此失败
信息是「缺什么、去哪儿填」，而不是一句 undefined variable。

## 首次连接新节点：主机密钥校验

`metal/ansible.cfg` **不开** `host_key_checking=false`：这些 play 带 `become: true`，
关掉校验等于允许 MITM 直接拿 root。首次连接前用带外渠道核对指纹，再写入
`known_hosts`：

```sh
ssh-keyscan -t ed25519 <host> >> ~/.ssh/known_hosts
```

## 改了配置为什么不生效？（已修）

k3s 只在进程启动时读取配置。`roles/k3s` 与 `roles/prerequisites` 现在都有
`handlers/main.yml`：unit 文件变化 → `daemon-reload`；`config.yaml`、
`kube-vip` manifest、`registries.yaml` 变化 → 重启 k3s。都在 play 末尾执行一次。

## monitoring CRD 谁负责

`metal/` **不再**安装 `prometheus-operator-crds`。集群里的 `*.monitoring.coreos.com`
CRD 由 `system/monitoring-system`（kube-prometheus-stack chart，ArgoCD 管理）持有，
且没有 Helm 归属元数据 —— metal 再 install 同一份 chart 必然报 `already exists`。
旧 role（chart 16.0.1）已删除，详见 `metal/cluster.yml` 顶部注释。

## etcd S3 快照凭据不在 metal/ 里

`metal/group_vars/all.yml` 的 `etcd_s3: true` 让 k3s 通过
`etcd-s3-config-secret: k3s-etcd-snapshot-s3-config` 读取 S3 凭据；这个 Secret
**不由 metal playbook 创建或更新**（线上已存在，650 天），所以 `metal/` 里没有对应
任务，也就没有可加 `no_log` 的对象。创建/轮换方式沿用
[backup-k3s-etcd-snapshot-to-s3.md](../docs/how-to-guides/backup-k3s-etcd-snapshot-to-s3.md)：
操作者用 `kubectl` 手工创建，凭据文件写在
`metal/roles/k3s/files/secret-k3s-etcd-snapshot-s3-config.yaml`（gitignore 已覆盖）。

## 标签

`cluster.yml` / `boot.yml` 的主要任务带 tag，可局部运行：

```sh
ansible-playbook -i metal/inventories/prod.yml metal/cluster.yml --tags registries
# 其他：k3s-binary / k3s-config / k3s-token / k3s-service / kubeconfig /
#       sysctl / firewall / tailscale / registries / cilium / cilium-cr /
#       tailscale-operator / tailscale-cr / automatic-upgrade / pxe / wake
```
