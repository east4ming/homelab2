# Ubuntu 24.04 LTS 升级到 26.04 LTS

本页记录把节点从 Ubuntu 24.04 LTS（Noble Numbat）就地升级到 26.04 LTS（Resolute Raccoon）的完整流程，
以及本次在 4 台 N100 节点上实际升级后踩到的坑 —— **通用教程不会提到这些，但升级后必须逐项检查**。

!!! info "通用步骤出处"

    通用流程参考 [How to Upgrade from Ubuntu 24.04 LTS to 26.04 LTS](https://linuxiac.com/how-to-upgrade-from-ubuntu-24-04-lts-to-26-04-lts/)。
    本页在其基础上补充 **Ubuntu Server + K3s + Rook Ceph** 场景的集群侧准备与升级后修复。
    官方发布说明见 [Ubuntu 26.04 release notes](https://documentation.ubuntu.com/release-notes/26.04/)。

## 升级路径

- Ubuntu 24.04 LTS 是 26.04 LTS 的**直属升级基线**，可以一步到位。
- 更早的版本（22.04、20.04…）必须先升到 24.04 LTS（或 25.10），不能直接跳到 26.04。
- 26.04 LTS 支持至 2031-04。

## 升级前

### 1. 确认升级通道

`do-release-upgrade` 只在 `Prompt=lts` 时才提供 LTS → LTS 的升级：

```sh
cat /etc/update-manager/release-upgrades | grep -i prompt
sudo sed -i 's/Prompt=.*/Prompt=lts/' /etc/update-manager/release-upgrades
```

若仍不提供升级（例如首个 point release 尚未进入常规通道），可用 `do-release-upgrade -d`。

### 2. 把 24.04 升到最新并重启

```sh
sudo apt update && sudo apt full-upgrade
sudo snap refresh          # Server 上通常没有 snap，可跳过
sudo reboot
```

!!! warning "本仓库的节点不要随手 `apt autoremove --purge`"

    通用教程会建议升级前先清理不再需要的包。本仓库的节点例外：
    为了裁掉用不到的固件，`linux-firmware` 的依赖关系被刻意改造过（装了空壳
    `linux-firmware-minimal`），参见
    [裁剪 Linux 固件包](trim-linux-firmware-packages.md)。盲目 `autoremove`
    有删掉 i915 / Wi-Fi 固件的风险。

    确实要执行时，先确认保留的固件包已被标记为 manual：

    ```sh
    apt-mark showmanual | grep linux-firmware
    ```

### 3. 集群侧准备

节点本身是可丢弃的（配置由 Ansible + GitOps 管理），真正需要保护的是 etcd 与集群数据：

```sh
# 在任一 master 上手工打一份 etcd 快照（本项目已配置定时快照到 S3，见备份文档）
sudo k3s etcd-snapshot save --name pre-26.04
# 集群当前状态存档
kubectl get nodes -o wide
kubectl -n rook-ceph exec deploy/rook-ceph-tools -- ceph -s
```

**逐台滚动**，不要 4 台并行：先 worker，再 control-plane 一台一台来，
每台升级完等节点 `Ready`、Pod 稳定后再动下一台。

!!! tip "升级窗口避开自动重启"

    本仓库的 `unattended-upgrades` 配了 `Automatic-Reboot "True"`（03:00），
    升级完成后用 `/var/run/reboot-required` 判断是否还需要重启。

## 执行升级

```sh
sudo do-release-upgrade
```

交互项的选择建议：

| 提问 | 选择 | 原因 |
| --- | --- | --- |
| 是否继续（下载/安装） | `y` | — |
| 自动重启服务 | **Yes** | 否则每个服务都要单独确认，且容易漏 |
| 本地修改过的配置文件 | **保留当前版本**（保守） | 但**必须**按下一节的「检查 3」逐个 diff |
| Remove obsolete packages | `y` | 清理 24.04 遗留包；注意仍有少量包删不掉（见检查 5） |

升级完成后重启。本次 4 台节点的升级日志位于 `/var/log/dist-upgrade/`，
它同时也是排查遗留问题的第一手证据（`apt-term.log`、`main.log`）。

## 升级后必查

以下 7 项是本次升级在 4 台节点上**实际**出现的问题，建议写成检查清单逐项过。

### 检查 1：`/etc/sysctl.conf` 被删除，内核参数全部回退

Ubuntu 26.04 的 `procps` 把 `/etc/sysctl.conf` 标记为 `remove-on-upgrade`，
升级时会**直接删除**它（即使你改过）：

```console
$ dpkg-query -W -f='${Conffiles}\n' procps | grep sysctl.conf
 /etc/sysctl.conf 72b7c827a9636cda7b3b371091ff2dce remove-on-upgrade

$ sudo grep -i obsolete /var/log/dist-upgrade/apt-term.log
Obsolete conffile /etc/sysctl.conf has been modified by you.
```

**任何把参数写进 `/etc/sysctl.conf` 的 Ansible 任务，升级后都会静默失效。**
本仓库原先正是如此（见 [prerequisites 角色](https://github.com/east4ming/homelab2/blob/master/metal/roles/prerequisites/tasks/main.yml)），
后果是 `fs.inotify.max_user_instances` 从 8192 掉回内核默认 128：

- `fwupd.service` / `fwupd-refresh.service` 每小时失败：
  `Could not initialize inotify, check /proc/sys/fs/inotify/max_user_instances`
- KubeVirt `virt-handler` 在 inotify 用量高的节点上 CrashLoopBackOff：
  `Failed to create an inotify watcher ... too many open files`
- `net.ipv6.conf.all.forwarding` 从 1 掉回 0、`accept_ra` 从 2 掉回 1

检查与修复：

```sh
sysctl fs.inotify.max_user_instances fs.inotify.max_user_watches \
  net.ipv4.ip_forward net.ipv6.conf.all.forwarding net.ipv6.conf.all.accept_ra
# 默认值参考：16 GiB 节点 max_user_watches≈122102，32 GiB 节点≈253149
```

参数要落到 `/etc/sysctl.d/` 下的独立文件，不要再用 module 默认的 `/etc/sysctl.conf`：

```yaml
- name: Adjust kernel parameters
  ansible.posix.sysctl:
    name: "{{ item.name }}"
    value: "{{ item.value }}"
    sysctl_file: /etc/sysctl.d/90-homelab-prerequisites.conf
```

### 检查 2：第三方 apt 源被禁用

`do-release-upgrade` 无法把第三方的一行式 `.list` 迁移成 deb822 `.sources`，
于是把文件**清空成一行注释**，原内容挪到同名的 `.disabled`，并在里面留下提示。
本次 Tailscale 就是这样丢的，而且因为源没了，升级工具还把 `tailscale` 判成了「废弃包」：

```console
$ cat /etc/apt/sources.list.d/tailscale.list
# Tailscale packages for ubuntu noble

$ cat /etc/apt/sources.list.d/tailscale.list.disabled
# This file could not be automatically migrated to a .sources file during the upgrade.
```

逐项检查并恢复（suite 用新代号 `resolute`，先确认上游确实发布了该 suite）：

```sh
ls -l /etc/apt/sources.list.d/            # 找 *.disabled / *.migrate / *.distUpgrade
apt-cache policy <第三方包>                # Version table 里没有第三方源就是丢了
```

```sh
# /etc/apt/sources.list.d/tailscale.list
# Tailscale packages for ubuntu resolute
deb [signed-by=/usr/share/keyrings/tailscale-archive-keyring.gpg] https://pkgs.tailscale.com/stable/ubuntu resolute main
```

### 检查 3：残留 conffile 让 logrotate 整体失败

选择「保留当前版本」之后，release 升级删掉的 conffile 会被留下，
两个包各留一份、glob 又相同，logrotate 直接判重复并让服务失败
（[Launchpad #2152107](https://bugs.launchpad.net/ubuntu/+source/cloud-init/+bug/2152107)，Noble → Resolute 已知问题）：

```console
$ systemctl --failed
● logrotate.service  loaded failed failed  Rotate log files

$ journalctl -u logrotate -n 3
logrotate[52282]: error: cloud-init-base:1 duplicate log entry for /var/log/cloud-init.log
```

处理（`rm` 也可以，改名便于回退；logrotate 会忽略 `.disabled`）：

```sh
sudo mv /etc/logrotate.d/cloud-init /etc/logrotate.d/cloud-init.disabled
sudo systemctl start logrotate && sudo logrotate -d /etc/logrotate.conf 2>&1 | grep -i error
```

顺带把升级留下的 diff 备份**逐个**看过再决定去留：

```sh
sudo find /etc \( -name '*.dpkg-dist' -o -name '*.dpkg-old' -o -name '*.ucf-dist' -o -name '*.ucf-old' \) -print
```

本次 4 台节点的结论：`nut`（`MODE=netclient` 是刻意保留的旧值，正确）、
`grub`（只差注释与 `GRUB_DISTRIBUTOR` 写法）、`50unattended-upgrades`
（本仓库自己管理该文件，`.ucf-dist` 只是上游新样本）、`ca-certificates.conf.dpkg-old`（新文件已生效）——
都不需要改动。

### 检查 4：24.04 的内核包与孤儿模块目录

旧内核不会全被自动清掉。本次每台节点剩 117–120 个 `rc` 状态包 + 约 40 个不再属于任何包的
`/usr/lib/modules/6.8.0-*` 目录（约 48 MB/台）。

```sh
dpkg -l 'linux-image-*' 'linux-modules-*' 'linux-headers-*' | awk '/^rc/{print $2}'
```

清理时**必须**保住还能引导的内核。注意老包把文件登记在 `/lib/modules/...`、
新包登记在 `/usr/lib/modules/...`（`/lib` 是符号链接），
所以 `dpkg -S <目录>` 查不到属主，别据此删目录：

```sh
# 属主来自已安装内核包的文件列表，两种前缀都要归一化
owned=$(dpkg-query -L $(dpkg-query -W -f='${db:Status-Abbrev}${Package}\n' \
  'linux-modules-*' 'linux-image-*' | awk '$1=="ii"{print $2}') 2>/dev/null |
  sed -n -e 's|^/lib/modules/\([^/]*\)/.*|/usr/lib/modules/\1|p' \
         -e 's|^/usr/lib/modules/\([^/]*\)/.*|/usr/lib/modules/\1|p' | sort -u)
# 断言：/boot 能引导的内核，其模块目录必须在 owned 里
for v in /boot/vmlinuz-*; do
  printf '%s\n' "$owned" | grep -qxF "/usr/lib/modules/${v#/boot/vmlinuz-}" || echo "ABORT: $v"
done
```

确认后再 `apt-get purge` 那些 `rc` 包、删除确认无属主的目录；
保留运行时内核与一个回退内核（本次是 `7.0.0-38` 与 `6.8.0-146`）。

### 检查 5：仍处于「废弃」但装着的包

升级工具最后会列出 `Obsolete:` 包（`/var/log/dist-upgrade/main.log`），
其中一部分**删不掉**，会一直留着：

```console
$ sudo grep -i 'obsolete package' /var/log/dist-upgrade/main.log
obsolete package 'libpython3.12-minimal' could not be removed
obsolete package 'linux-tools-6.8.0-146' could not be removed
```

本次留下的主要是 `libpython3.12{,-stdlib,-minimal}`（仅因为 `linux-tools-6.8.0-146`
还依赖它），以及 `rc` 状态的 `keyboxd`。它们体积小、不可达，
但属于已停止维护的代码，可按需清理 —— 清理前先用
`apt-cache rdepends --installed` 和 `apt-mark showauto` 确认没有别的依赖。

### 检查 6：netplan `gateway4` 已弃用

`netplan.io 1.2` 仍接受 `gateway4`，但每次 `netplan generate` 都会告警：

```console
$ sudo netplan generate
WARNING **: `gateway4` has been deprecated, use default routes instead.
```

新装机模板已经改用 `routes:`（见 [user-data.j2](https://github.com/east4ming/homelab2/blob/master/metal/roles/pxe_server/templates/user-data.j2)）。
已在跑且网络正常的节点**不要**为了消这个警告去改 cloud-init 生成的 netplan。

### 检查 7：集群组件逐项确认

```sh
systemctl --failed                                    # 期望：空
systemctl is-active k3s
kubectl get nodes -o wide                             # 期望：全部 Ready
kubectl get pods -A | grep -vE 'Running|Completed'
kubectl -n rook-ceph exec deploy/rook-ceph-tools -- ceph -s
kubectl -n kubevirt get pods -l kubevirt.io=virt-handler
```

!!! warning "Ceph OSD 可能不会被 Rook 自动接管"

    本次升级后 `n100-cheshi-0` 的 `osd.1` 一直 `down+out`：它的 bluestore 分区
    （`/dev/nvme0n1p3`）完好、fsid 也正是本集群的 fsid，但没有
    `rook-ceph-osd-1`，`osd-prepare` 反复报
    `skipping osd.1: ... belonging to a different ceph cluster`（Rook v1.20.7）。
    重启 operator 无效。

    **根因是 `rook-ceph-mon` Secret 里的 `fsid` 过期**（operator 拿它当期望值去比对磁盘），
    而不是磁盘或数据损坏。修复只需把该字段改成 `ceph fsid` 的真实值并重启 operator，
    OSD 会被自动接管并恢复原 crush weight：

    ```sh
    FSID=$(kubectl -n rook-ceph exec deploy/rook-ceph-tools -- ceph fsid | tr -d '\r\n')
    kubectl -n rook-ceph patch secret rook-ceph-mon --type merge \
      -p "{\"data\":{\"fsid\":\"$(printf '%s' "$FSID" | base64 -w0)\"}}"
    kubectl -n rook-ceph delete pod -l app=rook-ceph-operator --wait=false
    ```

    **不要**对该 OSD 执行 `ceph osd purge` 或抹掉分区：那会永久销毁一个完好副本，
    且在单副本仅剩 3 个 OSD 时毫无必要。完整证据、验证与预防措施见
    [Rook-Ceph OSD down/out 修复：mon secret FSID 失配](../how-to-guides/troubleshooting/rook-ceph-osd1-fsid-mismatch-recovery.md)。

    只要 pool 是 `size=2/min_size=1` 且 PG 全 `active+clean`，数据是安全的，
    但冗余已经降级 —— 升级后务必确认 `ceph -s` 里 **4 个 OSD 全 up/in**。

!!! note "KubeVirt 的 virt-handler 会跟着 inotify 一起挂"

    inotify 实例被耗尽时 `virt-handler` 会在启动阶段 fatal 退出，
    表现为 CrashLoopBackOff（`Failed to create an inotify watcher`）。
    修好检查 1 之后删除该 Pod 即可自行恢复。

## 本仓库需要同步的适配点

升级到 26.04.1 后，仓库里这些位置需要跟上（本次已更新）：

- `metal/roles/pxe_server/defaults/main.yml`：ISO 与 netboot.xyz squash 资源的 tag/校验和
- `metal/roles/pxe_server/templates/ubuntu.ipxe.j2`：新增 `resolute` 菜单项与 `:resolute_amd64`/`:resolute_arm64` 分支
- `metal/roles/pxe_server/templates/user-data.j2`：
    - 包列表：`libpcre3`/`libpcre3-dev` 在 26.04 已移除（PCRE1 被放弃），`dnsutils` 过渡包也没了 → 改用 `bind9-dnsutils`。
      **不改这里，全新 PXE 装机在 `packages:` 阶段就会失败。**
    - netplan：`gateway4` → `routes`
- `metal/roles/prerequisites/tasks/main.yml`：sysctl 落到 `/etc/sysctl.d/`
- `scripts/firmware-slim`、文档中的 24.04 版本描述

验证本次改动的命令：

```sh
yamllint -c .yamllint.yaml metal/roles/prerequisites/tasks/main.yml
ansible-playbook --syntax-check --check --limit n100-jumper-0 \
  -i metal/inventories/prod.yml metal/boot.yml
.venv/bin/mkdocs build --strict
```

## 速查表

| 现象 | 根因 | 处理 |
| --- | --- | --- |
| `fwupd`/`fwupd-refresh` 失败、`virt-handler` CrashLoop | `/etc/sysctl.conf` 被删除，inotify 限制回退 | 检查 1 |
| 第三方包升不了级 / 被判「废弃」 | `.list` 被升级工具禁用 | 检查 2 |
| `logrotate.service` failed | 残留 conffile 重复 | 检查 3 |
| 磁盘被旧内核占满 | `rc` 包 + 孤儿模块目录 | 检查 4 |
| `ceph -s` 里 OSD 少一个 | Rook 拒绝接管旧 OSD | 检查 7 |
| `netplan generate` 告警 | `gateway4` 弃用 | 检查 6 |
