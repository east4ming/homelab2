# Changelog

版本号格式与发布流程见 [版本管理](versioning.md)。新条目置顶，标题即 git 标签名。

## v2026.09.21

自 `v2025.02.17` 以来的状态快照，覆盖 830 个非合并提交。完整明细见 `git log v2025.02.17..v2026.09.21`。

### 新增应用

- **RustFS**：S3 兼容对象存储，启用 TLS、日志轮转与 Tailscale Ingress；lobe-chat 的对象存储由 MinIO 迁移至此
- **RSSHub**：RSS 聚合服务，含 PostgreSQL
- **Upsnap**：网络唤醒（Wake-on-LAN）管理面板
- **SearXNG**：自建元搜索引擎，并接入 lobe-chat
- **Semaphore**：任务编排面板，配置了 dnsPolicy 与时区
- **Kube Explorer**：Kubernetes 资源浏览器
- **Eraser**：节点镜像清理

### 移除

- **Webtop** 与 **MinIO**：不再使用，已移除部署与相关 egress 配置

### KubeVirt 虚拟机

- 引入 KubeVirt 与 CDI，新增虚拟机测试套件（unit / integration / e2e）
- 用 DataVolume PVC 作为 rootdisk，替换 containerDisk
- 支持从外部 Secret 注入 cloud-init，避免在公开仓库中泄露凭据
- control-plane 副本数降为 1，适配 4 节点规模
- Cilium datapathMode 由 `netkit` 调整为 `netkit-l2`

### 网络与 Tailscale

- Tailscale Operator 接管 Ingress / DNS / 证书 / Funnel，替代 nginx-ingress、external-dns、cert-manager、cloudflared
- 新增出口代理组（proxygroup）、proxyclass 与出口服务配置
- 多个外部服务补齐 HTTPS 端口与 proxy-class 注解
- Cilium 由 1.19.1 升级到 1.19.6，保持 native routing、BPF masquerade、DSR、netkit、Bandwidth Manager
- 因内核与 datapathMode 变更导致带 NetworkPolicy 的 Pod 异常，临时禁用本仓库全部 NetworkPolicy

### 系统与升级

- 新增系统升级流程，配合 kured 完成滚动重启
- csi-driver-nfs 补齐 resources requests/limits
- 适配 k3s 移除 kube-proxy IPVS 模式
- journald 日志接入
- 清理 linux-firmware 中不再需要的厂商子包

### 可观测性

- 4 个节点全部接入磁盘 SMART 监控，含仪表盘与告警规则（展示节点主机名与 IP）
- 新增 VolSync 与 kube-explorer 相关监控
- Grafana 12：启用 git sync、图像渲染器等新特性

### 文档与工程

- 重组 troubleshooting 文档结构，新增节点挂起故障排除指南
- 更新架构文档，移除 Zot Registry 相关内容
- 新增 KubeVirt、SMART 监控等能力的 Spec Kit 规格（`specs/`）

### 依赖

- Renovate 持续更新 Helm Chart 与容器镜像，非 major 依赖按周聚合合并

## v2025.02.17

- 进入 homelab2 目录后自动运行: `nix develop --extra-experimental-features nix-command --extra-experimental-features flakes`

### bash 实现

通过 `bash` 的重载 `cd` 函数来实现。

1. **创建一个脚本文件**：
   创建一个脚本文件（例如 `run_nix_develop.sh`），内容如下：

   ```sh
   #!/bin/sh
   nix develop --extra-experimental-features nix-command --extra-experimental-features flakes
   ```

   确保脚本具有可执行权限：

   ```bash
   chmod +x run_nix_develop.sh
   ```

2. **修改 `~/.bashrc` 文件**：
   在 `~/.bashrc` 文件中添加以下内容，以便在每次进入目录时检查是否在特定目录中，并执行相应的脚本。

   ```sh
   # ~/.bashrc
   function cd() {
       builtin cd "$@" || return
       if [ "$(pwd)" == "~/projects/homelab2" ]; then
           ~/projects/homelab2/run_nix_develop.sh
       fi
   }
   ```

   这个脚本会重写 `cd` 命令，使其在每次切换目录后检查当前目录是否为 `~/projects/homelab2`，如果是，则执行 `run_nix_develop.sh` 脚本。

3. **重新加载 `~/.bashrc` 文件**：
   重新加载 `~/.bashrc` 文件以使更改生效：

   ```bash
   source ~/.bashrc
   ```

### zsh 实现

在 `zsh` 中设置进入当前目录后自动执行 `run_nix_develop.sh` 脚本，可以通过以下方法实现：

**使用 `precmd` 钩子**

`precmd` 钩子会在每次显示命令提示符前触发，但需结合目录检查逻辑。

1. **修改 `~/.zshrc` 文件**：

   ```zsh
   # ~/.zshrc
   autoload -U add-zsh-hook

   # 定义钩子函数
   run_on_prompt() {
       if [[ "$(pwd)" == "~/projects/homelab2" ]]; then
           ~/projects/homelab2/run_nix_develop.sh
       fi
   }

   # 将函数绑定到 precmd 钩子
   add-zsh-hook precmd run_on_prompt
   ```

2. **重新加载 `~/.zshrc` 文件**：
   重新加载 `~/.zshrc` 文件以使更改生效：

   ```bash
   source ~/.zshrc
   ```

## v2025.02.16

- Remove Loki-stack, as Loki-stack is no longer actively maintained.
- Use Grafana Cloud -> grafana/k8s-monitoring to monitor logs and Profiles. See [kubernetes-monitoring/configuration](https://grafana.com/docs/grafana-cloud/monitor-infrastructure/kubernetes-monitoring/configuration/) for more details. Since this involves Grafana Cloud secrets, install directly using helm-dashboard; the helm chart's values.yaml is not maintained in this repo.

## 上游历史（fork 前）

以下条目继承自上游 [khuedoan/homelab](https://github.com/khuedoan/homelab)，正文逐字保留。
其中的版本号与 `-alpha` 后缀属于上游命名，不适用本仓库的 [CalVer 版式](versioning.md)。

### v0.0.8

Notable changes:

- **build:** run post install scripts by default
- **build:** set `KUBECONFIG` from global Makefile
- **feat(external-dns)!:** add cluster name as owner ID
- **feat(tools):** install `yamllint`, `ansible-lint` and `k9s`
- **feat(tools):** set `KUBECONFIG` by default
- **feat:** add pre-commit hooks
- **feat:** add script to setup Gitea tokens and OAuth apps
- **perf(argocd):** turning on selective sync
- **refactor(docs):** migrate to [mkdocs](https://squidfunk.github.io/mkdocs-material)
- **refactor(metal):** migrate to Fedora 36 for newer packages
- **refactor(pxe)!:** combine dhcpd and tftpd to dnsmasq
- Many bug fixes

Please see git log for full change log.

### 0.0.7-alpha

- Replace standard Vault with Vault Operator
- Automatically initialize and unseal Vault
- Declarative secret generation and management
- Declarative Gitea configuration with YAML
- Automatic OS rolling upgrade
- Automatic Kubernetes rolling upgrade
- Automatic application updates using Renovate (still require manual token generation)
- Add script to wait for essential services after deployment
- Add icons and bookmarks to the home page
- Deploy Matrix chat
- Replace Authentik with Dex for SSO (still require manual token generation)
- Switch to Mermaid for diagrams in documentation
- Replace Vagrant with k3d for development environment
- Use nip.io domain for development environment
- Remove Backblaze (S3 Glacier and/or Minio will be added in future version)
- Enable monitor for the majority of applications
- Many code refactorings and bug fixes

### 0.0.6-alpha

- Upgrade to Kubernetes 1.23
- Support external resources:
    - Cloudflare DNS and Tunnel
    - Backblaze for backup
    - Auto inject secrets to required namespaces
- Replace self-signed certificates with Let's Encrypt production (with API token injected from the `external` layer)
- Add DNS records automatically using external-dns
- Easy Cloudflare Tunnel configuration with annotations
- Offsite backup to Backblaze B2 bucket using k8up-operator
- Add private container registry
- Remove Knative to save resources (temporarily)
- Enable encryption at rest for Kubernetes Secrets
- Add more Tekton tasks and pipelines
- Initialize GitOps repository on Gitea automatically after install
- Generate MetalLB address pool automatically (default to the last `/27` subnet)
- Some bug fixes

### 0.0.5-alpha

- Add convenience scripts
- Add Loki for logging
- Add custom health check for Application and ApplicationSet
- Use Vault with dev mode on (temporarily until we hit beta)
- Replace Authelia with Authentik
- Upgrade to Kubernetes 1.22
- Upgrade most services to the latest version
- Set ingress class and storage class explicitly
- Initial Linkerd and Knative setup (not working yet)
- Set up Hajimari for home page with automatic ingress discovery
- Add dev VM for local development or evaluation
- Optimize bare metal provisioning performance
- Replace Syncthing with Seafile (may use both in the feature)
- Enable Gitea SSH cloning via Ingress
- Various code clean up
- Add more documents

### 0.0.4-alpha

- Switch to Rocky Linux
- Some optimization for bare metal provisioning
- Switch to k3s and combine Kubernetes cluster config in `./infra` layer to `./metal` layer (because k3s is also configured using Ansible)
- Split boostrap Helm charts in `./infra` layer to `./bootstrap` layer (with new ArgoCD pattern) and `./system` layer
- Add `./platform` layer for some applications like Gitea, Tekton...
- User only need to provision `./metal` and `bootstrap` layer, the `./bootstrap` layer will deploy the remaining layers
- Provisioning time from empty disk to running services is significantly reduced (thanks to k3s and new bootstrap pattern)
- Use [mdBook](https://rust-lang.github.io/mdBook/) for documents
- Replace Drone CI with Tekton
- Enable TLS on all Ingresses (using [cert-manager](https://cert-manager.io))
- Add some new applications

### 0.0.3-alpha

- Generate Terraform backend config automatically
- Switch to CoreOS
- Better PXE boot setup
- Diagrams as code

### 0.0.2-alpha

- Ensure idempotency for bare metal provisioning
- Extract instead of mounting the OS ISO file
- Easy initial controller setup (with only Docker)
- Switch to Fedora
- Remove LXD
- Move etcd (Terraform state backend) back to Docker

### 0.0.1-alpha

- Bare metal provisioning with PXE
- LXD cluster
- Terraform state backend (etcd)
- RKE cluster
- Core services (Vault, Gitea, ArgoCD,...)
- Public services to the internet (via port forwarding or Cloudflare Tunnel)
